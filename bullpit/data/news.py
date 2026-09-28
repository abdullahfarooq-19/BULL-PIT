"""Alpaca news for the lookback window before `as_of` (dev-plan.md Part 2,
Part 7; findings C2). alpaca-py 0.44 follows `next_page_token` itself when
no `limit` is set, so Bull Pit doesn't page by hand (M1-FR-14).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

import pandas as pd
from alpaca.data.models.news import NewsSet
from alpaca.data.requests import NewsRequest
from pydantic import BaseModel

from bullpit.broker.clients import make_data_clients
from bullpit.config import Settings
from bullpit.data import cache
from bullpit.data.calendar import session_close
from bullpit.errors import DataUnavailable

_NEWS_COLUMNS = ["id", "created_at", "headline", "summary", "symbols", "source", "url"]


class NewsArticle(BaseModel, frozen=True):
    id: int
    created_at: datetime
    headline: str
    summary: str
    symbols: list[str]
    source: str
    url: str | None


def _download_news(
    symbol: str, start: datetime, end: datetime, settings: Settings
) -> list[dict[str, Any]]:
    try:
        clients = make_data_clients(settings)
        request = NewsRequest(symbols=symbol, start=start, end=end, include_content=False)
        response = cast(NewsSet, clients.news.get_news(request))
    except Exception as exc:
        raise DataUnavailable(f"Alpaca news request failed for {symbol}") from exc
    return [article.model_dump(mode="json") for article in response.data.get("news", [])]


def _frame_from_news(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=_NEWS_COLUMNS)
    frame = pd.DataFrame(records)
    frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
    return frame[_NEWS_COLUMNS]


def get_news(symbol: str, as_of: date, *, settings: Settings) -> list[NewsArticle]:
    cutoff = session_close(as_of)
    window_start = cutoff - timedelta(days=settings.news_lookback_days)

    def fetch(a: date, b: date) -> pd.DataFrame:
        start = datetime.combine(a, datetime.min.time(), tzinfo=UTC)
        end = min(cutoff, datetime.combine(b, datetime.min.time(), tzinfo=UTC) + timedelta(days=1))
        records = _download_news(symbol, start, end, settings)
        return _frame_from_news(records)

    frame = cache.read_through(
        "news",
        symbol,
        window_start.date(),
        as_of,
        fetch=fetch,
        key=["id"],
        date_column="created_at",
        settings=settings,
    )
    frame = frame[frame["created_at"] > pd.Timestamp(window_start)].sort_values("created_at")
    records = cast("list[dict[str, Any]]", frame.to_dict(orient="records"))
    return [NewsArticle(**record) for record in records]
