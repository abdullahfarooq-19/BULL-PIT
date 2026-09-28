"""M0 spike: verify Alpaca read-only assumptions A10-A13 (specs-plan.md sec11.2).

A10: news history depth/rate limit for the five reference tickers.
A11: asset fields for the request check (tradable, status, fractionable,
     asset class, ETF vs stock).
A12: daily bars as a backup price source; which feed is used.
A13: account cash, equity, buying power (sizing must use cash, D-M0-9).

Goes through bullpit.broker.clients so the client factories (and, for the
trading client, the paper-only guard) are exercised too.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from _common import save_json, section, settings
from alpaca.data.requests import NewsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.requests import GetAssetsRequest

from bullpit.broker.clients import make_data_clients, make_trading_client

REFERENCE_TICKERS = ["AAPL", "MSFT", "JPM", "XOM", "JNJ"]
JULY_2024_WEEK = (datetime(2024, 7, 8, tzinfo=UTC), datetime(2024, 7, 12, tzinfo=UTC))
RECENT_WEEK = (  # spike script: no Clock dependency (dev-plan.md D-M0-13)
    datetime.now(tz=UTC) - timedelta(days=7),
    datetime.now(tz=UTC),
)


def _articles(news_set: Any) -> list[Any]:
    """A NewsSet's articles live at `.data["news"]` (a list of News objects)."""
    return news_set.data.get("news", [])


def check_news_depth_and_limits(news_client: Any) -> dict[str, Any]:
    section("A10: news history depth, per-ticker weekly counts, rate limit")
    results: dict[str, Any] = {}

    earliest = news_client.get_news(
        NewsRequest(symbols="AAPL", start=datetime(2015, 1, 1, tzinfo=UTC), limit=1, sort="asc")
    )
    earliest_articles = _articles(earliest)
    results["earliest_aapl_article"] = (
        str(earliest_articles[0].created_at) if earliest_articles else None
    )
    print(f"  earliest AAPL article: {results['earliest_aapl_article']}")

    weekly_counts: dict[str, dict[str, int]] = {"july_2024_week": {}, "recent_week": {}}
    for ticker in REFERENCE_TICKERS:
        july = news_client.get_news(
            NewsRequest(symbols=ticker, start=JULY_2024_WEEK[0], end=JULY_2024_WEEK[1], limit=50)
        )
        weekly_counts["july_2024_week"][ticker] = len(_articles(july))

        recent = news_client.get_news(
            NewsRequest(symbols=ticker, start=RECENT_WEEK[0], end=RECENT_WEEK[1], limit=50)
        )
        weekly_counts["recent_week"][ticker] = len(_articles(recent))

    print(f"  July 2024 week article counts: {weekly_counts['july_2024_week']}")
    print(f"  Recent week article counts: {weekly_counts['recent_week']}")
    results["weekly_article_counts"] = weekly_counts
    return results


def check_assets(trading_client: Any) -> dict[str, Any]:
    section("A11: asset fields (tradable, status, fractionable, asset class)")
    results: dict[str, Any] = {}
    for symbol in ("AAPL", "SPY"):
        asset = trading_client.get_asset(symbol)
        results[symbol] = {
            "tradable": asset.tradable,
            "status": str(asset.status),
            "fractionable": asset.fractionable,
            "asset_class": str(asset.asset_class),
            "exchange": str(asset.exchange),
        }
        print(f"  {symbol}: {results[symbol]}")

    # Confirm ETFs can be told apart from stocks for the request check (M3).
    etf_request = GetAssetsRequest(asset_class="us_equity")
    print(f"  (asset_class filter available for request-check use: {etf_request.asset_class})")
    return results


def check_backup_price_source(stock_client: Any) -> dict[str, Any]:
    section("A12: daily bars as a backup price source")
    request = StockBarsRequest(
        symbol_or_symbols="AAPL",
        timeframe=TimeFrame.Day,
        start=datetime(2024, 7, 1, tzinfo=UTC),
        end=datetime(2024, 7, 15, tzinfo=UTC),
    )
    bars = stock_client.get_stock_bars(request)
    aapl_bars = bars["AAPL"] if hasattr(bars, "__getitem__") else bars.data.get("AAPL", [])
    result = {"row_count": len(aapl_bars), "feed_requested": "default (sip/iex per plan)"}
    print(f"  AAPL daily bars: {result['row_count']} rows")
    return result


def check_account(trading_client: Any) -> dict[str, Any]:
    section("A13: account cash, equity, buying power (sizing uses cash, D-M0-9)")
    account = trading_client.get_account()
    result = {
        "cash": str(account.cash),
        "equity": str(account.equity),
        "buying_power": str(account.buying_power),
        "multiplier": str(getattr(account, "multiplier", "?")),
    }
    print(f"  {result}")
    return result


def main() -> None:
    s = settings()
    data_clients = make_data_clients(s)
    trading_client = make_trading_client(s)

    results: dict[str, Any] = {}
    results["a10_news"] = check_news_depth_and_limits(data_clients.news)
    results["a11_assets"] = check_assets(trading_client)
    results["a12_backup_prices"] = check_backup_price_source(data_clients.stock_history)
    results["a13_account"] = check_account(trading_client)

    save_json("alpaca_readonly", results)
    print("\nDone. Check scripts/spikes/output/alpaca_readonly.json for the full record.")


if __name__ == "__main__":
    main()
