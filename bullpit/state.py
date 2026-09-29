"""The shared graph state (architecture Part 0; M3 specs-plan sec5).

`RequestState` holds only the fields built so far; later milestones add theirs
(D-M3-4) -- CLAUDE.md forbids placeholder code for types that don't exist
yet. Every field crossing a graph node is typed (dev-plan.md sec2.2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from bullpit.domain import Account, Bar, ExitStyle, Position, SizedOrder
from bullpit.llm.schemas import DebatePoint, Evidence, Signal
from bullpit.report.model import Report
from bullpit.tools.fundamentals import FundamentalsMetrics
from bullpit.tools.indicators import Indicators


class PriceSnapshot(BaseModel, frozen=True):
    source: Literal["yfinance", "alpaca"]
    bars: list[Bar]  # point-in-time, oldest first, through as_of
    splits: list[tuple[date, float]]  # ex-date <= as_of, ratio new/old
    reference_price: Decimal  # latest close up to as_of


class SignalsBoard(BaseModel, frozen=True):
    signals: dict[str, Signal]  # keyed by analyst
    score: float
    conflict: bool
    evidence: dict[str, Evidence]  # the registry the debate may cite (M4)


class CheckedPoint(DebatePoint, frozen=True):
    """A debate point after the code checks (M4-FR-3): `unsupported` is set
    when it cites no evidence ID, or cites one that isn't registered."""

    unsupported: bool


class DebateTurn(BaseModel, frozen=True):
    side: Literal["bull", "bear"]
    round: int
    points: list[CheckedPoint]
    concessions: list[str]
    conviction: float
    word_count: int
    over_word_limit: bool
    flagged: bool


class Recommendation(BaseModel, frozen=True):
    """Built by code from `TraderReply` (M4-FR-6): `target_weight` clamped,
    `decisive_evidence` filtered to registered IDs, `ticker` filled in."""

    ticker: str
    action: Literal["buy", "no_trade"]
    target_weight: Decimal
    exit_style: ExitStyle
    confidence: float
    decisive_evidence: list[str]
    reasoning: str
    flagged: bool


class RiskVerdict(BaseModel, frozen=True):
    decision: Literal["approve", "shrink", "veto"]
    reason: str
    requested_shares: int | None
    clamped: bool
    flagged: bool


class TradeAttempt(BaseModel, frozen=True):
    """One trader call and what followed (M4-FR-16): Stage A either sizes it
    or blocks it, and Stage B reviews a sized order."""

    recommendation: Recommendation
    sized_order: SizedOrder | None = None
    blocked_reason: str | None = None
    verdict: RiskVerdict | None = None


class RequestState(BaseModel):
    request_id: str
    mode: Literal["live", "backtest"]
    as_of: date
    ticker: str
    rejection: str | None = None
    company_name: str | None = None
    account: Account | None = None
    position: Position | None = None
    prices: PriceSnapshot | None = None
    indicators: Indicators | None = None
    fundamentals: FundamentalsMetrics | None = None
    technical_signal: Signal | None = None
    fundamentals_signal: Signal | None = None
    sentiment_signal: Signal | None = None
    board: SignalsBoard | None = None
    route: Literal["debate", "no_trade"] | None = None
    warnings: list[str] = []
    debate: list[DebateTurn] = []
    attempts: list[TradeAttempt] = []
    sized_order: SizedOrder | None = None  # the final order; set iff outcome == "buy"
    outcome: Literal["buy", "no_trade"] | None = None
    no_trade_reason: str | None = None
    loss_warning: bool | None = None  # set by the backtest runner (M6-FR-12); None: unknown
    report: Report | None = None
