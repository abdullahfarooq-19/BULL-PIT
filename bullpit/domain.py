"""Non-LLM domain types shared across the request lifecycle (dev-plan.md
sec2.3). These are read-only snapshots a `Broker` hands back, never written
to by the graph (M3 specs-plan sec5).

Money fields use `Decimal` (dev-plan.md sec2.2: money handling).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


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
