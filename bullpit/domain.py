"""Non-LLM domain types shared across the request lifecycle (dev-plan.md
sec2.3). These are read-only snapshots a `Broker` hands back, never written
to by the graph (M3 specs-plan sec5).

Money fields use `Decimal` (dev-plan.md sec2.2: money handling).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class Bar(BaseModel, frozen=True):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


class Account(BaseModel, frozen=True):
    cash: Decimal
    equity: Decimal


class Position(BaseModel, frozen=True):
    symbol: str
    qty: int
    market_value: Decimal


class Asset(BaseModel, frozen=True):
    symbol: str
    name: str
    tradable: bool
    active: bool


# --- Risk manager (M4; architecture Part 11) --------------------------------

ExitStyle = Literal["tight", "normal", "wide"]
SizeLimit = Literal["target", "risk", "cap", "cash"]


class SizedOrder(BaseModel, frozen=True):
    """Stage A's sized order (M4-FR-7, FR-8): shares, exits, and which of the
    four limits set the size, so the report can show all four (M5)."""

    ticker: str
    shares: int
    reference_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    exit_style: ExitStyle
    cost: Decimal
    max_loss: Decimal
    max_gain: Decimal
    limit: SizeLimit
    limit_shares: dict[SizeLimit, int]


# --- Execution (M6; architecture Part 14) -----------------------------------

TradeStatus = Literal["pending", "open", "closed", "cancelled", "open_at_end"]
ExitReason = Literal["stop", "target", "window_end"]  # M8 adds "manual"


class Trade(BaseModel, frozen=True):
    """One bracket order's life in a broker (M6 specs-plan sec5)."""

    client_order_id: str
    ticker: str
    submitted_on: date
    shares: int  # after any downsizing at the open
    reference_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    status: TradeStatus
    entry_date: date | None = None
    entry_price: Decimal | None = None  # open x (1 + slippage), to the cent
    exit_date: date | None = None
    exit_price: Decimal | None = None  # the last close for open_at_end
    exit_reason: ExitReason | None = None
    cancel_reason: str | None = None

    @property
    def pnl(self) -> Decimal | None:
        """(exit - entry) x shares, once closed or marked at the window end."""
        if self.entry_price is None or self.exit_price is None:
            return None
        return (self.exit_price - self.entry_price) * self.shares
