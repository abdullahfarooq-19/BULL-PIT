"""Non-LLM domain types shared across the request lifecycle (dev-plan.md
sec2.3). These are read-only snapshots a `Broker` hands back, never written
to by the graph (M3 specs-plan sec5).

Money fields use `Decimal` (dev-plan.md sec2.2: money handling).
"""

from __future__ import annotations

from decimal import Decimal

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
