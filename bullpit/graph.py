"""Builds the LangGraph graph up through the debate/no-trade route
(architecture Part 0, sec5; M3-FR-18). The debate route ends here in M3;
M4 attaches the debate and everything after it (D-M3-5).

Dependencies (settings, journal sessions, the broker, the LLM completion
function) are bound when the graph is built and never stored in state, so
`RequestState` stays serialisable for M8's checkpointer.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from dataclasses import dataclass, field

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.brain import choose_route, data_warnings
from bullpit.agents.fundamentals import fundamentals_node
from bullpit.agents.sentiment import sentiment_node
from bullpit.agents.signals_board import build_board
from bullpit.agents.technical import technical_node
from bullpit.broker.base import Broker
from bullpit.config import Settings
from bullpit.errors import LookaheadViolation, QuotaExhausted
from bullpit.llm.gateway import CompletionFn, litellm_completion
from bullpit.llm.schemas import Signal
from bullpit.logging import get_logger
from bullpit.request_check import request_check_node
from bullpit.state import RequestState

logger = get_logger(__name__)

_ANALYST_NODES = ("technical", "fundamentals", "sentiment")

_AnalystFn = Callable[..., dict[str, object]]


@dataclass(frozen=True)
class Deps:
    settings: Settings
    sessions: sessionmaker[Session]
    broker: Broker
    completion_fn: CompletionFn = field(default=litellm_completion)


def _route_after_request_check(state: RequestState) -> list[str] | str:
    if state.rejection is not None:
        return END
    return list(_ANALYST_NODES)


def _analyst_node(
    field_name: str, analyst: str, fn: _AnalystFn, state: RequestState, *, deps: Deps
) -> dict[str, object]:
    """Every exception except `QuotaExhausted` and `LookaheadViolation`
    becomes a neutral, confidence-0, flagged signal (M3-FR-15); those two
    always fail the request loudly, since a backtest must pause rather
    than record a degraded signal, and the date guard never stays quiet.
    """
    try:
        return fn(
            state,
            settings=deps.settings,
            sessions=deps.sessions,
            completion_fn=deps.completion_fn,
        )
    except (QuotaExhausted, LookaheadViolation):
        raise
    except Exception as exc:
        logger.warning("analyst_failed", analyst=analyst, error=str(exc), exc_info=True)
        signal = Signal(
            ticker=state.ticker,
            analyst=analyst,
            direction="neutral",
            confidence=0.0,
            evidence=[],
            flagged=True,
            note=f"analyst failed: {exc}",
        )
        return {field_name: signal}


def _signals_board_node(state: RequestState, *, deps: Deps) -> dict[str, object]:
    signals: dict[str, Signal] = {}
    for name, signal in (
        ("technical", state.technical_signal),
        ("fundamentals", state.fundamentals_signal),
        ("sentiment", state.sentiment_signal),
    ):
        if signal is None:
            raise ValueError(f"signals_board ran before the {name} analyst finished")
        signals[name] = signal

    board = build_board(
        signals, conflict_min_confidence=deps.settings.brain_conflict_min_confidence
    )
    return {"board": board}


def _brain_node(state: RequestState, *, deps: Deps) -> dict[str, object]:
    if state.board is None:
        raise ValueError("brain ran before the signals board")
    route = choose_route(state.board, min_abs_score=deps.settings.brain_min_abs_score)
    warnings = data_warnings(state, thin_articles=deps.settings.news_thin_articles)
    return {"route": route, "warnings": warnings}


def build_graph(deps: Deps) -> CompiledStateGraph[RequestState, None, RequestState, RequestState]:
    graph = StateGraph(RequestState)

    graph.add_node(
        "request_check",
        functools.partial(request_check_node, settings=deps.settings, broker=deps.broker),
    )
    graph.add_node(
        "technical",
        functools.partial(
            _analyst_node, "technical_signal", "technical", technical_node, deps=deps
        ),
    )
    graph.add_node(
        "fundamentals",
        functools.partial(
            _analyst_node, "fundamentals_signal", "fundamentals", fundamentals_node, deps=deps
        ),
    )
    graph.add_node(
        "sentiment",
        functools.partial(
            _analyst_node, "sentiment_signal", "sentiment", sentiment_node, deps=deps
        ),
    )
    graph.add_node("signals_board", functools.partial(_signals_board_node, deps=deps))
    graph.add_node("brain", functools.partial(_brain_node, deps=deps))

    graph.add_edge(START, "request_check")
    graph.add_conditional_edges("request_check", _route_after_request_check, [*_ANALYST_NODES, END])
    for node in _ANALYST_NODES:
        graph.add_edge(node, "signals_board")
    graph.add_edge("signals_board", "brain")
    graph.add_edge("brain", END)

    return graph.compile()
