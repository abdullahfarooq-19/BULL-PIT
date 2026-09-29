"""Builds the LangGraph graph from the request check through to the report
(architecture Part 0, sec5; M3-FR-18; M4-FR-16; M5-FR-8). Only three pieces
are ever bound per build: settings, journal sessions and the broker
(architecture sec4's dependency injection).

M7 adds the baseline policies (M7 specs-plan sec9.3): a short graph from the
same builder, so only the buy decision differs from Bull Pit.

Dependencies (settings, journal sessions, the broker, the LLM completion
function) are bound when the graph is built and never stored in state, so
`RequestState` stays serialisable for M8's checkpointer.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.brain import choose_route, data_warnings
from bullpit.agents.debate import bear_node, bull_node
from bullpit.agents.fundamentals import fundamentals_node
from bullpit.agents.risk_review import risk_review_node
from bullpit.agents.sentiment import sentiment_node
from bullpit.agents.signals_board import build_board
from bullpit.agents.single_agent import single_agent_node
from bullpit.agents.technical import bars_frame, technical_node
from bullpit.agents.trader import attempt_update, trader_node
from bullpit.broker.base import Broker
from bullpit.clock import utc_now
from bullpit.config import Settings
from bullpit.data.prices import get_market_context
from bullpit.domain import ExitStyle
from bullpit.errors import DataUnavailable, LookaheadViolation, QuotaExhausted
from bullpit.eval.baselines import Policy, always_buy, fixed_recommendation, ma_rule
from bullpit.llm.gateway import CompletionFn, litellm_completion
from bullpit.llm.schemas import Signal
from bullpit.logging import get_logger
from bullpit.report.builder import market_context, report_node
from bullpit.report.model import MarketContext
from bullpit.request_check import request_check_node
from bullpit.risk.rules import stage_a
from bullpit.state import RequestState
from bullpit.tools.indicators import Indicators, compute_indicators

logger = get_logger(__name__)

_ANALYST_NODES = ("technical", "fundamentals", "sentiment")
_EXIT_STOP_ATR_SETTING: dict[ExitStyle, str] = {
    "tight": "exit_stop_atr_tight",
    "normal": "exit_stop_atr_normal",
    "wide": "exit_stop_atr_wide",
}

_AnalystFn = Callable[..., dict[str, object]]

_RULES: dict[Policy, Callable[[Indicators], bool]] = {"always_buy": always_buy, "ma_rule": ma_rule}
_RULE_REASONS: dict[Policy, dict[bool, str]] = {
    "always_buy": {True: "Buys every week."},
    "ma_rule": {
        True: "Close is above SMA 50.",
        False: "Close is not above SMA 50, or SMA 50 isn't available.",
    },
}


@dataclass(frozen=True)
class Deps:
    settings: Settings
    sessions: sessionmaker[Session]
    broker: Broker
    completion_fn: CompletionFn = field(default=litellm_completion)


def _route_after_request_check(state: RequestState) -> list[str] | str:
    if state.rejection is not None:
        return "report"
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
    result: dict[str, object] = {"route": route, "warnings": warnings}
    if route == "no_trade":
        result["outcome"] = "no_trade"
        result["no_trade_reason"] = (
            f"Signals too weak for a debate (board score {state.board.score:+.2f}, no conflict)."
        )
    return result


def _bull_node(state: RequestState, *, deps: Deps) -> dict[str, object]:
    return bull_node(
        state, settings=deps.settings, sessions=deps.sessions, completion_fn=deps.completion_fn
    )


def _bear_node(state: RequestState, *, deps: Deps) -> dict[str, object]:
    return bear_node(
        state, settings=deps.settings, sessions=deps.sessions, completion_fn=deps.completion_fn
    )


def _trader_node(state: RequestState, *, deps: Deps) -> dict[str, object]:
    return trader_node(
        state, settings=deps.settings, sessions=deps.sessions, completion_fn=deps.completion_fn
    )


def _risk_review_agent_node(state: RequestState, *, deps: Deps) -> dict[str, object]:
    return risk_review_node(
        state, settings=deps.settings, sessions=deps.sessions, completion_fn=deps.completion_fn
    )


def _risk_sizing_node(state: RequestState, *, deps: Deps) -> dict[str, object]:
    """Stage A (M4-FR-7 to FR-9): code sizes the last trader attempt. ATR is
    the one float-to-money boundary, converted with `Decimal(str(x))`
    (plan sec11.1); `target_weight` is already `Decimal` (trader_node)."""
    if not state.attempts:
        raise ValueError("risk_sizing ran before the trader")
    if state.account is None:
        raise ValueError("risk_sizing ran before the account snapshot")
    if state.prices is None or state.indicators is None:
        raise ValueError("risk_sizing ran before prices/indicators were computed")

    last_attempt = state.attempts[-1]
    recommendation = last_attempt.recommendation
    settings = deps.settings
    stop_atr: Decimal = getattr(settings, _EXIT_STOP_ATR_SETTING[recommendation.exit_style])
    atr = None if state.indicators.atr_14 is None else Decimal(str(state.indicators.atr_14))
    held_value = state.position.market_value if state.position is not None else Decimal("0")

    result = stage_a(
        ticker=state.ticker,
        reference=state.prices.reference_price,
        atr=atr,
        exit_style=recommendation.exit_style,
        target_weight=recommendation.target_weight,
        account=state.account,
        held_value=held_value,
        stop_atr=stop_atr,
        reward_risk=settings.exit_reward_risk,
        risk_pct=settings.risk_per_trade_pct,
        cap_pct=settings.max_position_pct,
    )

    if isinstance(result, str):
        updated = last_attempt.model_copy(update={"blocked_reason": result})
        return {
            "attempts": [*state.attempts[:-1], updated],
            "outcome": "no_trade",
            "no_trade_reason": result,
        }

    updated = last_attempt.model_copy(update={"sized_order": result})
    return {"attempts": [*state.attempts[:-1], updated]}


def _fetch_market(state: RequestState, settings: Settings) -> tuple[MarketContext, RequestState]:
    """Section 8's data (M5-FR-4). A data failure gives the all-`None` context
    and a warning; the request goes on. Only this module calls the data layer."""
    thresholds = {"vix_low": settings.vix_low_threshold, "vix_high": settings.vix_high_threshold}
    try:
        data = get_market_context(state.as_of, settings.price_history_sessions, settings=settings)
    except DataUnavailable as exc:
        warnings = [*state.warnings, f"market context not available: {exc}"]
        return market_context([], None, **thresholds), state.model_copy(
            update={"warnings": warnings}
        )
    vix_closes = data.vix.bars["close"]
    vix_close = float(vix_closes.iloc[-1]) if len(vix_closes) else None
    return market_context(data.spy.bars["close"].tolist(), vix_close, **thresholds), state


def _report_node(state: RequestState, *, deps: Deps) -> dict[str, object]:
    """The last node on every path. A rejected request costs nothing: no
    market fetch and no LLM call (M5-FR-8)."""
    market = None
    if state.rejection is None:
        market, state = _fetch_market(state, deps.settings)
    return report_node(
        state,
        settings=deps.settings,
        sessions=deps.sessions,
        market=market,
        generated_at=utc_now(),
        completion_fn=deps.completion_fn,
    )


def _route_after_brain(state: RequestState) -> str:
    return "bull" if state.route == "debate" else "report"


def _route_after_bear(state: RequestState, *, deps: Deps) -> str:
    return "bull" if len(state.debate) < 2 * deps.settings.debate_rounds else "trader"


def _route_after_trader(state: RequestState) -> str:
    return "report" if state.outcome is not None else "risk_sizing"


def _route_after_sizing(state: RequestState) -> str:
    return "report" if state.outcome is not None else "risk_review"


def _route_after_review(state: RequestState) -> str:
    return "report" if state.outcome is not None else "trader"


def _indicators_node(state: RequestState) -> dict[str, object]:
    if state.prices is None:
        raise ValueError("indicators ran before request_check populated prices")
    return {"indicators": compute_indicators(bars_frame(state.prices.bars))}


def _decide_node(
    state: RequestState,
    *,
    deps: Deps,
    policy: Policy,
    buy_decisions: Mapping[tuple[date, str], bool] | None,
) -> dict[str, object]:
    """The policy's buy decision (M7-FR-3, FR-4). A rule has no trader, so its
    decision is sized at the fixed baseline weight and exit style (Q8)."""
    if policy == "single_agent":
        return single_agent_node(
            state,
            settings=deps.settings,
            sessions=deps.sessions,
            completion_fn=deps.completion_fn,
        )
    if state.indicators is None:
        raise ValueError("decide ran before the indicators")
    if policy == "bullpit_fixed":
        if buy_decisions is None:
            raise ValueError("bullpit_fixed needs the source run's decisions")
        buy = buy_decisions.get((state.as_of, state.ticker), False)
        reason = "Replayed from the Bull Pit run's decision."
    else:
        buy = _RULES[policy](state.indicators)
        reason = _RULE_REASONS[policy][buy]
    recommendation = fixed_recommendation(
        state.ticker,
        buy,
        weight=deps.settings.baseline_target_weight,
        exit_style=deps.settings.baseline_exit_style,
        reason=reason,
    )
    return attempt_update(state, recommendation, [], actor="Baseline")


def _accept_node(state: RequestState) -> dict[str, object]:
    """Stage A sized the attempt; with no Stage B review, that order is final."""
    return {"outcome": "buy", "sized_order": state.attempts[-1].sized_order}


def _policy_route_after_request_check(state: RequestState) -> str:
    return END if state.rejection is not None else "indicators"


def _policy_route_after_decide(state: RequestState) -> str:
    return END if state.outcome is not None else "risk_sizing"


def _policy_route_after_sizing(state: RequestState) -> str:
    return END if state.outcome is not None else "accept"


def _build_policy_graph(
    deps: Deps, policy: Policy, buy_decisions: Mapping[tuple[date, str], bool] | None
) -> CompiledStateGraph[RequestState, None, RequestState, RequestState]:
    """Request check, indicators, the policy's decision, Stage A, accept. No
    analysts, debate, Stage B review or report (D-M7-1, D-M7-2)."""
    graph = StateGraph(RequestState)
    graph.add_node(
        "request_check",
        functools.partial(request_check_node, settings=deps.settings, broker=deps.broker),
    )
    graph.add_node("indicators", _indicators_node)
    graph.add_node(
        "decide",
        functools.partial(_decide_node, deps=deps, policy=policy, buy_decisions=buy_decisions),
    )
    graph.add_node("risk_sizing", functools.partial(_risk_sizing_node, deps=deps))
    graph.add_node("accept", _accept_node)

    graph.add_edge(START, "request_check")
    graph.add_conditional_edges(
        "request_check", _policy_route_after_request_check, ["indicators", END]
    )
    graph.add_edge("indicators", "decide")
    graph.add_conditional_edges("decide", _policy_route_after_decide, ["risk_sizing", END])
    graph.add_conditional_edges("risk_sizing", _policy_route_after_sizing, ["accept", END])
    graph.add_edge("accept", END)
    return graph.compile()


def build_graph(
    deps: Deps,
    *,
    policy: Policy = "bullpit",
    buy_decisions: Mapping[tuple[date, str], bool] | None = None,
) -> CompiledStateGraph[RequestState, None, RequestState, RequestState]:
    """The M6 graph for `bullpit`; any other policy gets the short policy graph.
    `buy_decisions` (by decision day and ticker) is for `bullpit_fixed` only."""
    if policy != "bullpit":
        return _build_policy_graph(deps, policy, buy_decisions)

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
    graph.add_node("bull", functools.partial(_bull_node, deps=deps))
    graph.add_node("bear", functools.partial(_bear_node, deps=deps))
    graph.add_node("trader", functools.partial(_trader_node, deps=deps))
    graph.add_node("risk_sizing", functools.partial(_risk_sizing_node, deps=deps))
    graph.add_node("risk_review", functools.partial(_risk_review_agent_node, deps=deps))
    graph.add_node("report", functools.partial(_report_node, deps=deps))

    graph.add_edge(START, "request_check")
    graph.add_conditional_edges(
        "request_check", _route_after_request_check, [*_ANALYST_NODES, "report"]
    )
    for node in _ANALYST_NODES:
        graph.add_edge(node, "signals_board")
    graph.add_edge("signals_board", "brain")
    graph.add_conditional_edges("brain", _route_after_brain, ["bull", "report"])
    graph.add_edge("bull", "bear")
    graph.add_conditional_edges(
        "bear", functools.partial(_route_after_bear, deps=deps), ["bull", "trader"]
    )
    graph.add_conditional_edges("trader", _route_after_trader, ["risk_sizing", "report"])
    graph.add_conditional_edges("risk_sizing", _route_after_sizing, ["risk_review", "report"])
    graph.add_conditional_edges("risk_review", _route_after_review, ["trader", "report"])
    graph.add_edge("report", END)

    return graph.compile()
