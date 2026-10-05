"""Alpaca implementation of the broker interfaces: the read side (dev-plan.md D4)
and, from M8, bracket orders and the reads the fill check needs (M8 specs-plan
sec3, sec11).

Every method goes through `make_trading_client`, so the paper-only guard
(bullpit/broker/safety.py) always runs before any network call. A 404
(unknown symbol, no open position, unknown order) becomes `None`; any other
Alpaca error becomes `BrokerRejected`, so no SDK exception leaves this module
(M3 specs-plan sec12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any, cast

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import (
    AssetStatus,
    OrderClass,
    OrderSide,
    OrderStatus,
    OrderType,
    QueryOrderStatus,
    TimeInForce,
)
from alpaca.trading.models import Asset as AlpacaAsset
from alpaca.trading.models import Clock as AlpacaClock
from alpaca.trading.models import Order as AlpacaOrder
from alpaca.trading.models import PortfolioHistory, TradeAccount
from alpaca.trading.models import Position as AlpacaPosition
from alpaca.trading.requests import (
    GetOrdersRequest,
    GetPortfolioHistoryRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)
from pydantic import BaseModel
from requests import RequestException

from bullpit.broker.clients import make_trading_client
from bullpit.config import Settings
from bullpit.data.calendar import NEW_YORK
from bullpit.domain import Account, Asset, Position, SizedOrder, Trade
from bullpit.domain import OrderType as EntryType
from bullpit.errors import BrokerRejected
from bullpit.risk.sizing import round_cent

_ACTIVE_LEG = {OrderStatus.NEW, OrderStatus.ACCEPTED, OrderStatus.HELD, OrderStatus.PENDING_NEW}
_ENTRY_NOT_FILLED = {OrderStatus.CANCELED, OrderStatus.EXPIRED, OrderStatus.REJECTED}
_DUPLICATE_ID_MESSAGE = "client_order_id must be unique"
_MAX_ORDERS_PER_LIST = 500  # Alpaca's page limit for the orders list


def _is_not_found(exc: APIError) -> bool:
    return bool(exc.status_code == 404)


def _outcome_unknown(exc: APIError) -> bool:
    """A duplicate `client_order_id` or a server error: Alpaca may already hold the order."""
    return _DUPLICATE_ID_MESSAGE in str(exc) or bool(exc.status_code and exc.status_code >= 500)


def _ny_date(moment: datetime) -> date:
    return moment.astimezone(NEW_YORK).date()


def _price(value: str | float | None) -> Decimal:
    """An Alpaca price string or float as a `Decimal`, rounded to the cent (M8-NFR-3)."""
    return round_cent(Decimal(str(value)))


def _filled(order: AlpacaOrder) -> int:
    """Whole shares filled so far (Alpaca sends the quantity as a string)."""
    return int(Decimal(str(order.filled_qty or 0)))


class LiveOrder(BaseModel, frozen=True):
    """An Alpaca bracket order read as a `Trade`, plus what the fill check needs."""

    trade: Trade
    exits_active: bool  # a leg is new, accepted, held or pending
    exits_cancelled_at: datetime | None  # both legs cancelled, none filled: the later time
    partial: bool  # the entry or a leg is partially filled


def live_order(order: AlpacaOrder, *, submitted_on: date, reference_price: Decimal) -> LiveOrder:
    """Map an Alpaca bracket order and its legs to a `Trade` (M8 specs-plan sec11.4).

    Pure. `reference_price` is the report's, which Alpaca doesn't hold.
    """
    legs = order.legs or []
    take_profit_leg = next((leg for leg in legs if leg.type == OrderType.LIMIT), None)
    stop_leg = next((leg for leg in legs if leg.type == OrderType.STOP), None)
    if take_profit_leg is None or stop_leg is None:
        raise BrokerRejected(f"order {order.client_order_id} has no stop and take-profit legs")

    filled_qty = _filled(order)
    entry_type: EntryType = "limit" if order.type == OrderType.LIMIT else "market"
    trade = Trade(
        client_order_id=order.client_order_id,
        ticker=order.symbol,
        submitted_on=submitted_on,
        shares=filled_qty or int(Decimal(str(order.qty))),
        reference_price=reference_price,
        stop_loss=_price(stop_leg.stop_price),
        take_profit=_price(take_profit_leg.limit_price),
        status="pending",
        order_id=str(order.id),
        stop_order_id=str(stop_leg.id),
        take_profit_order_id=str(take_profit_leg.id),
        order_type=entry_type,
        limit_price=_price(order.limit_price) if entry_type == "limit" else None,
    )

    if order.status in _ENTRY_NOT_FILLED and filled_qty == 0:
        trade = trade.model_copy(
            update={"status": "cancelled", "cancel_reason": f"entry {order.status.value}"}
        )
    elif order.status == OrderStatus.FILLED and order.filled_at is not None:
        trade = trade.model_copy(
            update={
                "status": "open",
                "entry_date": _ny_date(order.filled_at),
                "entry_price": _price(order.filled_avg_price),
            }
        )
        for leg, reason in ((stop_leg, "stop"), (take_profit_leg, "target")):
            if leg.status == OrderStatus.FILLED and leg.filled_at is not None:
                trade = trade.model_copy(
                    update={
                        "status": "closed",
                        "exit_date": _ny_date(leg.filled_at),
                        "exit_price": _price(leg.filled_avg_price),
                        "exit_reason": reason,
                    }
                )

    all_cancelled = all(leg.status == OrderStatus.CANCELED and _filled(leg) == 0 for leg in legs)
    cancelled_at = max((leg.canceled_at for leg in legs if leg.canceled_at), default=None)
    return LiveOrder(
        trade=trade,
        exits_active=any(leg.status in _ACTIVE_LEG for leg in legs),
        exits_cancelled_at=cancelled_at if all_cancelled else None,
        partial=(filled_qty > 0 and order.status != OrderStatus.FILLED)
        or any(leg.status == OrderStatus.PARTIALLY_FILLED for leg in legs),
    )


class AccountSummary(BaseModel, frozen=True):
    """What the dashboard's account card shows (M11.2-FR-1, FR-2): Alpaca's own
    figures, so the balance includes positions Bull Pit didn't open."""

    account_number: str
    status: str
    equity: Decimal
    cash: Decimal
    last_equity: Decimal  # equity at the previous close, for the day change


