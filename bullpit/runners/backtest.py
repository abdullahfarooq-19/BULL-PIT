"""The backtest runner: one graph run per stock on the last trading day of each
week, followed through the simulated broker, checkpointed after every week
so a quota pause resumes for free (architecture sec10; M6 specs-plan FR-6 to
FR-14, sec9.3, sec11).

A week is simulated and requested entirely in memory, then written in one
transaction together with its checkpoint. The LLM gateway commits its own
`llm_calls` rows on other connections, so the runner must not hold a write
lock while the graph runs.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal, cast

import structlog
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from bullpit.approval.gate import ApprovalDecision, backtest_policy
from bullpit.broker.base import Broker, client_order_id
from bullpit.broker.sim import SimBroker
from bullpit.config import Settings
from bullpit.data.calendar import decision_days, session_close, sessions_between
from bullpit.data.prices import get_prices
from bullpit.domain import Asset, Bar, Trade
from bullpit.errors import ConfigError, LLMUnavailable, QuotaExhausted
from bullpit.eval.baselines import Policy, bullpit_wanted_buy
from bullpit.graph import Deps, build_graph
from bullpit.journal.models import (
    ApprovalRecord,
    BacktestRun,
    EquitySnapshot,
    RecommendationRecord,
    Request,
    TradeRecord,
)
from bullpit.llm.gateway import CompletionFn, litellm_completion
from bullpit.risk.rules import loss_warning
from bullpit.runners.request import (
    add_request_rows,
    earliest_backtest_date,
    git_commit,
    naive_utc_now,
)
from bullpit.state import RequestState

_History = list[tuple[date, Decimal]]  # (session, equity), oldest first


class WeekSummary(BaseModel, frozen=True):
    decision_day: date
    outcomes: dict[str, str]  # ticker -> "BUY 12", "NO TRADE" or "REJECTED"
    equity: Decimal  # at the decision day's close


class RunResult(BaseModel, frozen=True):
    run_id: str
    status: Literal["completed", "paused"]
    reason: str | None  # why it paused
    end_equity: Decimal  # at the last completed decision day's close
    trades: list[Trade]  # every trade of the run, in submission order


def start_backtest(
    tickers: Sequence[str],
    start: date,
    *,
    weeks: int,
    seed: int,
    starting_cash: Decimal,
    settings: Settings,
    sessions: sessionmaker[Session],
    asset_lookup: Broker,
    policy: Policy = "bullpit",
    source_run: str | None = None,
) -> str:
    """Checks the inputs, records the run and returns its ID. A refusal raises
    `ConfigError` before anything is written (FR-7). `source_run` is the
    completed Bull Pit run a `bullpit_fixed` run replays (M7-FR-3)."""
    if start <= max(settings.llm_small_model_cutoff, settings.llm_large_model_cutoff):
        raise ConfigError(
            "Backtest dates must be after the models' training cutoff: "
            f"use {earliest_backtest_date(settings)} or later."
        )
    days = decision_days(start, weeks)
    if not days:
        raise ConfigError(f"No decision days in {weeks} weeks from {start}.")

    symbols = sorted({ticker.upper() for ticker in tickers})
    assets: list[Asset] = []
    for symbol in symbols:
        asset = asset_lookup.get_asset(symbol)
        if asset is None or not asset.tradable or not asset.active:
            raise ConfigError(f"{symbol} isn't a tradable stock on Alpaca.")
        assets.append(asset)

    if policy == "bullpit_fixed":
        _check_source_run(source_run, symbols, start, weeks, sessions)

    run = BacktestRun(
        id=secrets.token_hex(4),
        created_at=naive_utc_now(),
        tickers=symbols,
        start_date=start,
        end_date=days[-1],
        weeks=weeks,
        seed=seed,
        starting_cash=str(starting_cash),
        models=_configured_models(settings),
        assets=[asset.model_dump(mode="json") for asset in assets],
        git_commit=git_commit(),
        status="running",
        policy=policy,
        source_run_id=source_run,
    )
    with sessions() as session:
        session.add(run)
        session.commit()
        return run.id


def _check_source_run(
    source_run: str | None,
    symbols: list[str],
    start: date,
    weeks: int,
    sessions: sessionmaker[Session],
) -> None:
    """A `bullpit_fixed` run needs a completed Bull Pit run on the same stocks,
    start and length; otherwise it would be judged on different weeks."""
    with sessions() as session:
        source = None if source_run is None else session.get(BacktestRun, source_run)
    if (
        source is None
        or source.status != "completed"
        or source.policy != "bullpit"
        or (source.tickers, source.start_date, source.weeks) != (symbols, start, weeks)
    ):
        raise ConfigError(
            "bullpit_fixed needs --source-run: a completed bullpit run with the same "
            "tickers, start and weeks."
        )


def _source_decisions(
    sessions: sessionmaker[Session], source_run_id: str
) -> dict[tuple[date, str], bool]:
    """Bull Pit's buy decision per (decision day, ticker): the request's last
    trader attempt. A request with no attempt isn't listed, so it's no trade."""
    with sessions() as session:
        rows = session.execute(
            select(Request.as_of, Request.ticker, RecommendationRecord)
            .join(RecommendationRecord, RecommendationRecord.request_id == Request.id)
            .where(Request.run_id == source_run_id)
            .order_by(RecommendationRecord.attempt)
        )
        return {
            (as_of, ticker): bullpit_wanted_buy(attempt.action, attempt.review_decision)
            for as_of, ticker, attempt in rows
        }


def run_backtest(
    run_id: str,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
    on_week: Callable[[WeekSummary], None] | None = None,
) -> RunResult:
    """Runs (or resumes) a backtest from the week after its checkpoint. A quota
    or provider outage pauses it and returns; any other error marks it stopped
    and is re-raised. Either way the unfinished week leaves no rows (FR-11)."""
    with sessions() as session:
        run = session.get(BacktestRun, run_id)
        if run is None or run.status == "completed":
            raise ConfigError(f"No unfinished backtest run {run_id!r}.")
        if run.models != _configured_models(settings):
            raise ConfigError(
                f"Run {run_id} used models {run.models}, but the configured models are "
                f"{_configured_models(settings)}; a run can't change models."
            )
        rows = session.scalars(
            select(TradeRecord).where(TradeRecord.run_id == run_id).order_by(TradeRecord.id)
        ).all()
        history: _History = [
            (row.day, Decimal(row.equity))
            for row in session.scalars(
                select(EquitySnapshot)
                .where(EquitySnapshot.run_id == run_id)
                .order_by(EquitySnapshot.day)
            )
        ]
    _mark(sessions, run_id, "running", None)

    starting_cash = Decimal(run.starting_cash)
    settings = settings.model_copy(update={"llm_seed": run.seed})
    broker = SimBroker(
        starting_cash=starting_cash,
        slippage_pct=settings.sim_slippage_pct,
        assets={a["symbol"]: Asset.model_validate(a) for a in run.assets},
        trades=[trade_from_row(row) for row in rows],
    )
    graph = build_graph(
        Deps(settings=settings, sessions=sessions, broker=broker, completion_fn=completion_fn),
        policy=cast(Policy, run.policy),
        buy_decisions=(
            None if run.source_run_id is None else _source_decisions(sessions, run.source_run_id)
        ),
    )

    days = decision_days(run.start_date, run.weeks)
    done = run.checkpoint
    last = done if done is not None else run.start_date - timedelta(days=1)
    status: Literal["completed", "paused"] = "completed"
    reason: str | None = None
    try:
        for day in (d for d in days if done is None or d > done):
            summary = _run_week(
                day,
                last,
                is_last=day == days[-1],
                run=run,
                settings=settings,
                sessions=sessions,
                graph=graph,
                broker=broker,
                history=history,
            )
            last = day
            if on_week is not None:
                on_week(summary)
    except (QuotaExhausted, LLMUnavailable) as exc:
        status, reason = "paused", str(exc)
    except Exception as exc:
        _mark(sessions, run_id, "stopped", str(exc))
        raise
    _mark(sessions, run_id, status, reason)

    with sessions() as session:
        trades = [
            trade_from_row(row)
            for row in session.scalars(
                select(TradeRecord).where(TradeRecord.run_id == run_id).order_by(TradeRecord.id)
            )
        ]
    return RunResult(
        run_id=run_id,
        status=status,
        reason=reason,
        end_equity=history[-1][1] if history else starting_cash,
        trades=trades,
    )


def _configured_models(settings: Settings) -> dict[str, str]:
    return {"small": settings.llm_small_model, "large": settings.llm_large_model}


def _mark(
    sessions: sessionmaker[Session],
    run_id: str,
    status: Literal["running", "completed", "paused", "stopped"],
    reason: str | None,
) -> None:
    with sessions() as session:
        run = session.get(BacktestRun, run_id)
        if run is None:  # pragma: no cover - the run was loaded a moment ago
            raise ConfigError(f"No backtest run {run_id!r}.")
        run.status, run.status_reason = status, reason
        if status == "completed":
            run.finished_at = naive_utc_now()
        session.commit()


def _decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def trade_from_row(row: TradeRecord) -> Trade:
    return Trade.model_validate(
        {
            "client_order_id": row.client_order_id,
            "ticker": row.ticker,
            "submitted_on": row.submitted_on,
            "shares": row.shares,
            "reference_price": Decimal(row.reference_price),
            "stop_loss": Decimal(row.stop_loss),
            "take_profit": Decimal(row.take_profit),
            "status": row.status,
            "entry_date": row.entry_date,
            "entry_price": _decimal(row.entry_price),
            "exit_date": row.exit_date,
            "exit_price": _decimal(row.exit_price),
            "exit_reason": row.exit_reason,
            "cancel_reason": row.cancel_reason,
        }
    )


def _trade_fields(trade: Trade) -> dict[str, Any]:
    """The `trades` columns a broker `Trade` fills; money as `Decimal` strings."""
    return {
        "shares": trade.shares,
        "status": trade.status,
        "entry_date": trade.entry_date,
        "entry_price": None if trade.entry_price is None else str(trade.entry_price),
        "exit_date": trade.exit_date,
        "exit_price": None if trade.exit_price is None else str(trade.exit_price),
        "exit_reason": trade.exit_reason,
        "cancel_reason": trade.cancel_reason,
        "pnl": None if trade.pnl is None else str(trade.pnl),
    }


def _session_bar(ticker: str, day: date, settings: Settings) -> tuple[Bar, float]:
    """`day`'s bar and split ratio, read through the date guard at `as_of = day`
    (M6-NFR-5). A missing bar raises `DataUnavailable`."""
    history = get_prices(ticker, day, 1, settings=settings)
    row = history.bars.iloc[-1]
    bar = Bar(
        date=day,
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=float(row["volume"]),
    )
    return bar, next((ratio for _, ratio in history.splits), 1.0)


def _simulate(
    broker: SimBroker, days: list[date], settings: Settings
) -> tuple[dict[str, Trade], list[tuple[date, Decimal, Decimal]]]:
    """Steps the broker through `days`: the trades that changed, keyed by
    order ID, and each session's (day, cash, positions value)."""
    changed: dict[str, Trade] = {}
    snapshots: list[tuple[date, Decimal, Decimal]] = []
    for day in days:
        bars: dict[str, Bar] = {}
        splits: dict[str, float] = {}
        for ticker in broker.tickers_needing_bars():
            bars[ticker], splits[ticker] = _session_bar(ticker, day, settings)
        for trade in broker.on_session(day, bars, splits):
            changed[trade.client_order_id] = trade
        snapshots.append((day, *broker.valuation()))
    return changed, snapshots


