"""The graph end to end, with recorded fixtures, a fake broker and a fake
completion function (M3-AC-1 automated, AC-5, AC-6, AC-7, AC-9; M4-AC-4,
AC-6, AC-8, AC-12; M5-AC-8).
"""

from __future__ import annotations

import json
import re
import threading
from collections import defaultdict, deque
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest
from sqlalchemy.orm import Session, sessionmaker

from bullpit.clock import SimClock
from bullpit.config import Settings
from bullpit.domain import Account, Asset, Position
from bullpit.errors import DataUnavailable, LLMUnavailable, QuotaExhausted
from bullpit.journal.models import (
    DebateTurnRecord,
    LLMCall,
    RecommendationRecord,
    ReportRecord,
    Request,
    SignalRecord,
)
from bullpit.llm.gateway import CompletionReply, CompletionRequest
from bullpit.runners.request import run_request
from bullpit.state import RequestState
from tests.agents.conftest import (
    FIRST_LINE_BEAR,
    FIRST_LINE_BULL,
    FIRST_LINE_RISK_REVIEW,
    FIRST_LINE_TRADER,
)
from tests.broker.fake_broker import FakeBroker
from tests.conftest import fixture_path

AS_OF = date(2024, 7, 5)

_DEFAULT_DEBATE_REPLY = json.dumps(
    {
        "points": [{"claim": "The trend supports buying.", "evidence_ids": ["T1"]}],
        "concessions": [],
        "conviction": 0.6,
    }
)
_DEFAULT_TRADER_REPLY = json.dumps(
    {
        "action": "buy",
        "target_weight": 0.06,
        "exit_style": "normal",
        "confidence": 0.6,
        "decisive_evidence": ["T1"],
        "reasoning": "Trend and margins outweigh the news risk.",
    }
)
_DEFAULT_REVIEW_REPLY = json.dumps({"decision": "approve", "reason": "Sizing looks sound."})
_FIRST_LINE_REPORT = "You are the report writer"
_DEFAULT_REPORT_REPLY = json.dumps(
    {
        "summary": "The trend supports the recommendation (T1).",
        "strongest_bull": "The trend is intact (T1).",
        "strongest_bear": "The news is a risk.",
        "bull_conceded": "The bull conceded the momentum risk.",
        "unresolved": "How much the news matters.",
        "would_change_view": "A break of the trend.",
    }
)


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """A debated request makes up to 10 large-model calls in one test (M4
    NFR-3); raise the per-minute pacing so the real token bucket never
    sleeps through them (plan sec13, test-only override, no code change)."""
    return settings.model_copy(update={"llm_tpm_limit": 1_000_000, "llm_rpm_limit": 1_000})


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
    """Answers by which fixed first line the prompt starts with, since the
    three analysts call in parallel and arrive in any order (plan sec13);
    records every rendered prompt. The three M3 analyst replies are fixed
    per instance; the M4 and M5 templates can be scripted per test with
    `queue()` (consumed first, in order) and otherwise fall back to a
    sensible default (bullish debate point, a 6% normal buy, an approve).
    """

    def __init__(
        self,
        *,
        technical: tuple[str, float] = ("bullish", 0.6),
        fundamentals: tuple[str, float] = ("neutral", 0.4),
        sentiment_score: float = 0.6,
        sentiment_relevance: float = 0.9,
        trader_reply: str = _DEFAULT_TRADER_REPLY,
        review_reply: str = _DEFAULT_REVIEW_REPLY,
    ) -> None:
        self.technical = technical
        self.fundamentals = fundamentals
        self.sentiment_score = sentiment_score
        self.sentiment_relevance = sentiment_relevance
        self.trader_reply = trader_reply
        self.review_reply = review_reply
        self.prompts: list[str] = []
        self._lock = threading.Lock()
        self._queues: dict[str, deque[str]] = defaultdict(deque)

    def queue(self, first_line: str, content: str) -> None:
        self._queues[first_line].append(content)

    def __call__(self, request: CompletionRequest) -> CompletionReply:
        prompt = request.messages[0]["content"]
        with self._lock:
            self.prompts.append(prompt)

        for first_line, queue in self._queues.items():
            if prompt.startswith(first_line) and queue:
                return CompletionReply(
                    content=queue.popleft(), input_tokens=50, output_tokens=10, reasoning_tokens=5
                )

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
        elif prompt.startswith(FIRST_LINE_BULL) or prompt.startswith(FIRST_LINE_BEAR):
            content = _DEFAULT_DEBATE_REPLY
        elif prompt.startswith(FIRST_LINE_TRADER):
            content = self.trader_reply
        elif prompt.startswith(FIRST_LINE_RISK_REVIEW):
            content = self.review_reply
        elif prompt.startswith(_FIRST_LINE_REPORT):
            content = _DEFAULT_REPORT_REPLY
        else:
            raise AssertionError(f"unrecognised prompt: {prompt[:80]!r}")

        return CompletionReply(
            content=content, input_tokens=50, output_tokens=10, reasoning_tokens=5
        )


