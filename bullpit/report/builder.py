"""Builds the report: code fills every number, quoted LLM text is masked, and
Markdown is rendered from the structured object (architecture Part 12, sec7;
M5 specs-plan sec9 to sec11).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

import numpy as np
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.debate import final_conviction, transcript_lines
from bullpit.config import Settings
from bullpit.errors import LLMUnavailable, PromptTooLarge
from bullpit.llm.gateway import CompletionFn, Role, call_llm, litellm_completion
from bullpit.llm.schemas import DebateNarrativeReply, ReportProse, Signal
from bullpit.report.model import (
    AttemptRow,
    ClaimView,
    DataNotes,
    DebateNarrative,
    DebateSummary,
    DebateTurnView,
    MarketContext,
    ProseSource,
    Report,
    ReportOutcome,
)
from bullpit.report.number_check import (
    AllowedNumbers,
    allowed_numbers,
    check_text,
    mask_unknown_numbers,
)
from bullpit.state import DebateTurn, RequestState, TradeAttempt
from bullpit.tools.indicators import sma

_TEMPLATE = "report.md"
_NARRATIVE_TEMPLATE = "report_debate.md"
_SAFE_DEFAULT = ReportProse(
    summary="",
    strongest_bull="",
    strongest_bear="",
    bull_conceded="",
    unresolved="",
    would_change_view="",
)
_SPY_AVERAGE_SESSIONS = 200  # a named constant like M3's periods (D-M5-7)
_TEMPLATES_DIR = Path(__file__).parent / "templates"

_VixLabel = Literal["low", "normal", "high"]

# No digits, so the table can't widen the allowed-number set by accident.
_EXPLANATIONS: dict[tuple[bool | None, _VixLabel | None], str] = {
    (True, "low"): "The broad market is in an uptrend and calm.",
    (True, "normal"): "The broad market is in an uptrend with normal volatility.",
    (True, "high"): "The broad market is in an uptrend but volatility is high.",
    (False, "low"): "The broad market is in a downtrend, though volatility is low.",
    (False, "normal"): "The broad market is in a downtrend with normal volatility.",
    (False, "high"): "The broad market is in a downtrend and stressed.",
    (None, "low"): "The market trend is not available; volatility is low.",
    (None, "normal"): "The market trend is not available; volatility is normal.",
    (None, "high"): "The market trend is not available; volatility is high.",
    (True, None): "The broad market is in an uptrend; volatility is not available.",
    (False, None): "The broad market is in a downtrend; volatility is not available.",
    (None, None): "Market context not available.",
}


def _money(value: Decimal | float) -> str:
    return f"${value:,.2f}"


def _pct(value: Decimal | float) -> str:
    return f"{value:.1f}%"


def _num(value: Decimal | float | None) -> str:
    return "not available" if value is None else f"{value:,.2f}"


# Plain-text Markdown, not HTML, so autoescape would corrupt it (like the
# prompt templates in llm/gateway.py).
_env = Environment(  # noqa: S701
    loader=FileSystemLoader(_TEMPLATES_DIR),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
_env.filters.update(money=_money, pct=_pct, num=_num)


def market_context(
    spy_closes: Sequence[float], vix_close: float | None, *, vix_low: float, vix_high: float
) -> MarketContext:
    """Section 8 (M5-FR-4): SPY against its 200-session average and a VIX
    label; each part is `None` when its data is missing."""
    average = sma(np.asarray(spy_closes, dtype=float), _SPY_AVERAGE_SESSIONS)
    spy_close = spy_closes[-1] if spy_closes else None
    spy_above = None if average is None or spy_close is None else spy_close > average
    vix_label: _VixLabel | None
    if vix_close is None:
        vix_label = None
    elif vix_close < vix_low:
        vix_label = "low"
    elif vix_close > vix_high:
        vix_label = "high"
    else:
        vix_label = "normal"
    return MarketContext(
        spy_close=spy_close,
        spy_sma_200=average,
        spy_above=spy_above,
        vix_close=vix_close,
        vix_label=vix_label,
        explanation=_EXPLANATIONS[(spy_above, vix_label)],
    )


def _reason(state: RequestState) -> tuple[str | None, str | None]:
    """Code-written reason, plus the quoted LLM text for the two M4 reasons
    that carry it (M5-FR-2)."""
    if state.rejection is not None:
        return state.rejection, None
    if state.outcome != "no_trade":
        return None, None
    last = state.attempts[-1] if state.attempts else None
    if last is not None and last.blocked_reason is None:
        recommendation, verdict = last.recommendation, last.verdict
        if recommendation.action == "no_trade" and not recommendation.flagged and verdict is None:
            return "Trader recommended no trade.", recommendation.reasoning or None
        if verdict is not None and verdict.decision == "veto" and not verdict.flagged:
            vetoes = sum(
                1
                for attempt in state.attempts
                if attempt.verdict is not None and attempt.verdict.decision == "veto"
            )
            return f"Risk manager vetoed {vetoes} times.", verdict.reason or None
    return state.no_trade_reason, None


def _attempt_row(number: int, attempt: TradeAttempt) -> AttemptRow:
    recommendation, verdict = attempt.recommendation, attempt.verdict
    return AttemptRow(
        number=number,
        action=recommendation.action,
        target_weight=recommendation.target_weight,
        exit_style=recommendation.exit_style,
        confidence=recommendation.confidence,
        shares=None if attempt.sized_order is None else attempt.sized_order.shares,
        blocked_reason=attempt.blocked_reason,
        review_decision=None if verdict is None else verdict.decision,
        review_reason=None if verdict is None else verdict.reason or None,
        review_clamped=False if verdict is None else verdict.clamped,
    )


def _debate_summary(state: RequestState, prose: ReportProse | None) -> DebateSummary | None:
    if not state.debate:
        return None
    return DebateSummary(
        strongest_bull="" if prose is None else prose.strongest_bull,
        strongest_bear="" if prose is None else prose.strongest_bear,
        bull_conceded="" if prose is None else prose.bull_conceded,
        unresolved="" if prose is None else prose.unresolved,
        bull_conviction=final_conviction(state.debate, "bull"),
        bear_conviction=final_conviction(state.debate, "bear"),
        unsupported_points=sum(
            1 for turn in state.debate for point in turn.points if point.unsupported
        ),
    )


def _debate_turns(state: RequestState) -> list[DebateTurnView]:
    return [
        DebateTurnView(
            side=turn.side,
            round=turn.round,
            claims=[
                ClaimView(
                    text=point.claim,
                    evidence_ids=point.evidence_ids,
                    unsupported=point.unsupported,
                )
                for point in turn.points
            ],
            concessions=turn.concessions,
            conviction=turn.conviction,
        )
        for turn in state.debate
    ]


def _summaries(prose: ReportProse | None, signals: Sequence[Signal]) -> dict[str, str] | None:
    """The paragraphs the writer gave for the analysts that ran (FR-3)."""
    if prose is None:
        return None
    written = {
        signal.analyst: getattr(prose, f"{signal.analyst}_summary")
        for signal in signals
        if not signal.flagged
    }
    return {analyst: text for analyst, text in written.items() if text} or None


def _data_notes(state: RequestState, models: list[str]) -> DataNotes:
    sentiment = state.sentiment_signal
    fundamentals = state.fundamentals
    return DataNotes(
        models=models,
        news_headlines=(
            len(sentiment.evidence) if sentiment is not None and not sentiment.flagged else None
        ),
        filing_form=None if fundamentals is None else fundamentals.filing_form,
        filing_date=None if fundamentals is None else fundamentals.filing_date,
        price_source=None if state.prices is None else state.prices.source,
        warnings=list(state.warnings),
    )


def _mask(text: str | None, allowed: AllowedNumbers) -> str | None:
    return None if text is None else mask_unknown_numbers(text, allowed)


def build_report(
    state: RequestState,
    *,
    prose: ReportProse | None,
    prose_source: ProseSource,
    market: MarketContext | None,
    models: list[str],
    generated_at: datetime,
    narrative: DebateNarrative | None = None,
) -> Report:
    """The whole report from the final state (M5-FR-1 to FR-3). Quoted M4 text
    is masked against the numbers the code-written report shows (sec11.5)."""
    outcome: ReportOutcome
    if state.rejection is not None:
        outcome = "rejected"
    elif state.outcome is not None:
        outcome = state.outcome
    else:
        raise ValueError("report ran before the request reached an outcome")
    rejected = outcome == "rejected"
    reason, reason_detail = _reason(state)
    order = state.sized_order if outcome == "buy" else None
    equity = None if state.account is None else state.account.equity
    rows = [_attempt_row(number, a) for number, a in enumerate(state.attempts, start=1)]
    prose_summary = "" if prose is None else prose.summary
    signals = [
        signal
        for signal in (state.technical_signal, state.fundamentals_signal, state.sentiment_signal)
        if signal is not None
    ]
    live = state.mode == "live" and not rejected
    base = Report(
        request_id=state.request_id,
        ticker=state.ticker,
        company_name=state.company_name,
        mode=state.mode,
        as_of=state.as_of,
        generated_at=generated_at,
        outcome=outcome,
        confidence=state.attempts[-1].recommendation.confidence if state.attempts else None,
        summary=f"Rejected: {state.rejection}" if rejected else prose_summary,
        reason=reason,
        reason_detail=None,
        order=order,
        order_pct_of_equity=order.cost / equity * 100 if order is not None and equity else None,
        signals=signals,
        debate=_debate_summary(state, prose),
        attempts=[row.model_copy(update={"review_reason": None}) for row in rows],
        loss_warning=state.loss_warning,
        would_change_view=None if rejected or prose is None else prose.would_change_view,
        market=None if rejected else market,
        data_notes=_data_notes(state, models),
        prose_source=prose_source,
        analyst_summaries=_summaries(prose, signals) if live else None,
        board_score=state.board.score if live and state.board is not None else None,
        debate_turns=_debate_turns(state) if live and state.debate else None,
        debate_narrative=narrative if live else None,
    )
    allowed = allowed_numbers(render_markdown(base, for_prompt=True))
    return base.model_copy(
        update={
            "reason_detail": _mask(reason_detail, allowed),
            "attempts": [
                row.model_copy(update={"review_reason": _mask(row.review_reason, allowed)})
                for row in rows
            ],
        }
    )


def _side_ids(debate: list[DebateTurn], side: Literal["bull", "bear"]) -> list[str]:
    return sorted(
        {
            evidence_id
            for turn in debate
            if turn.side == side
            for point in turn.points
            if not point.unsupported
            for evidence_id in point.evidence_ids
        }
    )


def _case(side: Literal["bull", "bear"], debate: list[DebateTurn]) -> str:
    ids = _side_ids(debate, side)
    cited = ", ".join(ids) if ids else "no supported points"
    return f"The {side}'s case rests on {cited}."


def fallback_prose(report: Report, debate: list[DebateTurn]) -> ReportProse:
    """Template sentences built only from values the code-only report already
    shows, so they pass the number check by construction (M5-FR-7, sec11.3).
    `debate` is needed for the IDs each side cited, which the report omits."""
    if report.order is not None:
        summary = (
            f"Buy {report.order.shares} shares of {report.ticker}: "
            "the trader's recommendation passed the risk checks."
        )
        would_change = f"A close below {_money(report.order.stop_loss)} (the stop-loss)."
    else:
        summary = f"No trade: {report.reason}"
        would_change = "Stronger, agreeing analyst signals on a later request."
    analysts = {
        f"{signal.analyst}_summary": (
            f"{signal.analyst.capitalize()}: {signal.direction} with confidence "
            f"{signal.confidence:,.2f}. See the facts below."
        )
        for signal in report.signals
        if report.mode == "live" and not signal.flagged
    }
    if report.debate is None:
        return ReportProse(
            summary=summary,
            strongest_bull="",
            strongest_bear="",
            bull_conceded="",
            unresolved="",
            would_change_view=would_change,
            **analysts,
        )
    conceded = any(turn.concessions for turn in debate if turn.side == "bull")
    return ReportProse(
        summary=summary,
        strongest_bull=_case("bull", debate),
        strongest_bear=_case("bear", debate),
        bull_conceded=(
            "The bull made concessions during the debate."
            if conceded
            else "The bull made no concessions."
        ),
        unresolved="See the debate transcript.",
        would_change_view=would_change,
        **analysts,
    )


def render_markdown(report: Report, *, for_prompt: bool = False) -> str:
    """The owner-facing Markdown (sec11.4). `for_prompt` gives the code-only
    version the writing LLM sees: no prose, request ID or timestamp."""
    return _env.get_template("report.md").render(r=report, for_prompt=for_prompt)


def _masked_transcript(debate: list[DebateTurn], allowed: AllowedNumbers) -> list[str]:
    """The debate as the writer sees it: every number not in the report is
    `[?]` (D-M5-2). Only the text after the label is masked, so "round 1"
    survives."""
    lines = []
    for line in transcript_lines(debate):
        label, separator, text = line.partition(": ")
        lines.append(label + separator + mask_unknown_numbers(text, allowed))
    return lines


def _rejected_tokens(
    prose: ReportProse, allowed: AllowedNumbers, state: RequestState, analysts: list[str]
) -> list[str]:
    """Numbers and IDs in the reply that the report doesn't contain. The four
    debate fields are ignored, so unchecked, when there was no debate; so are the
    summaries of analysts that weren't asked about."""
    fields = [prose.summary, prose.would_change_view]
    fields += [getattr(prose, f"{analyst}_summary") for analyst in analysts]
    if state.debate:
        fields += [prose.strongest_bull, prose.strongest_bear, prose.bull_conceded]
        fields.append(prose.unresolved)
    registry = set() if state.board is None else set(state.board.evidence)
    rejected: list[str] = []
    for text in fields:
        rejected += [t for t in check_text(text, allowed, registry) if t not in rejected]
    return rejected


