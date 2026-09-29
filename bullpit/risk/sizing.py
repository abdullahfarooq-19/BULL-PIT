"""Pure sizing maths: ATR exits and the four share-count limits (architecture
Part 11 A; M4-FR-7, FR-8; D-M4-2, D-M4-8).

Pure over `Decimal` inputs: no settings, no I/O (dev-plan.md sec2.2; M4-NFR-2).
Exit prices are rounded to the cent, half up; every share limit is floored to
a whole share and never negative (D-M4-8).
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from bullpit.domain import Account, ExitStyle, SizedOrder, SizeLimit, Trade

_CENT = Decimal("0.01")


def round_cent(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


def floor_shares(value: Decimal) -> int:
    if value <= 0:
        return 0
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def exit_prices(
    reference: Decimal, atr: Decimal, *, stop_atr: Decimal, reward_risk: Decimal
) -> tuple[Decimal, Decimal]:
    """(stop_loss, take_profit), each rounded to the cent, half up."""
    stop = round_cent(reference - stop_atr * atr)
    take_profit = round_cent(reference + reward_risk * stop_atr * atr)
    return stop, take_profit


def cap_shares(equity: Decimal, held_value: Decimal, reference: Decimal, cap_pct: Decimal) -> int:
    """Shares that keep the position within the per-stock cap (limit 3)."""
    return floor_shares((cap_pct * equity - held_value) / reference)


def cash_shares(cash: Decimal, reference: Decimal) -> int:
    """Shares that cash alone can pay for (limit 4)."""
    return floor_shares(cash / reference)


def pending_cost(pending: list[Trade], ticker: str | None = None) -> Decimal:
    """What orders that haven't filled will cost, at their reference price as the
    simulated broker reserves it; only `ticker`'s when given."""
    return sum(
        (t.shares * t.reference_price for t in pending if ticker in (None, t.ticker)), Decimal(0)
    )


def net_of_pending(
    account: Account, held_value: Decimal, pending: list[Trade], ticker: str
) -> tuple[Account, Decimal]:
    """The account and the position value in `ticker`, net of orders that haven't
    filled (M8-FR-29): their cost leaves cash, and the ticker's own count as held.
    Equity is unchanged, since the cash isn't spent yet."""
    net = Account(cash=account.cash - pending_cost(pending), equity=account.equity)
    return net, held_value + pending_cost(pending, ticker)


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
        "target": floor_shares(target_weight * equity / reference),
        "risk": floor_shares(risk_pct * equity / risk_per_share),
        "cap": cap_shares(equity, held_value, reference, cap_pct),
        "cash": cash_shares(cash, reference),
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
