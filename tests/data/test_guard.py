"""The date guard (M1-FR-4 to FR-7).

`test_drop_after` is the unit half of M1-AC-2. The rest of this file
covers M1-AC-1 (no tool ever returns a row after the cutoff, even from a
source or a cache file that ignores the request filter) and the other
half of M1-AC-2 (a row injected straight into a cache file is dropped
and logged on the next read).
"""

from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from structlog.testing import capture_logs

from bullpit.config import Settings
from bullpit.data import cache, news, prices, sec
from bullpit.data.calendar import is_session, session_close
from bullpit.data.guard import drop_after
from bullpit.errors import LookaheadViolation


def _date_frame(dates: list[date]) -> pd.DataFrame:
    return pd.DataFrame({"date": pd.to_datetime(dates)})


class TestDropAfter:
    def test_later_row_is_dropped_and_logged_as_warning(self) -> None:
        frame = _date_frame([date(2024, 6, 5), date(2024, 6, 7), date(2024, 6, 10)])
        with capture_logs() as logs:
            result = drop_after(
                frame,
                "date",
                date(2024, 6, 7),
                later_rows_expected=False,
                dataset="prices",
                symbol="AAPL",
            )

        assert len(result) == 2
        assert result["date"].max() == pd.Timestamp(date(2024, 6, 7))
        dropped = [log for log in logs if log["event"] == "lookahead_row_dropped"]
        assert len(dropped) == 1
        assert dropped[0]["log_level"] == "warning"
        assert dropped[0]["dataset"] == "prices"
        assert dropped[0]["symbol"] == "AAPL"
        assert dropped[0]["as_of"] == "2024-06-07"

    def test_expected_later_row_is_logged_at_debug(self) -> None:
        frame = _date_frame([date(2024, 6, 10)])
        with capture_logs() as logs:
            result = drop_after(
                frame,
                "date",
                date(2024, 6, 7),
                later_rows_expected=True,
                dataset="sec_facts",
                symbol="AAPL",
            )

        assert len(result) == 0
        dropped = [log for log in logs if log["event"] == "lookahead_row_dropped"]
        assert dropped[0]["log_level"] == "debug"

    def test_no_rows_dropped_when_nothing_is_later(self) -> None:
        frame = _date_frame([date(2024, 6, 5), date(2024, 6, 7)])
        result = drop_after(
            frame, "date", date(2024, 6, 7), later_rows_expected=False, dataset="p", symbol="A"
        )
        assert len(result) == 2

    def test_undated_row_raises_lookahead_violation(self) -> None:
        frame = pd.DataFrame({"date": pd.to_datetime([date(2024, 6, 5), None])})
        with pytest.raises(LookaheadViolation):
            drop_after(
                frame, "date", date(2024, 6, 7), later_rows_expected=False, dataset="p", symbol="A"
            )

    def test_non_datetime_column_raises_lookahead_violation(self) -> None:
        frame = pd.DataFrame({"date": ["2024-06-05", "2024-06-07"]})
        with pytest.raises(LookaheadViolation):
            drop_after(
                frame, "date", date(2024, 6, 7), later_rows_expected=False, dataset="p", symbol="A"
            )


def _fresh_settings() -> Settings:
    """A Settings object with its own temp cache dir, outside pytest's
    per-test tmp_path (needed so each hypothesis example gets a fresh
    cache, not one shared across all 50 examples of a single test call).
    """
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        data_cache_dir=Path(tempfile.mkdtemp()),
        alpaca_api_key="fake-key",
        alpaca_secret_key="fake-secret",
        groq_api_key="fake-groq-key",
        sec_contact_email="test@example.com",
    )


def _honest_yfinance_download() -> Any:
    """A yfinance fake that serves exactly the requested (start, end) range,
    for tests that need a normal, non-leaky fetch to seed the cache."""

    def fake_download(
        symbol: str, start: date, end: date, timeout: float
    ) -> tuple[pd.DataFrame, pd.Series]:
        history = pd.DataFrame(
            {
                "Open": 1.0,
                "High": 1.0,
                "Low": 1.0,
                "Close": 1.0,
                "Adj Close": 1.0,
                "Volume": 100,
                "Dividends": 0.0,
                "Stock Splits": 0.0,
            },
            index=pd.date_range(start, end, freq="D", tz="America/New_York"),
        )
        history.index.name = "Date"
        return history, pd.Series(dtype=float)

    return patch("bullpit.data.prices._download_yfinance", side_effect=fake_download)


def _leaky_yfinance_download(as_of: date) -> Any:
    """A yfinance fake that ignores its (start, end) arguments and always
    returns 61 daily bars spanning 30 days either side of `as_of`."""
    dates = pd.date_range(
        as_of - timedelta(days=30), as_of + timedelta(days=30), freq="D", tz="America/New_York"
    )
    history = pd.DataFrame(
        {
            "Open": 1.0,
            "High": 1.0,
            "Low": 1.0,
            "Close": 1.0,
            "Adj Close": 1.0,
            "Volume": 100,
            "Dividends": 0.0,
            "Stock Splits": 0.0,
        },
        index=dates,
    )
    history.index.name = "Date"

    def fake_download(
        symbol: str, start: date, end: date, timeout: float
    ) -> tuple[pd.DataFrame, pd.Series]:
        return history, pd.Series(dtype=float)

    return patch("bullpit.data.prices._download_yfinance", side_effect=fake_download)