def _write_prose(
    code_only: Report,
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn,
) -> tuple[ReportProse, ProseSource, list[str]]:
    """One writing call, one retry naming the rejected tokens, then the code
    fallback (M5-FR-7, FR-9). Returns the prose, where it came from and the
    warnings for the data notes: a fallback, or a paragraph over its word limit."""
    allowed = allowed_numbers(render_markdown(code_only, for_prompt=True))
    analysts = [
        signal.analyst
        for signal in code_only.signals
        if code_only.mode == "live" and not signal.flagged
    ]
    variables = {
        "report_markdown": render_markdown(code_only, for_prompt=True),
        "transcript": _masked_transcript(state.debate, allowed),
        "analysts": analysts,
        "max_words": settings.report_paragraph_max_words,
    }
    fallback = fallback_prose(code_only, state.debate)
    rejected: list[str] = []
    for source in ("llm", "retry"):
        try:
            result = call_llm(
                Role.SMALL,
                _TEMPLATE,
                {**variables, "rejected": rejected},
                ReportProse,
                safe_default=_SAFE_DEFAULT,
                request_id=state.request_id,
                settings=settings,
                sessions=sessions,
                completion_fn=completion_fn,
            )
        except (LLMUnavailable, PromptTooLarge) as exc:
            return fallback, "fallback", [f"report wording written by code: {exc}"]
        if result.flagged:
            return fallback, "fallback", ["report wording written by code: LLM reply invalid"]
        rejected = _rejected_tokens(result.value, allowed, state, analysts)
        if not rejected:
            blank = {
                f"{analyst}_summary": getattr(fallback, f"{analyst}_summary")
                for analyst in analysts
                if not getattr(result.value, f"{analyst}_summary")
            }
            prose = result.value.model_copy(update=blank)  # a missed paragraph: code's sentence
            too_long = [
                analyst
                for analyst in analysts
                if len(getattr(prose, f"{analyst}_summary").split())
                > settings.report_paragraph_max_words
            ]
            warnings = [
                f"{analyst} summary is over {settings.report_paragraph_max_words} words"
                for analyst in too_long
            ]
            return prose, source, warnings
    return fallback, "fallback", [f"report wording written by code: rejected {', '.join(rejected)}"]


