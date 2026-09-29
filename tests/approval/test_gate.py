"""The approval gate's safety refusals (M8-AC-2, AC-3, AC-4, AC-10, AC-15):
shares can only go down, a stale price needs a confirmation, a report expires
after one trading day, the loss warning needs a confirmation, and the rules
are re-checked at the latest price. Pure, so no network and no clock."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from bullpit.approval.gate import (
    ApprovalDecision,
    ApprovalProblem,
    OwnerDecision,
    check_decision,
    expires_at,
)
from bullpit.domain import Account, SizedOrder, Trade
from bullpit.risk.sizing import net_of_pending

AS_OF = date(2024, 11, 27)  # the next session is Friday the 29th: Thanksgiving is the 28th
NOW = datetime(2024, 11, 27, 22, 0, tzinfo=UTC)
STALENESS = Decimal("0.02")
CAP = Decimal("0.10")
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
    )


def _approve(**fields: object) -> OwnerDecision:
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