def _run_week(
    day: date,
    last: date,
    *,
    is_last: bool,
    run: BacktestRun,
    settings: Settings,
    sessions: sessionmaker[Session],
    graph: CompiledStateGraph[RequestState, None, RequestState, RequestState],
    broker: SimBroker,
    history: _History,
) -> WeekSummary:
    """One decision day (FR-9): the sessions since `last`, one request per
    ticker in order, the window end if this is the last week, then one
    transaction for all of it plus the checkpoint."""
    changed, snapshots = _simulate(broker, sessions_between(last, day), settings)
    week_history = [*history, *((d, cash + positions) for d, cash, positions in snapshots)]

    requests: list[tuple[str, str, RequestState]] = []
    approvals: dict[str, ApprovalDecision] = {}
    submitted: dict[str, Trade] = {}  # request ID -> the trade as submitted
    for ticker in run.tickers:
        request_id = f"{day:%Y%m%d}-{ticker}-{run.id}"
        state = RequestState(
            request_id=request_id,
            mode="backtest",
            as_of=day,
            ticker=ticker,
            loss_warning=loss_warning(
                week_history,
                day,
                drop_pct=settings.loss_warning_pct,
                days=settings.loss_warning_days,
            ),
        )
        with structlog.contextvars.bound_contextvars(
            request_id=request_id, mode="backtest", as_of=str(day)
        ):
            result = RequestState.model_validate(graph.invoke(state))
        requests.append((request_id, ticker, result))
        if result.outcome == "buy" and result.sized_order is not None:
            approvals[request_id] = backtest_policy(result.sized_order)
            trade = broker.submit_bracket_order(
                result.sized_order, client_order_id=client_order_id(request_id), submitted_on=day
            )
            submitted[request_id] = trade
            changed[trade.client_order_id] = trade
    if is_last:
        for trade in broker.end_window(day):
            changed[trade.client_order_id] = trade

    with sessions() as session:
        for snap_day, cash, positions in snapshots:
            session.add(
                EquitySnapshot(
                    run_id=run.id,
                    day=snap_day,
                    cash=str(cash),
                    positions_value=str(positions),
                    equity=str(cash + positions),
                )
            )
        for request_id, ticker, result in requests:
            row = Request(
                id=request_id,
                mode="backtest",
                as_of=day,
                created_at=naive_utc_now(),
                ticker=ticker,
                run_id=run.id,
            )
            session.add(row)
            add_request_rows(session, row, result=result, error=None, settings=settings)
        for request_id, decision in approvals.items():
            session.add(
                ApprovalRecord(
                    request_id=request_id,
                    decision=decision.decision,
                    recommended_shares=decision.recommended_shares,
                    approved_shares=decision.approved_shares,
                    decided_by=decision.decided_by,
                    decided_at=session_close(day).replace(tzinfo=None),
                )
            )
        for request_id, trade in submitted.items():
            session.add(
                TradeRecord(
                    request_id=request_id,
                    run_id=run.id,
                    client_order_id=trade.client_order_id,
                    ticker=trade.ticker,
                    submitted_on=trade.submitted_on,
                    reference_price=str(trade.reference_price),
                    stop_loss=str(trade.stop_loss),
                    take_profit=str(trade.take_profit),
                    **_trade_fields(trade),
                )
            )
        session.flush()
        for trade in changed.values():
            record = session.scalars(
                select(TradeRecord).where(TradeRecord.client_order_id == trade.client_order_id)
            ).one()
            for column, value in _trade_fields(trade).items():
                setattr(record, column, value)
        checkpoint = session.get(BacktestRun, run.id)
        if checkpoint is None:  # pragma: no cover - the run was loaded at the start
            raise ConfigError(f"No backtest run {run.id!r}.")
        checkpoint.checkpoint = day
        session.commit()

    history.extend((d, cash + positions) for d, cash, positions in snapshots)
    outcomes = {
        ticker: _outcome_label(result, submitted.get(request_id))
        for request_id, ticker, result in requests
    }
    return WeekSummary(decision_day=day, outcomes=outcomes, equity=history[-1][1])


def _outcome_label(result: RequestState, trade: Trade | None) -> str:
    if result.rejection is not None:
        return "REJECTED"
    if trade is not None:
        return f"BUY {trade.shares}"
    return "NO TRADE"
