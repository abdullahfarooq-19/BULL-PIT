"""Evaluation metrics against hand-computed values (M7-AC-1, AC-3; dev-plan
sec7.1 evaluation metrics). Every expected value is worked out in the
docstring of its test.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from bullpit.domain import Bar, SizedOrder
from bullpit.eval.metrics import (
    CallRow,
    brier,
    buy_and_hold,
    calibration,
    hypothetical_trade,
    max_drawdown,
    no_trade_value,
    profit_factor,
    sharpe,
    tokens_per_request,
    total_return,
    weekly_returns,
    win_rate,
)

START = Decimal("100000")
# Decision-day equity after four weeks: +10%, -5%, +10%, -5%.
DECISION_EQUITY = [Decimal("110000"), Decimal("104500"), Decimal("114950"), Decimal("109202.5")]
SLIPPAGE = Decimal("0.0005")


def test_return_sharpe_and_drawdown() -> None:
    """Total return 109202.5 / 100000 - 1 = 0.092025. Weekly returns are
    0.10, -0.05, 0.10, -0.05: mean 0.025, deviations of +/-0.075, sample
    variance 4 x 0.005625 / 3 = 0.0075, so Sharpe = 0.025 / sqrt(0.0075) x
    sqrt(52) = 2.0817. Over the daily curve the falls 110000 -> 99000 and
    114950 -> 103455 are both 10%."""
    weekly = weekly_returns(START, DECISION_EQUITY)
    curve = [START, Decimal("110000"), Decimal("99000"), *DECISION_EQUITY[1:], Decimal("103455")]

    assert total_return(START, DECISION_EQUITY[-1]) == pytest.approx(0.092025)
    assert weekly == pytest.approx([0.10, -0.05, 0.10, -0.05])
    assert sharpe(weekly) == pytest.approx(2.0817, rel=1e-4)
    assert max_drawdown(curve) == pytest.approx(0.10)


def test_sharpe_is_none_without_a_ratio() -> None:
    assert sharpe([0.05]) is None
    assert sharpe([0.02, 0.02]) is None


def test_win_rate_and_profit_factor() -> None:
    """Closed P&L +300, +100, -100, -50: 2 of 4 win; gains 400 over losses
    150 is 2.6667. With no losing trade the factor is undefined."""
    pnls = [Decimal(300), Decimal(100), Decimal(-100), Decimal(-50)]

    assert win_rate(pnls) == pytest.approx(0.5)
    assert profit_factor(pnls) == pytest.approx(400 / 150)
    assert profit_factor([Decimal(300)]) is None
    assert win_rate([]) is None


def test_brier_and_calibration() -> None:
    """(0.8, won), (0.6, lost), (0.7, won), (0.3, lost): squared gaps 0.04,
    0.36, 0.09, 0.09, mean 0.58 / 4 = 0.145. In 5 bins: 0.3 sits in
    [0.2, 0.4); 0.6 and 0.7 in [0.6, 0.8) (mean 0.65, half won); 0.8 in
    [0.8, 1.0]."""
    pairs = [(0.8, True), (0.6, False), (0.7, True), (0.3, False)]

    assert brier(pairs) == pytest.approx(0.145)
    assert brier([]) is None
    bins = calibration(pairs, 5)
    assert [(b.low, b.count) for b in bins] == [(0.2, 1), (0.6, 2), (0.8, 1)]
    assert bins[1].mean_confidence == pytest.approx(0.65)
    assert [b.win_share for b in bins] == [0.0, 0.5, 1.0]


def test_tokens_count_a_cache_hit_at_its_original_cost() -> None:
    """Two real calls of 150 and 230 tokens, plus a cache hit whose original
    call cost 150: 530 tokens over 2 requests is 265."""
    calls = [
        CallRow(cache_key="k1", cache_hit=False, input_tokens=100, output_tokens=40,
                reasoning_tokens=10),
        CallRow(cache_key="k2", cache_hit=False, input_tokens=200, output_tokens=30,
                reasoning_tokens=0),
        CallRow(cache_key="k1", cache_hit=True, input_tokens=0, output_tokens=0,
                reasoning_tokens=0),
    ]  # fmt: skip

    cost = tokens_per_request(calls, {"k1": 150}, requests=2)

    assert (cost.total, cost.per_request) == (530, 265.0)
    assert tokens_per_request([], {}, requests=0).per_request == 0.0


def _order() -> SizedOrder:
    return SizedOrder(
        ticker="MSFT",
        shares=10,
        reference_price=Decimal("100"),
        stop_loss=Decimal("95"),
        take_profit=Decimal("107.5"),
        exit_style="normal",
        cost=Decimal("1000"),
        max_loss=Decimal("50"),
        max_gain=Decimal("75"),
        limit="target",
        limit_shares={"target": 10, "risk": 10, "cap": 10, "cash": 10},
    )


def _bar(day: int, open_: float, high: float, low: float, close: float) -> Bar:
    return Bar(date=date(2026, 8, day), open=open_, high=high, low=low, close=close, volume=1000)


def test_hypothetical_trade_and_no_trade_value() -> None:
    """Submitted on the 21st, entry at the next open 101 x 1.0005 = 101.05
    (to the cent). Stopped out on the 25th: the low of 94 crosses the 95 stop,
    so P&L = (95 - 101.05) x 10 = -60.50. A second trade never reaches a level
    and is marked at the last close 103: (103 - 101.05) x 10 = +19.50, open at
    the end."""
    stopped = hypothetical_trade(
        _order(),
        submitted_on=date(2026, 8, 21),
        bars=[_bar(24, 101, 103, 99, 102), _bar(25, 102, 105, 94, 96)],
        cash=START,
        slippage_pct=SLIPPAGE,
    )
    held = hypothetical_trade(
        _order(),
        submitted_on=date(2026, 8, 21),
        bars=[_bar(24, 101, 103, 99, 102), _bar(25, 102, 105, 100, 103)],
        cash=START,
        slippage_pct=SLIPPAGE,
    )

    assert (stopped.entry_price, stopped.exit_price, stopped.exit_reason) == (
        Decimal("101.05"),
        Decimal("95"),
        "stop",
    )
    assert stopped.pnl == Decimal("-60.50")
    assert (held.status, held.pnl) == ("open_at_end", Decimal("19.50"))

    value = no_trade_value([stopped, held])
    assert (value.count, value.wins, value.losses, value.open_at_end) == (2, 0, 1, 1)
    assert value.pnl == Decimal("-41.00")


def test_buy_and_hold() -> None:
    """Entry 100 x 1.0005 = 100.05; 110.055 / 100.05 - 1 = 0.10."""
    assert buy_and_hold(Decimal(100), Decimal("110.055"), SLIPPAGE) == pytest.approx(0.10)
