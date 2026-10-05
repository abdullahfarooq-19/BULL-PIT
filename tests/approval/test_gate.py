"""The approval gate's safety refusals (M8-AC-2, AC-3, AC-4, AC-10, AC-15;
M11.1-AC-7): shares can only go down, a stale price needs a confirmation, a
report expires after one trading day, the loss warning needs a confirmation,
the rules are re-checked at the latest price, a limit order skips staleness, and
advanced mode may override the cap and risk limit but never cash. Pure, so no
network and no clock."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st

from bullpit.approval.gate import (
    ApprovalDecision,
    ApprovalProblem,
    OwnerDecision,
    check_decision,
    expires_at,
    override_flags,
)
from bullpit.domain import Account, SizedOrder, Trade
from bullpit.risk.sizing import net_of_pending

AS_OF = date(2024, 11, 27)  # the next session is Friday the 29th: Thanksgiving is the 28th
NOW = datetime(2024, 11, 27, 22, 0, tzinfo=UTC)
STALENESS = Decimal("0.02")
CAP = Decimal("0.10")
RISK = Decimal("0.01")
REFERENCE = Decimal("100")

ORDER = SizedOrder(
    ticker="AAPL",
    shares=32,
    reference_price=REFERENCE,
    stop_loss=Decimal("90"),
    take_profit=Decimal("115"),
    exit_style="normal",
    cost=Decimal("3200"),
    max_loss=Decimal("320"),
    max_gain=Decimal("480"),
    limit="target",
    limit_shares={"target": 32, "risk": 100, "cap": 100, "cash": 1000},
)
ACCOUNT = Account(cash=Decimal("96000"), equity=Decimal("100000"))


def _check(
    body: OwnerDecision,
    *,
    now: datetime = NOW,
    latest: Decimal | None = REFERENCE,
    loss_warning: bool | None = False,
    account: Account = ACCOUNT,
    held: Decimal = Decimal("0"),
) -> ApprovalDecision | ApprovalProblem:
    return check_decision(
        body,
        ORDER,
        as_of=AS_OF,
        now=now,
        latest_price=latest,
        loss_warning=loss_warning,
        account=account,
        held_value=held,
        staleness_pct=STALENESS,
        cap_pct=CAP,
        risk_pct=RISK,
    )


def _approve(**fields: object) -> OwnerDecision:
    """Buy now at the report's price unless the test says otherwise."""
    fields.setdefault("seen_price", REFERENCE)
    return OwnerDecision(decision="approve", **fields)  # type: ignore[arg-type]


def _problem(result: ApprovalDecision | ApprovalProblem) -> ApprovalProblem:
    assert isinstance(result, ApprovalProblem), result
    return result


def _decision(result: ApprovalDecision | ApprovalProblem) -> ApprovalDecision:
    assert isinstance(result, ApprovalDecision), result
    return result


@pytest.mark.parametrize(
    ("shares", "allowed"),
    [(33, False), (100, False), (0, False), (-1, False), (32, True), (None, True), (5, True)],
)
def test_shares_only_go_down(shares: int | None, allowed: bool) -> None:
    result = _check(_approve(shares=shares))

    if allowed:
        assert _decision(result).approved_shares == (32 if shares is None else shares)
    else:
        problem = _problem(result)
        assert problem.code == "shares_invalid"
        assert problem.max_shares == 32


def test_reject_records_a_rejection_with_no_shares() -> None:
    decision = _decision(_check(OwnerDecision(decision="reject")))

    assert (decision.decision, decision.approved_shares, decision.decided_by) == (
        "rejected",
        0,
        "owner",
    )


class TestStaleness:
    def test_more_than_the_limit_is_refused_with_both_prices(self) -> None:
        problem = _problem(_check(_approve(), latest=Decimal("103")))

        assert problem.code == "stale"
        assert (problem.report_price, problem.latest_price) == (REFERENCE, Decimal("103"))
        assert problem.move_pct == Decimal("0.03")

    def test_a_drop_is_stale_too(self) -> None:
        assert _problem(_check(_approve(), latest=Decimal("97"))).code == "stale"

    def test_confirmed_goes_through_and_is_recorded(self) -> None:
        decision = _decision(_check(_approve(confirm_stale=True), latest=Decimal("103")))

        assert decision.confirmations == ["stale"]
        assert decision.latest_price == Decimal("103")

    def test_exactly_the_limit_needs_no_confirmation(self) -> None:
        decision = _decision(_check(_approve(), latest=Decimal("102")))

        assert decision.confirmations == []

    def test_no_price_is_refused(self) -> None:
        assert _problem(_check(_approve(), latest=None)).code == "price_unavailable"