def _round_case(debate: list[DebateTurn], side: Literal["bull", "bear"], round_: int) -> str:
    ids = sorted(
        {
            evidence_id
            for turn in debate
            if turn.side == side and turn.round == round_
            for point in turn.points
            if not point.unsupported
            for evidence_id in point.evidence_ids
        }
    )
    return ", ".join(ids) if ids else "no supported points"


def fallback_narrative(
    report: Report, summary: DebateSummary, state: RequestState, rounds: int
) -> DebateNarrative:
    """Sentences built only from values the code-only report already shows, so
    they pass the number check by construction (M11.1-FR-7)."""
    conviction = [
        "not available" if value is None else f"{value:,.2f}"
        for value in (summary.bull_conviction, summary.bear_conviction)
    ]
    last = state.attempts[-1] if state.attempts else None
    verdict = None if last is None else last.verdict
    decision = report.reason or (
        "The trader recommended a buy."
        if report.outcome == "buy"
        else "The trader recommended no trade."
    )
    conclusion = (
        f"The final convictions were bull {conviction[0]} and bear {conviction[1]}. {decision}"
    )
    if verdict is not None and report.outcome == "buy":
        conclusion += f" The risk review's decision: {verdict.decision}."
    return DebateNarrative(
        rounds=[
            f"The bull argued from {_round_case(state.debate, 'bull', number)}; "
            f"the bear answered with {_round_case(state.debate, 'bear', number)}."
            for number in range(1, rounds + 1)
        ],
        conclusion=conclusion,
    )


