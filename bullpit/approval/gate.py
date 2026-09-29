"""The approval gate's backtest policy (architecture Part 13; M6-FR-6).

No one can be asked in a backtest, so every buy is approved as sized. M8 adds
the owner's decision and the `interrupt()` node to this module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from bullpit.domain import SizedOrder


class ApprovalDecision(BaseModel, frozen=True):
    decision: Literal["approved", "rejected"]
    recommended_shares: int
    approved_shares: int
    decided_by: Literal["backtest_policy"]  # M8 adds "owner"


def backtest_policy(order: SizedOrder) -> ApprovalDecision:
    """Approve the order exactly as sized."""
    return ApprovalDecision(
        decision="approved",
        recommended_shares=order.shares,
        approved_shares=order.shares,
        decided_by="backtest_policy",
    )
