"""Daily bars: yfinance, Alpaca backup, point-in-time prices (ADR-0003;
dev-plan.md Part 2). `get_market_context` lives here too (D-M1-6): it's
two calls to the same path, not a module of its own.

Point-in-time prices (M1-FR-9): the cache stores raw, unadjusted prices
plus each session's `split_ratio`. `point_in_time` then divides every
bar's prices (and multiplies its volume) by the product of split ratios
with an ex-date strictly after that bar and on or before `as_of`, so a
stored history never changes after the fact and a query never sees a
split that hadn't happened yet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, cast

import pandas as pd
import yfinance as yf
from alpaca.data.enums import Adjustment, CorporateActionsType, DataFeed
from alpaca.data.models.bars import BarSet
from alpaca.data.models.corporate_actions import CorporateActionsSet, ForwardSplit, ReverseSplit
from alpaca.data.requests import CorporateActionsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from bullpit.broker.clients import make_data_clients
from bullpit.config import Settings
from bullpit.data import cache
from bullpit.data.calendar import NEW_YORK, lookback_start, session_close
from bullpit.errors import DataUnavailable
from bullpit.logging import get_logger

logger = get_logger(__name__)

_RAW_COLUMNS = ["date", "open", "high", "low", "close", "volume", "split_ratio", "source"]


@dataclass(frozen=True)
class PriceHistory:
    symbol: str
    as_of: date
    source: Literal["yfinance", "alpaca"]
    bars: pd.DataFrame
    splits: list[tuple[date, float]]  # (ex-date, ratio new/old); ex-date <= as_of, in window


@dataclass(frozen=True)
class MarketContextData:
    spy: PriceHistory
    vix: PriceHistory


def _yahoo_symbol(symbol: str) -> str:
    return symbol.replace(".", "-")


def _download_yfinance(
    symbol: str, start: date, end: date, timeout: float
) -> tuple[pd.DataFrame, pd.Series]:
    """Raw history and the FULL split list (ADR-0003: only this function
    reads splits later than the request; they never leave it."""
    try:
        ticker = yf.Ticker(_yahoo_symbol(symbol))
        history = ticker.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=False,
            actions=True,
            timeout=timeout,
        )
        splits = ticker.splits
    except Exception as exc:
        raise DataUnavailable(f"yfinance request failed for {symbol}") from exc
    return history, splits


def _raw_from_yfinance(history: pd.DataFrame, splits: pd.Series) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame(columns=_RAW_COLUMNS)

    dates = cast(pd.DatetimeIndex, history.index).tz_localize(None).normalize()
    if splits.empty:
        split_by_date: pd.Series = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    else:
        split_dates = cast(pd.DatetimeIndex, splits.index).tz_localize(None).normalize()
        split_by_date = pd.Series(splits.to_numpy(dtype=float), index=split_dates)

    frame = pd.DataFrame(
        {
            "date": dates,
            "open": history["Open"].to_numpy(dtype=float),
            "high": history["High"].to_numpy(dtype=float),
            "low": history["Low"].to_numpy(dtype=float),
            "close": history["Close"].to_numpy(dtype=float),
            "volume": history["Volume"].to_numpy(dtype=float),
        }
    )

    def factor_after(day: pd.Timestamp) -> float:
        later = split_by_date[split_by_date.index > day]
        return float(cast(float, later.prod())) if not later.empty else 1.0

    factors = frame["date"].map(factor_after)
    frame[["open", "high", "low", "close"]] = frame[["open", "high", "low", "close"]].mul(
        factors, axis=0
    )
    frame["volume"] = frame["volume"] / factors
    frame["split_ratio"] = frame["date"].map(lambda day: float(split_by_date.get(day, 1.0)))
    frame["source"] = "yfinance"
    return frame[_RAW_COLUMNS]


def _download_alpaca(
    symbol: str, start: date, end: date, *, settings: Settings
) -> tuple[pd.DataFrame, list[tuple[date, float]]]:
    try:
        clients = make_data_clients(settings)
        bars_request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, datetime.min.time(), tzinfo=NEW_YORK),
            end=session_close(end),
            adjustment=Adjustment.RAW,
            feed=DataFeed.SIP,
        )
        bars = cast(BarSet, clients.stock_history.get_stock_bars(bars_request)).df

        actions_request = CorporateActionsRequest(
            symbols=[symbol],
            start=start,
            end=end,
            types=[CorporateActionsType.FORWARD_SPLIT, CorporateActionsType.REVERSE_SPLIT],
        )
        actions = cast(
            CorporateActionsSet, clients.corporate_actions.get_corporate_actions(actions_request)
        )
    except Exception as exc:
        raise DataUnavailable(f"Alpaca request failed for {symbol}") from exc

    splits = [
        (event.ex_date, event.new_rate / event.old_rate)
        for kind in ("forward_splits", "reverse_splits")
        for event in cast(list[ForwardSplit | ReverseSplit], actions.data.get(kind, []))
    ]
    return bars, splits


def _raw_from_alpaca(bars: pd.DataFrame, splits: list[tuple[date, float]]) -> pd.DataFrame:
    if bars.empty:
        return pd.DataFrame(columns=_RAW_COLUMNS)

    frame = bars.reset_index()
    local_time = frame["timestamp"].dt.tz_convert(NEW_YORK)
    frame["date"] = local_time.dt.normalize().dt.tz_localize(None)
    split_by_date = dict(splits)
    frame["split_ratio"] = frame["date"].dt.date.map(lambda day: split_by_date.get(day, 1.0))
    frame["source"] = "alpaca"
    frame["volume"] = frame["volume"].astype(float)
    return frame[_RAW_COLUMNS]


def point_in_time(raw: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """Prices as they were quoted at `as_of` (M1-FR-9)."""
    if raw.empty:
        return raw
    subset = raw[raw["date"] <= pd.Timestamp(as_of)].sort_values("date").reset_index(drop=True)
    if subset.empty:
        return subset

    factor = subset["split_ratio"][::-1].cumprod()[::-1].shift(-1, fill_value=1.0)
    adjusted = subset.copy()
    price_columns = ["open", "high", "low", "close"]
    adjusted[price_columns] = adjusted[price_columns].div(factor, axis=0)
    adjusted["volume"] = adjusted["volume"] * factor
    return adjusted


def _fetch(symbol: str, settings: Settings) -> Callable[[date, date], pd.DataFrame]:
    def fetch(a: date, b: date) -> pd.DataFrame:
        try:
            history, splits = _download_yfinance(symbol, a, b, settings.http_timeout_seconds)
            raw = _raw_from_yfinance(history, splits)
        except DataUnavailable:
            raw = pd.DataFrame(columns=_RAW_COLUMNS)

        if not raw.empty:
            return raw
        if symbol.startswith("^"):
            raise DataUnavailable(f"No yfinance data for index symbol {symbol}")

        bars, alpaca_splits = _download_alpaca(symbol, a, b, settings=settings)
        return _raw_from_alpaca(bars, alpaca_splits)

    return fetch


def get_prices(symbol: str, as_of: date, sessions: int, *, settings: Settings) -> PriceHistory:
    start = lookback_start(as_of, sessions)

    raw = cache.read_through(
        "prices",
        symbol,
        start,
        as_of,
        fetch=_fetch(symbol, settings),
        key=["date"],
        date_column="date",
        settings=settings,
    )
    raw = raw[raw["date"] >= pd.Timestamp(start)]
    if raw.empty:
        raise DataUnavailable(f"No price data for {symbol} through {as_of}")

    adjusted = point_in_time(raw, as_of)
    source: Literal["yfinance", "alpaca"] = (
        "alpaca" if bool((adjusted["source"] == "alpaca").any()) else "yfinance"
    )
    split_rows = adjusted.loc[adjusted["split_ratio"] != 1.0, ["date", "split_ratio"]]
    splits = [
        (cast(pd.Timestamp, ts).date(), float(ratio))
        for ts, ratio in zip(split_rows["date"], split_rows["split_ratio"], strict=True)
    ]
    bars = adjusted.set_index("date")[["open", "high", "low", "close", "volume"]]
    logger.info("price_source", symbol=symbol, as_of=str(as_of), source=source)
    return PriceHistory(symbol=symbol, as_of=as_of, source=source, bars=bars, splits=splits)


def get_market_context(as_of: date, sessions: int, *, settings: Settings) -> MarketContextData:
    return MarketContextData(
        spy=get_prices("SPY", as_of, sessions, settings=settings),
        vix=get_prices("^VIX", as_of, sessions, settings=settings),
    )
