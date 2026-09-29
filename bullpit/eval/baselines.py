"""The decision rules of the code baselines and of Bull Pit (fixed sizing)
(architecture §12; M7 specs-plan FR-3, §11.3; D-M7-4, D-M7-5).

Pure: no I/O and no settings. A policy only answers "buy or not"; sizing and
exits stay with Stage A, so every approach is measured on the same rules.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from bullpit.domain import ExitStyle
from bullpit.state import Recommendation
from bullpit.tools.indicators import Indicators

Policy = Literal["bullpit", "single_agent", "always_buy", "ma_rule", "bullpit_fixed"]
CODE_POLICIES: frozenset[Policy] = frozenset({"always_buy", "ma_rule", "bullpit_fixed"})


def always_buy(indicators: Indicators) -> bool:
    """Buys every week; takes the indicators only to match every other rule."""
    return True


def ma_rule(indicators: Indicators) -> bool:
    """Buys when the close is above its 50-day average; no trade below it or
    when the average isn't available."""
    return indicators.above_sma_50 is True


def bullpit_wanted_buy(last_action: str, review_decision: str | None) -> bool:
    """Whether Bull Pit's last trader attempt was a buy the risk manager didn't
    veto. A Stage A block still counts: it is sizing in the source run's
    account, which the fixed-sizing variant replaces."""
    return last_action == "buy" and review_decision != "veto"


def fixed_recommendation(
    ticker: str, buy: bool, *, weight: Decimal, exit_style: ExitStyle, reason: str
) -> Recommendation:
    """A rule's decision in the trader's format. A rule has no confidence, so
    it records 0 and stays out of the Brier score."""
    return Recommendation(
        ticker=ticker,
        action="buy" if buy else "no_trade",
        target_weight=weight if buy else Decimal(0),
        exit_style=exit_style,
        confidence=0.0,
        decisive_evidence=[],
        reasoning=reason,
        flagged=False,
    )