def _write_narrative(
    code_only: Report,
    summary: DebateSummary,
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn,
) -> tuple[DebateNarrative, list[str]]:
    """The debate narrative: one small-model call, one retry naming what was
    rejected, then the code fallback (M11.1-FR-4, FR-7). Also returns the warnings
    for the data notes."""
    allowed = allowed_numbers(render_markdown(code_only, for_prompt=True))
    rounds = settings.debate_rounds
    fallback = fallback_narrative(code_only, summary, state, rounds)
    last = state.attempts[-1] if state.attempts else None
    verdict = None if last is None else last.verdict
    reasoning = "" if last is None else mask_unknown_numbers(last.recommendation.reasoning, allowed)
    variables = {
        "ticker": state.ticker,
        "decision": "buy" if code_only.outcome == "buy" else "no trade",
        "reason": code_only.reason,
        "transcript": _masked_transcript(state.debate, allowed),
        "bull_conviction": _num(summary.bull_conviction),
        "bear_conviction": _num(summary.bear_conviction),
        "reasoning": reasoning,
        "review": (
            "not reached"
            if verdict is None
            else f"{verdict.decision}, {mask_unknown_numbers(verdict.reason, allowed)}"
        ),
        "rounds": rounds,
        "max_words": settings.report_paragraph_max_words,
    }
    registry = set() if state.board is None else set(state.board.evidence)
    rejected: list[str] = []
    for _ in ("llm", "retry"):
        try:
            result = call_llm(
                Role.SMALL,
                _NARRATIVE_TEMPLATE,
                {**variables, "rejected": rejected},
                DebateNarrativeReply,
                safe_default=DebateNarrativeReply(rounds=[], conclusion=""),
                request_id=state.request_id,
                settings=settings,
                sessions=sessions,
                completion_fn=completion_fn,
            )
        except (LLMUnavailable, PromptTooLarge) as exc:
            return fallback, [f"debate narrative written by code: {exc}"]
        if result.flagged:
            return fallback, ["debate narrative written by code: LLM reply invalid"]
        reply = result.value
        rejected = [] if len(reply.rounds) == rounds else [f"{len(reply.rounds)} round paragraphs"]
        for text in [*reply.rounds, reply.conclusion]:
            rejected += [t for t in check_text(text, allowed, registry) if t not in rejected]
        if not rejected:
            limit = settings.report_paragraph_max_words
            too_long = sum(len(text.split()) > limit for text in [*reply.rounds, reply.conclusion])
            warnings = [f"{too_long} debate paragraphs are over {limit} words"] if too_long else []
            return DebateNarrative(rounds=reply.rounds, conclusion=reply.conclusion), warnings
    return fallback, [f"debate narrative written by code: rejected {', '.join(rejected)}"]


