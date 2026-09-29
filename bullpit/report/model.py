"""The structured report the owner decides from (architecture sec7, Part 12;
M5 specs-plan sec5). Pure data: no I/O, no settings. Sections that don't
apply to how the request ended are `None` (M5-FR-1). M8's dashboard renders
this object; the CLI renders Markdown from it.

It can't import `state.py` (which holds a `Report`), so a trader attempt is
flattened into `AttemptRow` (D-M5-9).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from bullpit.domain import ExitStyle, SizedOrder
from bullpit.llm.schemas import Signal

ReportOutcome = Literal["buy", "no_trade", "rejected"]
ProseSource = Literal["llm", "retry", "fallback", "none"]


class DebateSummary(BaseModel, frozen=True):
    """Section 5."""

    strongest_bull: str
    strongest_bear: str
    bull_conceded: str
    unresolved: str
    bull_conviction: float | None
    bear_conviction: float | None
    unsupported_points: int


class AttemptRow(BaseModel, frozen=True):
    """Section 6: one trader attempt and what the risk manager did with it."""

    number: int
    action: Literal["buy", "no_trade"]
    target_weight: Decimal
    exit_style: ExitStyle
    confidence: float
    shares: int | None  # Stage A size; None if blocked or not reached
    blocked_reason: str | None
    review_decision: Literal["approve", "shrink", "veto"] | None
    review_reason: str | None  # LLM text, numbers masked (M5-FR-3)
    review_clamped: bool


class MarketContext(BaseModel, frozen=True):
    """Section 8."""

    spy_close: float | None
    spy_sma_200: float | None
    spy_above: bool | None
    vix_close: float | None
    vix_label: Literal["low", "normal", "high"] | None
    explanation: str  # "Market context not available." on a data failure


class DataNotes(BaseModel, frozen=True):
    """Section 9."""

    models: list[str]  # the models actually called (D-M5-12)
    news_headlines: int | None  # None if the sentiment analyst failed
    filing_form: str | None
    filing_date: date | None
    price_source: Literal["yfinance", "alpaca"] | None
    warnings: list[str]


class Report(BaseModel, frozen=True):
    # 1 header
    request_id: str
    ticker: str
    company_name: str | None
    mode: Literal["live", "backtest"]
    as_of: date
    generated_at: datetime  # UTC
    # 2 recommendation
    outcome: ReportOutcome
    confidence: float | None
    summary: str
    reason: str | None  # code-written (M5-FR-2)
    reason_detail: str | None  # quoted LLM text, numbers masked
    # 3 suggested order; section 10 (actions) is derived from `order`
    order: SizedOrder | None
    order_pct_of_equity: Decimal | None
    # 4 analysts
    signals: list[Signal]
    # 5 debate
    debate: DebateSummary | None
    # 6 risk manager (the size-setting limit and all four limit shares are on `order`)
    attempts: list[AttemptRow]
    loss_warning: bool | None  # None = not available (D-M4-9)
    # 7 what would change the view
    would_change_view: str | None
    # 8 market context
    market: MarketContext | None  # None only for rejections
    # 9 data notes
    data_notes: DataNotes
    prose_source: ProseSource
