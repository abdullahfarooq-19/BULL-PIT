"""The shared graph state (architecture Part 0; M3 specs-plan sec5).

`RequestState` holds only M3's fields; M4-M8 add theirs as they're built
(D-M3-4) -- CLAUDE.md forbids placeholder code for types that don't exist
yet. Every field crossing a graph node is typed (dev-plan.md sec2.2).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from bullpit.domain import Account, Position
from bullpit.llm.schemas import Evidence, Signal
from bullpit.tools.fundamentals import FundamentalsMetrics
from bullpit.tools.indicators import Indicators


class Bar(BaseModel, frozen=True):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


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