def report_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    market: MarketContext | None,
    generated_at: datetime,
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    """The last graph node (M5-FR-5 to FR-9). A rejected request gets a
    code-only report and no LLM call; every other one gets the LLM's wording
    if it passes the number check, else the code fallback."""
    if state.rejection is not None:
        report = build_report(
            state,
            prose=None,
            prose_source="none",
            market=None,
            models=[],
            generated_at=generated_at,
        )
        return {"report": report}

    models = [settings.llm_small_model]
    if state.debate:
        models.append(settings.llm_large_model)
    code_only = build_report(
        state,
        prose=None,
        prose_source="none",
        market=market,
        models=models,
        generated_at=generated_at,
    )
    prose, source, new_warnings = _write_prose(
        code_only, state, settings=settings, sessions=sessions, completion_fn=completion_fn
    )
    narrative = None
    debate = code_only.debate
    if state.mode == "live" and debate is not None:
        narrative, narrative_warnings = _write_narrative(
            code_only,
            debate,
            state,
            settings=settings,
            sessions=sessions,
            completion_fn=completion_fn,
        )
        new_warnings = [*new_warnings, *narrative_warnings]
    report = build_report(
        state,
        prose=prose,
        prose_source=source,
        market=market,
        models=models,
        generated_at=generated_at,
        narrative=narrative,
    )
    if not new_warnings:
        return {"report": report, "warnings": state.warnings}
    # Added after masking: a warning may name rejected tokens, and they must not
    # join the allowed set the quoted M4 text was masked against.
    warnings = [*state.warnings, *new_warnings]
    notes = report.data_notes.model_copy(update={"warnings": warnings})
    return {"report": report.model_copy(update={"data_notes": notes}), "warnings": warnings}
