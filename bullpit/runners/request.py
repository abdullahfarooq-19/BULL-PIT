"""Runs one request end to end: the training-cutoff check, the duplicate
lock, the graph, and recording the result to the journal (architecture
sec5; M3-FR-1 to FR-3, FR-15, FR-18 to FR-20; D-M3-9, D-M3-13).

M8 splits that into `open_request`, `run_live` and `resume_live` for the
dashboard's pause-and-decide flow (M8 specs-plan sec11.1); `run_request`
is the same three steps in one call, for the CLI and backtests.
"""

from __future__ import annotations

import secrets
import shutil
import sqlite3
import subprocess
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal, get_args

import structlog
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from bullpit.approval.gate import ApprovalDecision, expires_at
from bullpit.broker.alpaca import AlpacaBroker
from bullpit.broker.base import Broker, client_order_id
from bullpit.clock import Clock, utc_now
from bullpit.config import Settings
from bullpit.domain import Account, Asset, Position, SizedOrder, Trade
from bullpit.errors import BrokerRejected
from bullpit.graph import Deps, build_graph
from bullpit.journal.models import (
    ApprovalRecord,
    DebateTurnRecord,
    EquitySnapshot,
    RecommendationRecord,
    ReportRecord,
    Request,
    SignalRecord,
    TradeRecord,
    trade_from_row,
    trade_record,
)
from bullpit.llm.gateway import CompletionFn, litellm_completion
from bullpit.logging import get_logger
from bullpit.risk.rules import loss_warning
from bullpit.risk.sizing import net_of_pending, pending_cost
from bullpit.state import RequestState, TradeAttempt

logger = get_logger(__name__)

_SECRET_CONFIG_FIELDS = {
    "alpaca_api_key",
    "alpaca_secret_key",
    "groq_api_key",
    "sec_contact_email",
    "langfuse_public_key",
    "langfuse_secret_key",
}


def naive_utc_now() -> datetime:
    return utc_now().replace(tzinfo=None)


def earliest_backtest_date(settings: Settings) -> date:
    latest_cutoff = max(settings.llm_small_model_cutoff, settings.llm_large_model_cutoff)
    return latest_cutoff + timedelta(days=1)


def _config_snapshot(settings: Settings) -> dict[str, Any]:
    dumped = settings.model_dump(mode="json")
    return {key: value for key, value in dumped.items() if key not in _SECRET_CONFIG_FIELDS}


