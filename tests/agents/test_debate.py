"""Debate node tests (M4-AC-11): ID normalisation, the unsupported check,
the word-limit flag, a flagged reply, round/side bookkeeping, and the
transcript the bear sees."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.debate import bear_node, bull_node
from bullpit.config import Settings
from bullpit.state import CheckedPoint, DebateTurn
from tests.agents.conftest import (
    FIRST_LINE_BEAR,
    FIRST_LINE_BULL,
    ScriptedLLM,
    make_board_state,
    make_reply,
)


def _reply_content(
    points: list[dict[str, object]], concessions: list[str], conviction: float
) -> str:
    return json.dumps({"points": points, "concessions": concessions, "conviction": conviction})


class TestIdNormalisationAndUnsupported:
    def test_ids_are_trimmed_upper_cased_and_checked(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        llm.queue(
            FIRST_LINE_BULL,
            make_reply(
                _reply_content(
                    points=[
                        {"claim": "Point A", "evidence_ids": [" t1", "F2 "]},
                        {"claim": "Point B", "evidence_ids": []},
                        {"claim": "Point C", "evidence_ids": ["T99"]},
                    ],
                    concessions=[],
                    conviction=0.7,
                )
            ),
        )

        result = bull_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        turn = result["debate"][-1]
        assert isinstance(turn, DebateTurn)
        assert turn.points[0].evidence_ids == ["T1", "F2"]
        assert turn.points[0].unsupported is False
        assert turn.points[1].unsupported is True  # no IDs
        assert turn.points[2].unsupported is True  # T99 isn't registered
        assert sum(1 for point in turn.points if point.unsupported) == 2


class TestWordLimit:
    def test_over_limit_turn_is_kept_and_flagged(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        long_claim = " ".join(f"word{i}" for i in range(170))
        llm.queue(
            FIRST_LINE_BULL,
            make_reply(
                _reply_content(
                    points=[{"claim": long_claim, "evidence_ids": ["T1"]}],
                    concessions=[],
                    conviction=0.5,
                )
            ),
        )

        result = bull_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        turn = result["debate"][-1]
        assert isinstance(turn, DebateTurn)
        assert turn.word_count == 170
        assert turn.over_word_limit is True
        assert turn.flagged is False
        assert len(turn.points) == 1
        assert any("170 words" in warning for warning in result["warnings"])


class TestFlaggedReply:
    def test_invalid_reply_becomes_an_empty_flagged_turn(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_BULL, make_reply("not json"))
        llm.queue(FIRST_LINE_BULL, make_reply("still not json"))  # the gateway's one retry

        result = bull_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        turn = result["debate"][-1]
        assert isinstance(turn, DebateTurn)
        assert turn.points == []
        assert turn.conviction == 0.0
        assert turn.flagged is True
        assert any("reply invalid" in warning for warning in result["warnings"])


class TestRoundAndSideFollowTurnCount:
    def test_round_advances_after_two_turns(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        state = make_board_state()
        llm = ScriptedLLM()
        for first_line in (FIRST_LINE_BULL, FIRST_LINE_BEAR, FIRST_LINE_BULL, FIRST_LINE_BEAR):
            llm.queue(first_line, make_reply(_reply_content([], [], 0.5)))

        result = bull_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        state = state.model_copy(update={"debate": result["debate"]})
        assert state.debate[-1].side == "bull"
        assert state.debate[-1].round == 1

        result = bear_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        state = state.model_copy(update={"debate": result["debate"]})
        assert state.debate[-1].side == "bear"
        assert state.debate[-1].round == 1

        result = bull_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        state = state.model_copy(update={"debate": result["debate"]})
        assert state.debate[-1].round == 2

        result = bear_node(state, settings=settings, sessions=sessions, completion_fn=llm)
        state = state.model_copy(update={"debate": result["debate"]})
        assert state.debate[-1].round == 2


class TestBearSeesUnsupportedBullPoint:
    def test_bear_prompt_labels_the_unsupported_bull_point(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        bull_turn = DebateTurn(
            side="bull",
            round=1,
            points=[
                CheckedPoint(
                    claim="Momentum favours buying", evidence_ids=["T99"], unsupported=True
                )
            ],
            concessions=[],
            conviction=0.6,
            word_count=4,
            over_word_limit=False,
            flagged=False,
        )
        state = make_board_state(debate=[bull_turn])
        llm = ScriptedLLM()
        llm.queue(FIRST_LINE_BEAR, make_reply(_reply_content([], [], 0.5)))

        bear_node(state, settings=settings, sessions=sessions, completion_fn=llm)

        assert len(llm.prompts) == 1
        assert "Momentum favours buying" in llm.prompts[0]
        assert "[unsupported]" in llm.prompts[0]
