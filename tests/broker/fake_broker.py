"""An in-memory `Broker`, for tests that need no network (dev-plan.md C1).

Pre-load it with the assets, positions and account a test wants to see;
anything not pre-loaded looks unknown (`get_asset`/`get_position` return
`None`), exactly like a real 404.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bullpit.broker.base import Broker
from bullpit.domain import Account, Asset, Position


@dataclass
class FakeBroker(Broker):
    account: Account
    assets: dict[str, Asset] = field(default_factory=dict)
    positions: dict[str, Position] = field(default_factory=dict)

    def get_account(self) -> Account:
        return self.account

    def get_position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def get_asset(self, symbol: str) -> Asset | None:
        return self.assets.get(symbol)
