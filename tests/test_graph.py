"""The graph end to end, with recorded fixtures, a fake broker and a fake
completion function (M3-AC-1 automated, AC-5, AC-6, AC-7, AC-9).
"""

from __future__ import annotations

import json
import re
import threading
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy.orm import Session, sessionmaker

from bullpit.clock import SimClock
from bullpit.config import Settings
from bullpit.domain import Account, Asset
from bullpit.errors import LLMUnavailable, QuotaExhausted
from bullpit.journal.models import LLMCall, Request, SignalRecord
from bullpit.llm.gateway import CompletionReply, CompletionRequest
from bullpit.runners.request import run_request
from tests.broker.fake_broker import FakeBroker
from tests.conftest import fixture_path

AS_OF = date(2024, 7, 5)


def _company_tickers() -> dict[str, Any]:
    return json.loads(fixture_path("sec", "company_tickers.json").read_text())


def _aapl_companyfacts() -> dict[str, Any]:
    return json.loads(fixture_path("sec", "aapl_companyfacts.json").read_text())


def _patch_sec() -> Any:
    responses = {"company_tickers": _company_tickers(), "companyfacts": _aapl_companyfacts()}

    def fake(url: str, *, settings: Settings) -> dict[str, Any]:
        for key, response in responses.items():
            if key in url:
                return response
        raise AssertionError(f"unexpected SEC URL in test: {url}")

    return patch("bullpit.data.sec._get_json", side_effect=fake)


def _patch_prices() -> Any:
    history = pd.read_parquet(fixture_path("prices", "aapl_yf.parquet")).set_index("Date")
    splits_frame = pd.read_parquet(fixture_path("prices", "aapl_yf_splits.parquet"))
    splits = splits_frame.set_index("Date")["Stock Splits"]

    def fake_download(
        symbol: str, start: date, end: date, timeout: float
    ) -> tuple[pd.DataFrame, pd.Series]:
        mask = (history.index.date >= start) & (history.index.date <= end)
        return history[mask], splits

    return patch("bullpit.data.prices._download_yfinance", side_effect=fake_download)


def _patch_news() -> Any:
    records = json.loads(fixture_path("news", "aapl_news.json").read_text())

    def fake(
        symbol: str, start: datetime, end: datetime, settings: Settings
    ) -> list[dict[str, Any]]:
        return [
            record
            for record in records
            if start <= datetime.fromisoformat(record["created_at"].replace("Z", "+00:00")) < end
        ]

    return patch("bullpit.data.news._download_news", side_effect=fake)


class RecordingLLM:
    """Answers by template, since the three analysts call in parallel and
    arrive in any order (plan sec13); records every rendered prompt."""

    def __init__(
        self,
        *,
        technical: tuple[str, float] = ("bullish", 0.6),
        fundamentals: tuple[str, float] = ("neutral", 0.4),
        sentiment_score: float = 0.6,
        sentiment_relevance: float = 0.9,
    ) -> None:
        self.technical = technical
        self.fundamentals = fundamentals
        self.sentiment_score = sentiment_score
        self.sentiment_relevance = sentiment_relevance
        self.prompts: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, request: CompletionRequest) -> CompletionReply:
        prompt = request.messages[0]["content"]
        with self._lock:
            self.prompts.append(prompt)

        if prompt.startswith("You are a news sentiment analyst"):
            ids = re.findall(r"^(S\d+):", prompt, re.MULTILINE)
            scores = [
                {
                    "id": headline_id,
                    "score": self.sentiment_score,
                    "relevance": self.sentiment_relevance,
                }
                for headline_id in ids
            ]
            content = json.dumps({"scores": scores})
        elif prompt.startswith("You are a technical analyst"):
            direction, confidence = self.technical
            content = json.dumps({"direction": direction, "confidence": confidence})
        elif prompt.startswith("You are a fundamentals analyst"):
            direction, confidence = self.fundamentals
            content = json.dumps({"direction": direction, "confidence": confidence})
        else:
            raise AssertionError(f"unrecognised prompt: {prompt[:80]!r}")

        return CompletionReply(
            content=content, input_tokens=50, output_tokens=10, reasoning_tokens=5
        )


def _fake_broker(settings: Settings) -> FakeBroker:
    return FakeBroker(
        account=Account(cash=Decimal("100000"), equity=Decimal("100000")),
        assets={"AAPL": Asset(symbol="AAPL", name="Apple Inc.", tradable=True, active=True)},
    )


def _llm_calls(sessions: sessionmaker[Session], request_id: str) -> list[LLMCall]:
    with sessions() as session:
        return list(session.query(LLMCall).filter(LLMCall.request_id == request_id).all())


def _signal_rows(sessions: sessionmaker[Session], request_id: str) -> list[SignalRecord]:
    with sessions() as session:
        return list(session.query(SignalRecord).filter(SignalRecord.request_id == request_id).all())