def git_commit() -> str:
    git = shutil.which("git")
    if git is None:
        return "unknown"
    try:
        result = subprocess.run(  # noqa: S603 - a fixed, argument-free git command
            [git, "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=5
        )
    except (subprocess.SubprocessError, OSError):
        return "unknown"
    commit = result.stdout.strip()
    return commit or "unknown"


def _insert_rejected_row(
    sessions: sessionmaker[Session],
    *,
    request_id: str,
    ticker: str,
    mode: str,
    as_of: date,
    message: str,
    settings: Settings,
) -> None:
    with sessions() as session:
        session.add(
            Request(
                id=request_id,
                mode=mode,
                as_of=as_of,
                created_at=naive_utc_now(),
                ticker=ticker,
                status="rejected",
                status_reason=message,
                config=_config_snapshot(settings),
                git_commit=git_commit(),
                finished_at=naive_utc_now(),
            )
        )
        session.commit()


def _acquire_lock(
    sessions: sessionmaker[Session],
    *,
    request_id: str,
    ticker: str,
    mode: str,
    as_of: date,
    timeout_minutes: int,
) -> str | None:
    """Marks abandoned `running` rows failed, then inserts this request's
    `running` row, all in one transaction. Returns `None` once the row is
    committed, or the duplicate message if another request is genuinely still
    running (M3-FR-3) or its report is waiting for a decision (M8-FR-11).
    """
    with sessions() as session:
        cutoff = naive_utc_now() - timedelta(minutes=timeout_minutes)
        stale = (
            session.execute(
                select(Request).where(
                    Request.ticker == ticker, Request.mode == mode, Request.status == "running"
                )
            )
            .scalars()
            .all()
        )
        for row in stale:
            created = row.created_at.replace(tzinfo=None)
            if created < cutoff:
                row.status = "failed"
                row.status_reason = "abandoned: running longer than the lock timeout"
                row.finished_at = naive_utc_now()
                logger.warning(
                    "request_lock_abandoned", ticker=ticker, mode=mode, request_id=row.id
                )

        session.add(
            Request(
                id=request_id,
                mode=mode,
                as_of=as_of,
                created_at=naive_utc_now(),
                ticker=ticker,
                status="running",
            )
        )
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            waiting = session.scalars(
                select(Request).where(
                    Request.ticker == ticker,
                    Request.mode == mode,
                    Request.status == "awaiting_approval",
                )
            ).first()
            if waiting is not None:
                return f"A report for {ticker} is waiting for your decision."
            return f"A {mode} request for {ticker} is already running."
    return None


def _recommendation_record(
    request_id: str, index: int, attempt: TradeAttempt, *, final_order: Any | None
) -> RecommendationRecord:
    recommendation = attempt.recommendation
    verdict = attempt.verdict
    return RecommendationRecord(
        request_id=request_id,
        attempt=index,
        action=recommendation.action,
        exit_style=recommendation.exit_style,
        target_weight=str(recommendation.target_weight),
        confidence=recommendation.confidence,
        decisive_evidence=list(recommendation.decisive_evidence),
        reasoning=recommendation.reasoning,
        flagged=recommendation.flagged,
        sized_order=None
        if attempt.sized_order is None
        else attempt.sized_order.model_dump(mode="json"),
        blocked_reason=attempt.blocked_reason,
        review_decision=None if verdict is None else verdict.decision,
        review_reason=None if verdict is None else verdict.reason,
        review_shares=None if verdict is None else verdict.requested_shares,
        review_clamped=None if verdict is None else verdict.clamped,
        review_flagged=None if verdict is None else verdict.flagged,
        final_order=final_order,
    )


def add_request_rows(
    session: Session,
    row: Request,
    *,
    result: RequestState | None,
    error: BaseException | None,
    settings: Settings,
    paused: bool = False,
) -> None:
    """Fills in `row` and adds the request's child rows. The caller commits, so
    the backtest runner can commit a week's requests with its checkpoint.
    `paused`: a live buy waiting for the owner (M8-FR-5), so not finished."""
    request_id = row.id
    if error is not None:
        row.status = "failed"
        row.status_reason = str(error)
    elif result is not None and result.rejection is not None:
        row.status = "rejected"
        row.status_reason = result.rejection
    elif paused:
        row.status = "awaiting_approval"
    else:
        row.status = "completed"

    row.route = None if result is None else result.route
    row.warnings = None if result is None else list(result.warnings)
    row.config = _config_snapshot(settings)
    row.git_commit = git_commit()
    row.price_source = None if result is None or result.prices is None else result.prices.source
    row.finished_at = None if paused and error is None else naive_utc_now()
    row.outcome = None if result is None else result.outcome
    row.no_trade_reason = None if result is None else result.no_trade_reason
    session.flush()  # the models have no relationships, so write the row before its children

    if result is not None:
        for signal in (
            result.technical_signal,
            result.fundamentals_signal,
            result.sentiment_signal,
        ):
            if signal is None:
                continue
            session.add(
                SignalRecord(
                    request_id=request_id,
                    analyst=signal.analyst,
                    direction=signal.direction,
                    confidence=signal.confidence,
                    evidence=[item.model_dump() for item in signal.evidence],
                    flagged=signal.flagged,
                    note=signal.note,
                )
            )

        for turn in result.debate:
            session.add(
                DebateTurnRecord(
                    request_id=request_id,
                    round=turn.round,
                    side=turn.side,
                    points=[point.model_dump() for point in turn.points],
                    concessions=list(turn.concessions),
                    conviction=turn.conviction,
                    word_count=turn.word_count,
                    unsupported_count=sum(1 for point in turn.points if point.unsupported),
                    over_word_limit=turn.over_word_limit,
                    flagged=turn.flagged,
                )
            )

        last_index = len(result.attempts) - 1
        for index, attempt in enumerate(result.attempts):
            is_winning_attempt = result.outcome == "buy" and index == last_index
            final_order = (
                result.sized_order.model_dump(mode="json")
                if is_winning_attempt and result.sized_order is not None
                else None
            )
            session.add(
                _recommendation_record(request_id, index + 1, attempt, final_order=final_order)
            )

        if result.report is not None:
            session.add(
                ReportRecord(request_id=request_id, report=result.report.model_dump(mode="json"))
            )


def _finalize(
    sessions: sessionmaker[Session],
    *,
    request_id: str,
    result: RequestState | None,
    error: BaseException | None,
    settings: Settings,
    paused: bool = False,
) -> None:
    with sessions() as session:
        row = session.get(Request, request_id)
        if row is None:
            raise ValueError(f"no requests row for {request_id!r} to finalize")
        add_request_rows(session, row, result=result, error=error, settings=settings, paused=paused)
        session.commit()


@dataclass(frozen=True)
class PendingAwareBroker:
    """An `AlpacaBroker` whose account and position reads are net of live orders that
    haven't filled (M8-FR-29), so a second request or approval can't spend the cash or
    the per-stock cap twice. The pending orders are read from the journal on every call."""

    broker: AlpacaBroker
    sessions: sessionmaker[Session]

    def _pending(self) -> list[Trade]:
        with self.sessions() as session:
            rows = session.scalars(
                select(TradeRecord).where(
                    TradeRecord.run_id.is_(None), TradeRecord.status == "pending"
                )
            ).all()
            return [trade_from_row(row) for row in rows]

    def get_account(self) -> Account:
        account = self.broker.get_account()
        return net_of_pending(account, Decimal(0), self._pending(), "")[0]

    def get_position(self, symbol: str) -> Position | None:
        position = self.broker.get_position(symbol)
        pending = [trade for trade in self._pending() if trade.ticker == symbol]
        if not pending:
            return position
        held = position or Position(symbol=symbol, qty=0, market_value=Decimal(0))
        return Position(
            symbol=symbol,
            qty=held.qty + sum(trade.shares for trade in pending),
            market_value=held.market_value + pending_cost(pending),
        )

    def get_asset(self, symbol: str) -> Asset | None:
        return self.broker.get_asset(symbol)


def _expire(session: Session, row: Request, broker: AlpacaBroker) -> None:
    """Expires one overdue waiting request. A recorded approval with no trade row
    may have an order at Alpaca (the process died between the two), so it is looked
    up first: found means recorded and completed, not found means expired with the
    reason, and an unreachable Alpaca leaves the row for the next try (D-M8-27)."""
    approval = session.scalars(
        select(ApprovalRecord).where(ApprovalRecord.request_id == row.id)
    ).one_or_none()
    has_trade = session.scalars(select(TradeRecord).where(TradeRecord.request_id == row.id)).first()
    reason = "Expired: not decided before the close of the first session after the report."
    if approval is not None and approval.decision == "approved" and has_trade is None:
        recommendation = session.scalars(
            select(RecommendationRecord).where(
                RecommendationRecord.request_id == row.id,
                RecommendationRecord.final_order.is_not(None),
            )
        ).first()
        if recommendation is None or recommendation.final_order is None:
            raise ValueError(f"approved request {row.id!r} has no final order")
        # A recorded approval knows its entry: a limit trade's reference is its limit (FR-20).
        reference = (
            Decimal(approval.entry_price)
            if approval.entry_price is not None
            else SizedOrder.model_validate(recommendation.final_order).reference_price
        )
        try:
            found = broker.find_order(
                client_order_id(row.id), submitted_on=row.as_of, reference_price=reference
            )
        except BrokerRejected as exc:
            logger.warning("expire_lookup_failed", request_id=row.id, error=str(exc))
            return
        if found is not None:
            session.add(trade_record(row.id, found.trade))
            row.status = "completed"
            row.finished_at = naive_utc_now()
            return
        reason = "Approved, but no order was placed before the report expired."
    row.status = "expired"
    row.status_reason = reason
    row.finished_at = naive_utc_now()


def expire_overdue(
    *,
    sessions: sessionmaker[Session],
    broker: AlpacaBroker,
    now: datetime,
    ticker: str | None = None,
    request_id: str | None = None,
) -> None:
    """Applies expiry (M8-FR-9) to the live requests waiting for a decision, all of
    them or only `ticker`'s or `request_id`'s. The one place expiry happens."""
    with sessions() as session:
        query = select(Request).where(Request.mode == "live", Request.status == "awaiting_approval")
        if ticker is not None:
            query = query.where(Request.ticker == ticker)
        if request_id is not None:
            query = query.where(Request.id == request_id)
        for row in session.scalars(query).all():
            if now > expires_at(row.as_of):
                _expire(session, row, broker)
                session.commit()


def open_request(
    ticker: str,
    mode: Literal["live", "backtest"],
    as_of: date,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    broker: AlpacaBroker | None,
    now: datetime,
) -> RequestState:
    """The training-cutoff check, then the duplicate lock (live requests first
    expire overdue waiting ones). The returned state has `rejection` set if the
    request was refused; otherwise its `running` row is committed."""
    ticker = ticker.upper()
    request_id = f"{as_of:%Y%m%d}-{ticker}-{secrets.token_hex(4)}"

    with structlog.contextvars.bound_contextvars(
        request_id=request_id, mode=mode, as_of=str(as_of)
    ):
        message: str | None = None
        latest_cutoff = max(settings.llm_small_model_cutoff, settings.llm_large_model_cutoff)
        if mode == "backtest" and as_of <= latest_cutoff:
            message = (
                "Backtest dates must be after the models' training cutoff: "
                f"use {earliest_backtest_date(settings)} or later."
            )
        else:
            if mode == "live" and broker is not None:
                expire_overdue(sessions=sessions, broker=broker, now=now, ticker=ticker)
            message = _acquire_lock(
                sessions,
                request_id=request_id,
                ticker=ticker,
                mode=mode,
                as_of=as_of,
                timeout_minutes=settings.request_lock_timeout_minutes,
            )
        if message is not None:
            _insert_rejected_row(
                sessions,
                request_id=request_id,
                ticker=ticker,
                mode=mode,
                as_of=as_of,
                message=message,
                settings=settings,
            )
        return RequestState(
            request_id=request_id, mode=mode, as_of=as_of, ticker=ticker, rejection=message
        )


def thread_config(request_id: str) -> Any:
    """LangGraph's config for a request's checkpointed thread (M8-FR-5)."""
    return {"configurable": {"thread_id": request_id}}


def _live_loss_warning(
    sessions: sessionmaker[Session], as_of: date, settings: Settings
) -> bool | None:
    """The loss warning from the live equity snapshots (M8-FR-17): `None` until
    the history reaches back far enough."""
    with sessions() as session:
        rows = session.execute(
            select(EquitySnapshot.day, EquitySnapshot.equity).where(EquitySnapshot.run_id.is_(None))
        ).all()
    history = [(day, Decimal(equity)) for day, equity in rows]
    return loss_warning(
        history, as_of, drop_pct=settings.loss_warning_pct, days=settings.loss_warning_days
    )


def _run_graph(
    state: RequestState,
    graph: CompiledStateGraph[RequestState, None, RequestState, RequestState],
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
) -> RequestState:
    """Runs the opened request's graph and records the result, whether it finished,
    failed or paused for the owner (a live buy, when the graph has the live tail)."""
    result: RequestState | None = None
    error: BaseException | None = None
    paused = False
    if state.mode == "live":
        state = state.model_copy(
            update={"loss_warning": _live_loss_warning(sessions, state.as_of, settings)}
        )
    try:
        raw_state = graph.invoke(state, thread_config(state.request_id))
        result = RequestState.model_validate(raw_state)
        paused = bool(raw_state.get("__interrupt__"))
    except BaseException as exc:
        error = exc
    finally:
        _finalize(
            sessions,
            request_id=state.request_id,
            result=result,
            error=error,
            settings=settings,
            paused=paused,
        )

    if error is not None:
        raise error
    if result is None:  # pragma: no cover - unreachable: error is None => result was set
        raise RuntimeError("the graph finished with neither a result nor an error")
    return result


def run_live(
    state: RequestState,
    graph: CompiledStateGraph[RequestState, None, RequestState, RequestState],
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
) -> RequestState:
    """Runs an opened live request to the owner's approval pause or to its end
    (M8-FR-5). The graph's state is checkpointed under the request ID."""
    with structlog.contextvars.bound_contextvars(
        request_id=state.request_id, mode=state.mode, as_of=str(state.as_of)
    ):
        return _run_graph(state, graph, settings=settings, sessions=sessions)


def _finish_if_waiting(
    sessions: sessionmaker[Session],
    request_id: str,
    *,
    status: Literal["completed", "failed"],
    reason: str | None = None,
) -> None:
    with sessions() as session:
        row = session.get(Request, request_id)
        if row is not None and row.status == "awaiting_approval":
            row.status = status
            row.status_reason = reason
            row.finished_at = naive_utc_now()
            session.commit()


def resume_live(
    request_id: str,
    decision: ApprovalDecision,
    graph: CompiledStateGraph[RequestState, None, RequestState, RequestState],
    *,
    sessions: sessionmaker[Session],
) -> RequestState:
    """Continues a request after the owner's decision is recorded in `approvals`
    (M8-FR-7). Resumes the pause if it is still pending, or picks up a run that
    stopped inside `execute`; a rejection, or a resend after the order step
    finished, just completes the request. A rejected order marks it failed."""
    config = thread_config(request_id)
    snapshot = graph.get_state(config)
    with structlog.contextvars.bound_contextvars(request_id=request_id):
        try:
            if "approval" in snapshot.next:
                raw_state = graph.invoke(Command(resume=decision.model_dump(mode="json")), config)
            elif snapshot.next:
                raw_state = graph.invoke(None, config)
            else:
                raw_state = snapshot.values
        except BrokerRejected as exc:
            _finish_if_waiting(sessions, request_id, status="failed", reason=str(exc))
            raise
        _finish_if_waiting(sessions, request_id, status="completed")
    return RequestState.model_validate(raw_state)


def _state_types() -> list[type[BaseModel]]:
    """`RequestState` and every model reachable from its fields: the exact types the
    checkpoint serializer may rebuild when a paused request is loaded (M8 sec7.1)."""
    found: list[type[BaseModel]] = []

    def visit(annotation: object) -> None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            if annotation in found:
                return
            found.append(annotation)
            for field in annotation.model_fields.values():
                visit(field.annotation)
        for argument in get_args(annotation):
            visit(argument)

    visit(RequestState)
    return found


def make_checkpointer(settings: Settings) -> SqliteSaver:
    """The SQLite checkpointer for paused requests, in its own file (M8 D-M8-8).
    Shared by the API's worker threads, hence `check_same_thread=False`; only
    Bull Pit's own state types may be deserialized from it."""
    connection = sqlite3.connect(settings.checkpoint_db_path, check_same_thread=False)
    connection.execute("PRAGMA journal_mode=WAL")
    return SqliteSaver(connection, serde=JsonPlusSerializer(allowed_msgpack_modules=_state_types()))


def run_request(
    ticker: str,
    mode: Literal["live", "backtest"],
    clock: Clock,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    broker: Broker,
    completion_fn: CompletionFn = litellm_completion,
    expiry_broker: AlpacaBroker | None = None,
) -> RequestState:
    """`open_request` then the graph without the live tail, in one call: the CLI's
    path, which never pauses and never orders (M8-FR-26). `expiry_broker` lets a
    live request expire overdue waiting ones before it takes the lock."""
    state = open_request(
        ticker,
        mode,
        clock.as_of(),
        settings=settings,
        sessions=sessions,
        broker=expiry_broker,
        now=utc_now(),
    )
    if state.rejection is not None:
        return state

    with structlog.contextvars.bound_contextvars(
        request_id=state.request_id, mode=mode, as_of=str(state.as_of)
    ):
        deps = Deps(
            settings=settings, sessions=sessions, broker=broker, completion_fn=completion_fn
        )
        return _run_graph(state, build_graph(deps), settings=settings, sessions=sessions)
