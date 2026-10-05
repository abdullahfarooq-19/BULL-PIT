"""In-memory brokers, for tests that need no network (dev-plan.md C1).

Pre-load `FakeBroker` with the assets, positions and account a test wants to
see; anything not pre-loaded looks unknown (`get_asset`/`get_position` return
`None`), exactly like a real 404. `FakeOrderBroker` adds bracket orders and the
reads the fill check and expiry use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from bullpit.broker.alpaca import LiveOrder
from bullpit.broker.base import Broker
from bullpit.domain import Account, Asset, Position, SizedOrder, Trade
from bullpit.errors import BrokerRejected


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
    `client_order_id` returns the existing order instead of placing a second.

    A test scripts what Alpaca later reports by putting a `LiveOrder` in
    `live_orders`, closing sells in `sell_fills` and the account's daily equity
    in `history`.
    """

    orders: dict[str, Trade] = field(default_factory=dict)
    live_orders: dict[str, LiveOrder] = field(default_factory=dict)
    sell_fills: list[tuple[datetime, date, Decimal]] = field(default_factory=list)
    history: list[tuple[date, Decimal]] = field(default_factory=list)
    cancelled: list[str] = field(default_factory=list)

    @property
    def submitted(self) -> list[Trade]:
        return list(self.orders.values())

    def submit_bracket_order(
        self,
        order: SizedOrder,
        *,
        client_order_id: str,
        submitted_on: date,
        limit_price: Decimal | None = None,
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
                order_type="market" if limit_price is None else "limit",
                limit_price=limit_price,
            )
        return self.orders[client_order_id]

    def cancel_order(self, order_id: str) -> None:
        """Like Alpaca, a no-op for an order that is no longer waiting: a test
        scripts a fill in `live_orders` before the cancel to make them cross."""
        self.cancelled.append(order_id)
        for client_order_id, trade in self.orders.items():
            if trade.order_id == order_id and trade.status == "pending":
                self.orders[client_order_id] = trade.model_copy(
                    update={"status": "cancelled", "cancel_reason": "entry canceled"}
                )

    def find_order(
        self, client_order_id: str, *, submitted_on: date, reference_price: Decimal
    ) -> LiveOrder | None:
        if client_order_id in self.live_orders:
            return self.live_orders[client_order_id]
        if client_order_id in self.orders:
            return LiveOrder(
                trade=self.orders[client_order_id],
                exits_active=self.orders[client_order_id].status != "cancelled",
                exits_cancelled_at=None,
                partial=False,
            )
        return None

    def get_live_order(self, trade: Trade) -> LiveOrder:
        found = self.find_order(
            trade.client_order_id,
            submitted_on=trade.submitted_on,
            reference_price=trade.reference_price,
        )
        if found is None:
            raise BrokerRejected(f"unknown client_order_id {trade.client_order_id!r}")
        return found

    def first_sell_fill(self, symbol: str, after: datetime) -> tuple[date, Decimal] | None:
        fills = [(at, day, price) for at, day, price in self.sell_fills if at >= after]
        return None if not fills else min(fills)[1:]

    def equity_history(self, start: date) -> list[tuple[date, Decimal]]:
        return [point for point in self.history if point[0] >= start]
