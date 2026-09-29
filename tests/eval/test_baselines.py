"""Decision rules of the code baselines (M7-AC-5; dev-plan sec7.1: a wrong
rule silently corrupts the comparison)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from bullpit.eval.baselines import (
    always_buy,
    bullpit_wanted_buy,
    fixed_recommendation,
    ma_rule,
)
from bullpit.tools.indicators import Indicators


def _indicators(above_sma_50: bool | None) -> Indicators:
    return Indicators(
        close=100.0,
        sma_20=None,
        sma_50=None if above_sma_50 is None else 95.0,
        above_sma_20=None,
        above_sma_50=above_sma_50,
        rsi_14=None,
        atr_14=2.0,
        volatility=None,
        return_1w=None,
        return_1m=None,
        return_3m=None,
    )


def test_always_buy() -> None:
    assert always_buy(_indicators(False)) is True


@pytest.mark.parametrize(("above", "expected"), [(True, True), (False, False), (None, False)])
def test_ma_rule(above: bool | None, expected: bool) -> None:
    assert ma_rule(_indicators(above)) is expected


@pytest.mark.parametrize(
    ("last_action", "review_decision", "expected"),
    [
        ("buy", "approve", True),
        ("buy", "shrink", True),
        ("buy", "veto", False),
        ("buy", None, True),  # Stage A blocked it: still a buy decision
        ("no_trade", None, False),
    ],
)
def test_replayed_decision(last_action: str, review_decision: str | None, expected: bool) -> None:
    assert bullpit_wanted_buy(last_action, review_decision) is expected


def test_fixed_recommendation_uses_the_fixed_weight_and_style() -> None:
    buy = fixed_recommendation(
        "MSFT", True, weight=Decimal("0.06"), exit_style="normal", reason="always buy"
    )
    skip = fixed_recommendation(
        "MSFT", False, weight=Decimal("0.06"), exit_style="normal", reason="below SMA 50"
    )

    assert (buy.action, buy.target_weight, buy.exit_style, buy.confidence) == (
        "buy",
        Decimal("0.06"),
        "normal",
        0.0,
    )
    assert (skip.action, skip.target_weight, skip.reasoning) == (
        "no_trade",
        Decimal(0),
        "below SMA 50",
    )