def _leaky_news_download(as_of: date) -> Any:
    """A news fake that ignores its (start, end) arguments and always
    returns articles spanning 30 days either side of as_of's cutoff."""
    cutoff = session_close(as_of)
    times = [cutoff - timedelta(days=30) + timedelta(days=i) for i in range(61)]

    def fake_download(
        symbol: str, start: datetime, end: datetime, settings: Settings
    ) -> list[dict[str, Any]]:
        return [
            {
                "id": i,
                "created_at": t.isoformat(),
                "headline": "leaky",
                "summary": "leaky",
                "symbols": [symbol],
                "source": "test",
                "url": None,
            }
            for i, t in enumerate(times)
        ]

    return patch("bullpit.data.news._download_news", side_effect=fake_download)


def _leaky_sec_get_json(as_of: date) -> Any:
    """SEC has no request filter at all (M1-FR-5), so its companyfacts
    naturally includes facts filed both before and after `as_of`."""
    tickers = {"1": {"cik_str": 999, "ticker": "LEAKYSEC", "title": "Leaky SEC Co"}}
    filed_dates = [as_of - timedelta(days=30), as_of, as_of + timedelta(days=30)]
    records = [
        {
            "start": "2024-01-01",
            "end": "2024-03-30",
            "val": 100 + i,
            "accn": f"0001-{i}",
            "fy": 2024,
            "fp": "Q1",
            "form": "10-Q",
            "filed": filed.isoformat(),
        }
        for i, filed in enumerate(filed_dates)
    ]
    companyfacts = {
        "cik": 999,
        "entityName": "Leaky SEC Co",
        "facts": {"us-gaap": {"Revenues": {"units": {"USD": records}}}},
    }

    def fake_get_json(url: str, *, settings: Settings) -> dict[str, Any]:
        if "company_tickers" in url:
            return tickers
        return companyfacts

    return patch("bullpit.data.sec._get_json", side_effect=fake_get_json)


def _assert_no_leak_for_all_tools(as_of: date) -> None:
    settings = _fresh_settings()
    cutoff = session_close(as_of)

    with _leaky_yfinance_download(as_of):
        price_history = prices.get_prices("LEAKY", as_of, 5, settings=settings)
    assert price_history.bars.index.max() <= pd.Timestamp(as_of)

    with _leaky_news_download(as_of):
        articles = news.get_news("LEAKYNEWS", as_of, settings=settings)
    assert all(article.created_at <= cutoff for article in articles)

    with _leaky_sec_get_json(as_of):
        facts = sec.get_sec_facts("LEAKYSEC", as_of, settings=settings)
    assert (facts.facts["filed"] <= pd.Timestamp(as_of)).all()


class TestNoRowAfterCutoff:
    """M1-AC-1: with leaky fakes (rows on both sides of the cutoff,
    ignoring the request filter), no tool ever returns a row after the
    cutoff.
    """

    def test_fixed_date(self) -> None:
        _assert_no_leak_for_all_tools(date(2024, 6, 7))

    @given(
        as_of=st.dates(min_value=date(2024, 1, 2), max_value=date(2025, 12, 30)).filter(is_session)
    )
    @hyp_settings(max_examples=50, deadline=None)
    def test_property(self, as_of: date) -> None:
        _assert_no_leak_for_all_tools(as_of)


class TestInjectedCacheRowIsDropped:
    """M1-AC-2: a row written straight into a cache file (bypassing every
    source's request filter) is dropped and logged on the next read.
    """

    def test_injected_future_row_is_dropped_on_read(self) -> None:
        settings = _fresh_settings()
        as_of = date(2024, 6, 7)

        with _honest_yfinance_download():
            prices.get_prices("INJECT", as_of, 5, settings=settings)

        entry = cache.load("prices", "INJECT", settings=settings)
        assert entry is not None
        future_row = pd.DataFrame(
            {
                "date": [pd.Timestamp(as_of + timedelta(days=3))],
                "open": [1.0],
                "high": [1.0],
                "low": [1.0],
                "close": [1.0],
                "volume": [100.0],
                "split_ratio": [1.0],
                "source": ["yfinance"],
            }
        )
        injected = pd.concat([entry.frame, future_row], ignore_index=True)
        cache.save(
            "prices",
            "INJECT",
            cache.CacheEntry(
                frame=injected, start=entry.start, complete_through=entry.complete_through
            ),
            settings=settings,
        )

        with capture_logs() as logs:
            result = prices.get_prices("INJECT", as_of, 5, settings=settings)

        assert result.bars.index.max() <= pd.Timestamp(as_of)
        dropped = [log for log in logs if log["event"] == "lookahead_row_dropped"]
        assert any(log["log_level"] == "debug" for log in dropped)
