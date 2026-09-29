"""The approval gate (architecture Part 13; M6-FR-6, M8-FR-6 to FR-10).

Pure: no I/O, no settings and no clock. The caller passes in `now`, the latest
price, and the account and position (already net of pending orders, M8-FR-29).
`backtest_policy` approves every buy as sized because no one can be asked in a
backtest; `check_decision` applies the owner's decision to the report's order.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from bullpit.data.calendar import session_close, sessions_between
from bullpit.domain import Account, SizedOrder
from bullpit.risk.sizing import cap_shares, cash_shares

# The first session after any date is at most a long weekend plus a holiday away.
_NEXT_SESSION_LOOKAHEAD = timedelta(days=7)


class ApprovalDecision(BaseModel, frozen=True):
    decision: Literal["approved", "rejected"]
    recommended_shares: int
    approved_shares: int
    decided_by: Literal["backtest_policy", "owner"]
    latest_price: Decimal | None = None  # the staleness check's price (owner decisions)
    confirmations: list[Literal["stale", "loss_warning"]] = []


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


ProblemCode = Literal[
    "not_awaiting",
    "expired",
    "shares_invalid",
    "price_unavailable",
    "stale",
    "loss_warning",
    "rules",
]


class ApprovalProblem(BaseModel, frozen=True):
    """Why a decision was refused. Nothing is recorded and no order is placed."""

    code: ProblemCode
    message: str
    report_price: Decimal | None = None
    latest_price: Decimal | None = None
    move_pct: Decimal | None = None  # signed fraction: 0.028 is +2.8%
    max_shares: int | None = None  # the largest count the rules would accept


def expires_at(as_of: date) -> datetime:
    """A report can be decided until the close of the first session after `as_of`
    (M8 D-M8-5): its prices are the close of `as_of`, good for one more session."""
    following = sessions_between(as_of, as_of + _NEXT_SESSION_LOOKAHEAD)[0]
    return session_close(following)


def _rules_problem(message: str, *, max_shares: int | None = None) -> ApprovalProblem:
    return ApprovalProblem(code="rules", message=message, max_shares=max_shares)


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
) -> ApprovalDecision | ApprovalProblem:
    """Apply the owner's decision to the report's order (M8-FR-6 steps 2 to 6).

    `account` and `held_value` are net of pending orders. Shares can only go
    down: more than the recommended count, or fewer than one, is refused.
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
    if not 1 <= shares <= order.shares:
        return ApprovalProblem(
            code="shares_invalid",
            message=f"Shares must be a whole number from 1 to {order.shares}.",
            max_shares=order.shares,
        )
    if latest_price is None:
        return ApprovalProblem(
            code="price_unavailable",
            message="The latest price isn't available, so the price check can't be made.",
        )

    move = (latest_price - order.reference_price) / order.reference_price
    stale = abs(move) > staleness_pct
    if stale and not body.confirm_stale:
        return ApprovalProblem(
            code="stale",
            message=(
                f"The price moved {move:+.1%} since the report: "
                f"${order.reference_price} to ${latest_price}. Confirm, or reject and re-run."
            ),
            report_price=order.reference_price,
            latest_price=latest_price,
            move_pct=move,
        )
    warned = loss_warning is True
    if warned and not body.confirm_loss_warning:
        return ApprovalProblem(
            code="loss_warning",
            message="The account fell more than the loss-warning limit recently. Confirm to go on.",
        )

    if latest_price <= order.stop_loss:
        return _rules_problem(
            f"The price ${latest_price} is at or below the stop ${order.stop_loss}: "
            "the order would exit at once. Reject and re-run."
        )
    if latest_price >= order.take_profit:
        return _rules_problem(
            f"The price ${latest_price} is at or above the target ${order.take_profit}: "
            "the order would exit at once. Reject and re-run."
        )
    fits = min(
        cash_shares(account.cash, latest_price),
        cap_shares(account.equity, held_value, latest_price, cap_pct),
    )
    if shares > fits:
        return _rules_problem(
            f"{shares} shares don't fit the cash and per-stock cap at ${latest_price}; "
            f"at most {fits} do. If an earlier order has filled, run the fill check and retry.",
            max_shares=fits,
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
    )
