"""Stage A pass/block, Stage B's only-shrink rule, and the loss warning
(architecture Part 11 A and B; M4-FR-9, FR-10, FR-12; D-M4-9, D-M4-10).

Pure over `Decimal`/`date` inputs: no settings, no I/O (M4-NFR-2). The exit
style is already resolved to its ATR multiple by the caller (plan sec9.2),
since that mapping lives in settings.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from bullpit.domain import Account, ExitStyle, SizedOrder, SizeLimit
from bullpit.risk.sizing import build_order, exit_prices, share_limits

_LIMIT_ORDER: tuple[SizeLimit, ...] = ("target", "risk", "cap", "cash")


def stage_a(
    *,
    ticker: str,
    reference: Decimal,
    atr: Decimal | None,
    exit_style: ExitStyle,
    target_weight: Decimal,
    account: Account,
    held_value: Decimal,
    stop_atr: Decimal,
    reward_risk: Decimal,
    risk_pct: Decimal,
    cap_pct: Decimal,
) -> SizedOrder | str:
    """Exits, sizing and the hard rules, checked in FR-9's order. Returns a
    `SizedOrder`, or the block reason as `str` (the first rule that fails)."""
    if atr is None or atr <= 0 or reference <= 0:
        return "ATR or price not available."
    if account.cash <= 0 or account.equity <= 0:
        return "No cash available."
    if held_value >= cap_pct * account.equity:
        held_pct = held_value / account.equity * 100
        cap_display = cap_pct * 100
        return (
            f"Per-stock cap reached: {ticker} is already {held_pct:.1f}% of equity "
            f"(cap {cap_display:.0f}%)."
        )

    stop, take_profit = exit_prices(reference, atr, stop_atr=stop_atr, reward_risk=reward_risk)
    if stop <= 0 or stop >= reference:
        return f"Exit prices invalid (stop {stop})."

    limits = share_limits(
        reference=reference,
        stop=stop,
        target_weight=target_weight,
        equity=account.equity,
        cash=account.cash,
        held_value=held_value,
        risk_pct=risk_pct,
        cap_pct=cap_pct,
    )
    shares = min(limits.values())
    limit = next(name for name in _LIMIT_ORDER if limits[name] == shares)
    if shares == 0:
        return f"Size rounds to 0 shares (set by the {limit} limit)."

    return build_order(
        ticker,
        shares,
        reference=reference,
        stop=stop,
        take_profit=take_profit,
        exit_style=exit_style,
        limit=limit,
        limit_shares=limits,
    )


def shrink(order: SizedOrder, shares: int) -> tuple[SizedOrder, bool]:
    """Stage B's only-shrink rule (M4-FR-12; D-M4-10). `shares` below the
    order's own size rebuilds it at that size (same exits, recomputed cost,
    loss and gain); at or above the order's size is clamped to the
    original, never enlarged. Returns `(order, clamped)`."""
    if shares >= order.shares:
        return order, True
    resized = build_order(
        order.ticker,
        shares,
        reference=order.reference_price,
        stop=order.stop_loss,
        take_profit=order.take_profit,
        exit_style=order.exit_style,
        limit=order.limit,
        limit_shares=order.limit_shares,
    )
    return resized, False


def _latest_on_or_before(
    history: Sequence[tuple[date, Decimal]], cutoff: date
) -> tuple[date, Decimal] | None:
    candidates = [pair for pair in history if pair[0] <= cutoff]
    return max(candidates, key=lambda pair: pair[0]) if candidates else None


def loss_warning(
    history: Sequence[tuple[date, Decimal]], as_of: date, *, drop_pct: Decimal, days: int
) -> bool | None:
    """`True` if equity fell more than `drop_pct` between the latest snapshot
    on or before `as_of - days` and the latest on or before `as_of`; `None`
    if the history doesn't reach back that far (C16: built and tested here,
    first called with a real equity history in M6 and M8)."""
    base = _latest_on_or_before(history, as_of - timedelta(days=days))
    current = _latest_on_or_before(history, as_of)
    if base is None or current is None:
        return None
    _, base_equity = base
    _, current_equity = current
    return (base_equity - current_equity) / base_equity > drop_pct
