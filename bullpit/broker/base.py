"""Read-only broker interface (dev-plan.md D4).

The request check (M3) only reads the account, a position and an asset's
tradability. Order placement is out of scope until M6 (simulated broker)
and M8 (Alpaca write side); this protocol grows those methods there, not
here (CLAUDE.md: no speculative code).
"""

from __future__ import annotations

from typing import Protocol

from bullpit.domain import Account, Asset, Position


class Broker(Protocol):
    def get_account(self) -> Account: ...
    def get_position(self, symbol: str) -> Position | None: ...
    def get_asset(self, symbol: str) -> Asset | None: ...  # None: unknown symbol
