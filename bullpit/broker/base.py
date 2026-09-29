"""Broker interfaces (dev-plan.md D4; M6 specs-plan D-M6-2).

`Broker` is the read side the request check needs. `OrderBroker` adds the
order side the simulated broker implements in M6; the Alpaca write side
joins it in M8, not before (CLAUDE.md: no speculative code).
"""

from __future__ import annotations

from datetime import date
from typing import Protocol

from bullpit.domain import Account, Asset, Position, SizedOrder, Trade


class Broker(Protocol):
    def get_account(self) -> Account: ...
    def get_position(self, symbol: str) -> Position | None: ...
    def get_asset(self, symbol: str) -> Asset | None: ...  # None: unknown symbol


class OrderBroker(Broker, Protocol):
    def submit_bracket_order(
        self, order: SizedOrder, *, client_order_id: str, submitted_on: date
    ) -> Trade: ...
    def get_order(self, client_order_id: str) -> Trade: ...


def client_order_id(request_id: str) -> str:
    """The deterministic order ID for a request, so a retry can't duplicate it
    (architecture Part 14)."""
    return f"bullpit-{request_id}"
