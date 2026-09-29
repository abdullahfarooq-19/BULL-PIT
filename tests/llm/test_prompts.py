"""The four M4 prompt templates (M4-AC-13) and the M5 report writer
(M5-AC-10): each renders from its owner's own variable-building code, starts
with its fixed first line, has no Jinja `include`, and a worst-case prompt
stays under the per-call token ceiling (NFR-3).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.debate import bear_node, bull_node
from bullpit.agents.risk_review import risk_review_node
from bullpit.agents.trader import exit_style_descriptions, trader_node
from bullpit.config import Settings
from bullpit.domain import SizedOrder
from bullpit.llm.gateway import _estimate_tokens, _render
from bullpit.llm.schemas import Evidence, Signal
from bullpit.report.builder import market_context, report_node
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
FIRST_LINE_REPORT = "You are the report writer"
_TEMPLATES = ("bull.md", "bear.md", "trader.md", "risk_review.md", "report.md")

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
    def test_templates_have_no_jinja_include(self) -> None:
        for name in _TEMPLATES:
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


class TestReportWorstCase:
    def test_report_renders_and_stays_under_the_ceiling(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        """15 headlines, a full 4-turn transcript of 150-word points, and 3
        vetoed attempts with long reasons (M5-NFR-2)."""
        veto = RiskVerdict(
            decision="veto",
            reason=_long_claim(40),
            requested_shares=None,
            clamped=False,
            flagged=False,
        )
        attempts = [
            TradeAttempt(recommendation=_recommendation(), sized_order=_ORDER, verdict=veto)
            for _ in range(3)
        ]
        turns = [
            _worst_transcript()[i % 3].model_copy(update={"side": side, "round": i // 2 + 1})
            for i, side in enumerate(("bull", "bear", "bull", "bear"))
        ]
        state = _worst_case_state(
            debate=turns,
            attempts=attempts,
            outcome="no_trade",
            no_trade_reason="Risk manager vetoed 3 times: " + _long_claim(40),
            warnings=["a data warning of some length"] * 5,
        )
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_REPORT,
            make_reply(
                '{"summary": "s", "strongest_bull": "", "strongest_bear": "", '
                '"bull_conceded": "", "unresolved": "", "would_change_view": "w"}'
            ),
        )

        report_node(
            state,  # type: ignore[arg-type]
            settings=settings,
            sessions=sessions,
            market=market_context([100.0] * 250, 20.0, vix_low=15.0, vix_high=25.0),
            generated_at=datetime(2024, 10, 18, 21, 0, tzinfo=UTC),
            completion_fn=llm,
        )

        prompt = llm.prompts[0]
        assert prompt.startswith(FIRST_LINE_REPORT)
        assert _estimate_tokens(prompt, settings) < settings.llm_tpm_limit


class TestSingleAgentWorstCase:
    def test_single_agent_with_every_fact_stays_under_the_ceiling(self, settings: Settings) -> None:
        facts = [f"T{i}" for i in range(1, 7)] + [f"F{i}" for i in range(1, 6)]
        evidence = [{"id": fact_id, "fact": "A" * 120} for fact_id in facts]
        evidence += [
            {"id": f"S{i}", "fact": "2026-08-21: " + '"' + "A" * 120 + '"'} for i in range(1, 16)
        ]

        prompt, _ = _render(
            "single_agent.md",
            {
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "evidence": evidence,
                "cash": Decimal("96000"),
                "equity": Decimal("100000"),
                "held_value": Decimal("4000"),
                "held_pct": 4.0,
                "max_target_weight_pct": 10.0,
                "exit_styles": exit_style_descriptions(settings),
            },
        )

        assert prompt.startswith("You are a single analyst-trader")
        assert _estimate_tokens(prompt, settings) < settings.llm_tpm_limit
