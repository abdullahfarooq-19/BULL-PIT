"""Pure sizing maths: ATR exits and the four share-count limits (architecture
Part 11 A; M4-FR-7, FR-8; D-M4-2, D-M4-8).

Pure over `Decimal` inputs: no settings, no I/O (dev-plan.md sec2.2; M4-NFR-2).
Exit prices are rounded to the cent, half up; every share limit is floored to
a whole share and never negative (D-M4-8).
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from bullpit.domain import ExitStyle, SizedOrder, SizeLimit

_CENT = Decimal("0.01")


def _round_cent(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def _floor_shares(value: Decimal) -> int:
    if value <= 0:
        return 0
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def exit_prices(
    reference: Decimal, atr: Decimal, *, stop_atr: Decimal, reward_risk: Decimal
) -> tuple[Decimal, Decimal]:
    """(stop_loss, take_profit), each rounded to the cent, half up."""
    stop = _round_cent(reference - stop_atr * atr)
    take_profit = _round_cent(reference + reward_risk * stop_atr * atr)
    return stop, take_profit


def share_limits(
    *,
    reference: Decimal,
    stop: Decimal,
    target_weight: Decimal,
    equity: Decimal,
    cash: Decimal,
    held_value: Decimal,
    risk_pct: Decimal,
    cap_pct: Decimal,
) -> dict[SizeLimit, int]:
    """The architecture's four limits (Part 11), each floored to whole
    shares and never below 0. Caller ensures `reference > 0` and
    `stop < reference` (M4-FR-9 checks both before this is called)."""
    risk_per_share = reference - stop
    return {
        "target": _floor_shares(target_weight * equity / reference),
        "risk": _floor_shares(risk_pct * equity / risk_per_share),
        "cap": _floor_shares((cap_pct * equity - held_value) / reference),
        "cash": _floor_shares(cash / reference),
    }


def build_order(
    ticker: str,
    shares: int,
    *,
    reference: Decimal,
    stop: Decimal,
    take_profit: Decimal,
    exit_style: ExitStyle,
    limit: SizeLimit,
    limit_shares: dict[SizeLimit, int],
) -> SizedOrder:
    """Cost, maximum loss (at the stop) and possible gain (at the target)."""
    return SizedOrder(
        ticker=ticker,
        shares=shares,
        reference_price=reference,
        stop_loss=stop,
        take_profit=take_profit,
        exit_style=exit_style,
        cost=Decimal(shares) * reference,
        max_loss=Decimal(shares) * (reference - stop),
        max_gain=Decimal(shares) * (take_profit - reference),
        limit=limit,
        limit_shares=limit_shares,
    )
