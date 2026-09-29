"""Pure sizing maths (M4-AC-1, AC-2): the architecture's worked example, the
exit table, a property test over the four limits, and the holding/tie-break
rule."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import assume, given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from bullpit.domain import ExitStyle, SizeLimit
from bullpit.risk.sizing import build_order, exit_prices, share_limits

_EXIT_STOP_ATR: dict[ExitStyle, Decimal] = {
    "tight": Decimal("1.5"),
    "normal": Decimal("2"),
    "wide": Decimal("3"),
}
_REWARD_RISK = Decimal("1.5")
_LIMIT_ORDER: tuple[SizeLimit, ...] = ("target", "risk", "cap", "cash")


def _select(limits: dict[SizeLimit, int]) -> tuple[int, SizeLimit]:
    shares = min(limits.values())
    limit = next(name for name in _LIMIT_ORDER if limits[name] == shares)
    return shares, limit


class TestWorkedExample:
    def test_worked_example(self) -> None:
        """The architecture's example (Part 11): equity $100,000, cash
        $96,000, AAPL at $182, ATR $4, normal exit, 6% target, nothing held."""
        reference = Decimal("182")
        atr = Decimal("4")
        stop, take_profit = exit_prices(
            reference, atr, stop_atr=_EXIT_STOP_ATR["normal"], reward_risk=_REWARD_RISK
        )
        assert stop == Decimal("174.00")
        assert take_profit == Decimal("194.00")

        limits = share_limits(
            reference=reference,
            stop=stop,
            target_weight=Decimal("0.06"),
            equity=Decimal("100000"),
            cash=Decimal("96000"),
            held_value=Decimal("0"),
            risk_pct=Decimal("0.01"),
            cap_pct=Decimal("0.10"),
        )
        assert limits == {"target": 32, "risk": 125, "cap": 54, "cash": 527}

        shares, limit = _select(limits)
        order = build_order(
            "AAPL",
            shares,
            reference=reference,
            stop=stop,
            take_profit=take_profit,
            exit_style="normal",
            limit=limit,
            limit_shares=limits,
        )
        assert order.shares == 32
        assert order.limit == "target"
        assert order.cost == Decimal("5824.00")
        assert order.max_loss == Decimal("256.00")
        assert order.max_gain == Decimal("384.00")


class TestExitTable:
    @pytest.mark.parametrize(
        ("exit_style", "expected_stop", "expected_take_profit"),
        [
            ("tight", Decimal("97.00"), Decimal("104.50")),
            ("normal", Decimal("96.00"), Decimal("106.00")),
            ("wide", Decimal("94.00"), Decimal("109.00")),
        ],
    )
    def test_exit_table(
        self, exit_style: ExitStyle, expected_stop: Decimal, expected_take_profit: Decimal
    ) -> None:
        """Reference $100, ATR $2: tight 1.5/2.25, normal 2/3, wide 3/4.5 ATR."""
        stop, take_profit = exit_prices(
            Decimal("100"),
            Decimal("2"),
            stop_atr=_EXIT_STOP_ATR[exit_style],
            reward_risk=_REWARD_RISK,
        )
        assert stop == expected_stop
        assert take_profit == expected_take_profit

    def test_rounds_half_up_to_the_cent(self) -> None:
        stop, take_profit = exit_prices(
            Decimal("100.005"), Decimal("1"), stop_atr=Decimal("1.5"), reward_risk=_REWARD_RISK
        )
        assert stop == Decimal("98.51")  # 100.005 - 1.5 = 98.505 -> half up
        assert take_profit == Decimal("102.26")  # 100.005 + 2.25 = 102.255 -> half up


class TestLimitsHoldForAnyInput:
    @given(
        reference_cents=st.integers(min_value=100, max_value=500_000),
        equity_cents=st.integers(min_value=100_000, max_value=1_000_000_000),
        exit_style=st.sampled_from(["tight", "normal", "wide"]),
        target_weight_units=st.integers(min_value=0, max_value=1000),
        cash_fraction=st.integers(min_value=0, max_value=100),
        held_fraction=st.integers(min_value=0, max_value=15),
        atr_fraction=st.integers(min_value=1, max_value=25),
    )
    @hyp_settings(max_examples=200, deadline=None)
    def test_limits_hold_for_any_input(
        self,
        reference_cents: int,
        equity_cents: int,
        exit_style: ExitStyle,
        target_weight_units: int,
        cash_fraction: int,
        held_fraction: int,
        atr_fraction: int,
    ) -> None:
        reference = Decimal(reference_cents) / 100
        equity = Decimal(equity_cents) / 100
        target_weight = Decimal(target_weight_units) / 10_000  # 0.0000 to 0.1000
        cash = equity * Decimal(cash_fraction) / 100
        held_value = equity * Decimal(held_fraction) / 100
        atr = reference * Decimal(atr_fraction) / 100  # up to reference / 4
        risk_pct = Decimal("0.01")
        cap_pct = Decimal("0.10")

        # A holding already at or above the cap is blocked by Stage A's hard
        # rule (M4-FR-9) before sizing ever runs (M4-AC-2: "blocked inputs
        # are skipped").
        assume(held_value < cap_pct * equity)

        stop, take_profit = exit_prices(
            reference, atr, stop_atr=_EXIT_STOP_ATR[exit_style], reward_risk=_REWARD_RISK
        )

        limits = share_limits(
            reference=reference,
            stop=stop,
            target_weight=target_weight,
            equity=equity,
            cash=cash,
            held_value=held_value,
            risk_pct=risk_pct,
            cap_pct=cap_pct,
        )
        shares, limit = _select(limits)
        order = build_order(
            "TEST",
            shares,
            reference=reference,
            stop=stop,
            take_profit=take_profit,
            exit_style=exit_style,
            limit=limit,
            limit_shares=limits,
        )

        assert order.shares >= 0
        assert order.cost <= cash
        assert order.max_loss <= risk_pct * equity
        assert held_value + order.cost <= cap_pct * equity
        assert abs((take_profit - reference) - _REWARD_RISK * (reference - stop)) <= Decimal("0.02")


class TestHeldValueAndTieBreak:
    def test_held_value_lowers_cap_shares(self) -> None:
        no_holding = share_limits(
            reference=Decimal("100"),
            stop=Decimal("80"),
            target_weight=Decimal("1"),
            equity=Decimal("100000"),
            cash=Decimal("100000"),
            held_value=Decimal("0"),
            risk_pct=Decimal("0.01"),
            cap_pct=Decimal("0.10"),
        )
        with_holding = share_limits(
            reference=Decimal("100"),
            stop=Decimal("80"),
            target_weight=Decimal("1"),
            equity=Decimal("100000"),
            cash=Decimal("100000"),
            held_value=Decimal("9000"),
            risk_pct=Decimal("0.01"),
            cap_pct=Decimal("0.10"),
        )
        assert no_holding["cap"] == 100
        assert with_holding["cap"] == 10

    def test_tie_break_prefers_the_first_limit_in_order(self) -> None:
        limits = share_limits(
            reference=Decimal("100"),
            stop=Decimal("80"),
            target_weight=Decimal("0.01"),
            equity=Decimal("100000"),
            cash=Decimal("100000"),
            held_value=Decimal("9000"),
            risk_pct=Decimal("0.01"),
            cap_pct=Decimal("0.10"),
        )
        assert limits == {"target": 10, "risk": 50, "cap": 10, "cash": 1000}
        _, limit = _select(limits)
        assert limit == "target"
