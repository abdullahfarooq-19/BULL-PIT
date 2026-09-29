"""The fill check: records what Alpaca did with live orders (architecture Part 14;
M8-FR-13 to FR-16). It only records: it never places, cancels or changes an order.

It runs when the dashboard opens and on demand (`bullpit fill-check`,
`POST /fill-check`), with no scheduler (dev-plan C9).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from bullpit.broker.alpaca import AlpacaBroker
from bullpit.config import Settings
from bullpit.data.calendar import sessions_between
from bullpit.domain import Trade
from bullpit.journal.models import EquitySnapshot, TradeRecord, trade_fields, trade_from_row

# The longest closure between two NYSE sessions is well under a week.
_SESSION_GAP = timedelta(days=7)


class FillCheckResult(BaseModel, frozen=True):
    changed: list[Trade]  # trades whose journal row was updated
    snapshots: int  # live equity snapshots written or changed
    warnings: list[str]


def _record_trades(broker: AlpacaBroker, session: Session, warnings: list[str]) -> list[Trade]:
    """Reads each live trade still `pending` or `open` and updates its row."""
    rows = session.scalars(
        select(TradeRecord)
        .where(TradeRecord.run_id.is_(None), TradeRecord.status.in_(("pending", "open")))
        .order_by(TradeRecord.id)
    ).all()
    changed: list[Trade] = []
    for row in rows:
        before = trade_from_row(row)
        live = broker.get_live_order(before)
        trade = live.trade
        label = f"{trade.ticker} order {trade.client_order_id}"
        if trade.status == "open" and not live.exits_active:
            # Closed from Alpaca's dashboard: the legs were cancelled, then a sell filled.
            fill = (
                broker.first_sell_fill(trade.ticker, live.exits_cancelled_at)
                if live.exits_cancelled_at is not None
                else None
            )
            if fill is None:
                warnings.append(f"{label}: open trade without active exits")
            else:
                trade = trade.model_copy(
                    update={
                        "status": "closed",
                        "exit_date": fill[0],
                        "exit_price": fill[1],
                        "exit_reason": "manual",
                    }
                )
        if live.partial:
            warnings.append(f"{label}: partial fill")
        if trade != before:
            for column, value in trade_fields(trade).items():
                setattr(row, column, value)
            changed.append(trade)
    return changed


def _record_equity(
    broker: AlpacaBroker, session: Session, *, as_of: date, settings: Settings
) -> int:
    """Upserts live equity snapshots from the base day of the loss warning's window
    through the latest close (M8-FR-15). Returns how many were written or changed."""
    base_day = as_of - timedelta(days=settings.loss_warning_days)
    start = sessions_between(base_day - _SESSION_GAP, base_day)[-1]
    written = 0
    for day, equity in broker.equity_history(start):
        snapshot = session.scalars(
            select(EquitySnapshot).where(EquitySnapshot.run_id.is_(None), EquitySnapshot.day == day)
        ).one_or_none()
        if snapshot is None:
            session.add(EquitySnapshot(run_id=None, day=day, equity=str(equity)))
        elif Decimal(snapshot.equity) != equity:
            snapshot.equity = str(equity)
        else:
            continue
        written += 1
    return written


def fill_check(
    *,
    broker: AlpacaBroker,
    sessions: sessionmaker[Session],
    as_of: date,
    settings: Settings,
) -> FillCheckResult:
    """Records the state of every open live order and the account's daily equity.
    Nothing is written if Alpaca can't be reached: the journal changes in one
    transaction after every read."""
    warnings: list[str] = []
    with sessions() as session:
        changed = _record_trades(broker, session, warnings)
        snapshots = _record_equity(broker, session, as_of=as_of, settings=settings)
        session.commit()
    return FillCheckResult(changed=changed, snapshots=snapshots, warnings=warnings)
