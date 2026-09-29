"""Request check: the graph's first node, code only, before any LLM call
(architecture Part 1; M3-FR-4, FR-5, FR-6). A failed check ends the graph
with a rejection message the owner can act on; a passed check fetches
prices exactly once and hands the point-in-time snapshot to every
analyst through state (D-M3-2).
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast

import pandas as pd

from bullpit.broker.base import Broker
from bullpit.config import Settings
from bullpit.data.prices import get_prices
from bullpit.data.sec import get_sec_facts
from bullpit.domain import Bar
from bullpit.errors import DataUnavailable
from bullpit.state import PriceSnapshot, RequestState


def request_check_node(
    state: RequestState, *, settings: Settings, broker: Broker
) -> dict[str, object]:
    asset = broker.get_asset(state.ticker)
    if asset is None or not asset.tradable or not asset.active:
        return {"rejection": f"{state.ticker} isn't a tradable stock on Alpaca."}

    try:
        get_sec_facts(state.ticker, state.as_of, settings=settings)
    except DataUnavailable:
        # ETFs and unknown tickers are rejected here, not via Alpaca's
        # asset_class (M0 finding A11): SEC has no filings for either --
        # either no CIK at all, or a CIK with no companyfacts (an ETF's
        # 404), so the message is normalised rather than passed through.
        return {"rejection": "No SEC filings found for this ticker. Try a US company stock."}

    try:
        prices = get_prices(
            state.ticker, state.as_of, settings.price_history_sessions, settings=settings
        )
    except DataUnavailable:
        return {
            "rejection": (
                f"{state.ticker} has only 0 trading days of prices up to "
                f"{state.as_of}; at least {settings.min_price_sessions} are needed."
            )
        }

    session_count = len(prices.bars)
    if session_count < settings.min_price_sessions:
        return {
            "rejection": (
                f"{state.ticker} has only {session_count} trading days of prices up to "
                f"{state.as_of}; at least {settings.min_price_sessions} are needed."
            )
        }

    account = broker.get_account()
    position = broker.get_position(state.ticker)

    bars = [
        Bar(
            date=cast(pd.Timestamp, index).date(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for index, row in prices.bars.iterrows()
    ]
    reference_price = Decimal(str(bars[-1].close))
    snapshot = PriceSnapshot(
        source=prices.source, bars=bars, splits=prices.splits, reference_price=reference_price
    )

    return {
        "company_name": asset.name,
        "account": account,
        "position": position,
        "prices": snapshot,
    }
