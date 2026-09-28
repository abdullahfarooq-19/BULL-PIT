"""SEC EDGAR: ticker-to-CIK, companyfacts, point-in-time facts
(M1-AC-3, M1-AC-10). Downloads are patched; no network (M1-NFR-1).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

from bullpit.config import Settings
from bullpit.data import sec
from bullpit.errors import DataUnavailable
from tests.conftest import fixture_path


def _company_tickers() -> dict[str, Any]:
    return json.loads(fixture_path("sec", "company_tickers.json").read_text())


def _aapl_companyfacts() -> dict[str, Any]:
    return json.loads(fixture_path("sec", "aapl_companyfacts.json").read_text())


def _restated_companyfacts() -> dict[str, Any]:
    return json.loads(fixture_path("sec", "restated.json").read_text())


def _fake_get_json(responses: dict[str, dict[str, Any]]) -> Any:
    def fake(url: str, *, settings: Settings) -> dict[str, Any]:
        for key, response in responses.items():
            if key in url:
                return response
        raise DataUnavailable(f"unexpected URL in test: {url}")

    return patch("bullpit.data.sec._get_json", side_effect=fake)


class TestGetCik:
    def test_resolves_a_known_ticker(self, settings: Settings) -> None:
        with _fake_get_json({"company_tickers": _company_tickers()}):
            assert sec.get_cik("AAPL", settings=settings) == 320193

    def test_resolves_a_share_class_ticker(self, settings: Settings) -> None:
        with _fake_get_json({"company_tickers": _company_tickers()}):
            assert sec.get_cik("BRK.B", settings=settings) == 1067983

    def test_unknown_ticker_refetches_once_then_raises(self, settings: Settings) -> None:
        with _fake_get_json({"company_tickers": _company_tickers()}) as mock:
            with pytest.raises(DataUnavailable):
                sec.get_cik("ZZZZ", settings=settings)
            assert mock.call_count == 2  # initial load + the one forced refetch


class TestGetSecFacts:
    def test_parses_recorded_companyfacts(self, settings: Settings) -> None:
        with _fake_get_json(
            {"company_tickers": _company_tickers(), "companyfacts": _aapl_companyfacts()}
        ):
            facts = sec.get_sec_facts("AAPL", date(2024, 7, 12), settings=settings)

        assert facts.cik == 320193
        assert set(facts.facts["tag"]) >= {
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
        }

    def test_unknown_ticker_raises_data_unavailable(self, settings: Settings) -> None:
        with (
            _fake_get_json({"company_tickers": _company_tickers()}),
            pytest.raises(DataUnavailable),
        ):
            sec.get_sec_facts("ZZZZ", date(2024, 7, 12), settings=settings)

    def test_point_in_time_facts(self, settings: Settings) -> None:
        """A fact ending 2024-03-30 filed 2024-05-03 is absent before its
        filing date and present from it; a restated value only appears
        from its own filing date (M1-AC-3).
        """
        tickers = {"1": {"cik_str": 1, "ticker": "REST", "title": "Restated Test Co"}}
        with _fake_get_json({"company_tickers": tickers, "companyfacts": _restated_companyfacts()}):
            before_filing = sec.get_sec_facts("REST", date(2024, 5, 1), settings=settings)
            assert before_filing.facts.empty

            at_first_filing = sec.get_sec_facts("REST", date(2024, 5, 3), settings=settings)
            assert list(at_first_filing.facts["value"]) == [100.0]

            after_restatement = sec.get_sec_facts("REST", date(2024, 8, 1), settings=settings)
            assert list(after_restatement.facts["value"]) == [105.0]
