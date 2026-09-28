"""Daily bars: point-in-time prices and the yfinance/Alpaca parsers
(M1-AC-9, M1-AC-10). Downloads are patched; no network (M1-NFR-1).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

from bullpit.config import Settings
from bullpit.data import prices
from bullpit.errors import DataUnavailable
from tests.conftest import fixture_path


def _yfinance_history(symbol: str) -> tuple[pd.DataFrame, pd.Series]:
    history = pd.read_parquet(fixture_path("prices", f"{symbol}_yf.parquet")).set_index("Date")
    splits_frame = pd.read_parquet(fixture_path("prices", f"{symbol}_yf_splits.parquet"))
    splits = splits_frame.set_index("Date")["Stock Splits"]
    return history, splits


def _patch_yfinance(*symbols_by_ticker: tuple[str, str]) -> Any:
    """Patch `_download_yfinance` to serve recorded fixtures, dispatched by
    the requested ticker: `_patch_yfinance(("AAPL", "aapl"))`.
    """
    fixtures = {ticker: _yfinance_history(stem) for ticker, stem in symbols_by_ticker}

    def fake_download(
        symbol: str, start: date, end: date, timeout: float
    ) -> tuple[pd.DataFrame, pd.Series]:
        history, splits = fixtures[symbol]
        mask = (history.index.date >= start) & (history.index.date <= end)
        return history[mask], splits

    return patch("bullpit.data.prices._download_yfinance", side_effect=fake_download)


def _alpaca_bars_and_splits() -> tuple[pd.DataFrame, list[tuple[date, float]]]:
    bars = pd.read_parquet(fixture_path("prices", "nvda_alpaca.parquet"))
    bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True)
    bars = bars.set_index(["symbol", "timestamp"])
    raw_splits = json.loads(fixture_path("prices", "nvda_alpaca_splits.json").read_text())
    splits = [(date.fromisoformat(s["ex_date"]), s["new_rate"] / s["old_rate"]) for s in raw_splits]
    return bars, splits


class TestPointInTimeSplit:
    """M1-AC-9: NVDA's 2024-06-10 10:1 split, from both sources."""

    def test_yfinance_before_split(self, settings: Settings) -> None:
        with _patch_yfinance(("NVDA", "nvda")):
            history = prices.get_prices("NVDA", date(2024, 6, 7), 5, settings=settings)
        assert history.bars["close"].iloc[-1] == pytest.approx(1208.88, abs=0.01)

    def test_yfinance_after_split(self, settings: Settings) -> None:
        with _patch_yfinance(("NVDA", "nvda")):
            history = prices.get_prices("NVDA", date(2024, 6, 11), 10, settings=settings)
        assert history.bars.loc[pd.Timestamp("2024-06-07"), "close"] == pytest.approx(
            120.888, abs=0.01
        )

    def test_alpaca_after_split_matches_yfinance(self, settings: Settings) -> None:
        bars, splits = _alpaca_bars_and_splits()

        def fake_yfinance_fails(
            symbol: str, start: date, end: date, timeout: float
        ) -> tuple[pd.DataFrame, pd.Series]:
            raise DataUnavailable("forced failure for the test")

        def fake_alpaca(
            symbol: str, start: date, end: date, *, settings: Settings
        ) -> tuple[pd.DataFrame, list[tuple[date, float]]]:
            index_dates = bars.index.get_level_values("timestamp").date
            mask = (index_dates >= start) & (index_dates <= end)
            return bars[mask], splits

        with (
            patch("bullpit.data.prices._download_yfinance", side_effect=fake_yfinance_fails),
            patch("bullpit.data.prices._download_alpaca", side_effect=fake_alpaca),
        ):
            history = prices.get_prices("NVDA", date(2024, 6, 11), 10, settings=settings)

        assert history.source == "alpaca"
        assert history.bars.loc[pd.Timestamp("2024-06-07"), "close"] == pytest.approx(
            120.888, abs=0.01
        )

    def test_dividends_are_not_adjusted(self, settings: Settings) -> None:
        """NVDA's 2024-06-11 ex-dividend date is inside the fixture window: every
        close must equal the recorded Close (undone for splits only), not Adj Close.
        """
        history, _splits = _yfinance_history("nvda")
        with _patch_yfinance(("NVDA", "nvda")):
            result = prices.get_prices("NVDA", date(2024, 6, 21), 19, settings=settings)

        recorded_close_2024_06_11 = history.loc["2024-06-11", "Close"]
        assert result.bars.loc[pd.Timestamp("2024-06-11"), "close"] == pytest.approx(
            recorded_close_2024_06_11, abs=0.01
        )


class TestPricesAndMarketContext:
    """M1-AC-10: one happy-path parse per source shape."""

    def test_get_prices_aapl(self, settings: Settings) -> None:
        with _patch_yfinance(("AAPL", "aapl")):
            history = prices.get_prices("AAPL", date(2024, 7, 31), 20, settings=settings)

        assert history.symbol == "AAPL"
        assert history.source == "yfinance"
        assert list(history.bars.columns) == ["open", "high", "low", "close", "volume"]
        assert len(history.bars) == 20
        assert history.bars.index.max() == pd.Timestamp("2024-07-31")

    def test_get_market_context(self, settings: Settings) -> None:
        with _patch_yfinance(("SPY", "spy"), ("^VIX", "vix")):
            context = prices.get_market_context(date(2024, 7, 31), 10, settings=settings)

        assert context.spy.symbol == "SPY"
        assert context.vix.symbol == "^VIX"
        assert len(context.spy.bars) == 10
        assert len(context.vix.bars) == 10
