"""The API: FastAPI over the live runner, the fill check and the journal (M8
specs-plan FR-18 to FR-21, sec9.4). One user on localhost, no auth (dev-plan Q6).

Handlers are plain functions so FastAPI runs them in its thread pool; a request
runs in the background and the approval handler runs one at a time (D-M8-30).
Every refusal is a `Problem` JSON with a stable `code` (FR-19).
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request as HttpRequest

from bullpit.api.schemas import (
    AccountOut,
    ApprovalResult,
    EquityPoint,
    HistoryRow,
    HistoryState,
    MarketOut,
    NewRequest,
    OrderPreview,
    OrderPreviewBody,
    PortfolioStats,
    PreviewWarning,
    Problem,
    RequestDetail,
    RequestStarted,
    RequestSummary,
    TradeOut,
    WatchlistStock,
)
from bullpit.approval.gate import (
    ApprovalDecision,
    ApprovalProblem,
    OwnerDecision,
    check_decision,
    expires_at,
    final_order,
    override_flags,
)
from bullpit.broker.alpaca import AlpacaBroker
from bullpit.clock import utc_now
from bullpit.config import Settings
from bullpit.data.calendar import last_completed_session
from bullpit.data.prices import latest_price as fetch_latest_price
from bullpit.domain import Account, SizedOrder
from bullpit.errors import BrokerRejected, DataUnavailable
from bullpit.graph import ApprovalWiring, Deps, build_graph
from bullpit.journal.models import (
    ApprovalRecord,
    EquitySnapshot,
    LikedStock,
    ReportRecord,
    TradeRecord,
    approval_record,
    decision_from_row,
    trade_fields,
    trade_from_row,
)
from bullpit.journal.models import Request as RequestRow
from bullpit.llm.gateway import CompletionFn, litellm_completion
from bullpit.logging import get_logger
from bullpit.report.model import Report
from bullpit.risk.sizing import cap_shares, cash_shares, round_cent
from bullpit.runners.fill_check import FillCheckResult, fill_check
from bullpit.runners.request import (
    PendingAwareBroker,
    expire_overdue,
    open_request,
    resume_live,
    run_live,
    thread_config,
)
from bullpit.state import RequestState

logger = get_logger(__name__)

_TICKER = re.compile(r"^[A-Z][A-Z.]{0,9}$")
_DEFAULT_LIMIT = 50
_HISTORY_LIMIT = 200
_HISTORY_MAX = 500
_MAX_LIMIT = 200
# Where a running request is, by the next node the checkpointer shows (M8 sec11.6).
_STAGES = {
    "request_check": "checking",
    "technical": "analysts",
    "fundamentals": "analysts",
    "sentiment": "analysts",
    "signals_board": "analysts",
    "brain": "analysts",
    "bull": "debate",
    "bear": "debate",
    "trader": "trader",
    "risk_sizing": "risk",
    "risk_review": "risk",
    "report": "report",
}

_WATCHLIST_FILE = Path(__file__).resolve().parents[1] / "data" / "sp100.json"
_BROKER_NAME = "Alpaca Paper"
_MASK_KEEP = 4

Graph = CompiledStateGraph[RequestState, None, RequestState, RequestState]


class Refusal(Exception):
    """Raised by a handler to answer with a `Problem` and a status code."""

    def __init__(self, status: int, body: Problem | ApprovalProblem) -> None:
        super().__init__(body.message)
        self.status = status
        self.body = body


def _not_found(what: str) -> Refusal:
    return Refusal(404, Problem(code="not_found", message=f"No such {what}."))


def _utc(moment: datetime) -> datetime:
    """The journal keeps naive UTC datetimes; the API sends them with their zone."""
    return moment.replace(tzinfo=UTC)


def _trade_out(row: TradeRecord, overrides: list[str] | None = None) -> TradeOut:
    return TradeOut(
        **trade_from_row(row).model_dump(), request_id=row.request_id, overrides=overrides or []
    )


def _overrides(session: Session) -> dict[str, list[str]]:
    """Each request's approval overrides, for the trades' badges."""
    found = session.execute(select(ApprovalRecord.request_id, ApprovalRecord.overrides)).all()
    return {request_id: overrides or [] for request_id, overrides in found}


def _summary(row: RequestRow, approval: ApprovalRecord | None) -> dict[str, Any]:
    return {
        "id": row.id,
        "ticker": row.ticker,
        "as_of": row.as_of,
        "status": row.status,
        "status_reason": row.status_reason,
        "outcome": row.outcome,
        "created_at": _utc(row.created_at),
        "expires_at": expires_at(row.as_of) if row.status == "awaiting_approval" else None,
        "decision": None if approval is None else approval.decision,
        "order_type": None
        if approval is None or approval.decision != "approved"
        else approval.order_type,
        "overrides": [] if approval is None else approval.overrides or [],
    }


def history_state(
    status: str,
    outcome: str | None,
    decision: str | None,
    trade_status: str | None,
    order_type: str | None,
) -> HistoryState:
    """The one label a request shows on Trades History (M11.2 specs-plan sec11.1):
    the request's status until it waits for a decision, then the trade's life. A buy report
    that completed with no recorded decision (a CLI run, or one from before the approval
    step) is "no_decision"."""
    by_status: dict[str, HistoryState] = {
        "running": "analysing",
        "failed": "failed",
        "rejected": "rejected_by_check",
        "awaiting_approval": "decision_pending",
    }
    by_trade: dict[str | None, HistoryState] = {
        "open": "open",
        "closed": "closed",
        "cancelled": "cancelled",
    }
    if status in by_status:
        return by_status[status]
    if trade_status in by_trade:
        return by_trade[trade_status]
    if trade_status == "pending":
        return "waiting_at_limit" if order_type == "limit" else "order_placed"
    if decision == "approved":
        return "order_placed"
    if decision == "rejected":
        return "rejected_by_you"
    if status == "expired":
        return "expired"
    return "no_decision" if outcome == "buy" else "no_trade"


def portfolio_stats(
    decisions: Sequence[str], trades: Sequence[tuple[str, Decimal | None]]
) -> PortfolioStats:
    """Realised statistics (M11.2-FR-18) from the owner's decisions and the live
    trades' `(status, pnl)`: ongoing trades are pending or open; profit and loss
    sum the closed trades' P&L by sign."""
    profit = sum(
        (pnl for status, pnl in trades if status == "closed" and pnl and pnl > 0), Decimal(0)
    )
    loss = sum(
        (pnl for status, pnl in trades if status == "closed" and pnl and pnl < 0), Decimal(0)
    )
    return PortfolioStats(
        approved=decisions.count("approved"),
        rejected=decisions.count("rejected"),
        ongoing=sum(status in ("pending", "open") for status, _ in trades),
        closed=sum(status == "closed" for status, _ in trades),
        total_profit=profit,
        total_loss=loss,
        net_pnl=profit + loss,
    )


