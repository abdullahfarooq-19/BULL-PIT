"""The API: FastAPI over the live runner, the fill check and the journal (M8
specs-plan FR-18 to FR-21, sec9.4). One user on localhost, no auth (dev-plan Q6).

Handlers are plain functions so FastAPI runs them in its thread pool; a request
runs in the background and the approval handler runs one at a time (D-M8-30).
Every refusal is a `Problem` JSON with a stable `code` (FR-19).
"""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from starlette.requests import Request as HttpRequest

from bullpit.api.schemas import (
    ApprovalResult,
    BacktestDetail,
    BacktestRunOut,
    EquityPoint,
    NewRequest,
    OrderPreview,
    OrderPreviewBody,
    PreviewWarning,
    Problem,
    RequestDetail,
    RequestStarted,
    RequestSummary,
    ResultsPage,
    TradeOut,
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
    BacktestRun,
    EquitySnapshot,
    ReportRecord,
    TradeRecord,
    approval_record,
    decision_from_row,
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


def _trade_out(row: TradeRecord) -> TradeOut:
    return TradeOut(**trade_from_row(row).model_dump(), request_id=row.request_id)


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
    }


def _progress(graph: Graph, row: RequestRow) -> tuple[str, int | None]:
    """The stage a request is at, and the debate round while it debates."""
    if row.status != "running":
        return row.status, None
    snapshot = graph.get_state(thread_config(row.id))
    stage = _STAGES.get(snapshot.next[0], "starting") if snapshot.next else "starting"
    round_ = len(snapshot.values.get("debate", [])) // 2 + 1 if stage == "debate" else None
    return stage, round_


def _last_equity(session: Session, run_id: str) -> Decimal | None:
    latest = session.scalars(
        select(EquitySnapshot)
        .where(EquitySnapshot.run_id == run_id)
        .order_by(EquitySnapshot.day.desc())
    ).first()
    return None if latest is None else Decimal(latest.equity)


def _run_out(session: Session, run: BacktestRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "policy": run.policy,
        "tickers": run.tickers,
        "start_date": run.start_date,
        "end_date": run.end_date,
        "weeks": run.weeks,
        "status": run.status,
        "status_reason": run.status_reason,
        "created_at": _utc(run.created_at),
        "last_equity": _last_equity(session, run.id),
    }


def _results_images(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.glob("*.png"))


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
                trade=None if trade is None else _trade_out(trade),
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
            else TradeOut(**state.trade.model_dump(), request_id=request_id)
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
            return [_trade_out(row) for row in rows]

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

    # --- backtests and results (read only, C6) --------------------------------

    @app.get("/backtests", response_model=list[BacktestRunOut])
    def list_backtests() -> list[BacktestRunOut]:
        with sessions() as session:
            runs = session.scalars(
                select(BacktestRun).order_by(BacktestRun.created_at.desc())
            ).all()
            return [BacktestRunOut(**_run_out(session, run)) for run in runs]

    @app.get(
        "/backtests/{run_id}/results",
        response_model=BacktestDetail,
        responses={404: {"model": Problem}},
    )
    def get_backtest(run_id: str) -> BacktestDetail:
        with sessions() as session:
            run = session.get(BacktestRun, run_id)
            if run is None:
                raise _not_found("backtest run")
            trades = session.scalars(
                select(TradeRecord).where(TradeRecord.run_id == run_id).order_by(TradeRecord.id)
            ).all()
            snapshots = session.scalars(
                select(EquitySnapshot)
                .where(EquitySnapshot.run_id == run_id)
                .order_by(EquitySnapshot.day)
            ).all()
            return BacktestDetail(
                **_run_out(session, run),
                seed=run.seed,
                starting_cash=Decimal(run.starting_cash),
                models=run.models,
                trades=[_trade_out(row) for row in trades],
                equity=[EquityPoint(date=s.day, equity=Decimal(s.equity)) for s in snapshots],
            )

    @app.get("/results", response_model=ResultsPage, responses={404: {"model": Problem}})
    def get_results() -> ResultsPage:
        page = settings.results_dir / "results.md"
        if not page.is_file():
            raise _not_found("results page (run `bullpit eval` first)")
        return ResultsPage(
            markdown=page.read_text(encoding="utf-8"), images=_results_images(settings.results_dir)
        )

    @app.get(
        "/results/files/{name}",
        response_class=FileResponse,
        responses={404: {"model": Problem}},
    )
    def get_result_image(name: str) -> FileResponse:
        if name not in _results_images(settings.results_dir):  # only the listed charts
            raise _not_found("chart")
        return FileResponse(settings.results_dir / name, media_type="image/png")

    return app
