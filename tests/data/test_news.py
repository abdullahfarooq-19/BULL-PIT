"""Alpaca news (M1-AC-10). Downloads are patched; no network (M1-NFR-1)."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from unittest.mock import patch

from bullpit.config import Settings
from bullpit.data import news
from tests.conftest import fixture_path


def _aapl_records() -> list[dict[str, Any]]:
    return json.loads(fixture_path("news", "aapl_news.json").read_text())


def _patch_download(records: list[dict[str, Any]]) -> Any:
    def fake(
        symbol: str, start: datetime, end: datetime, settings: Settings
    ) -> list[dict[str, Any]]:
        return [
            r
            for r in records
            if start <= datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) < end
        ]

    return patch("bullpit.data.news._download_news", side_effect=fake)


class TestGetNews:
    def test_parses_recorded_news(self, settings: Settings) -> None:
        records = _aapl_records()
        with _patch_download(records):
            articles = news.get_news("AAPL", date(2024, 7, 8), settings=settings)

        assert len(articles) > 0
        assert all(a.symbols and "AAPL" in a.symbols for a in articles)
        assert all(a.headline for a in articles)
        first = articles[0]
        assert isinstance(first.id, int)
        assert first.created_at.tzinfo is not None

    def test_no_articles_gives_empty_list(self, settings: Settings) -> None:
        with _patch_download([]):
            articles = news.get_news("AAPL", date(2024, 7, 8), settings=settings)
        assert articles == []