def unrealised_pnl(entry_price: Decimal, price: Decimal, shares: int) -> Decimal:
    """What an open trade would make or lose at `price`, to the cent (M11.3-FR-1)."""
    return round_cent((price - entry_price) * shares)


def _history_row(
    row: RequestRow,
    approval_row: ApprovalRecord | None,
    trade_row: TradeRecord | None,
    plan: SizedOrder | None,
    price: Decimal | None = None,
) -> HistoryRow:
    """One Trades History row: numbers from the trade, else the approval the owner
    gave, else the report's plan (so a row that waits for a decision shows it).
    `price` is the symbol's current price, used only while the trade is open."""
    summary = _summary(row, approval_row)
    approval = None if approval_row is None else decision_from_row(approval_row)
    trade = None if trade_row is None else trade_from_row(trade_row)
    approved = approval is not None and approval.decision == "approved"
    state = history_state(
        row.status,
        row.outcome,
        None if approval is None else approval.decision,
        None if trade is None else trade.status,
        None if trade is None else trade.order_type,
    )
    shares: int | None = None
    take_profit = stop_loss = limit = plan_price = None
    if trade is not None:
        shares, take_profit, stop_loss = trade.shares, trade.take_profit, trade.stop_loss
        limit, plan_price = trade.limit_price, trade.reference_price
    elif approval is not None and approved:
        shares, take_profit, stop_loss = (
            approval.approved_shares,
            approval.take_profit,
            approval.stop_loss,
        )
        limit = approval.limit_price
    if plan is not None:
        plan_price = plan.reference_price
        if not (trade or approved):
            shares, take_profit, stop_loss = plan.shares, plan.take_profit, plan.stop_loss
    live_price = price if state == "open" else None
    return HistoryRow(
        id=row.id,
        ticker=row.ticker,
        created_at=summary["created_at"],
        as_of=row.as_of,
        state=state,
        outcome=row.outcome,
        status_reason=row.status_reason,
        expires_at=summary["expires_at"],
        order_type=summary["order_type"],
        overrides=summary["overrides"],
        shares=shares,
        plan_price=plan_price,
        entry_price=None if trade is None else trade.entry_price,
        limit_price=limit,
        take_profit=take_profit,
        stop_loss=stop_loss,
        exit_price=None if trade is None else trade.exit_price,
        exit_date=None if trade is None else trade.exit_date,
        exit_reason=None if trade is None else trade.exit_reason,
        cancel_reason=None if trade is None else trade.cancel_reason,
        pnl=None if trade is None else trade.pnl,
        current_price=live_price,
        unrealised_pnl=(
            None
            if live_price is None or trade is None or trade.entry_price is None
            else unrealised_pnl(trade.entry_price, live_price, trade.shares)
        ),
    )


