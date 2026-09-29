"""Journal tables (dev-plan.md sec8; M2 specs-plan sec5.4, sec10).

M2 defines only `requests` (minimal columns) and `llm_calls`; later
milestones extend `requests` and add their own tables against the same
`Base`, so one migration chain covers the whole journal.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Request(Base):
    """One research/trading request (M2 specs-plan sec2.2; M3-FR-21).

    The partial unique index is the duplicate-request lock (M3-FR-3): at
    most one `running` row per (ticker, mode).
    """

    __tablename__ = "requests"
    __table_args__ = (
        Index(
            "uq_requests_running",
            "ticker",
            "mode",
            unique=True,
            sqlite_where=text("status = 'running'"),
        ),
    )

    id: Mapped[str] = mapped_column(primary_key=True)
    mode: Mapped[str]
    as_of: Mapped[date]
    created_at: Mapped[datetime]
    ticker: Mapped[str]
    status: Mapped[str]  # running | completed | rejected | failed
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
    decided_by: Mapped[str]  # backtest_policy (M8: owner)
    decided_at: Mapped[datetime]  # simulated: the close of `as_of`


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


class EquitySnapshot(Base):
    """Account value at a session's close; `cash` includes pending reservations."""

    __tablename__ = "equity_snapshots"
    __table_args__ = (UniqueConstraint("run_id", "date", name="uq_equity_snapshots_run_date"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("backtest_runs.id"), index=True, default=None
    )  # None for live (M8)
    day: Mapped[date] = mapped_column("date")
    cash: Mapped[str]
    positions_value: Mapped[str]
    equity: Mapped[str]


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
