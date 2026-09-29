"""The simulated broker for backtests (architecture Part 14, simulated broker;
M6 specs-plan FR-1 to FR-5, sec11.2; ADR-0005).

Pure: no I/O and no settings. The runner hands it each session's bars, the
slippage and the starting cash. All money is `Decimal`, rounded to the cent.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal

from bullpit.domain import Account, Asset, Bar, ExitReason, Position, SizedOrder, Trade
from bullpit.errors import BrokerRejected, DataUnavailable
from bullpit.risk.sizing import floor_shares, round_cent


def _exit_fill(trade: Trade, bar: Bar) -> tuple[Decimal, ExitReason] | None:
    """The exit a bar triggers, if any. A gap past a level fills at the open;
    otherwise the stop is checked before the target, so it wins a tie."""
    opened, high, low = Decimal(str(bar.open)), Decimal(str(bar.high)), Decimal(str(bar.low))
    if opened <= trade.stop_loss:
        return round_cent(opened), "stop"
    if opened >= trade.take_profit:
        return round_cent(opened), "target"
    if low <= trade.stop_loss:
        return trade.stop_loss, "stop"
    if high >= trade.take_profit:
        return trade.take_profit, "target"
    return None


class SimBroker:
    """One shared account. Pass `trades` to rebuild it from the journal on
    resume (specs-plan sec11.4); marks return with the next session's bars."""

    def __init__(
        self,
        *,
        starting_cash: Decimal,
        slippage_pct: Decimal,
        assets: Mapping[str, Asset],
        trades: Sequence[Trade] = (),
    ) -> None:
        self._slippage_pct = slippage_pct
        self._assets = dict(assets)
        self._trades = {trade.client_order_id: trade for trade in trades}
        self._marks: dict[str, Decimal] = {}
        self._cash = starting_cash  # includes the cash pending orders reserve
        for trade in self._trades.values():
            if trade.entry_price is not None:
                self._cash -= trade.entry_price * trade.shares
            if trade.status == "closed" and trade.exit_price is not None:
                self._cash += trade.exit_price * trade.shares

    def _with_status(self, status: str) -> list[Trade]:
        return [trade for trade in self._trades.values() if trade.status == status]

    def _reserved(self) -> Decimal:
        return sum(
            (trade.shares * trade.reference_price for trade in self._with_status("pending")),
            Decimal(0),
        )

    def _positions_value(self) -> Decimal:
        return sum(
            (trade.shares * self._marks[trade.ticker] for trade in self._with_status("open")),
            Decimal(0),
        )

    def get_account(self) -> Account:
        """`cash` excludes pending reservations; `equity` includes them."""
        return Account(
            cash=self._cash - self._reserved(), equity=self._cash + self._positions_value()
        )

    def get_position(self, symbol: str) -> Position | None:
        shares = sum(t.shares for t in self._with_status("open") if t.ticker == symbol)
        if shares == 0:
            return None
        return Position(symbol=symbol, qty=shares, market_value=shares * self._marks[symbol])

    def get_asset(self, symbol: str) -> Asset | None:
        return self._assets.get(symbol)

    def submit_bracket_order(
        self, order: SizedOrder, *, client_order_id: str, submitted_on: date
    ) -> Trade:
        """Records a pending trade; its cost is reserved until it fills."""
        if client_order_id in self._trades:
            raise BrokerRejected(f"duplicate client_order_id {client_order_id!r}")
        trade = Trade(
            client_order_id=client_order_id,
            ticker=order.ticker,
            submitted_on=submitted_on,
            shares=order.shares,
            reference_price=order.reference_price,
            stop_loss=order.stop_loss,
            take_profit=order.take_profit,
            status="pending",
        )
        self._trades[client_order_id] = trade
        return trade

    def get_order(self, client_order_id: str) -> Trade:
        try:
            return self._trades[client_order_id]
        except KeyError:
            raise BrokerRejected(f"unknown client_order_id {client_order_id!r}") from None

    def tickers_needing_bars(self) -> list[str]:
        """The tickers with a pending or open trade, in a fixed order."""
        return sorted({t.ticker for t in self._trades.values() if t.status in ("pending", "open")})

    def on_session(
        self, day: date, bars: Mapping[str, Bar], splits: Mapping[str, float]
    ) -> list[Trade]:
        """Runs one session: entries at the open, then exits (the entry day
        included), then marks at the close. Returns the trades that changed."""
        for ticker in self.tickers_needing_bars():
            if ticker not in bars:
                raise DataUnavailable(f"no {ticker} bar on {day} for a pending or open trade")
            if splits.get(ticker, 1.0) != 1.0:
                raise DataUnavailable(
                    f"{ticker} split on {day}: splits during a trade are not simulated"
                )

        changed: dict[str, Trade] = {}
        for trade in self._with_status("pending"):
            changed[trade.client_order_id] = self._fill_entry(trade, bars[trade.ticker], day)
        for trade in self._with_status("open"):
            fill = _exit_fill(trade, bars[trade.ticker])
            if fill is not None:
                price, reason = fill
                self._cash += trade.shares * price
                changed[trade.client_order_id] = self._store(
                    trade,
                    status="closed",
                    exit_date=day,
                    exit_price=price,
                    exit_reason=reason,
                )
        for ticker, bar in bars.items():
            self._marks[ticker] = round_cent(Decimal(str(bar.close)))
        return list(changed.values())

    def _fill_entry(self, trade: Trade, bar: Bar, day: date) -> Trade:
        """Fills at the open plus slippage, downsized to the cash left after the
        other pending orders' reservations; 0 shares cancels the order."""
        price = round_cent(Decimal(str(bar.open)) * (1 + self._slippage_pct))
        reserved_by_others = self._reserved() - trade.shares * trade.reference_price
        shares = min(trade.shares, floor_shares((self._cash - reserved_by_others) / price))
        if shares == 0:
            return self._store(
                trade, status="cancelled", cancel_reason="not enough cash at the open"
            )
        self._cash -= shares * price
        return self._store(trade, status="open", shares=shares, entry_date=day, entry_price=price)

    def valuation(self) -> tuple[Decimal, Decimal]:
        """(cash including reservations, open positions at their last close)."""
        return self._cash, self._positions_value()

    def end_window(self, day: date) -> list[Trade]:
        """Cancels pending orders and marks open trades at the last close."""
        changed = [
            self._store(t, status="cancelled", cancel_reason="window ended before entry")
            for t in self._with_status("pending")
        ]
        changed += [
            self._store(
                t,
                status="open_at_end",
                exit_date=day,
                exit_price=self._marks[t.ticker],
                exit_reason="window_end",
            )
            for t in self._with_status("open")
        ]
        return changed

    def _store(self, trade: Trade, **update: object) -> Trade:
        updated = trade.model_copy(update=update)
        self._trades[trade.client_order_id] = updated
        return updated
