"""Journal tables (dev-plan.md sec8; M2 specs-plan sec5.4, sec10).

M2 defines only `requests` (minimal columns) and `llm_calls`; later
milestones extend `requests` and add their own tables against the same
`Base`, so one migration chain covers the whole journal.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from bullpit.approval.gate import ApprovalDecision
from bullpit.domain import Trade


class Base(DeclarativeBase):
    pass


class Request(Base):
    """One research/trading request (M2 specs-plan sec2.2; M3-FR-21).

    The partial unique index is the duplicate-request lock (M3-FR-3, M8-FR-11):
    at most one `running` or `awaiting_approval` row per (ticker, mode).
    """

    __tablename__ = "requests"
    __table_args__ = (
        Index(
            "uq_requests_running",
            "ticker",
            "mode",
            unique=True,
            sqlite_where=text("status IN ('running', 'awaiting_approval')"),
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    mode: Mapped[str]
    as_of: Mapped[date]
    created_at: Mapped[datetime]
    ticker: Mapped[str]
    status: Mapped[str]  # running | awaiting_approval | completed | rejected | failed | expired
    status_reason: Mapped[str | None] = mapped_column(default=None)
    route: Mapped[str | None] = mapped_column(default=None)  # debate | no_trade
    warnings: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    git_commit: Mapped[str | None] = mapped_column(default=None)
    price_source: Mapped[str | None] = mapped_column(default=None)  # yfinance | alpaca
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    outcome: Mapped[str | None] = mapped_column(default=None)  # buy | no_trade (M4-FR-19)
    no_trade_reason: Mapped[str | None] = mapped_column(default=None)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("backtest_runs.id"), index=True, default=None
    )  # None for a single request (M6-FR-15)


class SignalRecord(Base):
    """One analyst's signal for a request (M3-FR-21). Named `SignalRecord`
    so it doesn't clash with `bullpit.llm.schemas.Signal`."""

    __tablename__ = "signals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True)
    analyst: Mapped[str]
    direction: Mapped[str]
    confidence: Mapped[float]
    evidence: Mapped[list[dict[str, str]]] = mapped_column(JSON)
    flagged: Mapped[bool]
    note: Mapped[str | None] = mapped_column(default=None)


class DebateTurnRecord(Base):
    """One bull or bear turn (M4-FR-19; sec10)."""

    __tablename__ = "debate_turns"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True)
    round: Mapped[int]
    side: Mapped[str]
    points: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    concessions: Mapped[list[str]] = mapped_column(JSON)
    conviction: Mapped[float]
    word_count: Mapped[int]
    unsupported_count: Mapped[int]
    over_word_limit: Mapped[bool]
    flagged: Mapped[bool]


class RecommendationRecord(Base):
    """One trader attempt and what followed it: Stage A, Stage B (M4-FR-19;
    sec10). Up to `risk_max_vetoes + 1` rows per request."""

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True)
    attempt: Mapped[int]
    action: Mapped[str]
    exit_style: Mapped[str]
    target_weight: Mapped[str]  # Decimal as a string (SQLite has no exact decimal)
    confidence: Mapped[float]
    decisive_evidence: Mapped[list[str]] = mapped_column(JSON)
    reasoning: Mapped[str]
    flagged: Mapped[bool]  # the trader reply was invalid
    sized_order: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    blocked_reason: Mapped[str | None] = mapped_column(default=None)
    review_decision: Mapped[str | None] = mapped_column(default=None)
    review_reason: Mapped[str | None] = mapped_column(default=None)
    review_shares: Mapped[int | None] = mapped_column(default=None)
    review_clamped: Mapped[bool | None] = mapped_column(default=None)
    review_flagged: Mapped[bool | None] = mapped_column(default=None)
    final_order: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)


class ReportRecord(Base):
    """The structured report as JSON, one per request (M5-FR-12; C3: the
    Markdown is re-rendered from it, never stored)."""

    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True, unique=True)
    report: Mapped[dict[str, Any]] = mapped_column(JSON)


