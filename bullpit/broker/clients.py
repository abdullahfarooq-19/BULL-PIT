"""Factories for Alpaca clients.

These are the *only* place in bullpit that constructs an Alpaca client.
`make_trading_client` always runs the paper-only guard first (bullpit/broker/
safety.py) before touching the network. `make_data_clients` builds read-only
market-data and news clients against Alpaca's fixed data host, which serves
both paper and live accounts and cannot place orders (dev-plan.md D-M0-7) --
so the paper guard doesn't apply to it, and it never receives the trading
base URL.
"""

from __future__ import annotations

from dataclasses import dataclass

from alpaca.data.historical.news import NewsClient
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.trading.client import TradingClient

from bullpit.broker.safety import assert_paper_url
from bullpit.config import Settings


@dataclass(frozen=True)
class DataClients:
    """Read-only Alpaca clients. Neither can place or modify an order."""

    news: NewsClient
    stock_history: StockHistoricalDataClient


def make_trading_client(settings: Settings) -> TradingClient:
    """Build an Alpaca trading client, guaranteed to be paper-only.

    Raises `LiveTradingRefused` (from `assert_paper_url`) before any network
    call if `settings.alpaca_base_url` isn't exactly Alpaca's paper endpoint.
    Also raises `ConfigError` if the API keys aren't configured.
    """
    paper_url = assert_paper_url(settings.alpaca_base_url)

    api_key = settings.require("ALPACA_API_KEY")
    secret_key = settings.require("ALPACA_SECRET_KEY")

    return TradingClient(
        api_key=api_key,
        secret_key=secret_key,
        paper=True,
        url_override=paper_url,
    )


def make_data_clients(settings: Settings) -> DataClients:
    """Build read-only Alpaca market-data and news clients.

    These use the SDK's own fixed data host, not `settings.alpaca_base_url`.
    """
    api_key = settings.require("ALPACA_API_KEY")
    secret_key = settings.require("ALPACA_SECRET_KEY")

    return DataClients(
        news=NewsClient(api_key=api_key, secret_key=secret_key),
        stock_history=StockHistoricalDataClient(api_key=api_key, secret_key=secret_key),
    )
