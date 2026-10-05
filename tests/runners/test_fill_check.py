"""The fill check records what Alpaca reports and never changes an order
(M8-AC-7 automated, AC-11): one pass over a trade that filled, one stopped out,
one closed by hand, and one open without exits."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from bullpit.broker.alpaca import LiveOrder
from bullpit.config import Settings
from bullpit.domain import Account, Trade
from bullpit.journal.models import (
    EquitySnapshot,
    Request,
    TradeRecord,
    trade_from_row,
    trade_record,
)
from bullpit.runners.fill_check import fill_check
from tests.broker.fake_broker import FakeOrderBroker

AS_OF = date(2026, 9, 29)
CLOSED_AT = datetime(2026, 10, 1, 14, 30, tzinfo=UTC)


def _trade(ticker: str, **fields: object) -> Trade:
    return Trade(
        client_order_id=f"bullpit-{ticker}",
        ticker=ticker,
        submitted_on=date(2026, 9, 25),
        shares=10,
        reference_price=Decimal("100"),
        stop_loss=Decimal("90"),
        take_profit=Decimal("115"),
        **{"status": "pending", **fields},  # type: ignore[arg-type]
    )


def _journal(sessions: sessionmaker[Session], *trades: Trade) -> None:
    with sessions() as session:
        for trade in trades:
            request_id = f"request-{trade.ticker}"
            session.add(
                Request(
                    id=request_id,
                    mode="live",
                    as_of=trade.submitted_on,
                    created_at=datetime(2026, 9, 25, tzinfo=UTC),
                    ticker=trade.ticker,
                    status="completed",
                )
            )
            session.flush()
            session.add(trade_record(request_id, trade))
        session.commit()


def _live(trade: Trade, *, active: bool = True, cancelled_at: datetime | None = None) -> LiveOrder:
    return LiveOrder(
        trade=trade, exits_active=active, exits_cancelled_at=cancelled_at, partial=False
    )


def _rows(sessions: sessionmaker[Session]) -> dict[str, Trade]:
    with sessions() as session:
        return {row.ticker: trade_from_row(row) for row in session.query(TradeRecord).all()}


def test_fill_check_happy_path(settings: Settings, sessions: sessionmaker[Session]) -> None:
    filled = _trade("FILL")
    stopped = _trade(
        "STOP", status="open", entry_date=date(2026, 9, 28), entry_price=Decimal("100")
    )
    manual = _trade("HAND", status="open", entry_date=date(2026, 9, 28), entry_price=Decimal("100"))
    bare = _trade("BARE", status="open", entry_date=date(2026, 9, 28), entry_price=Decimal("100"))
    _journal(sessions, filled, stopped, manual, bare)

    broker = FakeOrderBroker(account=Account(cash=Decimal(0), equity=Decimal(0)))
    broker.live_orders = {
        filled.client_order_id: _live(
            filled.model_copy(
                update={
                    "status": "open",
                    "entry_date": date(2026, 9, 28),
                    "entry_price": Decimal("100.10"),
                }
            )
        ),
        stopped.client_order_id: _live(
            stopped.model_copy(
                update={
                    "status": "closed",
                    "exit_date": date(2026, 9, 30),
                    "exit_price": Decimal("90"),
                    "exit_reason": "stop",
                }
            ),
            active=False,
        ),
        manual.client_order_id: _live(manual, active=False, cancelled_at=CLOSED_AT),
        bare.client_order_id: _live(bare, active=False),
    }
    broker.sell_fills = [(CLOSED_AT, date(2026, 10, 1), Decimal("102.50"))]
    broker.history = [(date(2026, 9, 24), Decimal("100000")), (date(2026, 9, 28), Decimal("99435"))]

    result = fill_check(broker=broker, sessions=sessions, as_of=AS_OF, settings=settings)  # type: ignore[arg-type]

    rows = _rows(sessions)
    assert rows["FILL"].status == "open"
    assert rows["FILL"].entry_price == Decimal("100.10")
    assert (rows["STOP"].status, rows["STOP"].exit_reason) == ("closed", "stop")
    assert rows["STOP"].pnl == Decimal("-100")
    assert (rows["HAND"].status, rows["HAND"].exit_reason) == ("closed", "manual")
    assert (rows["HAND"].exit_date, rows["HAND"].exit_price) == (
        date(2026, 10, 1),
        Decimal("102.50"),
    )
    assert rows["HAND"].pnl == Decimal("25.00")
    assert rows["BARE"].status == "open"  # only a warning: the check never guesses
    assert {trade.ticker for trade in result.changed} == {"FILL", "STOP", "HAND"}
    assert result.warnings == ["BARE order bullpit-BARE: open trade without active exits"]
    assert result.snapshots == 2
    with sessions() as session:
        days = {s.day: s.equity for s in session.query(EquitySnapshot).filter_by(run_id=None)}
    assert days == {date(2026, 9, 24): "100000", date(2026, 9, 28): "99435"}

    again = fill_check(broker=broker, sessions=sessions, as_of=AS_OF, settings=settings)  # type: ignore[arg-type]

    assert again.changed == []
    assert again.snapshots == 0
    assert again.warnings == result.warnings
