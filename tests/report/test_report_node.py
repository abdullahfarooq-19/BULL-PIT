"""Report writing step (M5-AC-3): a clean reply is used, an invented number
or unknown ID gets one retry that names it, a second failure or a flagged
reply gets the code fallback."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.report.builder import market_context, render_markdown, report_node
from bullpit.report.model import Report
from bullpit.report.number_check import allowed_numbers, check_text
from bullpit.state import RequestState
from tests.agents.conftest import ScriptedLLM, make_reply
from tests.report.test_builder import _state, _technical_failed

_FIRST_LINE = "You are the report writer"
_RETRY_MARK = "Your previous draft used numbers or IDs that are not in the report"
_NARRATIVE_FIRST_LINE = "You are the debate narrator"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """The gateway's real pacing must never sleep through a scripted retry."""
    return settings.model_copy(update={"llm_tpm_limit": 1_000_000, "llm_rpm_limit": 1_000})


def _prose(**overrides: str) -> str:
    fields = {
        "summary": "Buy 32 shares of AAPL, backed by the trend (T1).",
        "strongest_bull": "The trend is intact (T1).",
        "strongest_bear": "Sentiment is weak (S1).",
        "bull_conceded": "The bull conceded the momentum risk.",
        "unresolved": "How much the news matters.",
        "would_change_view": "A close below $174.00.",
    }
    return json.dumps({**fields, **overrides})


def _narrative_fields() -> dict[str, object]:
    return {
        "rounds": ["The bull pressed the trend (T1); the bear pointed to the news (S1)."] * 2,
        "conclusion": "The convictions were bull 0.70 and bear 0.60, so the trader went on.",
    }


def _narrative(**overrides: object) -> str:
    """A clean debate narrative for a two-round debate."""
    return json.dumps({**_narrative_fields(), **overrides})


def _run(
    llm: ScriptedLLM,
    settings: Settings,
    sessions: sessionmaker[Session],
    kind: str = "buy",
    mode: str = "backtest",
    state: RequestState | None = None,
    narrative: str | None = None,
) -> tuple[Report, dict[str, object], RequestState]:
    """Runs the report node. A live debated report makes the narrative call too: it is
    answered with `narrative`, or a clean one."""
    state = (state or _state(kind)).model_copy(update={"mode": mode})
    if mode == "live" and state.debate:
        llm.queue(_NARRATIVE_FIRST_LINE, make_reply(narrative or _narrative()))
    result = report_node(
        state,
        settings=settings,
        sessions=sessions,
        market=market_context([100.0] * 250, 20.0, vix_low=15.0, vix_high=25.0),
        generated_at=datetime(2024, 10, 18, 21, 0, tzinfo=UTC),
        completion_fn=llm,
    )
    report = result["report"]
    assert isinstance(report, Report)
    return report, result, state


def test_clean_reply_is_used(settings: Settings, sessions: sessionmaker[Session]) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose()))

    report, _, _ = _run(llm, settings, sessions)

    assert report.prose_source == "llm"
    assert report.summary == "Buy 32 shares of AAPL, backed by the trend (T1)."
    assert report.would_change_view == "A close below $174.00."
    assert len(llm.prompts) == 1
    assert "openai/gpt-oss-120b" in report.data_notes.models


def test_invented_number_is_retried_with_the_token_named(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(summary="Target $200 looks reachable.")))
    llm.queue(_FIRST_LINE, make_reply(_prose()))

    report, _, _ = _run(llm, settings, sessions)

    assert report.prose_source == "retry"
    assert _RETRY_MARK not in llm.prompts[0]
    assert _RETRY_MARK in llm.prompts[1]
    assert "$200" in llm.prompts[1]


def test_second_failure_falls_back_with_a_warning(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(unresolved="See T99.")))
    llm.queue(_FIRST_LINE, make_reply(_prose(unresolved="See T99 again.")))

    report, result, _ = _run(llm, settings, sessions)

    assert report.prose_source == "fallback"
    assert (
        report.summary
        == "Buy 32 shares of AAPL: the trader's recommendation passed the risk checks."
    )
    assert any("T99" in warning for warning in report.data_notes.warnings)
    assert result["warnings"] == report.data_notes.warnings


def test_flagged_reply_falls_back_without_a_retry(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply("not json"))
    llm.queue(_FIRST_LINE, make_reply("still not json"))

    report, _, _ = _run(llm, settings, sessions)

    assert report.prose_source == "fallback"
    assert not any(_RETRY_MARK in prompt for prompt in llm.prompts)


