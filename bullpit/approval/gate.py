"""The approval gate (architecture Part 13; M6-FR-6, M8-FR-6 to FR-10).

Pure: no I/O, no settings and no clock. The caller passes in `now`, the latest
price, and the account and position (already net of pending orders, M8-FR-29).
`backtest_policy` approves every buy as sized because no one can be asked in a
backtest; `check_decision` applies the owner's decision to the report's order.
From M11.1 the order is priced from the entry the owner chose (D16), and the
opt-in advanced mode may override the plan's limits (D18; M11.1 specs-plan §11.3).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, model_validator

from bullpit.data.calendar import session_close, sessions_between
from bullpit.domain import Account, OrderType, SizedOrder
from bullpit.risk.sizing import build_order, cap_shares, cash_shares, reprice, round_cent

# The first session after any date is at most a long weekend plus a holiday away.
_NEXT_SESSION_LOOKAHEAD = timedelta(days=7)

OverrideFlag = Literal["custom_exits", "size_above_plan", "above_cap", "above_risk_limit"]


class ApprovalDecision(BaseModel, frozen=True):
    decision: Literal["approved", "rejected"]
    recommended_shares: int
    approved_shares: int
    decided_by: Literal["backtest_policy", "owner"]
    latest_price: Decimal | None = None  # the staleness check's price (owner decisions)
    confirmations: list[Literal["stale", "loss_warning"]] = []
    # What was approved, so the order can be rebuilt from the recorded row (M11.1-FR-18).
    order_type: OrderType = "market"
    entry_price: Decimal | None = None  # None for a rejection and for the backtest policy
    limit_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    seen_price: Decimal | None = None
    overrides: list[OverrideFlag] = []


def backtest_policy(order: SizedOrder) -> ApprovalDecision:
    """Approve the order exactly as sized."""
    return ApprovalDecision(
        decision="approved",
        recommended_shares=order.shares,
        approved_shares=order.shares,
        decided_by="backtest_policy",
    )


class OwnerDecision(BaseModel, frozen=True):
    """The approval request body."""

    decision: Literal["approve", "reject"]
    shares: int | None = None  # None: the recommended count
    confirm_stale: bool = False
    confirm_loss_warning: bool = False
    order_type: OrderType = "market"
    limit_price: Decimal | None = None  # "limit" only
    seen_price: Decimal | None = None  # the price on screen; required to buy now
    advanced: bool = False
    stop_loss: Decimal | None = None  # advanced only; None keeps the repriced value
    take_profit: Decimal | None = None  # advanced only; None keeps the repriced value
    confirm_overrides: bool = False

    @model_validator(mode="after")
    def _buy_now_needs_the_seen_price(self) -> OwnerDecision:
        if (
            self.decision == "approve"
            and self.order_type == "market"
            and (self.seen_price is None or self.seen_price <= 0)
        ):
            raise ValueError("seen_price is required to buy now")
        return self


ProblemCode = Literal[
    "not_awaiting",
    "expired",
    "shares_invalid",
    "price_unavailable",
    "stale",
    "loss_warning",
    "rules",
    "limit_invalid",
    "exits_invalid",
    "override_not_confirmed",
]


class ApprovalProblem(BaseModel, frozen=True):
    """Why a decision was refused. Nothing is recorded and no order is placed."""

    code: ProblemCode
    message: str
    report_price: Decimal | None = None  # the price the owner saw (buy now)
    latest_price: Decimal | None = None
    move_pct: Decimal | None = None  # signed fraction: 0.028 is +2.8%
    max_shares: int | None = None  # the largest count the rules would accept
    overrides: list[OverrideFlag] | None = None  # override_not_confirmed: what to confirm


def expires_at(as_of: date) -> datetime:
    """A report can be decided until the close of the first session after `as_of`
    (M8 D-M8-5): its prices are the close of `as_of`, good for one more session."""
    following = sessions_between(as_of, as_of + _NEXT_SESSION_LOOKAHEAD)[0]
    return session_close(following)


def _rules_problem(message: str, *, max_shares: int | None = None) -> ApprovalProblem:
    return ApprovalProblem(code="rules", message=message, max_shares=max_shares)


def final_order(
    order: SizedOrder, body: OwnerDecision, entry: Decimal
) -> SizedOrder | ApprovalProblem:
    """The order the owner approved (M11.1-FR-12, FR-16): the plan repriced to
    `entry`, then, in advanced mode only, the owner's stop, take-profit and shares
    (None keeps the repriced value, or the recommended count). Outside advanced
    mode the page's exits are never read (D-M11.1-9)."""
    repriced = reprice(order, entry)
    stop = None if repriced is None else repriced.stop_loss
    target = None if repriced is None else repriced.take_profit
    if body.advanced:
        stop = stop if body.stop_loss is None else round_cent(body.stop_loss)
        target = target if body.take_profit is None else round_cent(body.take_profit)
    if stop is None or target is None:
        return ApprovalProblem(
            code="exits_invalid",
            message="The plan's stop would be at or below zero at this entry price.",
        )
    if not 0 < stop < entry < target:
        return ApprovalProblem(
            code="exits_invalid",
            message=(
                "Exits must satisfy 0 < stop < entry < take-profit: "
                f"stop ${stop:.2f}, entry ${entry:.2f}, take-profit ${target:.2f}."
            ),
        )
    return build_order(
        order.ticker,
        order.shares if body.shares is None else body.shares,
        reference=entry,
        stop=stop,
        take_profit=target,
        exit_style=order.exit_style,
        limit=order.limit,
        limit_shares=order.limit_shares,
    )