class MarketClock(BaseModel, frozen=True):
    """Alpaca's market clock (M11.3-FR-12): both times are timezone-aware."""

    is_open: bool
    next_open: datetime
    next_close: datetime


@dataclass(frozen=True)
class AlpacaBroker:
    """Broker backed by an Alpaca paper trading client."""

    client: TradingClient

    def get_account(self) -> Account:
        try:
            account = cast(TradeAccount, self.client.get_account())
        except APIError as exc:
            raise BrokerRejected(f"get_account failed: {exc}") from exc
        return Account(cash=Decimal(str(account.cash)), equity=Decimal(str(account.equity)))

    def get_account_summary(self) -> AccountSummary:
        """The account's number, status, equity, cash and last close's equity."""
        try:
            account = cast(TradeAccount, self.client.get_account())
        except APIError as exc:
            raise BrokerRejected(f"get_account failed: {exc}") from exc
        return AccountSummary(
            account_number=account.account_number,
            status=account.status.value,
            equity=Decimal(str(account.equity)),
            cash=Decimal(str(account.cash)),
            last_equity=Decimal(str(account.last_equity)),
        )

    def last_prices(self) -> dict[str, Decimal]:
        """The current price of every open position, by symbol, in one call
        (M11.3-FR-1)."""
        try:
            positions = cast(list[AlpacaPosition], self.client.get_all_positions())
        except (APIError, RequestException) as exc:
            raise BrokerRejected(f"list positions failed: {exc}") from exc
        return {
            position.symbol: Decimal(str(position.current_price))
            for position in positions
            if position.current_price is not None
        }

    def market_clock(self) -> MarketClock:
        """Whether the US market is open, and when it next opens and closes."""
        try:
            clock = cast(AlpacaClock, self.client.get_clock())
        except (APIError, RequestException) as exc:
            raise BrokerRejected(f"get_clock failed: {exc}") from exc
        return MarketClock(
            is_open=clock.is_open, next_open=clock.next_open, next_close=clock.next_close
        )

    def get_position(self, symbol: str) -> Position | None:
        try:
            position = cast(AlpacaPosition, self.client.get_open_position(symbol))
        except APIError as exc:
            if _is_not_found(exc):
                return None
            raise BrokerRejected(f"get_position({symbol}) failed: {exc}") from exc
        return Position(
            symbol=position.symbol,
            qty=int(Decimal(str(position.qty))),
            market_value=Decimal(str(position.market_value)),
        )

    def get_asset(self, symbol: str) -> Asset | None:
        try:
            asset = cast(AlpacaAsset, self.client.get_asset(symbol))
        except APIError as exc:
            if _is_not_found(exc):
                return None
            raise BrokerRejected(f"get_asset({symbol}) failed: {exc}") from exc
        return Asset(
            symbol=asset.symbol,
            name=asset.name,
            tradable=asset.tradable,
            active=asset.status == AssetStatus.ACTIVE,
        )

    def submit_bracket_order(
        self,
        order: SizedOrder,
        *,
        client_order_id: str,
        submitted_on: date,
        limit_price: Decimal | None = None,
    ) -> Trade:
        """One buy of `order.shares` whole shares with its stop-loss and
        take-profit legs, GTC (ADR-0002): a market entry, or with `limit_price` a
        limit entry that waits for that price (ADR-0008). Idempotent (M8-FR-2): a
        duplicate ID, or a failure that leaves it unknown whether Alpaca took the
        order, looks the order up by `client_order_id`; only a missing order is a
        rejection."""
        legs: dict[str, Any] = {
            "symbol": order.ticker,
            "qty": order.shares,
            "side": OrderSide.BUY,
            "time_in_force": TimeInForce.GTC,
            "order_class": OrderClass.BRACKET,
            "client_order_id": client_order_id,
            "take_profit": TakeProfitRequest(limit_price=float(order.take_profit)),
            "stop_loss": StopLossRequest(stop_price=float(order.stop_loss)),
        }
        request = (
            MarketOrderRequest(**legs)
            if limit_price is None
            else LimitOrderRequest(limit_price=float(limit_price), **legs)
        )
        try:
            placed = cast(AlpacaOrder, self.client.submit_order(request))
        except (APIError, RequestException) as exc:
            if isinstance(exc, APIError) and not _outcome_unknown(exc):
                raise BrokerRejected(f"Alpaca rejected the order: {exc}") from exc
            found = self.find_order(
                client_order_id, submitted_on=submitted_on, reference_price=order.reference_price
            )
            if found is None:
                raise BrokerRejected(f"Alpaca rejected the order: {exc}") from exc
            return found.trade
        return live_order(
            placed, submitted_on=submitted_on, reference_price=order.reference_price
        ).trade

    def cancel_order(self, order_id: str) -> None:
        """Asks Alpaca to cancel an order and its legs. Alpaca answers without an
        error for an order that is already filled or cancelled (checked 2026-10-05,
        ADR-0008), so the caller re-reads the order to learn what happened. An
        unknown order is a 404."""
        try:
            self.client.cancel_order_by_id(order_id)
        except (APIError, RequestException) as exc:
            raise BrokerRejected(f"cancel_order({order_id}) failed: {exc}") from exc

    def find_order(
        self, client_order_id: str, *, submitted_on: date, reference_price: Decimal
    ) -> LiveOrder | None:
        """The order with its legs, or `None` if Alpaca has no such order."""
        try:
            order = cast(AlpacaOrder, self.client.get_order_by_client_id(client_order_id))
        except APIError as exc:
            if _is_not_found(exc):
                return None
            raise BrokerRejected(f"get_order({client_order_id}) failed: {exc}") from exc
        except RequestException as exc:
            raise BrokerRejected(f"get_order({client_order_id}) failed: {exc}") from exc
        return live_order(order, submitted_on=submitted_on, reference_price=reference_price)

    def get_live_order(self, trade: Trade) -> LiveOrder:
        """The current state of a trade already in the journal."""
        found = self.find_order(
            trade.client_order_id,
            submitted_on=trade.submitted_on,
            reference_price=trade.reference_price,
        )
        if found is None:
            raise BrokerRejected(f"unknown client_order_id {trade.client_order_id!r}")
        return found

    def first_sell_fill(self, symbol: str, after: datetime) -> tuple[date, Decimal] | None:
        """Date and price of the first filled sell of `symbol` at or after `after`
        that isn't a bracket leg (a manual close, M8-FR-14). Listed nested, so
        legs sit inside their parent orders and never appear as sells."""
        try:
            orders = cast(
                list[AlpacaOrder],
                self.client.get_orders(
                    GetOrdersRequest(
                        status=QueryOrderStatus.CLOSED,
                        symbols=[symbol],
                        side=OrderSide.SELL,
                        nested=True,
                        limit=_MAX_ORDERS_PER_LIST,
                    )
                ),
            )
        except (APIError, RequestException) as exc:
            raise BrokerRejected(f"list orders for {symbol} failed: {exc}") from exc
        fills = [
            (o.filled_at, o)
            for o in orders
            if o.status == OrderStatus.FILLED and o.filled_at is not None and o.filled_at >= after
        ]
        if not fills:
            return None
        filled_at, first = min(fills, key=lambda pair: pair[0])
        return _ny_date(filled_at), _price(first.filled_avg_price)

    def equity_history(self, start: date) -> list[tuple[date, Decimal]]:
        """Daily account equity from `start`, one point per session, oldest first.
        Alpaca stamps each session at 00:00 UTC of the next day, so the New York
        date of the stamp is the session; days before the account existed report
        0 and are dropped."""
        try:
            history = cast(
                PortfolioHistory,
                self.client.get_portfolio_history(
                    GetPortfolioHistoryRequest(
                        start=datetime.combine(start, time.min, tzinfo=UTC), timeframe="1D"
                    )
                ),
            )
        except (APIError, RequestException) as exc:
            raise BrokerRejected(f"portfolio history failed: {exc}") from exc
        return [
            (_ny_date(datetime.fromtimestamp(stamp, UTC)), round_cent(Decimal(str(equity))))
            for stamp, equity in zip(history.timestamp, history.equity, strict=True)
            if equity
        ]


def make_alpaca_broker(settings: Settings) -> AlpacaBroker:
    return AlpacaBroker(client=make_trading_client(settings))