def test_fallback_warning_does_not_unmask_quoted_text(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    """The trader's quoted "40%" is masked; the writer repeating it twice makes
    the fallback warning name it, and that must not unmask the quote."""
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(summary="The bear case is 40% stronger.")))
    llm.queue(_FIRST_LINE, make_reply(_prose(summary="Still 40% stronger.")))

    report, _, _ = _run(llm, settings, sessions, kind="trader_no_trade")

    assert report.prose_source == "fallback"
    assert any("40%" in warning for warning in report.data_notes.warnings)
    assert report.reason_detail == "Bear case is [?] stronger."


_SUMMARIES = {
    "technical_summary": "Prices sit above their averages, so the trend is up (T1).",
    "fundamentals_summary": "Profits are steady but not growing fast (F1).",
    "sentiment_summary": "Recent headlines lean negative (S1).",
}


def test_live_report_gets_the_analyst_paragraphs(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**_SUMMARIES)))

    report, _, _ = _run(llm, settings, sessions, mode="live")

    assert report.prose_source == "llm"
    assert report.analyst_summaries == {
        "technical": _SUMMARIES["technical_summary"],
        "fundamentals": _SUMMARIES["fundamentals_summary"],
        "sentiment": _SUMMARIES["sentiment_summary"],
    }
    assert "technical_summary" in llm.prompts[0] and "at most 110 words" in llm.prompts[0]


def test_a_backtest_report_asks_for_no_paragraphs(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose()))

    report, _, _ = _run(llm, settings, sessions, mode="backtest")

    assert len(llm.prompts) == 1  # the same single call as before M11.1
    assert "_summary" not in llm.prompts[0]
    assert report.analyst_summaries is None and report.debate_turns is None


def test_a_failed_analyst_is_not_asked_about(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**_SUMMARIES)))

    report, _, _ = _run(
        llm, settings, sessions, mode="live", state=_technical_failed(_state("buy"))
    )

    assert "technical_summary" not in llm.prompts[0]
    assert report.analyst_summaries is not None
    assert list(report.analyst_summaries) == ["fundamentals", "sentiment"]


@pytest.mark.parametrize("bad", ["The price will reach $200 soon (T1).", "A clear trend (T99)."])
def test_an_invented_number_or_id_in_a_paragraph_is_retried_then_replaced(
    settings: Settings, sessions: sessionmaker[Session], bad: str
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**{**_SUMMARIES, "technical_summary": bad})))
    llm.queue(_FIRST_LINE, make_reply(_prose(**{**_SUMMARIES, "technical_summary": bad})))

    report, _, _ = _run(llm, settings, sessions, mode="live")

    assert report.prose_source == "fallback"
    assert report.analyst_summaries is not None
    assert report.analyst_summaries["technical"] == (
        "Technical: bullish with confidence 0.60. See the facts below."
    )
    assert _RETRY_MARK in llm.prompts[1] and ("$200" in llm.prompts[1] or "T99" in llm.prompts[1])


def test_a_clean_retry_is_used_for_a_paragraph(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**{**_SUMMARIES, "technical_summary": "Up $99."})))
    llm.queue(_FIRST_LINE, make_reply(_prose(**_SUMMARIES)))

    report, _, _ = _run(llm, settings, sessions, mode="live")

    assert report.prose_source == "retry"
    assert report.analyst_summaries is not None
    assert report.analyst_summaries["technical"] == _SUMMARIES["technical_summary"]


def test_a_long_paragraph_is_kept_and_warned_about(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    long = " ".join(["steady"] * 120)
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**{**_SUMMARIES, "sentiment_summary": long})))

    report, result, _ = _run(llm, settings, sessions, mode="live")

    assert report.analyst_summaries is not None
    assert report.analyst_summaries["sentiment"] == long  # never truncated
    assert report.data_notes.warnings == ["sentiment summary is over 110 words"]
    assert result["warnings"] == report.data_notes.warnings


def test_a_missed_paragraph_is_written_by_code(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**{**_SUMMARIES, "technical_summary": ""})))

    report, _, _ = _run(llm, settings, sessions, mode="live")

    assert report.prose_source == "llm"
    assert report.analyst_summaries is not None
    assert report.analyst_summaries["technical"] == (
        "Technical: bullish with confidence 0.60. See the facts below."
    )
    assert report.analyst_summaries["sentiment"] == _SUMMARIES["sentiment_summary"]


