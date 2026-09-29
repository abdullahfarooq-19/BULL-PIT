"""Risk review node tests (M4-AC-5, AC-11): approve, shrink and the
only-shrink clamp (with the risk_review_clamped log event), veto and the
final veto, and a flagged reply."""

from __future__ import annotations

import json
from decimal import Decimal

import structlog.testing
from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.risk_review import risk_review_node
from bullpit.config import Settings
from bullpit.domain import SizedOrder
from bullpit.state import Recommendation, RiskVerdict, TradeAttempt
from tests.agents.conftest import FIRST_LINE_RISK_REVIEW, ScriptedLLM, make_board_state, make_reply

_ORDER = SizedOrder(
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


def _recommendation() -> Recommendation:
    return Recommendation(
        ticker="AAPL",
        action="buy",
        target_weight=Decimal("0.06"),
        exit_style="normal",
        confidence=0.6,
        decisive_evidence=["T1"],
        reasoning="Trend and margins outweigh the news risk.",
        flagged=False,
    )


def _state_with_sized_order() -> object:
    attempt = TradeAttempt(recommendation=_recommendation(), sized_order=_ORDER)
    return make_board_state(attempts=[attempt])


def _reply_content(**overrides: object) -> str:
    payload: dict[str, object] = {"decision": "approve", "reason": "Looks sound."}
    payload.update(overrides)
    return json.dumps(payload)


class TestApprove:
    def test_approve_keeps_stage_a_order(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = _state_with_sized_order()
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_RISK_REVIEW, make_reply(_reply_content()))

        result = risk_review_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        assert result["outcome"] == "buy"
        assert result["sized_order"] == _ORDER
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.verdict is not None
        assert attempt.verdict.decision == "approve"


class TestShrink:
    def test_shrink_below_stage_a_recomputes_the_order(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = _state_with_sized_order()
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_RISK_REVIEW,
            make_reply(_reply_content(decision="shrink", shares=20, reason="Confidence is thin.")),
        )

        result = risk_review_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        assert result["outcome"] == "buy"
        resized = result["sized_order"]
        assert isinstance(resized, SizedOrder)
        assert resized.shares == 20
        assert resized.cost == Decimal("3640.00")
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.verdict is not None
        assert attempt.verdict.decision == "shrink"
        assert attempt.verdict.clamped is False

    def test_shrink_at_or_above_stage_a_is_clamped_and_logged(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = _state_with_sized_order()
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_RISK_REVIEW,
            make_reply(_reply_content(decision="shrink", shares=40, reason="Too small already.")),
        )

        with structlog.testing.capture_logs() as captured:
            result = risk_review_node(
                state, settings=settings, sessions=sessions, completion_fn=llm
            )

        assert result["outcome"] == "buy"
        assert result["sized_order"] == _ORDER
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.verdict is not None
        assert attempt.verdict.clamped is True
        assert any("clamped" in warning for warning in result["warnings"])
        assert any(entry["event"] == "risk_review_clamped" for entry in captured)


class TestVeto:
    def test_veto_with_trips_left_records_the_verdict_and_sets_no_outcome(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = _state_with_sized_order()
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_RISK_REVIEW,
            make_reply(_reply_content(decision="veto", reason="Size too big for the confidence.")),
        )

        result = risk_review_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        assert "outcome" not in result
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.verdict is not None
        assert attempt.verdict.decision == "veto"

    def test_third_veto_ends_in_no_trade(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        earlier_verdict = RiskVerdict(
            decision="veto",
            reason="earlier reason",
            requested_shares=None,
            clamped=False,
            flagged=False,
        )
        earlier_attempts = [
            TradeAttempt(
                recommendation=_recommendation(), sized_order=_ORDER, verdict=earlier_verdict
            )
            for _ in range(2)
        ]
        final_attempt = TradeAttempt(recommendation=_recommendation(), sized_order=_ORDER)
        state = make_board_state(attempts=[*earlier_attempts, final_attempt])
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_RISK_REVIEW,
            make_reply(_reply_content(decision="veto", reason="still too big")),
        )

        result = risk_review_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        assert result["outcome"] == "no_trade"
        assert result["no_trade_reason"] == "Risk manager vetoed 3 times: still too big"


class TestFlaggedReply:
    def test_invalid_reply_ends_the_request(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = _state_with_sized_order()
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_RISK_REVIEW, make_reply("not json"))
        llm.queue(FIRST_LINE_RISK_REVIEW, make_reply("still not json"))

        result = risk_review_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        assert result["outcome"] == "no_trade"
        assert result["no_trade_reason"] == "Risk review reply was invalid."
        attempt = result["attempts"][-1]
        assert isinstance(attempt, TradeAttempt)
        assert attempt.verdict is not None
        assert attempt.verdict.flagged is True
