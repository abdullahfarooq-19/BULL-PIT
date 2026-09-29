"""The four M4 prompt templates (M4-AC-13): each renders from its agent's
own variable-building code, starts with its fixed first line, has no Jinja
`include`, and a worst-case prompt stays under the per-call token ceiling
(NFR-3).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.debate import bear_node, bull_node
from bullpit.agents.risk_review import risk_review_node
from bullpit.agents.trader import trader_node
from bullpit.config import Settings
from bullpit.domain import SizedOrder
from bullpit.llm.gateway import _estimate_tokens
from bullpit.llm.schemas import Evidence, Signal
from bullpit.state import CheckedPoint, DebateTurn, Recommendation, RiskVerdict, TradeAttempt
from tests.agents.conftest import (
    FIRST_LINE_BEAR,
    FIRST_LINE_BULL,
    FIRST_LINE_RISK_REVIEW,
    FIRST_LINE_TRADER,
    ScriptedLLM,
    make_board_state,
    make_reply,
)

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "bullpit" / "llm" / "prompts"
_M4_TEMPLATES = ("bull.md", "bear.md", "trader.md", "risk_review.md")

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


def _long_claim(word_count: int) -> str:
    return " ".join(f"word{i}" for i in range(word_count))


def _worst_transcript() -> list[DebateTurn]:
    """Three 150-word turns (the worst case a template ever has to render:
    bear's round-2 call sees all three prior turns)."""
    turns = []
    for index, side in enumerate(("bull", "bear", "bull")):
        point = CheckedPoint(claim=_long_claim(150), evidence_ids=["T1"], unsupported=False)
        turns.append(
            DebateTurn(
                side=side,
                round=index // 2 + 1,
                points=[point],
                concessions=[],
                conviction=0.6,
                word_count=150,
                over_word_limit=False,
                flagged=False,
            )
        )
    return turns


def _worst_case_state(**overrides: object) -> object:
    """15 sentiment headlines at 120 characters each (the M3 cap), plus
    whatever debate/attempts the caller overrides with."""
    technical = Signal(
        ticker="AAPL",
        analyst="technical",
        direction="bullish",
        confidence=0.6,
        evidence=[Evidence(id=f"T{i}", fact=f"Technical fact {i}") for i in range(1, 7)],
    )
    fundamentals = Signal(
        ticker="AAPL",
        analyst="fundamentals",
        direction="neutral",
        confidence=0.4,
        evidence=[Evidence(id=f"F{i}", fact=f"Fundamentals fact {i}") for i in range(1, 6)],
    )
    sentiment = Signal(
        ticker="AAPL",
        analyst="sentiment",
        direction="bearish",
        confidence=0.5,
        evidence=[Evidence(id=f"S{i}", fact="A" * 120) for i in range(1, 16)],
    )
    return make_board_state(
        technical_signal=technical,
        fundamentals_signal=fundamentals,
        sentiment_signal=sentiment,
        **overrides,
    )


def _recommendation(reasoning: str = "Trend and margins outweigh the news risk.") -> Recommendation:
    return Recommendation(
        ticker="AAPL",
        action="buy",
        target_weight=Decimal("0.06"),
        exit_style="normal",
        confidence=0.6,
        decisive_evidence=["T1"],
        reasoning=reasoning,
        flagged=False,
    )


class TestNoTemplateUsesInclude:
    def test_m4_templates_have_no_jinja_include(self) -> None:
        for name in _M4_TEMPLATES:
            content = (_PROMPTS_DIR / name).read_text(encoding="utf-8")
            assert "{% include" not in content, name


class TestBullAndBearWorstCase:
    def test_bull_renders_and_stays_under_the_ceiling(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = _worst_case_state(debate=_worst_transcript())
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_BULL, make_reply('{"points": [], "concessions": [], "conviction": 0.5}')
        )

        bull_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        prompt = llm.prompts[-1]
        assert prompt.startswith(FIRST_LINE_BULL)
        assert _estimate_tokens(prompt, settings) < settings.llm_tpm_limit

    def test_bear_renders_and_stays_under_the_ceiling(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = _worst_case_state(debate=_worst_transcript())
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_BEAR, make_reply('{"points": [], "concessions": [], "conviction": 0.5}')
        )

        bear_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        prompt = llm.prompts[-1]
        assert prompt.startswith(FIRST_LINE_BEAR)
        assert _estimate_tokens(prompt, settings) < settings.llm_tpm_limit


class TestTraderWorstCase:
    def test_trader_renders_with_two_earlier_vetoes_and_stays_under_the_ceiling(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        veto_verdict = RiskVerdict(
            decision="veto",
            reason="Size did not match the trader's stated confidence for this signal mix.",
            requested_shares=None,
            clamped=False,
            flagged=False,
        )
        earlier_attempts = [
            TradeAttempt(recommendation=_recommendation(), sized_order=_ORDER, verdict=veto_verdict)
            for _ in range(2)
        ]
        state = _worst_case_state(debate=_worst_transcript(), attempts=earlier_attempts)
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_TRADER,
            make_reply(
                '{"action": "buy", "target_weight": 0.05, "exit_style": "normal", '
                '"confidence": 0.5, "decisive_evidence": [], "reasoning": "ok"}'
            ),
        )

        trader_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        prompt = llm.prompts[-1]
        assert prompt.startswith(FIRST_LINE_TRADER)
        assert "Veto 1:" in prompt
        assert "Veto 2:" in prompt
        assert _estimate_tokens(prompt, settings) < settings.llm_tpm_limit


class TestRiskReviewWorstCase:
    def test_risk_review_renders_and_stays_under_the_ceiling(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        attempt = TradeAttempt(recommendation=_recommendation(), sized_order=_ORDER)
        state = _worst_case_state(debate=_worst_transcript(), attempts=[attempt])
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_RISK_REVIEW, make_reply('{"decision": "approve", "reason": "ok"}'))

        risk_review_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        prompt = llm.prompts[-1]
        assert prompt.startswith(FIRST_LINE_RISK_REVIEW)
        assert _estimate_tokens(prompt, settings) < settings.llm_tpm_limit