def _fake_broker(settings: Settings, *, positions: dict[str, Position] | None = None) -> FakeBroker:
    return FakeBroker(
        account=Account(cash=Decimal("100000"), equity=Decimal("100000")),
        assets={"AAPL": Asset(symbol="AAPL", name="Apple Inc.", tradable=True, active=True)},
        positions=positions or {},
    )


def _llm_calls(sessions: sessionmaker[Session], request_id: str) -> list[LLMCall]:
    with sessions() as session:
        return list(session.query(LLMCall).filter(LLMCall.request_id == request_id).all())


def _signal_rows(sessions: sessionmaker[Session], request_id: str) -> list[SignalRecord]:
    with sessions() as session:
        return list(session.query(SignalRecord).filter(SignalRecord.request_id == request_id).all())


def _debate_turn_rows(sessions: sessionmaker[Session], request_id: str) -> list[DebateTurnRecord]:
    with sessions() as session:
        return list(
            session.query(DebateTurnRecord)
            .filter(DebateTurnRecord.request_id == request_id)
            .order_by(DebateTurnRecord.id)
            .all()
        )


def _recommendation_rows(
    sessions: sessionmaker[Session], request_id: str
) -> list[RecommendationRecord]:
    with sessions() as session:
        return list(
            session.query(RecommendationRecord)
            .filter(RecommendationRecord.request_id == request_id)
            .order_by(RecommendationRecord.id)
            .all()
        )


def _report_rows(sessions: sessionmaker[Session], request_id: str) -> list[ReportRecord]:
    with sessions() as session:
        return list(session.query(ReportRecord).filter(ReportRecord.request_id == request_id).all())


def _assert_report(
    sessions: sessionmaker[Session], result: RequestState, outcome: str, prose_source: str = "llm"
) -> None:
    """M5-AC-8: the request ends with a report in state and one `reports` row."""
    assert result.report is not None
    assert result.report.outcome == outcome
    assert result.report.prose_source == prose_source
    rows = _report_rows(sessions, result.request_id)
    assert len(rows) == 1
    assert rows[0].report["request_id"] == result.request_id
    assert rows[0].report["outcome"] == outcome