def _progress(graph: Graph, row: RequestRow) -> tuple[str, int | None]:
    """The stage a request is at, and the debate round while it debates."""
    if row.status != "running":
        return row.status, None
    snapshot = graph.get_state(thread_config(row.id))
    stage = _STAGES.get(snapshot.next[0], "starting") if snapshot.next else "starting"
    round_ = len(snapshot.values.get("debate", [])) // 2 + 1 if stage == "debate" else None
    return stage, round_


@lru_cache(maxsize=1)
def _watchlist() -> list[tuple[str, str]]:
    """The S&P 100 names the home page offers, as `(symbol, name)` in file order."""
    stocks = json.loads(_WATCHLIST_FILE.read_text(encoding="utf-8"))["stocks"]
    return [(stock["symbol"], stock["name"]) for stock in stocks]


def _percent(part: Decimal, whole: Decimal) -> Decimal | None:
    return None if whole <= 0 else part / whole * 100


def _preview(
    body: OrderPreviewBody,
    order: SizedOrder,
    *,
    latest: Decimal | None,
    fetched_at: datetime,
    as_of: date,
    loss_warning: bool | None,
    account: Account,
    held: Decimal,
    settings: Settings,
) -> OrderPreview:
    """Prices the order the chosen mode would place, with the gate's own functions
    so the box and the approval can't disagree (M11.1-FR-10, sec11.2). The gate's
    refusal for this order, if any, is shown as a warning."""
    is_limit = body.order_type == "limit"
    entry = body.limit_price if is_limit else latest
    warnings: list[PreviewWarning] = []
    if latest is None:
        warnings.append(
            PreviewWarning(
                code="price_unavailable", message="The latest price isn't available right now."
            )
        )
    numbers: dict[str, Any] = {}
    overrides: list[str] = []
    max_shares: int | None = None
    if entry is not None:
        entry = round_cent(entry)
        decision = OwnerDecision(
            decision="approve",
            shares=body.shares,
            order_type=body.order_type,
            limit_price=entry if is_limit else None,
            seen_price=None if is_limit else entry,
            advanced=body.advanced,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
            confirm_stale=True,
            confirm_loss_warning=True,
            confirm_overrides=True,
        )
        final = final_order(order, decision, entry)
        if isinstance(final, ApprovalProblem):
            warnings.append(PreviewWarning(code=final.code, message=final.message))
        else:
            equity = account.equity
            cash_fits = cash_shares(account.cash, entry)
            max_shares = (
                cash_fits
                if body.advanced
                else min(
                    order.shares,
                    cash_fits,
                    cap_shares(equity, held, entry, settings.max_position_pct),
                )
            )
            if body.advanced:
                overrides = list(
                    override_flags(
                        final,
                        order,
                        equity,
                        held,
                        cap_pct=settings.max_position_pct,
                        risk_pct=settings.risk_per_trade_pct,
                    )
                )
            position_pct = _percent(held + final.cost, equity)
            loss_pct = _percent(final.max_loss, equity)
            if "above_cap" in overrides and position_pct is not None:
                cap = settings.max_position_pct * 100
                warnings.append(
                    PreviewWarning(
                        code="above_cap",
                        message=(
                            f"This puts {position_pct:.1f}% of equity in one stock "
                            f"(plan cap {cap:.0f}%)."
                        ),
                    )
                )
            if "above_risk_limit" in overrides and loss_pct is not None:
                risk = settings.risk_per_trade_pct * 100
                warnings.append(
                    PreviewWarning(
                        code="above_risk_limit",
                        message=(f"Maximum loss is {loss_pct:.1f}% of equity (plan {risk:.0f}%)."),
                    )
                )
            numbers = {
                "stop_loss": final.stop_loss,
                "take_profit": final.take_profit,
                "cost": final.cost,
                "max_loss": final.max_loss,
                "max_gain": final.max_gain,
                "pct_of_equity": _percent(final.cost, equity),
                "loss_pct_of_equity": loss_pct,
                "position_pct_after": position_pct,
            }
            if latest is not None:
                if is_limit and entry >= latest:
                    warnings.append(
                        PreviewWarning(
                            code="limit_at_or_above_price",
                            message="This fills at once, at the market price.",
                        )
                    )
                outcome = check_decision(
                    decision,
                    order,
                    as_of=as_of,
                    now=fetched_at,
                    latest_price=latest,
                    loss_warning=loss_warning,
                    account=account,
                    held_value=held,
                    staleness_pct=settings.approval_staleness_pct,
                    cap_pct=settings.max_position_pct,
                    risk_pct=settings.risk_per_trade_pct,
                )
                if isinstance(outcome, ApprovalProblem):
                    warnings.append(PreviewWarning(code=outcome.code, message=outcome.message))
    return OrderPreview(
        price=latest,
        fetched_at=fetched_at,
        order_type=body.order_type,
        entry_price=entry,
        shares=order.shares if body.shares is None else body.shares,
        max_shares=max_shares,
        overrides=overrides,
        warnings=warnings,
        **numbers,
    )


