"""Report builder (M5-AC-1, AC-2 automated half, AC-5, AC-6): the sections and
reason for each way a request can end, the architecture's example card, that
every number a reader sees is traceable, and market context."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from bullpit.domain import SizedOrder
from bullpit.report.builder import (
    build_report,
    fallback_prose,
    market_context,
    render_markdown,
)
from bullpit.report.model import MarketContext, Report
from bullpit.report.number_check import allowed_numbers, check_text
from bullpit.risk.sizing import build_order
from bullpit.state import (
    CheckedPoint,
    DebateTurn,
    Recommendation,
    RequestState,
    RiskVerdict,
    TradeAttempt,
)
from tests.agents.conftest import AS_OF, make_board_state

_NOW = datetime(2024, 10, 18, 21, 0, tzinfo=UTC)
_MARKET = market_context([100.0] * 250, 20.0, vix_low=15.0, vix_high=25.0)
_HEADINGS = [
    "## Recommendation",
    "## Suggested order",
    "## What the analysts found",
    "## The debate",
    "## Risk manager",
    "## What would change the view",
    "## Market context",
    "## Data notes",
    "## Actions",
]
_DISCLAIMER = "*Research, not financial advice. Paper trading only.*"


def _order(shares: int = 32) -> SizedOrder:
    return build_order(
        "AAPL",
        shares,
        reference=Decimal("182"),
        stop=Decimal("174"),
        take_profit=Decimal("194"),
        exit_style="normal",
        limit="target",
        limit_shares={"target": 32, "risk": 125, "cap": 54, "cash": 527},
    )


def _recommendation(action: str = "buy", reasoning: str = "Trend and margins.") -> Recommendation:
    return Recommendation(
        ticker="AAPL",
        action=action,  # type: ignore[arg-type]
        target_weight=Decimal("0.06"),
        exit_style="normal",
        confidence=0.62,
        decisive_evidence=["T1", "F2"],
        reasoning=reasoning,
        flagged=False,
    )


def _veto(reason: str) -> RiskVerdict:
    return RiskVerdict(
        decision="veto", reason=reason, requested_shares=None, clamped=False, flagged=False
    )


def _turns() -> list[DebateTurn]:
    def turn(side: str, round_number: int, conviction: float, concessions: list[str]) -> DebateTurn:
        return DebateTurn(
            side=side,  # type: ignore[arg-type]
            round=round_number,
            points=[CheckedPoint(claim="A claim", evidence_ids=["T1"], unsupported=False)],
            concessions=concessions,
            conviction=conviction,
            word_count=3,
            over_word_limit=False,
            flagged=False,
        )

    return [
        turn("bull", 1, 0.7, []),
        turn("bear", 1, 0.6, []),
        turn("bull", 2, 0.7, ["RSI is high"]),
        turn("bear", 2, 0.6, []),
    ]


def _state(kind: str) -> RequestState:
    if kind == "rejected":
        return RequestState(
            request_id="20241018-SPY-test",
            mode="backtest",
            as_of=AS_OF,
            ticker="SPY",
            rejection="SPY is an ETF: no SEC filings found.",
        )
    if kind == "weak":
        return make_board_state(
            route="no_trade",
            outcome="no_trade",
            no_trade_reason="Signals too weak for a debate (board score +0.05, no conflict).",
        )
    if kind == "buy":
        attempt = TradeAttempt(
            recommendation=_recommendation(),
            sized_order=_order(),
            verdict=RiskVerdict(
                decision="approve",
                reason="Size is fine, RSI 70.1 and $999 stop.",
                requested_shares=None,
                clamped=False,
                flagged=False,
            ),
        )
        return make_board_state(
            debate=_turns(), attempts=[attempt], sized_order=_order(), outcome="buy"
        )
    if kind == "trader_no_trade":
        attempt = TradeAttempt(
            recommendation=_recommendation("no_trade", "Bear case is 40% stronger.")
        )
        return make_board_state(
            debate=_turns(),
            attempts=[attempt],
            outcome="no_trade",
            no_trade_reason="Trader recommended no trade: Bear case is 40% stronger.",
        )
    if kind == "stage_a_block":
        blocked = "Per-stock cap reached: AAPL is already 12.0% of equity (cap 10%)."
        attempt = TradeAttempt(recommendation=_recommendation(), blocked_reason=blocked)
        return make_board_state(
            debate=_turns(), attempts=[attempt], outcome="no_trade", no_trade_reason=blocked
        )
    attempts = [
        TradeAttempt(
            recommendation=_recommendation(), sized_order=_order(), verdict=_veto(f"Veto {n}, $999")
        )
        for n in range(3)
    ]
    return make_board_state(
        debate=_turns(),
        attempts=attempts,
        outcome="no_trade",
        no_trade_reason="Risk manager vetoed 3 times: Veto 2, $999",
    )


def _report(state: RequestState, market: MarketContext | None = _MARKET) -> Report:
    """As `report_node` builds it: code-only first, then the fallback prose."""
    models = [] if state.rejection else ["openai/gpt-oss-20b"]
    code_only = build_report(
        state, prose=None, prose_source="none", market=market, models=models, generated_at=_NOW
    )
    prose = None if state.rejection else fallback_prose(code_only, state.debate)
    return build_report(
        state,
        prose=prose,
        prose_source="none" if prose is None else "fallback",
        market=market,
        models=models,
        generated_at=_NOW,
    )


_KINDS = {
    "buy": _HEADINGS,
    "weak": [_HEADINGS[i] for i in (0, 2, 5, 6, 7)],
    "trader_no_trade": [_HEADINGS[i] for i in (0, 2, 3, 4, 5, 6, 7)],
    "stage_a_block": [_HEADINGS[i] for i in (0, 2, 3, 4, 5, 6, 7)],
    "veto_limit": [_HEADINGS[i] for i in (0, 2, 3, 4, 5, 6, 7)],
    "rejected": [_HEADINGS[0], _HEADINGS[7]],
}


def test_example_card() -> None:
    markdown = render_markdown(_report(_state("buy")))
    for expected in (
        "# AAPL, Apple Inc.: Buy",
        "confidence 0.62",
        "32 shares, about $5,824.00 (5.8% of equity)",
        "$174.00, maximum loss about $256.00",
        "$194.00, possible gain about $384.00",
        "Stage A size set by the target limit.",
        "| technical | bullish | 0.60 |",
        "| fundamentals | neutral | 0.40 |",
        "| sentiment | bearish | 0.50 |",
        "Approve up to 32 shares, or reject.",
    ):
        assert expected in markdown


@pytest.mark.parametrize("kind", _KINDS)
def test_sections_per_outcome(kind: str) -> None:
    report = _report(_state(kind))
    markdown = render_markdown(report)

    present = [heading for heading in _HEADINGS if heading in markdown]
    assert present == _KINDS[kind]
    assert [markdown.index(heading) for heading in present] == sorted(
        markdown.index(heading) for heading in present
    )
    assert markdown.rstrip().endswith(_DISCLAIMER)

    expected_reason = {
        "buy": None,
        "weak": "Signals too weak for a debate (board score +0.05, no conflict).",
        "trader_no_trade": "Trader recommended no trade.",
        "stage_a_block": "Per-stock cap reached: AAPL is already 12.0% of equity (cap 10%).",
        "veto_limit": "Risk manager vetoed 3 times.",
        "rejected": "SPY is an ETF: no SEC filings found.",
    }[kind]
    assert report.reason == expected_reason
    assert report.outcome == {"buy": "buy", "rejected": "rejected"}.get(kind, "no_trade")
    if kind == "rejected":
        assert report.summary == "Rejected: SPY is an ETF: no SEC filings found."
        assert report.market is None
    assert (report.reason_detail is not None) == (kind in {"trader_no_trade", "veto_limit"})
    if kind == "trader_no_trade":
        assert report.reason_detail == "Bear case is [?] stronger."
        assert "Trader recommended no trade." in markdown
        assert "Bear case is [?] stronger." in markdown


@pytest.mark.parametrize("kind", ["buy", "trader_no_trade", "veto_limit", "weak"])
def test_every_number_traceable(kind: str) -> None:
    state = _state(kind)
    report = _report(state)
    code_only = report.model_copy(update={"summary": ""})
    allowed = allowed_numbers(render_markdown(code_only, for_prompt=True))
    registry = set(state.board.evidence) if state.board else set()

    prose = fallback_prose(code_only, state.debate)
    texts = [*prose.model_dump().values(), report.reason_detail]
    texts += [attempt.review_reason for attempt in report.attempts]
    for text in texts:
        assert check_text(text or "", allowed, registry) == []

    if kind == "veto_limit":
        assert report.reason_detail == "Veto 2, [?]"
        assert all(
            attempt.review_reason and "[?]" in attempt.review_reason for attempt in report.attempts
        )
    if kind == "buy":
        assert report.attempts[0].review_reason == "Size is fine, RSI [?] and [?] stop."


@pytest.mark.parametrize(
    ("closes", "vix", "above", "label"),
    [
        ([100.0] * 199 + [110.0], 10.0, True, "low"),
        ([100.0] * 199 + [90.0], 20.0, False, "normal"),
        ([100.0] * 199 + [110.0], 30.0, True, "high"),
        ([100.0] * 199 + [110.0], 15.0, True, "normal"),
        ([100.0] * 199 + [110.0], 25.0, True, "normal"),
        ([100.0] * 199, 20.0, None, "normal"),
        ([100.0] * 199 + [110.0], None, True, None),
        ([], None, None, None),
    ],
)
def test_market_context(
    closes: list[float], vix: float | None, above: bool | None, label: str | None
) -> None:
    context = market_context(closes, vix, vix_low=15.0, vix_high=25.0)
    assert context.spy_above is above
    assert context.vix_label == label
    assert context.explanation
    assert (context.spy_sma_200 is None) == (above is None)
    if above is None and label is None:
        assert context.explanation == "Market context not available."


_SUMMARIES = ["technical", "fundamentals", "sentiment"]


def _live(state: RequestState) -> RequestState:
    return state.model_copy(update={"mode": "live"})


def _technical_failed(state: RequestState) -> RequestState:
    assert state.technical_signal is not None
    signal = state.technical_signal.model_copy(
        update={
            "direction": "neutral",
            "confidence": 0.0,
            "evidence": [],
            "flagged": True,
            "note": "analyst failed: boom",
        }
    )
    return state.model_copy(update={"technical_signal": signal})


@pytest.mark.parametrize(
    ("kind", "live", "failed", "summaries", "turns"),
    [
        ("buy", True, False, _SUMMARIES, True),
        ("trader_no_trade", True, False, _SUMMARIES, True),
        ("weak", True, False, _SUMMARIES, False),
        ("buy", True, True, ["fundamentals", "sentiment"], True),
        ("buy", False, False, None, False),
        ("rejected", True, False, None, False),
    ],
)
def test_report_modes(
    kind: str, live: bool, failed: bool, summaries: list[str] | None, turns: bool
) -> None:
    """Live reports carry the analyst paragraphs, the board score and the debate's
    turns; a failed analyst gets no paragraph; backtest and rejected reports carry
    none of them (M11.1-AC-1, AC-3)."""
    state = _state(kind)
    state = _technical_failed(state) if failed else state
    state = _live(state) if live else state

    report = _report(state)

    assert (
        None if report.analyst_summaries is None else list(report.analyst_summaries)
    ) == summaries
    if summaries is None:
        assert report.board_score is None
    else:
        assert state.board is not None and report.board_score == state.board.score
        assert report.analyst_summaries is not None
        assert report.analyst_summaries.get("fundamentals") == (
            "Fundamentals: neutral with confidence 0.40. See the facts below."
        )
    assert (report.debate_turns is not None) == turns
    if turns:
        assert report.debate_turns is not None
        assert [(t.side, t.round) for t in report.debate_turns] == [
            ("bull", 1),
            ("bear", 1),
            ("bull", 2),
            ("bear", 2),
        ]
        first = report.debate_turns[0]
        assert (first.claims[0].text, first.claims[0].evidence_ids) == ("A claim", ["T1"])
        assert (first.claims[0].unsupported, first.conviction) == (False, 0.7)
        assert report.debate_turns[2].concessions == ["RSI is high"]


def test_m8_report_json_still_loads() -> None:
    """A report stored by M8 (captured from its unchanged model) validates, with
    every M11.1 field unset (M11.1-AC-17d)."""
    stored = json.loads(
        (Path(__file__).parent.parent / "fixtures" / "reports" / "m8_buy_report.json").read_text(
            encoding="utf-8"
        )
    )

    report = Report.model_validate(stored)

    assert (report.ticker, report.outcome, report.order is not None) == ("AAPL", "buy", True)
    assert report.analyst_summaries is None
    assert report.board_score is None
    assert report.debate_turns is None