def test_a_debated_live_report_gets_a_narrative(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**_SUMMARIES)))

    report, _, _ = _run(llm, settings, sessions, mode="live")

    assert report.debate_narrative is not None
    assert len(report.debate_narrative.rounds) == 2
    assert "bull 0.70 and bear 0.60" in report.debate_narrative.conclusion
    assert len(llm.prompts) == 2  # the report call, then the narrative call
    narrator = llm.prompts[1]
    assert narrator.startswith(_NARRATIVE_FIRST_LINE)
    assert "Final convictions: bull 0.70, bear 0.60." in narrator
    assert "exactly 2 paragraphs" in narrator and "Bull, round 1: A claim (T1)" in narrator


def test_a_skipped_debate_has_no_narrative(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(
        _FIRST_LINE,
        make_reply(
            _prose(
                summary="No trade: the signals are weak.",
                would_change_view="Stronger signals.",
                **_SUMMARIES,
            )
        ),
    )

    report, _, _ = _run(llm, settings, sessions, kind="weak", mode="live")

    assert report.debate_narrative is None and report.debate_turns is None
    assert len(llm.prompts) == 1


@pytest.mark.parametrize(
    "bad",
    [
        {"conclusion": "The stock could reach $200 (T1)."},
        {"rounds": ["The bull cited T99.", "The bear replied."]},
        {"rounds": ["Only one round was written."]},
    ],
    ids=["invented-number", "unknown-id", "wrong-round-count"],
)
def test_a_bad_narrative_is_retried_once_then_used(
    settings: Settings, sessions: sessionmaker[Session], bad: dict[str, object]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**_SUMMARIES)))
    llm.queue(_NARRATIVE_FIRST_LINE, make_reply(_narrative(**bad)))

    report, _, _ = _run(llm, settings, sessions, mode="live")

    assert report.debate_narrative is not None
    assert report.debate_narrative.conclusion == _narrative_fields()["conclusion"]
    assert len(llm.prompts) == 3
    assert "was rejected for" in llm.prompts[2]
    assert not report.data_notes.warnings


def test_a_twice_bad_narrative_is_written_by_code(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    bad = _narrative(conclusion="The stock could reach $200.")
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**_SUMMARIES)))
    llm.queue(_NARRATIVE_FIRST_LINE, make_reply(bad))

    report, result, state = _run(llm, settings, sessions, mode="live", narrative=bad)

    narrative = report.debate_narrative
    assert narrative is not None
    assert narrative.rounds == [
        "The bull argued from T1; the bear answered with T1.",
        "The bull argued from T1; the bear answered with T1.",
    ]
    assert narrative.conclusion == (
        "The final convictions were bull 0.70 and bear 0.60. The trader recommended a buy. "
        "The risk review's decision: approve."
    )
    assert any(
        "debate narrative written by code: rejected $200" in w for w in report.data_notes.warnings
    )
    assert result["warnings"] == report.data_notes.warnings
    allowed = allowed_numbers(render_markdown(report, for_prompt=True))
    registry = set(state.board.evidence) if state.board else set()
    for text in [*narrative.rounds, narrative.conclusion]:
        assert check_text(text, allowed, registry) == []


def test_an_invalid_narrative_reply_falls_back_with_a_warning(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**_SUMMARIES)))
    llm.queue(_NARRATIVE_FIRST_LINE, make_reply("not json"))

    report, _, _ = _run(llm, settings, sessions, mode="live", narrative="still not json")

    assert report.debate_narrative is not None
    assert report.data_notes.warnings == ["debate narrative written by code: LLM reply invalid"]


def test_a_long_narrative_paragraph_is_kept_and_warned_about(
    settings: Settings, sessions: sessionmaker[Session]
) -> None:
    long = " ".join(["steady"] * 120)
    llm = ScriptedLLM()
    llm.queue(_FIRST_LINE, make_reply(_prose(**_SUMMARIES)))

    report, _, _ = _run(llm, settings, sessions, mode="live", narrative=_narrative(conclusion=long))

    assert report.debate_narrative is not None
    assert report.debate_narrative.conclusion == long
    assert report.data_notes.warnings == ["1 debate paragraphs are over 110 words"]
