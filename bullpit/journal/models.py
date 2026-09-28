"""Journal tables (dev-plan.md sec8; M2 specs-plan sec5.4, sec10).

M2 defines only `requests` (minimal columns) and `llm_calls`; later
milestones extend `requests` and add their own tables against the same
`Base`, so one migration chain covers the whole journal.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Request(Base):
    """One research/trading request. M3 fills in the remaining columns
    (config snapshot, git commit, status, request lock) (M2 specs-plan sec2.2).
    """

    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(primary_key=True)
    mode: Mapped[str]
    as_of: Mapped[date]
    created_at: Mapped[datetime]


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
