"""The single-agent baseline: one large-model call sees the code-written facts
of all three analysts and answers in the trader's format (architecture §12;
M7 specs-plan FR-4; D-M7-3).

Headlines carry no sentiment score, since a score is the sentiment analyst's
LLM judgment. The trader's code checks apply to the reply.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.fundamentals import evidence_from_metrics
from bullpit.agents.technical import evidence_from_indicators
from bullpit.agents.trader import (
    attempt_update,
    exit_style_descriptions,
    invalid_recommendation,
    recommendation_from_reply,
)
from bullpit.config import Settings
from bullpit.data.news import get_news
from bullpit.data.sec import get_sec_facts
from bullpit.llm.gateway import CompletionFn, Role, call_llm, litellm_completion
from bullpit.llm.schemas import Evidence, TraderReply
from bullpit.state import RequestState
from bullpit.tools.fundamentals import compute_fundamentals
from bullpit.tools.sentiment import select_headlines

_TEMPLATE = "single_agent.md"
_SAFE_DEFAULT = TraderReply(
    action="no_trade",
    target_weight=0.0,
    exit_style="normal",
    confidence=0.0,
    decisive_evidence=[],
    reasoning="",
)


def _fundamentals_facts(state: RequestState, settings: Settings) -> list[Evidence]:
    """F1-F5, including P/E; none if the latest quarter's figures are missing."""
    if state.prices is None:
        raise ValueError("single_agent runs after request_check populates prices")
    facts = get_sec_facts(state.ticker, state.as_of, settings=settings)
    metrics = compute_fundamentals(
        facts.facts,
        reference_price=float(state.prices.reference_price),
        splits=state.prices.splits,
    )
    if metrics.latest_revenue is None or metrics.latest_net_income is None:
        return []
    return evidence_from_metrics(metrics, latest_revenue=metrics.latest_revenue)


def _headline_facts(state: RequestState, settings: Settings) -> list[Evidence]:
    articles = get_news(state.ticker, state.as_of, settings=settings)
    pairs = select_headlines(
        [(article.created_at, article.headline) for article in articles],
        max_headlines=settings.news_max_headlines,
        duplicate_similarity=settings.news_duplicate_similarity,
    )
    return [
        Evidence(
            id=headline_id,
            fact=f'{articles[index].created_at.date()}: "{articles[index].headline}"',
        )
        for headline_id, index in pairs
    ]


def single_agent_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    """One large-model call per request; an invalid reply is a flagged "no
    trade". `QuotaExhausted` and `LLMUnavailable` propagate, so the runner pauses."""
    if state.indicators is None or state.account is None:
        raise ValueError("single_agent ran before the indicators and account snapshot")

    evidence = [
        *evidence_from_indicators(state.indicators),
        *_fundamentals_facts(state, settings),
        *_headline_facts(state, settings),
    ]
    equity = state.account.equity
    held_value = state.position.market_value if state.position is not None else Decimal("0")
    held_pct = (held_value / equity * 100) if equity > 0 else Decimal("0")

    result = call_llm(
        Role.LARGE,
        _TEMPLATE,
        {
            "ticker": state.ticker,
            "company_name": state.company_name,
            "evidence": [item.model_dump() for item in evidence],
            "cash": state.account.cash,
            "equity": equity,
            "held_value": held_value,
            "held_pct": float(held_pct),
            "max_target_weight_pct": float(settings.max_position_pct * 100),
            "exit_styles": exit_style_descriptions(settings),
        },
        TraderReply,
        safe_default=_SAFE_DEFAULT,
        request_id=state.request_id,
        settings=settings,
        sessions=sessions,
        completion_fn=completion_fn,
    )

    if result.flagged:
        return attempt_update(state, invalid_recommendation(state.ticker), [], actor="Single agent")
    recommendation, warnings = recommendation_from_reply(
        result.value,
        ticker=state.ticker,
        registry={item.id: item for item in evidence},
        settings=settings,
    )
    return attempt_update(state, recommendation, warnings, actor="Single agent")
