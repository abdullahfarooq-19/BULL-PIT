"""Trader node tests (M4-AC-11): ticker filled by code, the weight clamp
and decisive-ID filter, no-trade and flagged outcomes, and the retry
prompt listing earlier vetoes."""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.trader import trader_node
from bullpit.config import Settings
from bullpit.domain import SizedOrder
from bullpit.state import Recommendation, RiskVerdict, TradeAttempt
from tests.agents.conftest import FIRST_LINE_TRADER, ScriptedLLM, make_board_state, make_reply


def _reply_content(**overrides: object) -> str:
    payload: dict[str, object] = {
        "action": "buy",
        "target_weight": 0.05,
        "exit_style": "normal",
        "confidence": 0.6,
        "decisive_evidence": ["T1"],
        "reasoning": "The uptrend outweighs the news risk.",
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestTickerFromRequest:
    def test_ticker_comes_from_state_not_the_reply(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_TRADER, make_reply(_reply_content()))

        result = trader_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.recommendation.ticker == "AAPL"


class TestWeightClamp:
    def test_weight_above_the_cap_is_clamped_with_a_warning(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_TRADER, make_reply(_reply_content(target_weight=0.25)))

        result = trader_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.recommendation.target_weight == Decimal("0.10")
        assert any("clamped" in warning for warning in result["warnings"])


class TestDecisiveEvidenceFilter:
    def test_unregistered_ids_are_dropped_with_a_warning(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_TRADER, make_reply(_reply_content(decisive_evidence=["T1", "X9"])))

        result = trader_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.recommendation.decisive_evidence == ["T1"]
        assert any("X9" in warning for warning in result["warnings"])


class TestNoTradeOutcome:
    def test_no_trade_action_ends_the_request(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_TRADER,
            make_reply(_reply_content(action="no_trade", reasoning="Too much uncertainty.")),
        )

        result = trader_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        assert result["outcome"] == "no_trade"
        assert result["no_trade_reason"] == "Trader recommended no trade: Too much uncertainty."


class TestFlaggedReply:
    def test_invalid_reply_ends_the_request(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_TRADER, make_reply("not json"))
        llm.queue(FIRST_LINE_TRADER, make_reply("still not json"))

        result = trader_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        assert result["outcome"] == "no_trade"
        assert result["no_trade_reason"] == "Trader reply was invalid."
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.recommendation.flagged is True


class TestRetryPromptListsVetoes:
    def test_earlier_vetoes_are_listed_with_weight_style_shares_and_reason(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        sized_order = SizedOrder(
            ticker="AAPL",
            shares=32,
            reference_price=Decimal("182"),
            stop_loss=Decimal("174.00"),
            take_profit=Decimal("194.00"),
            exit_style="normal",
            cost=Decimal("5824.00"),
            max_loss=Decimal("256.00"),
            max_gain=Decimal("384.00"),
            limit="target",
            limit_shares={"target": 32, "risk": 125, "cap": 54, "cash": 527},
        )
        recommendation = Recommendation(
            ticker="AAPL",
            action="buy",
            target_weight=Decimal("0.06"),
            exit_style="normal",
            confidence=0.6,
            decisive_evidence=["T1"],
            reasoning="Trend looks strong.",
            flagged=False,
        )
        verdict = RiskVerdict(
            decision="veto",
            reason="too big for this confidence",
            requested_shares=None,
            clamped=False,
            flagged=False,
        )
        attempt = TradeAttempt(
            recommendation=recommendation, sized_order=sized_order, verdict=verdict
        )
        state = make_board_state(attempts=[attempt])

        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_TRADER, make_reply(_reply_content()))

        trader_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        assert len(llm.prompts) == 1
        prompt = llm.prompts[0]
        assert "Veto 1:" in prompt
        assert "6% normal" in prompt
        assert "sized to 32 shares" in prompt
        assert "too big for this confidence" in prompt
