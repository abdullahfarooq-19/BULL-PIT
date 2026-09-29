"""In-memory brokers, for tests that need no network (dev-plan.md C1).

Pre-load `FakeBroker` with the assets, positions and account a test wants to
see; anything not pre-loaded looks unknown (`get_asset`/`get_position` return
`None`), exactly like a real 404. `FakeOrderBroker` adds bracket orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from bullpit.broker.base import Broker
from bullpit.domain import Account, Asset, Position, SizedOrder, Trade


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


@dataclass
class FakeOrderBroker(FakeBroker):
    """Records the orders it places. Like `AlpacaBroker`, a reused
    `client_order_id` returns the existing order instead of placing a second."""

    orders: dict[str, Trade] = field(default_factory=dict)

    @property
    def submitted(self) -> list[Trade]:
        return list(self.orders.values())

    def submit_bracket_order(
        self, order: SizedOrder, *, client_order_id: str, submitted_on: date
    ) -> Trade:
        if client_order_id not in self.orders:
            self.orders[client_order_id] = Trade(
                client_order_id=client_order_id,
                ticker=order.ticker,
                submitted_on=submitted_on,
                shares=order.shares,
                reference_price=order.reference_price,
                stop_loss=order.stop_loss,
                take_profit=order.take_profit,
                status="pending",
                order_id=f"order-{client_order_id}",
                stop_order_id=f"stop-{client_order_id}",
                take_profit_order_id=f"target-{client_order_id}",
            )
        return self.orders[client_order_id]