class BacktestRun(Base):
    """One backtest: its inputs, progress and resume point (M6-FR-15; sec10)."""

    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(primary_key=True)  # 8 hex characters
    created_at: Mapped[datetime]
    finished_at: Mapped[datetime | None] = mapped_column(default=None)
    tickers: Mapped[list[str]] = mapped_column(JSON)  # sorted
    start_date: Mapped[date]
    end_date: Mapped[date]  # the last decision day
    weeks: Mapped[int]
    seed: Mapped[int]
    starting_cash: Mapped[str]  # Decimal as a string
    models: Mapped[dict[str, str]] = mapped_column(JSON)  # {"small": ..., "large": ...}
    assets: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    git_commit: Mapped[str]
    status: Mapped[str]  # running | paused | stopped | completed
    status_reason: Mapped[str | None] = mapped_column(default=None)
    checkpoint: Mapped[date | None] = mapped_column(default=None)  # last completed decision day
    policy: Mapped[str] = mapped_column(
        default="bullpit", server_default="bullpit"
    )  # bullpit | single_agent | always_buy | ma_rule | bullpit_fixed (M7)
    source_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("backtest_runs.id"), default=None
    )  # bullpit_fixed only: the run whose decisions it replays


class ApprovalRecord(Base):
    """One approval decision per request (M6-FR-6; architecture Part 13)."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True, unique=True)
    decision: Mapped[str]  # approved | rejected
    recommended_shares: Mapped[int]
    approved_shares: Mapped[int]
    decided_by: Mapped[str]  # backtest_policy | owner
    decided_at: Mapped[datetime]  # backtest: the close of `as_of`; owner: wall-clock UTC
    latest_price: Mapped[str | None] = mapped_column(default=None)  # the staleness check's price
    confirmations: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    # M11.1: what was approved, so the order can be rebuilt from this row (FR-18).
    order_type: Mapped[str] = mapped_column(default="market", server_default="market")
    entry_price: Mapped[str | None] = mapped_column(default=None)
    limit_price: Mapped[str | None] = mapped_column(default=None)
    stop_loss: Mapped[str | None] = mapped_column(default=None)
    take_profit: Mapped[str | None] = mapped_column(default=None)
    seen_price: Mapped[str | None] = mapped_column(default=None)
    overrides: Mapped[list[str] | None] = mapped_column(JSON, default=None)


class TradeRecord(Base):
    """A `domain.Trade` plus its request and run (M6 sec10). Money is text."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("requests.id"), index=True, unique=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("backtest_runs.id"), index=True, default=None
    )  # None for live (M8)
    client_order_id: Mapped[str] = mapped_column(index=True, unique=True)
    ticker: Mapped[str]
    submitted_on: Mapped[date]
    shares: Mapped[int]  # after any downsizing at the open
    reference_price: Mapped[str]
    stop_loss: Mapped[str]
    take_profit: Mapped[str]
    status: Mapped[str]  # pending | open | closed | cancelled | open_at_end
    entry_date: Mapped[date | None] = mapped_column(default=None)
    entry_price: Mapped[str | None] = mapped_column(default=None)
    exit_date: Mapped[date | None] = mapped_column(default=None)
    exit_price: Mapped[str | None] = mapped_column(default=None)
    exit_reason: Mapped[str | None] = mapped_column(default=None)
    cancel_reason: Mapped[str | None] = mapped_column(default=None)
    pnl: Mapped[str | None] = mapped_column(default=None)  # (exit - entry) x shares
    order_id: Mapped[str | None] = mapped_column(default=None)  # Alpaca IDs, live only
    stop_order_id: Mapped[str | None] = mapped_column(default=None)
    take_profit_order_id: Mapped[str | None] = mapped_column(default=None)
    order_type: Mapped[str] = mapped_column(default="market", server_default="market")  # M11.1
    limit_price: Mapped[str | None] = mapped_column(default=None)


