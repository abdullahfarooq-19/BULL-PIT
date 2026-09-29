"""Trader: reads the debate and recommends buy or no trade, a target size
and an exit style (architecture Part 10; M4-FR-5, FR-6; D-M4-5, D-M4-6,
D-M4-7).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from bullpit.agents.debate import evidence_list, final_conviction, signals_summary, transcript_lines
from bullpit.config import Settings
from bullpit.domain import ExitStyle
from bullpit.llm.gateway import CompletionFn, Role, call_llm, litellm_completion
from bullpit.llm.schemas import Evidence, TraderReply
from bullpit.state import Recommendation, RequestState, TradeAttempt

_TEMPLATE = "trader.md"
_SAFE_DEFAULT = TraderReply(
    action="no_trade",
    target_weight=0.0,
    exit_style="normal",
    confidence=0.0,
    decisive_evidence=[],
    reasoning="",
)
_EXIT_STYLE_SETTINGS: dict[ExitStyle, str] = {
    "tight": "exit_stop_atr_tight",
    "normal": "exit_stop_atr_normal",
    "wide": "exit_stop_atr_wide",
}


def exit_style_descriptions(settings: Settings) -> list[str]:
    """One line per exit style: its stop and target in ATR multiples."""
    lines = []
    for style, field_name in _EXIT_STYLE_SETTINGS.items():
        stop_mult: Decimal = getattr(settings, field_name)
        take_profit_mult = stop_mult * settings.exit_reward_risk
        lines.append(f"{style}: stop {stop_mult} ATR below, target {take_profit_mult} ATR above")
    return lines


def recommendation_from_reply(
    reply: TraderReply, *, ticker: str, registry: Mapping[str, Evidence], settings: Settings
) -> tuple[Recommendation, list[str]]:
    """The code checks on a valid reply (M4-FR-6): the weight is clamped to the
    per-stock cap and cited evidence IDs are kept only if registered. Returns
    the recommendation and a warning for each correction."""
    warnings: list[str] = []
    target_weight = Decimal(str(reply.target_weight))
    clamped_weight = min(max(target_weight, Decimal("0")), settings.max_position_pct)
    if clamped_weight != target_weight:
        warnings.append(f"trader target weight {target_weight:.4f} clamped to {clamped_weight:.4f}")

    decisive = [eid for eid in reply.decisive_evidence if eid in registry]
    dropped = [eid for eid in reply.decisive_evidence if eid not in registry]
    if dropped:
        warnings.append(f"trader decisive evidence dropped (not registered): {', '.join(dropped)}")

    recommendation = Recommendation(
        ticker=ticker,
        action=reply.action,
        target_weight=clamped_weight,
        exit_style=reply.exit_style,
        confidence=reply.confidence,
        decisive_evidence=decisive,
        reasoning=reply.reasoning,
        flagged=False,
    )
    return recommendation, warnings


def invalid_recommendation(ticker: str) -> Recommendation:
    """The "no trade" recorded when a reply stayed invalid after the retry."""
    return Recommendation(
        ticker=ticker,
        action="no_trade",
        target_weight=Decimal("0"),
        exit_style="normal",
        confidence=0.0,
        decisive_evidence=[],
        reasoning="",
        flagged=True,
    )


def attempt_update(
    state: RequestState, recommendation: Recommendation, warnings: list[str], *, actor: str
) -> dict[str, object]:
    """The state update for one recommendation: the attempt is appended, and a
    "no trade" (or an invalid reply) ends the request."""
    update: dict[str, object] = {
        "attempts": [*state.attempts, TradeAttempt(recommendation=recommendation)],
        "warnings": [*state.warnings, *warnings],
    }
    if recommendation.flagged:
        update["outcome"] = "no_trade"
        update["no_trade_reason"] = f"{actor} reply was invalid."
    elif recommendation.action == "no_trade":
        update["outcome"] = "no_trade"
        update["no_trade_reason"] = f"{actor} recommended no trade: {recommendation.reasoning}"
    return update


def _veto_lines(attempts: list[TradeAttempt]) -> list[str]:
    lines = []
    for index, attempt in enumerate(attempts, start=1):
        if attempt.verdict is None or attempt.verdict.decision != "veto":
            continue
        weight_pct = attempt.recommendation.target_weight * 100
        shares = attempt.sized_order.shares if attempt.sized_order is not None else 0
        lines.append(
            f"Veto {index}: you recommended {weight_pct:.0f}% {attempt.recommendation.exit_style}, "
            f"sized to {shares} shares; the risk manager said: {attempt.verdict.reason}"
        )
    return lines


def trader_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    if state.board is None:
        raise ValueError("trader ran before the signals board")
    if state.account is None:
        raise ValueError("trader ran before the account snapshot")

    equity = state.account.equity
    held_value = state.position.market_value if state.position is not None else Decimal("0")
    held_pct = (held_value / equity * 100) if equity > 0 else Decimal("0")

    result = call_llm(
        Role.LARGE,
        _TEMPLATE,
        {
            "ticker": state.ticker,
            "company_name": state.company_name,
            "board_score": state.board.score,
            "conflict": state.board.conflict,
            "signals": signals_summary(state.board),
            "evidence": evidence_list(state.board),
            "transcript": transcript_lines(state.debate),
            "bull_conviction": final_conviction(state.debate, "bull"),
            "bear_conviction": final_conviction(state.debate, "bear"),
            "cash": state.account.cash,
            "equity": equity,
            "held_value": held_value,
            "held_pct": float(held_pct),
            "max_target_weight_pct": float(settings.max_position_pct * 100),
            "exit_styles": exit_style_descriptions(settings),
            "vetoes": _veto_lines(state.attempts),
        },
        TraderReply,
        safe_default=_SAFE_DEFAULT,
        request_id=state.request_id,
        settings=settings,
        sessions=sessions,
        completion_fn=completion_fn,
    )

    if result.flagged:
        return attempt_update(state, invalid_recommendation(state.ticker), [], actor="Trader")

    recommendation, warnings = recommendation_from_reply(
        result.value, ticker=state.ticker, registry=state.board.evidence, settings=settings
    )
    return attempt_update(state, recommendation, warnings, actor="Trader")
