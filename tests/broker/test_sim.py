"""Simulated broker fill rules, one hand-built bar fixture each (M6-AC-1 to
AC-3; dev-plan.md sec7.1). Order: entry 100 (open 100 x 1.0005 = 100.05),
stop 95, target 110.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from bullpit.broker.sim import SimBroker
from bullpit.data.calendar import sessions_between
from bullpit.domain import Asset, Bar, ExitReason, SizedOrder
from bullpit.errors import DataUnavailable
from bullpit.risk.sizing import build_order

SLIPPAGE = Decimal("0.0005")
SUBMITTED = date(2024, 7, 8)
DAY_1 = date(2024, 7, 9)  # the entry day
DAY_2 = date(2024, 7, 10)


def _broker(cash: str = "100000") -> SimBroker:
    assets = {
        symbol: Asset(symbol=symbol, name=symbol, tradable=True, active=True)
        for symbol in ("AAPL", "MSFT")
    }
    return SimBroker(starting_cash=Decimal(cash), slippage_pct=SLIPPAGE, assets=assets)


def _order(ticker: str, shares: int, take_profit: str) -> SizedOrder:
    return build_order(
        ticker,
        shares,
        reference=Decimal("100"),
        stop=Decimal("95"),
        take_profit=Decimal(take_profit),
        exit_style="normal",
        limit="target",
        limit_shares={"target": shares, "risk": shares, "cap": shares, "cash": shares},
    )


def _bar(day: date, open_: float, high: float, low: float, close: float) -> Bar:
    return Bar(date=day, open=open_, high=high, low=low, close=close, volume=1e6)


def _submit(
    broker: SimBroker, ticker: str = "AAPL", shares: int = 10, take_profit: str = "110"
) -> str:
    order_id = f"order-{ticker}"
    broker.submit_bracket_order(
        _order(ticker, shares, take_profit), client_order_id=order_id, submitted_on=SUBMITTED
    )
    return order_id


QUIET_ENTRY_DAY = _bar(DAY_1, 100, 101, 99, 100)

EXIT_CASES = [
    pytest.param(QUIET_ENTRY_DAY, _bar(DAY_2, 100, 101, 94, 95), "95", "stop", DAY_2, id="stop"),
    pytest.param(
        QUIET_ENTRY_DAY, _bar(DAY_2, 100, 111, 99, 110), "110", "target", DAY_2, id="target"
    ),
    pytest.param(
        QUIET_ENTRY_DAY, _bar(DAY_2, 100, 111, 94, 100), "95", "stop", DAY_2, id="both-stop-wins"
    ),
    pytest.param(
        QUIET_ENTRY_DAY, _bar(DAY_2, 93, 94, 92, 93), "93", "stop", DAY_2, id="gap-down-past-stop"
    ),
    pytest.param(
        QUIET_ENTRY_DAY,
        _bar(DAY_2, 112, 113, 111, 112),
        "112",
        "target",
        DAY_2,
        id="gap-up-past-target",
    ),
    pytest.param(_bar(DAY_1, 100, 101, 94, 95), None, "95", "stop", DAY_1, id="entry-day-stop"),
]


@pytest.mark.parametrize(("first", "second", "price", "reason", "exit_day"), EXIT_CASES)
def test_exit_rules(
    first: Bar, second: Bar | None, price: str, reason: ExitReason, exit_day: date
) -> None:
    broker = _broker()
    order_id = _submit(broker)
    broker.on_session(DAY_1, {"AAPL": first}, {})
    if second is not None:
        broker.on_session(DAY_2, {"AAPL": second}, {})

    trade = broker.get_order(order_id)
    assert trade.status == "closed"
    assert (trade.exit_price, trade.exit_reason, trade.exit_date) == (
        Decimal(price),
        reason,
        exit_day,
    )
    assert trade.entry_price == Decimal("100.05")


def test_entry_next_open_with_slippage() -> None:
    broker = _broker()
    order_id = _submit(broker, take_profit="300")
    # 2024-07-04 is a holiday: an order submitted 2024-07-03 fills on 2024-07-05.
    entry_day = sessions_between(date(2024, 7, 3), date(2024, 7, 10))[0]
    assert entry_day == date(2024, 7, 5)

    broker.on_session(entry_day, {"AAPL": _bar(entry_day, 187.31, 190, 186, 189)}, {})

    trade = broker.get_order(order_id)
    assert (trade.status, trade.entry_date) == ("open", entry_day)
    assert trade.entry_price == Decimal("187.40")  # 187.31 x 1.0005 = 187.4047 -> cent
    assert broker.get_account().cash == Decimal("100000") - Decimal("187.40") * 10


def test_fill_downsized_when_cash_short() -> None:
    broker = _broker(cash="1000")
    ids = [_submit(broker, t, 5, "200") for t in ("AAPL", "MSFT")]  # each reserves 500

    bar = _bar(DAY_1, 150, 151, 149, 150)
    broker.on_session(DAY_1, {"AAPL": bar, "MSFT": bar}, {})

    filled = [broker.get_order(order_id) for order_id in ids]
    assert [(t.status, t.shares) for t in filled] == [("open", 3), ("open", 3)]
    assert broker.get_account().cash >= 0


def test_fill_cancelled_when_cash_cannot_buy_a_share() -> None:
    broker = _broker(cash="100")
    order_id = _submit(broker, shares=1, take_profit="200")

    broker.on_session(DAY_1, {"AAPL": _bar(DAY_1, 150, 151, 149, 150)}, {})

    trade = broker.get_order(order_id)
    assert (trade.status, trade.cancel_reason) == ("cancelled", "not enough cash at the open")
    assert broker.get_account().cash == Decimal("100")


def test_window_end() -> None:
    broker = _broker()
    open_id = _submit(broker, "AAPL")
    broker.on_session(DAY_1, {"AAPL": QUIET_ENTRY_DAY}, {})
    pending_id = _submit(broker, "MSFT")  # submitted after the last session it could fill on

    broker.end_window(DAY_1)

    open_trade = broker.get_order(open_id)
    assert (open_trade.status, open_trade.exit_reason) == ("open_at_end", "window_end")
    assert open_trade.exit_price == Decimal("100.00")  # the last close
    pending = broker.get_order(pending_id)
    assert (pending.status, pending.cancel_reason) == ("cancelled", "window ended before entry")


@pytest.mark.parametrize(
    ("bars", "splits"),
    [
        pytest.param({}, {}, id="missing-bar"),
        pytest.param({"AAPL": QUIET_ENTRY_DAY}, {"AAPL": 2.0}, id="split"),
    ],
)
def test_split_or_missing_bar_stops(bars: dict[str, Bar], splits: dict[str, float]) -> None:
    broker = _broker()
    _submit(broker)

    with pytest.raises(DataUnavailable, match="AAPL"):
        broker.on_session(DAY_1, bars, splits)