def create_app(
    settings: Settings,
    *,
    broker: AlpacaBroker,
    sessions: sessionmaker[Session],
    checkpointer: BaseCheckpointSaver[str],
    now: Callable[[], datetime] = utc_now,
    completion_fn: CompletionFn = litellm_completion,
    latest_price: Callable[[str], Decimal] | None = None,
) -> FastAPI:
    """Builds the app. `now`, the LLM and the latest-price source are injectable so
    tests fix them; the graph is built once and holds no per-request state."""
    price_of = latest_price or (lambda symbol: fetch_latest_price(symbol, settings=settings))
    live_broker = PendingAwareBroker(broker, sessions)
    graph = build_graph(
        Deps(settings=settings, sessions=sessions, broker=live_broker, completion_fn=completion_fn),
        approval=ApprovalWiring(checkpointer=checkpointer, broker=broker),
    )
    approval_lock = threading.Lock()
    fill_check_lock = threading.Lock()
    app = FastAPI(title="Bull Pit")

    @app.exception_handler(Refusal)
    def _refusal(_: HttpRequest, exc: Refusal) -> JSONResponse:
        return JSONResponse(exc.body.model_dump(mode="json", exclude_none=True), exc.status)

    @app.exception_handler(RequestValidationError)
    def _invalid(_: HttpRequest, exc: RequestValidationError) -> JSONResponse:
        message = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
            for error in exc.errors()
        )
        return JSONResponse(Problem(code="invalid_request", message=message).model_dump(), 422)

    @app.exception_handler(Exception)
    def _internal(_: HttpRequest, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", error=str(exc))
        problem = Problem(code="internal", message="Something went wrong. See the API log.")
        return JSONResponse(problem.model_dump(), 500)

    def run_in_background(state: RequestState) -> None:
        try:
            run_live(state, graph, settings=settings, sessions=sessions)
        except Exception:
            logger.exception("request_failed", request_id=state.request_id)

    def sweep(**filters: str) -> None:
        expire_overdue(sessions=sessions, broker=broker, now=now(), **filters)

    # --- requests ---------------------------------------------------------

    @app.post(
        "/requests",
        status_code=202,
        response_model=RequestStarted,
        responses={409: {"model": Problem}, 422: {"model": Problem}},
    )
    def start_request(body: NewRequest, background: BackgroundTasks) -> RequestStarted:
        ticker = body.ticker.strip().upper()
        if not _TICKER.match(ticker):
            raise Refusal(
                422, Problem(code="invalid_ticker", message=f"{body.ticker!r} isn't a ticker.")
            )
        state = open_request(
            ticker,
            "live",
            last_completed_session(now()),
            settings=settings,
            sessions=sessions,
            broker=broker,
            now=now(),
        )
        if state.rejection is not None:
            raise Refusal(409, Problem(code="duplicate", message=state.rejection))
        background.add_task(run_in_background, state)
        return RequestStarted(request_id=state.request_id)

    @app.get("/requests", response_model=list[RequestSummary])
    def list_requests(
        limit: int = Query(_DEFAULT_LIMIT, ge=1, le=_MAX_LIMIT),
    ) -> list[RequestSummary]:
        sweep()
        with sessions() as session:
            found = session.execute(
                select(RequestRow, ApprovalRecord)
                .outerjoin(ApprovalRecord, ApprovalRecord.request_id == RequestRow.id)
                .where(RequestRow.mode == "live")
                .order_by(RequestRow.created_at.desc())
                .limit(limit)
            ).all()
            return [RequestSummary(**_summary(row, approval)) for row, approval in found]

    @app.get(
        "/requests/{request_id}",
        response_model=RequestDetail,
        responses={404: {"model": Problem}},
    )
    def get_request(request_id: str) -> RequestDetail:
        sweep(request_id=request_id)
        with sessions() as session:
            row = session.get(RequestRow, request_id)
            if row is None:
                raise _not_found("request")
            approval = session.scalars(
                select(ApprovalRecord).where(ApprovalRecord.request_id == request_id)
            ).one_or_none()
            trade = session.scalars(
                select(TradeRecord).where(TradeRecord.request_id == request_id)
            ).one_or_none()
            stage, debate_round = _progress(graph, row)
            return RequestDetail(
                **_summary(row, approval),
                stage=stage,
                debate_round=debate_round,
                approval=None if approval is None else decision_from_row(approval),
                trade=None
                if trade is None
                else _trade_out(trade, None if approval is None else approval.overrides),
            )

    @app.get(
        "/requests/{request_id}/report",
        response_model=Report,
        responses={404: {"model": Problem}},
    )
    def get_report(request_id: str) -> Report:
        with sessions() as session:
            stored = session.scalars(
                select(ReportRecord).where(ReportRecord.request_id == request_id)
            ).one_or_none()
            if stored is None:
                raise _not_found("report")
            return Report.model_validate(stored.report)

    # --- approval -----------------------------------------------------------

    def resume(request_id: str, decision: ApprovalDecision) -> ApprovalResult:
        try:
            state = resume_live(request_id, decision, graph, sessions=sessions)
        except BrokerRejected as exc:
            raise Refusal(502, Problem(code="broker_rejected", message=str(exc))) from exc
        trade = (
            None
            if state.trade is None
            else TradeOut(
                **state.trade.model_dump(),
                request_id=request_id,
                overrides=list(decision.overrides),
            )
        )
        return ApprovalResult(approval=decision, trade=trade)

    def market_view(ticker: str) -> tuple[Decimal | None, Account, Decimal]:
        """The latest price and the account and position value net of pending orders."""
        try:
            account = live_broker.get_account()
            position = live_broker.get_position(ticker)
        except BrokerRejected as exc:
            raise Refusal(502, Problem(code="broker_unavailable", message=str(exc))) from exc
        try:
            latest: Decimal | None = price_of(ticker)
        except DataUnavailable:
            latest = None
        return latest, account, Decimal(0) if position is None else position.market_value

    @app.post(
        "/requests/{request_id}/approval",
        response_model=ApprovalResult,
        responses={
            404: {"model": Problem},
            409: {"model": ApprovalProblem},
            502: {"model": Problem},
        },
    )
    def decide(request_id: str, body: OwnerDecision) -> ApprovalResult:
        with approval_lock:
            sweep(request_id=request_id)
            with sessions() as session:
                row = session.get(RequestRow, request_id)
                if row is None or row.mode != "live":
                    raise _not_found("request")
                recorded = session.scalars(
                    select(ApprovalRecord).where(ApprovalRecord.request_id == request_id)
                ).one_or_none()
                report_row = session.scalars(
                    select(ReportRecord).where(ReportRecord.request_id == request_id)
                ).one_or_none()
                status, reason = row.status, row.status_reason
                ticker, as_of = row.ticker, row.as_of

            if status == "expired":
                raise Refusal(409, ApprovalProblem(code="expired", message=reason or "Expired."))
            if status != "awaiting_approval":
                said = "" if recorded is None else f" ({recorded.decision})"
                raise Refusal(
                    409,
                    ApprovalProblem(
                        code="not_awaiting",
                        message=f"This request isn't waiting for a decision{said}: it is {status}.",
                    ),
                )
            if recorded is not None:  # the process died before the order step: finish it (FR-10)
                return resume(request_id, decision_from_row(recorded))
            if report_row is None:
                raise _not_found("report")
            report = Report.model_validate(report_row.report)
            if report.order is None:
                raise ValueError(f"request {request_id} awaits approval without an order")

            if body.decision == "approve":
                latest, account, held = market_view(ticker)
            else:  # a rejection needs neither the price nor the account
                latest, account, held = (
                    None,
                    Account(cash=Decimal(0), equity=Decimal(0)),
                    Decimal(0),
                )
            result = check_decision(
                body,
                report.order,
                as_of=as_of,
                now=now(),
                latest_price=latest,
                loss_warning=report.loss_warning,
                account=account,
                held_value=held,
                staleness_pct=settings.approval_staleness_pct,
                cap_pct=settings.max_position_pct,
                risk_pct=settings.risk_per_trade_pct,
            )
            if isinstance(result, ApprovalProblem):
                raise Refusal(409, result)

            with sessions() as session:
                session.add(
                    approval_record(request_id, result, decided_at=now().replace(tzinfo=None))
                )
                try:
                    session.commit()
                except IntegrityError as exc:
                    raise Refusal(
                        409,
                        ApprovalProblem(code="not_awaiting", message="Already decided."),
                    ) from exc
            return resume(request_id, result)

    @app.post(
        "/requests/{request_id}/order-preview",
        response_model=OrderPreview,
        responses={
            404: {"model": Problem},
            409: {"model": ApprovalProblem},
            502: {"model": Problem},
        },
    )
    def order_preview(request_id: str, body: OrderPreviewBody) -> OrderPreview:
        sweep(request_id=request_id)
        with sessions() as session:
            row = session.get(RequestRow, request_id)
            if row is None or row.mode != "live":
                raise _not_found("request")
            report_row = session.scalars(
                select(ReportRecord).where(ReportRecord.request_id == request_id)
            ).one_or_none()
            status, ticker, as_of = row.status, row.ticker, row.as_of
        if status != "awaiting_approval" or report_row is None:
            raise Refusal(
                409,
                ApprovalProblem(
                    code="not_awaiting",
                    message=f"This request isn't waiting for a decision: it is {status}.",
                ),
            )
        report = Report.model_validate(report_row.report)
        if report.order is None:
            raise ValueError(f"request {request_id} awaits approval without an order")
        latest, account, held = market_view(ticker)
        return _preview(
            body,
            report.order,
            latest=latest,
            fetched_at=now(),
            as_of=as_of,
            loss_warning=report.loss_warning,
            account=account,
            held=held,
            settings=settings,
        )

    # --- trades, equity, fill check ------------------------------------------

    @app.get("/trades", response_model=list[TradeOut])
    def list_trades() -> list[TradeOut]:
        with sessions() as session:
            rows = session.scalars(
                select(TradeRecord)
                .where(TradeRecord.run_id.is_(None))
                .order_by(TradeRecord.id.desc())
            ).all()
            overrides = _overrides(session)
            return [_trade_out(row, overrides.get(row.request_id)) for row in rows]

    @app.post(
        "/trades/{request_id}/cancel",
        response_model=TradeOut,
        responses={404: {"model": Problem}, 409: {"model": Problem}, 502: {"model": Problem}},
    )
    def cancel_trade(request_id: str) -> TradeOut:
        """Cancels a live trade whose entry is still waiting (M11.1-FR-21). Alpaca is
        asked, then the order is read again: it may have filled as the cancel crossed."""
        with fill_check_lock, sessions() as session:
            row = session.scalars(
                select(TradeRecord).where(
                    TradeRecord.request_id == request_id, TradeRecord.run_id.is_(None)
                )
            ).one_or_none()
            if row is None:
                raise _not_found("trade")
            if row.status != "pending":
                raise Refusal(
                    409,
                    Problem(
                        code="not_cancellable",
                        message=f"This order isn't waiting to fill: the trade is {row.status}.",
                    ),
                )
            trade = trade_from_row(row)
            try:
                if trade.order_id is None:
                    raise BrokerRejected(f"trade {trade.client_order_id} has no Alpaca order ID")
                broker.cancel_order(trade.order_id)
                live = broker.get_live_order(trade).trade
            except BrokerRejected as exc:
                raise Refusal(502, Problem(code="broker_unavailable", message=str(exc))) from exc
            if live.status == "cancelled":
                row.status = "cancelled"
                row.cancel_reason = "cancelled by owner"
                session.commit()
                return _trade_out(row, _overrides(session).get(request_id))
            for column, value in trade_fields(live).items():  # as the fill check records it
                setattr(row, column, value)
            session.commit()
        raise Refusal(
            409,
            Problem(
                code="not_cancellable",
                message=(
                    "The entry had already filled, wholly or in part, so nothing was "
                    "cancelled. The trade is updated: review it."
                ),
            ),
        )

    @app.get("/equity", response_model=list[EquityPoint])
    def list_equity() -> list[EquityPoint]:
        with sessions() as session:
            rows = session.scalars(
                select(EquitySnapshot)
                .where(EquitySnapshot.run_id.is_(None))
                .order_by(EquitySnapshot.day)
            ).all()
            return [EquityPoint(date=row.day, equity=Decimal(row.equity)) for row in rows]

    @app.post("/fill-check", response_model=FillCheckResult, responses={502: {"model": Problem}})
    def run_fill_check() -> FillCheckResult:
        with fill_check_lock:
            try:
                return fill_check(
                    broker=broker,
                    sessions=sessions,
                    as_of=last_completed_session(now()),
                    settings=settings,
                )
            except BrokerRejected as exc:
                raise Refusal(502, Problem(code="broker_unavailable", message=str(exc))) from exc

    # --- account, history, portfolio, watchlist (M11.2) -------------------------

    @app.get("/account", response_model=AccountOut, responses={502: {"model": Problem}})
    def get_account() -> AccountOut:
        try:
            summary = broker.get_account_summary()
        except BrokerRejected as exc:
            raise Refusal(502, Problem(code="broker_unavailable", message=str(exc))) from exc
        change = summary.equity - summary.last_equity
        return AccountOut(
            broker=_BROKER_NAME,
            account_type="demo",
            account_number="•" * _MASK_KEEP + summary.account_number[-_MASK_KEEP:],
            status=summary.status,
            equity=summary.equity,
            cash=summary.cash,
            last_equity=summary.last_equity,
            day_change=change,
            day_change_pct=_percent(change, summary.last_equity),
        )

    @app.get("/market", response_model=MarketOut, responses={502: {"model": Problem}})
    def get_market() -> MarketOut:
        try:
            clock = broker.market_clock()
        except BrokerRejected as exc:
            raise Refusal(502, Problem(code="broker_unavailable", message=str(exc))) from exc
        return MarketOut(**clock.model_dump())

    @app.get("/history", response_model=list[HistoryRow])
    def list_history(
        limit: int = Query(_HISTORY_LIMIT, ge=1, le=_HISTORY_MAX),
    ) -> list[HistoryRow]:
        sweep()
        with sessions() as session:
            found = session.execute(
                select(RequestRow, ApprovalRecord, TradeRecord)
                .outerjoin(ApprovalRecord, ApprovalRecord.request_id == RequestRow.id)
                .outerjoin(TradeRecord, TradeRecord.request_id == RequestRow.id)
                .where(RequestRow.mode == "live")
                .order_by(RequestRow.created_at.desc())
                .limit(limit)
            ).all()
            planned = [row.id for row, _, trade in found if trade is None and row.outcome == "buy"]
            reports = session.execute(
                select(ReportRecord.request_id, ReportRecord.report).where(
                    ReportRecord.request_id.in_(planned)
                )
            ).all()
            plans = {
                request_id: SizedOrder.model_validate(report["order"])
                for request_id, report in reports
                if report.get("order")
            }
            prices: dict[str, Decimal] = {}
            if any(trade is not None and trade.status == "open" for _, _, trade in found):
                try:
                    prices = broker.last_prices()
                except BrokerRejected:  # the table still loads; open rows show no price
                    logger.warning("last_prices_failed", exc_info=True)
            return [
                _history_row(row, approval, trade, plans.get(row.id), prices.get(row.ticker))
                for row, approval, trade in found
            ]

    @app.get("/portfolio", response_model=PortfolioStats)
    def get_portfolio() -> PortfolioStats:
        with sessions() as session:
            decisions = session.scalars(
                select(ApprovalRecord.decision)
                .join(RequestRow, RequestRow.id == ApprovalRecord.request_id)
                .where(RequestRow.mode == "live")
            ).all()
            trades = session.execute(
                select(TradeRecord.status, TradeRecord.pnl).where(TradeRecord.run_id.is_(None))
            ).all()
        return portfolio_stats(
            decisions, [(status, None if pnl is None else Decimal(pnl)) for status, pnl in trades]
        )

    @app.get("/watchlist", response_model=list[WatchlistStock])
    def list_watchlist() -> list[WatchlistStock]:
        with sessions() as session:
            liked = dict(session.execute(select(LikedStock.symbol, LikedStock.created_at)).all())
        return [
            WatchlistStock(
                symbol=symbol,
                name=name,
                liked=symbol in liked,
                liked_at=_utc(liked[symbol]) if symbol in liked else None,
            )
            for symbol, name in _watchlist()
        ]

    def set_liked(symbol: str, liked: bool) -> WatchlistStock:
        """Likes or unlikes a watchlist stock; repeating it changes nothing."""
        symbol = symbol.upper()
        names = dict(_watchlist())
        if symbol not in names:
            raise _not_found("watchlist stock")
        with sessions() as session:
            row = session.get(LikedStock, symbol)
            if liked and row is None:
                row = LikedStock(symbol=symbol, created_at=now().replace(tzinfo=None))
                session.add(row)
            elif not liked and row is not None:
                session.delete(row)
                row = None
            session.commit()
            return WatchlistStock(
                symbol=symbol,
                name=names[symbol],
                liked=row is not None,
                liked_at=None if row is None else _utc(row.created_at),
            )

    @app.put(
        "/watchlist/{symbol}", response_model=WatchlistStock, responses={404: {"model": Problem}}
    )
    def like_stock(symbol: str) -> WatchlistStock:
        return set_liked(symbol, True)

    @app.delete(
        "/watchlist/{symbol}", response_model=WatchlistStock, responses={404: {"model": Problem}}
    )
    def unlike_stock(symbol: str) -> WatchlistStock:
        return set_liked(symbol, False)

    return app
