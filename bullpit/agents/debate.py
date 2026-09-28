"""Bull vs bear debate: two rounds, bull first (architecture Part 9;
M4-FR-2 to FR-4; D-M4-1, D-M4-3, D-M4-4).

Bull and bear share one `_turn` function and the same code checks; only the
prompt template and the round's task differ. Code assigns evidence-ID
citations their `unsupported` flag and counts words; the LLM never decides
whether its own claim is supported.
"""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.llm.gateway import CompletionFn, Role, call_llm, litellm_completion
from bullpit.llm.schemas import DebatePoint, DebateReply, Evidence
from bullpit.state import CheckedPoint, DebateTurn, RequestState, SignalsBoard

_Side = Literal["bull", "bear"]

_TEMPLATES: dict[_Side, str] = {"bull": "bull.md", "bear": "bear.md"}
_TASKS: dict[tuple[_Side, int], str] = {
    ("bull", 1): "State your three strongest points for buying.",
    ("bear", 1): "Rebut each bull point and add counter-evidence.",
    ("bull", 2): "Answer the bear's attacks.",
    ("bear", 2): "Give your final response.",
}
_SAFE_DEFAULT = DebateReply(points=[], concessions=[], conviction=0.0)


def _signals_summary(board: SignalsBoard) -> list[dict[str, object]]:
    return [
        {
            "analyst": analyst,
            "direction": signal.direction,
            "confidence": signal.confidence,
            "flagged": signal.flagged,
        }
        for analyst, signal in board.signals.items()
    ]


def _evidence_list(board: SignalsBoard) -> list[dict[str, str]]:
    return [
        {"id": item.id, "fact": item.fact}
        for item in sorted(board.evidence.values(), key=lambda item: item.id)
    ]


def _transcript_lines(turns: list[DebateTurn]) -> list[str]:
    lines: list[str] = []
    for turn in turns:
        label = f"{turn.side.capitalize()}, round {turn.round}"
        if turn.flagged:
            lines.append(f"{label}: [reply invalid, skipped]")
            continue
        for point in turn.points:
            ids = ", ".join(point.evidence_ids) if point.evidence_ids else "no IDs"
            suffix = " [unsupported]" if point.unsupported else ""
            lines.append(f"{label}: {point.claim} ({ids}){suffix}")
        for concession in turn.concessions:
            lines.append(f"{label} concedes: {concession}")
    return lines


def _check_point(point: DebatePoint, evidence: dict[str, Evidence]) -> CheckedPoint:
    """Normalises cited IDs (trimmed, upper-case, M4-FR-3) and marks the
    point unsupported if it cites none, or cites one that isn't registered
    (D-M4-4)."""
    normalized_ids = [raw_id.strip().upper() for raw_id in point.evidence_ids]
    unsupported = not normalized_ids or any(pid not in evidence for pid in normalized_ids)
    return CheckedPoint(claim=point.claim, evidence_ids=normalized_ids, unsupported=unsupported)


def _word_count(reply: DebateReply) -> int:
    texts = [point.claim for point in reply.points] + list(reply.concessions)
    return sum(len(text.split()) for text in texts)


def _turn(
    side: _Side,
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    if state.board is None:
        raise ValueError(f"{side} ran before the signals board")
    round_number = len(state.debate) // 2 + 1

    result = call_llm(
        Role.LARGE,
        _TEMPLATES[side],
        {
            "ticker": state.ticker,
            "company_name": state.company_name,
            "task": _TASKS[(side, round_number)],
            "round": round_number,
            "board_score": state.board.score,
            "conflict": state.board.conflict,
            "signals": _signals_summary(state.board),
            "evidence": _evidence_list(state.board),
            "transcript": _transcript_lines(state.debate),
            "max_words": settings.debate_turn_max_words,
        },
        DebateReply,
        safe_default=_SAFE_DEFAULT,
        request_id=state.request_id,
        settings=settings,
        sessions=sessions,
        completion_fn=completion_fn,
    )

    warnings: list[str] = []
    if result.flagged:
        turn = DebateTurn(
            side=side,
            round=round_number,
            points=[],
            concessions=[],
            conviction=0.0,
            word_count=0,
            over_word_limit=False,
            flagged=True,
        )
        warnings.append(f"{side} round {round_number}: reply invalid after retry")
    else:
        points = [_check_point(point, state.board.evidence) for point in result.value.points]
        word_count = _word_count(result.value)
        over_limit = word_count > settings.debate_turn_max_words
        turn = DebateTurn(
            side=side,
            round=round_number,
            points=points,
            concessions=result.value.concessions,
            conviction=result.value.conviction,
            word_count=word_count,
            over_word_limit=over_limit,
            flagged=False,
        )
        if over_limit:
            warnings.append(
                f"{side} round {round_number}: turn is {word_count} words "
                f"(limit {settings.debate_turn_max_words})"
            )
        unsupported_count = sum(1 for point in points if point.unsupported)
        if unsupported_count:
            warnings.append(
                f"{side} round {round_number}: {unsupported_count} unsupported point(s)"
            )

    return {"debate": [*state.debate, turn], "warnings": [*state.warnings, *warnings]}


def bull_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    return _turn("bull", state, settings=settings, sessions=sessions, completion_fn=completion_fn)


def bear_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    return _turn("bear", state, settings=settings, sessions=sessions, completion_fn=completion_fn)
