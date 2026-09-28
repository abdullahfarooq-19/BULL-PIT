"""Read-only Alpaca implementation of the `Broker` protocol (dev-plan.md D4).

Every method goes through `make_trading_client`, so the paper-only guard
(bullpit/broker/safety.py) always runs before any network call. A 404
(unknown symbol, or no open position) becomes `None`; any other Alpaca
error becomes `BrokerRejected`, so no SDK exception leaves this module
(M3 specs-plan sec12).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetStatus
from alpaca.trading.models import Asset as AlpacaAsset
from alpaca.trading.models import Position as AlpacaPosition
from alpaca.trading.models import TradeAccount

from bullpit.broker.clients import make_trading_client
from bullpit.config import Settings
from bullpit.domain import Account, Asset, Position
from bullpit.errors import BrokerRejected


def _is_not_found(exc: APIError) -> bool:
    return bool(exc.status_code == 404)


@dataclass(frozen=True)
class AlpacaBroker:
    """Read-only broker backed by an Alpaca paper trading client."""

    client: TradingClient

    def get_account(self) -> Account:
        try:
            account = cast(TradeAccount, self.client.get_account())
        except APIError as exc:
            raise BrokerRejected(f"get_account failed: {exc}") from exc
        return Account(cash=Decimal(str(account.cash)), equity=Decimal(str(account.equity)))

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


def make_alpaca_broker(settings: Settings) -> AlpacaBroker:
    return AlpacaBroker(client=make_trading_client(settings))
