"""Stage A hard rules, the rule order, the only-shrink rule, and the loss
warning (M4-AC-3, AC-5, AC-9)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from bullpit.domain import Account, SizedOrder
from bullpit.risk.rules import loss_warning, shrink, stage_a

_BASELINE: dict[str, Any] = {
    "ticker": "AAPL",
    "reference": Decimal("182"),
    "atr": Decimal("4"),
    "exit_style": "normal",
    "target_weight": Decimal("0.06"),
    "account": Account(cash=Decimal("96000"), equity=Decimal("100000")),
    "held_value": Decimal("0"),
    "stop_atr": Decimal("2"),
    "reward_risk": Decimal("1.5"),
    "risk_pct": Decimal("0.01"),
    "cap_pct": Decimal("0.10"),
}


def _call(**overrides: object) -> SizedOrder | str:
    return stage_a(**{**_BASELINE, **overrides})


class TestHardRulesBlock:
    def test_price_not_positive(self) -> None:
        assert _call(reference=Decimal("0")) == "ATR or price not available."

    def test_atr_missing(self) -> None:
        assert _call(atr=None) == "ATR or price not available."

    def test_atr_not_positive(self) -> None:
        assert _call(atr=Decimal("0")) == "ATR or price not available."

    def test_no_cash(self) -> None:
        assert _call(account=Account(cash=Decimal("0"), equity=Decimal("100000"))) == (
            "No cash available."
        )

    def test_no_equity(self) -> None:
        assert _call(account=Account(cash=Decimal("96000"), equity=Decimal("0"))) == (
            "No cash available."
        )

    def test_cap_reached(self) -> None:
        assert _call(held_value=Decimal("12000")) == (
            "Per-stock cap reached: AAPL is already 12.0% of equity (cap 10%)."
        )

    def test_stop_not_positive(self) -> None:
        result = _call(atr=Decimal("100"))  # stop = 182 - 2*100 = -18.00
        assert result == "Exit prices invalid (stop -18.00)."

    def test_stop_rounds_up_to_the_reference(self) -> None:
        # raw stop = 182 - 2*0.001 = 181.998 -> rounds half up to 182.00 == reference.
        result = _call(atr=Decimal("0.001"))
        assert result == "Exit prices invalid (stop 182.00)."

    def test_size_rounds_to_zero_shares(self) -> None:
        result = _call(reference=Decimal("50000"))
        assert result == "Size rounds to 0 shares (set by the target limit)."


class TestFirstFailingRuleWins:
    def test_cash_before_cap(self) -> None:
        result = _call(
            account=Account(cash=Decimal("0"), equity=Decimal("100000")),
            held_value=Decimal("50000"),  # also breaks the cap rule
        )
        assert result == "No cash available."


class TestStageAPasses:
    def test_worked_example_end_to_end(self) -> None:
        result = _call()
        assert isinstance(result, SizedOrder)
        assert result.shares == 32
        assert result.stop_loss == Decimal("174.00")
        assert result.take_profit == Decimal("194.00")
        assert result.limit == "target"


class TestShrinkOnlyLowers:
    def _order(self) -> SizedOrder:
        result = _call()
        assert isinstance(result, SizedOrder)
        return result

    def test_shrink_to_more_shares_is_clamped(self) -> None:
        order = self._order()
        resized, clamped = shrink(order, 40)
        assert clamped is True
        assert resized == order

    def test_shrink_to_the_same_shares_is_clamped(self) -> None:
        order = self._order()
        resized, clamped = shrink(order, order.shares)
        assert clamped is True
        assert resized == order

    def test_shrink_to_fewer_shares_recomputes_cost_loss_and_gain(self) -> None:
        order = self._order()
        resized, clamped = shrink(order, 20)
        assert clamped is False
        assert resized.shares == 20
        assert resized.cost == Decimal("3640.00")
        assert resized.max_loss == Decimal("160.00")
        assert resized.max_gain == Decimal("240.00")
        assert resized.stop_loss == order.stop_loss
        assert resized.take_profit == order.take_profit


class TestLossWarning:
    _AS_OF = date(2024, 7, 12)
    _BASE_DATE = date(2024, 7, 1)

    @pytest.mark.parametrize(
        ("current_equity", "expected"),
        [
            (Decimal("94000"), True),  # 6% drop
            (Decimal("96000"), False),  # 4% drop
            (Decimal("95000"), False),  # exactly 5%, not "more than"
        ],
    )
    def test_drop_against_a_week_ago(self, current_equity: Decimal, expected: bool) -> None:
        history = [(self._BASE_DATE, Decimal("100000")), (self._AS_OF, current_equity)]
        result = loss_warning(history, self._AS_OF, drop_pct=Decimal("0.05"), days=7)
        assert result is expected

    def test_history_too_short_is_unknown(self) -> None:
        history = [(date(2024, 7, 10), Decimal("100000"))]
        result = loss_warning(history, self._AS_OF, drop_pct=Decimal("0.05"), days=7)
        assert result is None