class TestDebateRoute:
    def test_buy_path(self, settings: Settings, sessions: sessionmaker[Session]) -> None:
        """M3's debate-route test, extended (M4-AC-4, AC-8): the bull's
        round-1 reply cites the unregistered T99, and the request runs all
        the way through to a buy."""
        llm = RecordingLLM(technical=("bullish", 0.6), fundamentals=("neutral", 0.4))
        llm.queue(
            FIRST_LINE_BULL,
            json.dumps(
                {
                    "points": [{"claim": "Momentum is strong.", "evidence_ids": ["T99"]}],
                    "concessions": [],
                    "conviction": 0.6,
                }
            ),
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

        signal_rows = _signal_rows(sessions, result.request_id)
        assert {row.analyst for row in signal_rows} == {"technical", "fundamentals", "sentiment"}

        # M4: the debate ran, the T99 citation is unsupported, and the
        # request ends in a buy sized from the fixture's own close and ATR.
        assert len(result.debate) == 4
        first_bull_turn = result.debate[0]
        assert first_bull_turn.side == "bull"
        assert first_bull_turn.points[0].evidence_ids == ["T99"]
        assert first_bull_turn.points[0].unsupported is True

        assert result.outcome == "buy"
        assert result.sized_order is not None
        assert result.prices is not None
        assert result.sized_order.reference_price == result.prices.reference_price
        assert result.sized_order.exit_style == "normal"
        assert result.sized_order.shares > 0

        turn_rows = _debate_turn_rows(sessions, result.request_id)
        assert len(turn_rows) == 4
        assert turn_rows[0].side == "bull"
        assert turn_rows[0].round == 1
        assert turn_rows[0].unsupported_count == 1

        recommendation_rows = _recommendation_rows(sessions, result.request_id)
        assert len(recommendation_rows) == 1
        assert recommendation_rows[0].final_order is not None

        with sessions() as session:
            journal_row = session.get(Request, result.request_id)
            assert journal_row is not None
            assert journal_row.status == "completed"
            assert journal_row.route == "debate"
            assert journal_row.outcome == "buy"

        _assert_report(sessions, result, "buy")
        assert sum(p.startswith(_FIRST_LINE_REPORT) for p in llm.prompts) == 1
        assert result.report is not None
        assert result.report.order == result.sized_order


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
        assert result.outcome == "no_trade"
        assert result.no_trade_reason is not None
        assert result.no_trade_reason.startswith("Signals too weak for a debate")
        assert result.debate == []
        assert result.attempts == []

        rows = _llm_calls(sessions, result.request_id)
        assert len(rows) == 4  # three analysts and the report writer: no debate/trader/review

        assert _debate_turn_rows(sessions, result.request_id) == []
        assert _recommendation_rows(sessions, result.request_id) == []
        _assert_report(sessions, result, "no_trade")

        with sessions() as session:
            journal_row = session.get(Request, result.request_id)
            assert journal_row is not None
            assert journal_row.outcome == "no_trade"


class TestVetoLimit:
    def test_reviewer_always_vetoes_ends_in_no_trade(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM(
            review_reply=json.dumps(
                {"decision": "veto", "reason": "Size does not match the trader's confidence."}
            )
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

        assert result.outcome == "no_trade"
        assert result.no_trade_reason is not None
        assert result.no_trade_reason.startswith("Risk manager vetoed 3 times:")
        assert len(result.attempts) == 3

        # Each trader retry prompt is distinct (it lists the growing veto
        # history, D-M4-6), so all three are real calls. The risk-review
        # prompt doesn't vary between rounds here (same recommendation, same
        # order each time), so its 2nd and 3rd calls are cache hits -- the
        # verdict is still applied three times, which the recorded
        # recommendation rows below confirm (M4-AC-6: "3 trader calls, 3
        # reviews" counts risk_review_node's logical calls, not raw network
        # calls).
        trader_prompts = [p for p in llm.prompts if p.startswith(FIRST_LINE_TRADER)]
        assert len(trader_prompts) == 3
        assert "Veto 1:" in trader_prompts[1]
        assert "Veto 1:" in trader_prompts[2]
        assert "Veto 2:" in trader_prompts[2]

        recommendation_rows = _recommendation_rows(sessions, result.request_id)
        assert len(recommendation_rows) == 3
        assert all(row.review_decision == "veto" for row in recommendation_rows)
        assert all(row.final_order is None for row in recommendation_rows)
        _assert_report(sessions, result, "no_trade")


class TestTraderNoTrade:
    def test_no_trade_action_skips_the_risk_manager(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM(
            trader_reply=json.dumps(
                {
                    "action": "no_trade",
                    "target_weight": 0.0,
                    "exit_style": "normal",
                    "confidence": 0.4,
                    "decisive_evidence": [],
                    "reasoning": "Too much uncertainty this week.",
                }
            )
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

        assert result.outcome == "no_trade"
        assert (
            result.no_trade_reason == "Trader recommended no trade: Too much uncertainty this week."
        )
        assert not any(p.startswith(FIRST_LINE_RISK_REVIEW) for p in llm.prompts)

        recommendation_rows = _recommendation_rows(sessions, result.request_id)
        assert len(recommendation_rows) == 1
        assert recommendation_rows[0].sized_order is None
        assert recommendation_rows[0].blocked_reason is None
        _assert_report(sessions, result, "no_trade")


class TestStageABlock:
    def test_existing_holding_at_the_cap_blocks_before_review(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM()
        broker = _fake_broker(
            settings,
            positions={"AAPL": Position(symbol="AAPL", qty=10, market_value=Decimal("12000"))},
        )
        with _patch_sec(), _patch_prices(), _patch_news():
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=broker,
                completion_fn=llm,
            )

        assert result.outcome == "no_trade"
        assert result.no_trade_reason is not None
        assert result.no_trade_reason.startswith("Per-stock cap reached")
        assert not any(p.startswith(FIRST_LINE_RISK_REVIEW) for p in llm.prompts)

        recommendation_rows = _recommendation_rows(sessions, result.request_id)
        assert len(recommendation_rows) == 1
        assert recommendation_rows[0].blocked_reason is not None
        assert recommendation_rows[0].blocked_reason.startswith("Per-stock cap reached")
        _assert_report(sessions, result, "no_trade")


class TestFlaggedDebateTurn:
    def test_bears_round_one_reply_invalid_twice_becomes_a_flagged_turn(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM()
        llm.queue(FIRST_LINE_BEAR, "not json")
        llm.queue(FIRST_LINE_BEAR, "still not json")  # the gateway's one retry

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

        assert len(result.debate) == 4
        bear_round_one = result.debate[1]
        assert bear_round_one.side == "bear"
        assert bear_round_one.round == 1
        assert bear_round_one.flagged is True

        with sessions() as session:
            journal_row = session.get(Request, result.request_id)
            assert journal_row is not None
            assert journal_row.status == "completed"

        turn_rows = _debate_turn_rows(sessions, result.request_id)
        flagged_rows = [row for row in turn_rows if row.side == "bear" and row.round == 1]
        assert len(flagged_rows) == 1
        assert flagged_rows[0].flagged is True
        _assert_report(sessions, result, "buy")


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


class TestM4NodeException:
    def test_trader_exception_fails_the_request_and_releases_the_lock(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        """M4-FR-15, AC-12: an exception past the brain (unlike an analyst
        failure) fails the whole request loudly, with no partial outcome.
        A later request for the same ticker isn't refused (lock released),
        and that successful run's debate rows are recorded normally."""
        llm = RecordingLLM()

        def broken_trader(*args: object, **kwargs: object) -> dict[str, object]:
            raise LLMUnavailable("forced failure for the test")

        with (
            _patch_sec(),
            _patch_prices(),
            _patch_news(),
            patch("bullpit.graph.trader_node", side_effect=broken_trader),
            pytest.raises(LLMUnavailable),
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
        assert len(result.debate) == 4
        assert len(_debate_turn_rows(sessions, result.request_id)) == 4


class TestRejectedRequest:
    def test_request_check_rejection_gets_a_free_code_only_report(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        """M5-FR-8: no LLM call and no market-data fetch for a bad request."""
        llm = RecordingLLM()
        with (
            _patch_sec(),
            _patch_prices(),
            _patch_news(),
            patch("bullpit.graph.get_market_context") as market_fetch,
        ):
            result = run_request(
                "ZZZZ",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=llm,
            )

        assert result.rejection is not None
        _assert_report(sessions, result, "rejected", prose_source="none")
        assert result.report is not None
        assert result.report.summary == f"Rejected: {result.rejection}"
        assert result.report.market is None
        assert llm.prompts == []
        assert _llm_calls(sessions, result.request_id) == []
        market_fetch.assert_not_called()


class TestReportStepErrors:
    def test_llm_unavailable_falls_back_and_completes(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        with (
            _patch_sec(),
            _patch_prices(),
            _patch_news(),
            patch("bullpit.report.builder.call_llm", side_effect=LLMUnavailable("forced")),
        ):
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=RecordingLLM(),
            )

        _assert_report(sessions, result, "buy", prose_source="fallback")
        assert result.report is not None
        assert any("forced" in w for w in result.report.data_notes.warnings)
        with sessions() as session:
            journal_row = session.get(Request, result.request_id)
            assert journal_row is not None
            assert journal_row.status == "completed"

    def test_market_data_failure_is_a_warning_not_a_failure(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        """M5-AC-6: section 8 says "not available" and the request completes."""
        with (
            _patch_sec(),
            _patch_prices(),
            _patch_news(),
            patch("bullpit.graph.get_market_context", side_effect=DataUnavailable("no SPY")),
        ):
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=RecordingLLM(),
            )

        _assert_report(sessions, result, "buy")
        assert result.report is not None
        assert result.report.market is not None
        assert result.report.market.explanation == "Market context not available."
        assert any("no SPY" in w for w in result.report.data_notes.warnings)

    def test_quota_exhausted_fails_the_request_and_releases_the_lock(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        with (
            _patch_sec(),
            _patch_prices(),
            _patch_news(),
            patch("bullpit.report.builder.call_llm", side_effect=QuotaExhausted("forced")),
            pytest.raises(QuotaExhausted),
        ):
            run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=RecordingLLM(),
            )

        with sessions() as session:
            failed = session.query(Request).filter(Request.ticker == "AAPL").one()
            assert failed.status == "failed"
            assert session.query(ReportRecord).count() == 0

        with _patch_sec(), _patch_prices(), _patch_news():
            result = run_request(
                "AAPL",
                "backtest",
                SimClock(AS_OF),
                settings=settings,
                sessions=sessions,
                broker=_fake_broker(settings),
                completion_fn=RecordingLLM(),
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
