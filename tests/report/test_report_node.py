"""Report writing step (M5-AC-3): a clean reply is used, an invented number
or unknown ID gets one retry that names it, a second failure or a flagged
reply gets the code fallback."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.report.builder import market_context, report_node
from bullpit.report.model import Report
from bullpit.state import RequestState
from tests.agents.conftest import ScriptedLLM, make_reply
from tests.report.test_builder import _state

_FIRST_LINE = "You are the report writer"
_RETRY_MARK = "Your previous draft used numbers or IDs that are not in the report"


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


def _run(
    llm: ScriptedLLM, settings: Settings, sessions: sessionmaker[Session], kind: str = "buy"
) -> tuple[Report, dict[str, object], RequestState]:
    state = _state(kind)
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
