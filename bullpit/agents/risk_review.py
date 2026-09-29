"""Risk manager, Stage B: an LLM review of Stage A's sized order
(architecture Part 11 B; M4-FR-11 to FR-14; D-M4-7, D-M4-10, D-M4-11).

Runs only when Stage A passes. Code enforces that a `shrink` can only ever
lower the size (bullpit.risk.rules.shrink); the veto loop and its limit are
counted here from the attempts already recorded.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.debate import signals_summary, transcript_lines
from bullpit.config import Settings
from bullpit.domain import SizedOrder
from bullpit.llm.gateway import CompletionFn, Role, call_llm, litellm_completion
from bullpit.llm.schemas import RiskReviewReply
from bullpit.logging import get_logger
from bullpit.risk.rules import shrink
from bullpit.state import Recommendation, RequestState, RiskVerdict

logger = get_logger(__name__)

_TEMPLATE = "risk_review.md"
_SAFE_DEFAULT = RiskReviewReply(decision="veto", shares=None, reason="")


def _recommendation_view(recommendation: Recommendation) -> dict[str, object]:
    return {
        "action": recommendation.action,
        "target_weight_pct": float(recommendation.target_weight * 100),
        "exit_style": recommendation.exit_style,
        "confidence": recommendation.confidence,
        "decisive_evidence": recommendation.decisive_evidence,
        "reasoning": recommendation.reasoning,
    }


def _order_view(order: SizedOrder, *, equity_pct: float) -> dict[str, object]:
    return {
        "shares": order.shares,
        "cost": order.cost,
        "pct_of_equity": equity_pct,
        "stop_loss": order.stop_loss,
        "take_profit": order.take_profit,
        "max_loss": order.max_loss,
        "max_gain": order.max_gain,
        "limit": order.limit,
    }


def risk_review_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    if not state.attempts:
        raise ValueError("risk_review ran before the trader")
    last_attempt = state.attempts[-1]
    if last_attempt.sized_order is None:
        raise ValueError("risk_review ran before Stage A sized the order")
    if state.board is None:
        raise ValueError("risk_review ran before the signals board")
    if state.account is None:
        raise ValueError("risk_review ran before the account snapshot")

    order = last_attempt.sized_order
    equity_pct = float(order.cost / state.account.equity * 100) if state.account.equity > 0 else 0.0

    result = call_llm(
        Role.LARGE,
        _TEMPLATE,
        {
            "ticker": state.ticker,
            "company_name": state.company_name,
            "signals": signals_summary(state.board),
            "transcript": transcript_lines(state.debate),
            "recommendation": _recommendation_view(last_attempt.recommendation),
            "order": _order_view(order, equity_pct=equity_pct),
        },
        RiskReviewReply,
        safe_default=_SAFE_DEFAULT,
        request_id=state.request_id,
        settings=settings,
        sessions=sessions,
        completion_fn=completion_fn,
    )

    if result.flagged:
        verdict = RiskVerdict(
            decision="veto",
            reason="Risk review reply was invalid.",
            requested_shares=None,
            clamped=False,
            flagged=True,
        )
        attempts = [*state.attempts[:-1], last_attempt.model_copy(update={"verdict": verdict})]
        return {
            "attempts": attempts,
            "outcome": "no_trade",
            "no_trade_reason": "Risk review reply was invalid.",
        }

    reply = result.value

    if reply.decision == "approve":
        verdict = RiskVerdict(
            decision="approve",
            reason=reply.reason,
            requested_shares=None,
            clamped=False,
            flagged=False,
        )
        attempts = [*state.attempts[:-1], last_attempt.model_copy(update={"verdict": verdict})]
        return {"attempts": attempts, "sized_order": order, "outcome": "buy"}

    if reply.decision == "shrink":
        if reply.shares is None:  # schema-validated (D-M4-10); narrows for mypy
            raise ValueError("a 'shrink' reply passed validation without 'shares'")
        requested_shares = reply.shares
        resized_order, clamped = shrink(order, requested_shares)
        warnings = list(state.warnings)
        if clamped:
            logger.info(
                "risk_review_clamped",
                request_id=state.request_id,
                requested_shares=requested_shares,
                stage_a_shares=order.shares,
            )
            warnings.append(
                f"risk review requested {requested_shares} shares, at or above the sized "
                f"{order.shares}; clamped to {order.shares}"
            )
        verdict = RiskVerdict(
            decision="shrink",
            reason=reply.reason,
            requested_shares=requested_shares,
            clamped=clamped,
            flagged=False,
        )
        attempts = [*state.attempts[:-1], last_attempt.model_copy(update={"verdict": verdict})]
        return {
            "attempts": attempts,
            "warnings": warnings,
            "sized_order": resized_order,
            "outcome": "buy",
        }

    # veto (M4-FR-13): counted across every attempt recorded so far,
    # including this one, against the configured trip limit.
    verdict = RiskVerdict(
        decision="veto", reason=reply.reason, requested_shares=None, clamped=False, flagged=False
    )
    attempts = [*state.attempts[:-1], last_attempt.model_copy(update={"verdict": verdict})]
    veto_count = sum(
        1
        for attempt in attempts
        if attempt.verdict is not None and attempt.verdict.decision == "veto"
    )
    if veto_count > settings.risk_max_vetoes:
        return {
            "attempts": attempts,
            "outcome": "no_trade",
            "no_trade_reason": f"Risk manager vetoed {veto_count} times: {reply.reason}",
        }
    return {"attempts": attempts}