class TestExpiry:
    def test_a_report_lasts_until_the_close_of_the_next_session(self) -> None:
        close = datetime(2024, 11, 29, 18, 0, tzinfo=UTC)  # the early close
        assert expires_at(AS_OF) == close

        assert isinstance(_check(_approve(), now=close), ApprovalDecision)
        late = _problem(_check(_approve(), now=close + timedelta(seconds=1)))
        assert late.code == "expired"
        assert (
            _problem(
                _check(OwnerDecision(decision="reject"), now=close + timedelta(seconds=1))
            ).code
            == "expired"
        )

    def test_a_friday_report_lasts_until_monday(self) -> None:
        assert expires_at(date(2024, 11, 29)) == datetime(2024, 12, 2, 21, 0, tzinfo=UTC)


class TestLossWarning:
    def test_needs_a_confirmation(self) -> None:
        assert _problem(_check(_approve(), loss_warning=True)).code == "loss_warning"

    def test_confirmed_goes_through_and_is_recorded(self) -> None:
        decision = _decision(_check(_approve(confirm_loss_warning=True), loss_warning=True))

        assert decision.confirmations == ["loss_warning"]

    @pytest.mark.parametrize("warning", [False, None])
    def test_no_warning_needs_nothing(self, warning: bool | None) -> None:
        assert _decision(_check(_approve(), loss_warning=warning)).confirmations == []


class TestRulesRechecked:
    def test_cash_short_gives_the_largest_count_that_fits(self) -> None:
        poor = Account(cash=Decimal("1500"), equity=Decimal("100000"))

        problem = _problem(_check(_approve(), account=poor))

        assert (problem.code, problem.max_shares) == ("rules", 15)

    def test_cap_reached_gives_the_largest_count_that_fits(self) -> None:
        problem = _problem(_check(_approve(), held=Decimal("9000")))  # 10% cap is 10000

        assert (problem.code, problem.max_shares) == ("rules", 10)

    def test_a_lower_count_that_fits_is_approved(self) -> None:
        poor = Account(cash=Decimal("1500"), equity=Decimal("100000"))

        assert _decision(_check(_approve(shares=15), account=poor)).approved_shares == 15

    @pytest.mark.parametrize(
        "latest", [Decimal("90"), Decimal("85"), Decimal("115"), Decimal("120")]
    )
    def test_a_price_outside_the_exits_is_refused_even_when_confirmed(
        self, latest: Decimal
    ) -> None:
        problem = _problem(_check(_approve(confirm_stale=True), latest=latest))

        assert problem.code == "rules"
        assert problem.max_shares is None


class TestMarketAgainstTheSeenPrice:
    def test_staleness_is_measured_from_the_price_on_screen(self) -> None:
        seen = Decimal("110")  # the report said 100; the owner saw 110
        fresh = _check(_approve(seen_price=seen), latest=Decimal("111"))
        assert _decision(fresh).confirmations == []
        problem = _problem(_check(_approve(seen_price=seen), latest=Decimal("100")))
        assert (problem.code, problem.report_price) == ("stale", seen)

    def test_exits_follow_the_seen_price_and_the_page_cannot_change_them(self) -> None:
        body = _approve(
            seen_price=Decimal("110"), stop_loss=Decimal("1"), take_profit=Decimal("999")
        )

        decision = _decision(_check(body, latest=Decimal("111")))

        assert (decision.entry_price, decision.stop_loss, decision.take_profit) == (
            Decimal("110"),
            Decimal("100"),
            Decimal("125"),
        )
        assert (decision.order_type, decision.limit_price, decision.seen_price) == (
            "market",
            None,
            Decimal("110"),
        )
        assert decision.overrides == []

    def test_a_buy_now_body_needs_the_seen_price(self) -> None:
        with pytest.raises(ValueError, match="seen_price"):
            OwnerDecision(decision="approve")