def override_flags(
    final: SizedOrder,
    plan: SizedOrder,
    equity: Decimal,
    held_value: Decimal,
    *,
    cap_pct: Decimal,
    risk_pct: Decimal,
) -> list[OverrideFlag]:
    """Which of the plan's rules an advanced-mode order steps outside (FR-19)."""
    repriced = reprice(plan, final.reference_price)
    flags: list[OverrideFlag] = []
    if repriced is None or (final.stop_loss, final.take_profit) != (
        repriced.stop_loss,
        repriced.take_profit,
    ):
        flags.append("custom_exits")
    if final.shares > plan.shares:
        flags.append("size_above_plan")
    if held_value + final.cost > cap_pct * equity:
        flags.append("above_cap")
    if final.max_loss > risk_pct * equity:
        flags.append("above_risk_limit")
    return flags


def check_decision(
    body: OwnerDecision,
    order: SizedOrder,
    *,
    as_of: date,
    now: datetime,
    latest_price: Decimal | None,
    loss_warning: bool | None,
    account: Account,
    held_value: Decimal,
    staleness_pct: Decimal,
    cap_pct: Decimal,
    risk_pct: Decimal,
) -> ApprovalDecision | ApprovalProblem:
    """Apply the owner's decision to the report's order (M11.1-FR-17, §11.3),
    refusing at the first failing check.

    `account` and `held_value` are net of pending orders. Outside advanced mode
    shares can only go down and the cash and cap limits are hard; in advanced mode
    only cash is, and the cap and risk limit become recorded overrides.
    """
    if now > expires_at(as_of):
        return ApprovalProblem(code="expired", message="This report has expired.")
    if body.decision == "reject":
        return ApprovalDecision(
            decision="rejected",
            recommended_shares=order.shares,
            approved_shares=0,
            decided_by="owner",
        )

    shares = order.shares if body.shares is None else body.shares
    if shares < 1 or (not body.advanced and shares > order.shares):
        return ApprovalProblem(
            code="shares_invalid",
            message=(
                "Shares must be a whole number of at least 1."
                if body.advanced
                else f"Shares must be a whole number from 1 to {order.shares}."
            ),
            max_shares=None if body.advanced else order.shares,
        )
    is_limit = body.order_type == "limit"
    chosen = body.limit_price if is_limit else body.seen_price
    if chosen is None or chosen <= 0:
        return ApprovalProblem(
            code="limit_invalid", message="The limit price must be greater than zero."
        )
    entry = round_cent(chosen)
    if latest_price is None:
        return ApprovalProblem(
            code="price_unavailable",
            message="The latest price isn't available, so the price check can't be made.",
        )
    final = final_order(order, body, entry)
    if isinstance(final, ApprovalProblem):
        return final

    stale = False
    if not is_limit:  # a limit protects the price, so it skips the staleness check
        move = (latest_price - entry) / entry
        stale = abs(move) > staleness_pct
        if stale and not body.confirm_stale:
            return ApprovalProblem(
                code="stale",
                message=(
                    f"The price moved {move:+.1%} since you saw it: "
                    f"${entry:.2f} to ${latest_price:.2f}. Confirm, or reject and re-run."
                ),
                report_price=entry,
                latest_price=latest_price,
                move_pct=move,
            )
    warned = loss_warning is True
    if warned and not body.confirm_loss_warning:
        return ApprovalProblem(
            code="loss_warning",
            message="The account fell more than the loss-warning limit recently. Confirm to go on.",
        )

    # A waiting limit order may sit far below the market, so only its stop side
    # matters (a limit above the market would fill below its own stop).
    if latest_price <= final.stop_loss:
        return _rules_problem(
            f"The price ${latest_price:.2f} is at or below the stop ${final.stop_loss:.2f}: "
            "the order would exit at once. Reject and re-run."
        )
    if not is_limit and latest_price >= final.take_profit:
        return _rules_problem(
            f"The price ${latest_price:.2f} is at or above the target ${final.take_profit:.2f}: "
            "the order would exit at once. Reject and re-run."
        )

    # A market order fills near the latest price, which may have moved past the entry.
    basis = entry if is_limit else max(entry, latest_price)
    if body.advanced:
        fits = cash_shares(account.cash, basis)
        scope = "the available cash"
    else:
        fits = min(
            cash_shares(account.cash, basis),
            cap_shares(account.equity, held_value, basis, cap_pct),
        )
        scope = "the cash and per-stock cap"
    if shares > fits:
        return _rules_problem(
            f"{shares} shares don't fit {scope} at ${basis:.2f}; "
            f"at most {fits} do. If an earlier order has filled, run the fill check and retry.",
            max_shares=fits,
        )

    overrides = (
        override_flags(final, order, account.equity, held_value, cap_pct=cap_pct, risk_pct=risk_pct)
        if body.advanced
        else []
    )
    if overrides and not body.confirm_overrides:
        return ApprovalProblem(
            code="override_not_confirmed",
            message="This order overrides the plan's rules. Confirm to go on.",
            overrides=overrides,
        )

    confirmations: list[Literal["stale", "loss_warning"]] = []
    if stale:
        confirmations.append("stale")
    if warned:
        confirmations.append("loss_warning")
    return ApprovalDecision(
        decision="approved",
        recommended_shares=order.shares,
        approved_shares=shares,
        decided_by="owner",
        latest_price=latest_price,
        confirmations=confirmations,
        order_type=body.order_type,
        entry_price=entry,
        limit_price=entry if is_limit else None,
        stop_loss=final.stop_loss,
        take_profit=final.take_profit,
        seen_price=None if is_limit else entry,
        overrides=overrides,
    )