class EquitySnapshot(Base):
    """Account value at a session's close; `cash` includes pending reservations.
    Live rows (`run_id` NULL) hold equity only: Alpaca's history has no cash split."""

    __tablename__ = "equity_snapshots"
    __table_args__ = (
        UniqueConstraint("run_id", "date", name="uq_equity_snapshots_run_date"),
        Index(
            "uq_equity_snapshots_live_date",
            "date",
            unique=True,
            sqlite_where=text("run_id IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("backtest_runs.id"), index=True, default=None
    )  # None for live (M8)
    day: Mapped[date] = mapped_column("date")
    cash: Mapped[str | None] = mapped_column(default=None)
    positions_value: Mapped[str | None] = mapped_column(default=None)
    equity: Mapped[str]


class LikedStock(Base):
    """A watchlist stock the owner saved (M11.2-FR-8); `created_at` is naive UTC."""

    __tablename__ = "liked_stocks"

    symbol: Mapped[str] = mapped_column(primary_key=True)
    created_at: Mapped[datetime]


def _decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


def approval_record(
    request_id: str, decision: ApprovalDecision, *, decided_at: datetime
) -> ApprovalRecord:
    """A new `approvals` row for `decision`; money as `Decimal` strings."""
    return ApprovalRecord(
        request_id=request_id,
        decision=decision.decision,
        recommended_shares=decision.recommended_shares,
        approved_shares=decision.approved_shares,
        decided_by=decision.decided_by,
        decided_at=decided_at,
        latest_price=None if decision.latest_price is None else str(decision.latest_price),
        confirmations=list(decision.confirmations),
        order_type=decision.order_type,
        entry_price=None if decision.entry_price is None else str(decision.entry_price),
        limit_price=None if decision.limit_price is None else str(decision.limit_price),
        stop_loss=None if decision.stop_loss is None else str(decision.stop_loss),
        take_profit=None if decision.take_profit is None else str(decision.take_profit),
        seen_price=None if decision.seen_price is None else str(decision.seen_price),
        overrides=list(decision.overrides),
    )


def decision_from_row(row: ApprovalRecord) -> ApprovalDecision:
    """The `ApprovalDecision` an `approvals` row records. Rows from before M11.1
    read as market orders with no entry or overrides."""
    return ApprovalDecision.model_validate(
        {
            "decision": row.decision,
            "recommended_shares": row.recommended_shares,
            "approved_shares": row.approved_shares,
            "decided_by": row.decided_by,
            "latest_price": _decimal(row.latest_price),
            "confirmations": row.confirmations or [],
            "order_type": row.order_type,
            "entry_price": _decimal(row.entry_price),
            "limit_price": _decimal(row.limit_price),
            "stop_loss": _decimal(row.stop_loss),
            "take_profit": _decimal(row.take_profit),
            "seen_price": _decimal(row.seen_price),
            "overrides": row.overrides or [],
        }
    )


def trade_from_row(row: TradeRecord) -> Trade:
    """The broker `Trade` a `trades` row records (backtest and live)."""
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
            "order_id": row.order_id,
            "stop_order_id": row.stop_order_id,
            "take_profit_order_id": row.take_profit_order_id,
            "order_type": row.order_type,
            "limit_price": _decimal(row.limit_price),
        }
    )


def trade_fields(trade: Trade) -> dict[str, Any]:
    """The `trades` columns a broker `Trade` fills that change over its life;
    money as `Decimal` strings."""
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


def trade_record(request_id: str, trade: Trade, *, run_id: str | None = None) -> TradeRecord:
    """A new `trades` row for `trade`; `run_id` is `None` for a live trade."""
    return TradeRecord(
        request_id=request_id,
        run_id=run_id,
        client_order_id=trade.client_order_id,
        ticker=trade.ticker,
        submitted_on=trade.submitted_on,
        reference_price=str(trade.reference_price),
        stop_loss=str(trade.stop_loss),
        take_profit=str(trade.take_profit),
        order_id=trade.order_id,
        stop_order_id=trade.stop_order_id,
        take_profit_order_id=trade.take_profit_order_id,
        order_type=trade.order_type,
        limit_price=None if trade.limit_price is None else str(trade.limit_price),
        **trade_fields(trade),
    )


class LLMCall(Base):
    """One completed `call_llm` invocation: cache hit, success or flagged
    fallback (M2-FR-11). A call refused by `PromptTooLarge` or
    `QuotaExhausted` writes no row, since nothing was spent.
    """

    __tablename__ = "llm_calls"
    __table_args__ = (Index("ix_llm_calls_model_created_at", "model", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Plain indexed string, not a hard FK yet: M2 callers (e.g. the
    # measurement script) have no real Request row to point to (M2-FR-13).
    request_id: Mapped[str] = mapped_column(index=True)
    role: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str]
    cache_hit: Mapped[bool]
    cache_key: Mapped[str]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    reasoning_tokens: Mapped[int]
    latency_ms: Mapped[int]
    flagged: Mapped[bool]
    created_at: Mapped[datetime]