class TestLimitOrders:
    def test_skips_staleness_and_records_the_limit(self) -> None:
        body = _approve(order_type="limit", limit_price=Decimal("100"), seen_price=None)

        decision = _decision(_check(body, latest=Decimal("103")))

        assert decision.confirmations == []
        assert (decision.order_type, decision.entry_price, decision.limit_price) == (
            "limit",
            Decimal("100"),
            Decimal("100"),
        )
        assert (decision.stop_loss, decision.take_profit) == (Decimal("90"), Decimal("115"))

    @pytest.mark.parametrize("limit", [None, Decimal("0"), Decimal("-5")])
    def test_refuses_a_missing_or_non_positive_limit(self, limit: Decimal | None) -> None:
        body = _approve(order_type="limit", limit_price=limit, seen_price=None)

        assert _problem(_check(body)).code == "limit_invalid"

    def test_far_below_the_market_waits_even_past_the_take_profit(self) -> None:
        body = _approve(order_type="limit", limit_price=Decimal("80"), seen_price=None)

        decision = _decision(_check(body, latest=Decimal("100")))  # target would be 95

        assert decision.take_profit == Decimal("95")

    def test_above_the_market_by_more_than_the_stop_distance_is_refused(self) -> None:
        body = _approve(order_type="limit", limit_price=Decimal("120"), seen_price=None)

        assert _problem(_check(body, latest=Decimal("100"))).code == "rules"  # stop would be 110

    def test_cash_and_cap_are_checked_at_the_limit_price(self) -> None:
        body = _approve(order_type="limit", limit_price=Decimal("90"), seen_price=None)

        problem = _problem(_check(body, held=Decimal("9000")))  # (10000 - 9000) / 90

        assert (problem.code, problem.max_shares) == ("rules", 11)

    def test_a_limit_that_cannot_hold_the_plans_stop_is_refused(self) -> None:
        body = _approve(order_type="limit", limit_price=Decimal("10"), seen_price=None)

        assert _problem(_check(body)).code == "exits_invalid"  # stop would be 0


class TestExitsAgainstTheLatestPriceInAdvancedMode:
    def test_a_custom_stop_at_the_price_is_refused(self) -> None:
        body = _approve(advanced=True, stop_loss=Decimal("99"))

        assert _problem(_check(body, latest=Decimal("99"))).code == "rules"

    def test_a_custom_target_at_the_price_is_refused(self) -> None:
        body = _approve(advanced=True, take_profit=Decimal("101"))

        assert _problem(_check(body, latest=Decimal("102"))).code == "rules"


class TestAdvancedMode:
    def test_shares_above_the_plan_are_allowed_once_confirmed(self) -> None:
        refused = _problem(_check(_approve(advanced=True, shares=40)))
        assert (refused.code, refused.overrides) == ("override_not_confirmed", ["size_above_plan"])

        decision = _decision(_check(_approve(advanced=True, shares=40, confirm_overrides=True)))

        assert (decision.approved_shares, decision.overrides) == (40, ["size_above_plan"])

    def test_above_the_cap_and_the_risk_limit_become_flags(self) -> None:
        body = _approve(advanced=True, shares=150, confirm_overrides=True)

        decision = _decision(_check(body))

        assert decision.overrides == ["size_above_plan", "above_cap", "above_risk_limit"]

    def test_custom_exits_are_recorded(self) -> None:
        body = _approve(
            advanced=True,
            stop_loss=Decimal("95"),
            take_profit=Decimal("110"),
            confirm_overrides=True,
        )

        decision = _decision(_check(body))

        assert (decision.stop_loss, decision.take_profit) == (Decimal("95"), Decimal("110"))
        assert decision.overrides == ["custom_exits"]

    def test_cash_is_the_only_hard_limit(self) -> None:
        poor = Account(cash=Decimal("1500"), equity=Decimal("100000"))

        problem = _problem(_check(_approve(advanced=True, confirm_overrides=True), account=poor))

        assert (problem.code, problem.max_shares) == ("rules", 15)

    @pytest.mark.parametrize(
        ("stop", "target"),
        [("100", None), ("120", None), ("0", None), ("-1", None), (None, "100"), (None, "90")],
    )
    def test_bad_exits_are_refused(self, stop: str | None, target: str | None) -> None:
        body = _approve(
            advanced=True,
            stop_loss=None if stop is None else Decimal(stop),
            take_profit=None if target is None else Decimal(target),
            confirm_overrides=True,
        )

        assert _problem(_check(body)).code == "exits_invalid"

    def test_zero_shares_are_still_refused(self) -> None:
        assert _problem(_check(_approve(advanced=True, shares=0))).code == "shares_invalid"

    def test_a_plain_body_with_exits_is_not_advanced(self) -> None:
        assert _decision(_check(_approve(stop_loss=Decimal("95")))).overrides == []


