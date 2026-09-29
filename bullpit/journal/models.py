"""Journal tables (dev-plan.md sec8; M2 specs-plan sec5.4, sec10).

M2 defines only `requests` (minimal columns) and `llm_calls`; later
milestones extend `requests` and add their own tables against the same
`Base`, so one migration chain covers the whole journal.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Index, text
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