class TestDebateRoute:
    def test_conflicting_signals_route_to_debate(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM(technical=("bullish", 0.6), fundamentals=("neutral", 0.4))
        with _patch_sec(), _patch_prices(), _patch_news():
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=llm,
            )

        assert result.rejection is None
        assert result.route == "debate"

        for signal in (
            result.technical_signal,
            result.fundamentals_signal,
            result.sentiment_signal,
        ):
            assert signal is not None
            assert signal.flagged is False

        # sentiment: every scored headline used the same score/relevance, so
        # the relevance-weighted average equals that score exactly (FR-14).
        assert result.sentiment_signal is not None
        assert result.sentiment_signal.direction == "bullish"
        assert result.sentiment_signal.confidence == pytest.approx(llm.sentiment_score)

        assert result.board is not None
        all_ids = list(result.board.evidence.keys())
        assert len(all_ids) == len(set(all_ids))
        for signal in (
            result.technical_signal,
            result.fundamentals_signal,
            result.sentiment_signal,
        ):
            for item in signal.evidence:  # type: ignore[union-attr]
                prefix = {"technical": "T", "fundamentals": "F", "sentiment": "S"}[signal.analyst]  # type: ignore[union-attr]
                assert item.id.startswith(prefix)
                assert item.id in result.board.evidence

        rows = _llm_calls(sessions, result.request_id)
        assert len(rows) == 3
        assert {row.role for row in rows} == {"small"}

        signal_rows = _signal_rows(sessions, result.request_id)
        assert {row.analyst for row in signal_rows} == {"technical", "fundamentals", "sentiment"}

        with sessions() as session:
            journal_row = session.get(Request, result.request_id)
            assert journal_row is not None
            assert journal_row.status == "completed"
            assert journal_row.route == "debate"


class TestWeakSignalsRouteToNoTrade:
    def test_all_neutral_routes_to_no_trade(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM(
            technical=("neutral", 0.05),
            fundamentals=("neutral", 0.05),
            sentiment_score=0.0,
            sentiment_relevance=0.5,
        )
        with _patch_sec(), _patch_prices(), _patch_news():
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=llm,
            )

        assert result.route == "no_trade"
        rows = _llm_calls(sessions, result.request_id)
        assert len(rows) == 3


class TestFailedAnalyst:
    def test_llm_unavailable_becomes_a_flagged_neutral_signal(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM()

        def broken_fundamentals(*args: object, **kwargs: object) -> dict[str, object]:
            raise LLMUnavailable("forced failure for the test")

        with (
            _patch_sec(),
            _patch_prices(),
            _patch_news(),
            patch("bullpit.graph.fundamentals_node", side_effect=broken_fundamentals),
        ):
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=llm,
            )

        assert result.rejection is None
        assert result.fundamentals_signal is not None
        assert result.fundamentals_signal.flagged is True
        assert result.fundamentals_signal.direction == "neutral"
        assert result.fundamentals_signal.confidence == 0.0
        assert any("fundamentals" in warning for warning in result.warnings)

        with sessions() as session:
            journal_row = session.get(Request, result.request_id)
            assert journal_row is not None
            assert journal_row.status == "completed"

    def test_quota_exhausted_fails_the_request_and_releases_the_lock(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM()

        def out_of_quota(*args: object, **kwargs: object) -> dict[str, object]:
            raise QuotaExhausted("forced quota failure for the test")

        with (
            _patch_sec(),
            _patch_prices(),
            _patch_news(),
            patch("bullpit.graph.fundamentals_node", side_effect=out_of_quota),
            pytest.raises(QuotaExhausted),
        ):
            run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=llm,
            )

        with sessions() as session:
            failed = session.query(Request).filter(Request.ticker == "AAPL").one()
            assert failed.status == "failed"

        # The lock was released: a second request for the same ticker isn't refused.
        with _patch_sec(), _patch_prices(), _patch_news():
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=llm,
            )
        assert result.rejection is None


class TestNoFutureDataReachesAPrompt:
    def test_no_prompt_or_state_number_is_dated_after_as_of(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        """The recorded fixtures hold real data after AS_OF (prices through
        2024-07-31, news through 2024-07-07, SEC facts through 2026): none
        of it may reach a prompt or a state number (M3-AC-9)."""
        llm = RecordingLLM()
        with _patch_sec(), _patch_prices(), _patch_news():
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=llm,
            )

        assert result.rejection is None
        for prompt in llm.prompts:
            assert "2024-07-06" not in prompt
            assert "2024-07-07" not in prompt
            for later_year in ("2025", "2026"):
                assert later_year not in prompt

        assert result.prices is not None
        assert result.prices.bars[-1].date == AS_OF
        assert result.prices.bars[-1].close == pytest.approx(226.34, abs=0.01)

        assert result.fundamentals is not None
        assert result.fundamentals.filing_date is not None
        assert result.fundamentals.filing_date <= AS_OF