def test_override_flags() -> None:
    def flags(final: SizedOrder, held: str = "0") -> list[str]:
        return list(
            override_flags(
                final, ORDER, Decimal("100000"), Decimal(held), cap_pct=CAP, risk_pct=RISK
            )
        )

    assert flags(ORDER) == []
    assert flags(ORDER.model_copy(update={"stop_loss": Decimal("95")})) == ["custom_exits"]
    assert flags(ORDER.model_copy(update={"shares": 33})) == ["size_above_plan"]
    assert flags(ORDER, held="7000") == ["above_cap"]  # 7000 + 3200 > 10000
    assert flags(ORDER.model_copy(update={"max_loss": Decimal("1000.01")})) == ["above_risk_limit"]


# Near the plan's $100, so a fair share of the draws are accepted and reach the asserts.
_prices = st.decimals(min_value="5", max_value="200", places=2)


@given(
    mode=st.sampled_from(["market", "limit"]),
    advanced=st.booleans(),
    entry=_prices,
    move=st.decimals(min_value="-0.05", max_value="0.05", places=3),
    shares=st.integers(min_value=-1, max_value=60),
    cash=st.decimals(min_value="0", max_value="20000", places=2),
    equity=st.decimals(min_value="10000", max_value="1000000", places=2),
    held_pct=st.decimals(min_value="0", max_value="0.2", places=2),
    stop_gap=st.none() | st.decimals(min_value="-3", max_value="30", places=2),
    target_gap=st.none() | st.decimals(min_value="-3", max_value="30", places=2),
)
@hyp_settings(max_examples=200, deadline=None)
def test_gate_property(
    mode: str,
    advanced: bool,
    entry: Decimal,
    move: Decimal,
    shares: int,
    cash: Decimal,
    equity: Decimal,
    held_pct: Decimal,
    stop_gap: Decimal | None,
    target_gap: Decimal | None,
) -> None:
    """Whatever the owner sends, an accepted decision never costs more than the
    cash it was checked against and always has 0 < stop < entry < take-profit;
    every refusal carries a code."""
    body = OwnerDecision(
        decision="approve",
        shares=shares,
        order_type=mode,  # type: ignore[arg-type]
        limit_price=entry if mode == "limit" else None,
        seen_price=entry if mode == "market" else None,
        advanced=advanced,
        stop_loss=None if stop_gap is None else entry - stop_gap,
        take_profit=None if target_gap is None else entry + target_gap,
        confirm_stale=True,
        confirm_loss_warning=True,
        confirm_overrides=True,
    )

    latest = entry * (1 + move)
    result = _check(
        body, latest=latest, account=Account(cash=cash, equity=equity), held=equity * held_pct
    )

    if isinstance(result, ApprovalProblem):
        assert result.code
        return
    assert result.entry_price is not None
    assert result.stop_loss is not None
    assert result.take_profit is not None
    assert 0 < result.stop_loss < result.entry_price < result.take_profit
    assert result.approved_shares >= 1
    assert (
        result.approved_shares * max(result.entry_price, latest if mode == "market" else 0) <= cash
    )


def test_net_of_pending() -> None:
    pending = [
        _trade("AAPL", shares=10, reference=Decimal("100")),
        _trade("MSFT", shares=5, reference=Decimal("200")),
    ]

    account, held = net_of_pending(ACCOUNT, Decimal("500"), pending, "AAPL")

    assert account == Account(cash=Decimal("94000"), equity=Decimal("100000"))
    assert held == Decimal("1500")  # only AAPL's pending 10 x 100 joins the position


def test_a_pending_order_counts_against_the_next_approval() -> None:
    tight = Account(cash=Decimal("4000"), equity=Decimal("100000"))
    pending = [_trade("MSFT", shares=10, reference=Decimal("200"))]  # 2000 already spoken for
    net, held = net_of_pending(tight, Decimal("0"), pending, "AAPL")

    assert isinstance(_check(_approve(), account=tight), ApprovalDecision)
    problem = _problem(_check(_approve(), account=net, held=held))
    assert (problem.code, problem.max_shares) == ("rules", 20)


def _trade(ticker: str, *, shares: int, reference: Decimal) -> Trade:
    return Trade(
        client_order_id=f"bullpit-{ticker}",
        ticker=ticker,
        submitted_on=AS_OF,
        shares=shares,
        reference_price=reference,
        stop_loss=reference - 10,
        take_profit=reference + 15,
        status="pending",
    )
