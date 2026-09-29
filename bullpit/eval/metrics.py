"""Evaluation metrics, pure over journal data (architecture §12; M7 specs-plan
FR-6 to FR-10, §11.1, §11.2; D-M7-6 to D-M7-8).

No I/O and no settings. Money stays `Decimal` until a metric turns it into a
ratio; a ratio with no denominator is `None`, so every run is scored the same
way. The annualisation factor defines what "Sharpe" means (like an indicator
period), so it isn't a setting.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from itertools import pairwise

from pydantic import BaseModel

from bullpit.broker.sim import SimBroker
from bullpit.domain import Bar, SizedOrder, Trade
from bullpit.risk.sizing import round_cent

_WEEKS_PER_YEAR = 52
_HYPOTHETICAL_ORDER_ID = "hypothetical"


class CalibrationBin(BaseModel, frozen=True):
    low: float
    high: float
    count: int
    mean_confidence: float
    win_share: float


class NoTradeValue(BaseModel, frozen=True):
    """What the skipped trades would have done (entered ones only)."""

    count: int
    wins: int
    losses: int
    open_at_end: int
    pnl: Decimal  # closed and marked-open trades together


class CallRow(BaseModel, frozen=True):
    """The token columns of one `llm_calls` row."""

    cache_key: str
    cache_hit: bool
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int


class TokenCost(BaseModel, frozen=True):
    total: int
    requests: int
    per_request: float


def total_return(start: Decimal, end: Decimal) -> float:
    """End equity over start equity, minus one."""
    return float(end / start - 1)


def weekly_returns(start: Decimal, decision_equity: Sequence[Decimal]) -> list[float]:
    """The return of each week: from `start` to the first decision day's
    equity, then between consecutive decision days."""
    values = [start, *decision_equity]
    return [float(after / before - 1) for before, after in pairwise(values)]


def sharpe(weekly: Sequence[float]) -> float | None:
    """Mean over sample standard deviation of weekly returns, times √52, with a
    risk-free rate of 0. `None` with fewer than 2 returns or no variation."""
    if len(weekly) < 2:
        return None
    deviation = statistics.stdev(weekly)
    if deviation == 0:
        return None
    return statistics.fmean(weekly) / deviation * math.sqrt(_WEEKS_PER_YEAR)


def max_drawdown(curve: Sequence[Decimal]) -> float:
    """The largest (peak - value) / peak along the equity curve."""
    worst = Decimal(0)
    peak = Decimal(0)
    for value in curve:
        peak = max(peak, value)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return float(worst)


def win_rate(pnls: Sequence[Decimal]) -> float | None:
    """The share of closed trades that made money; `None` with none."""
    if not pnls:
        return None
    return sum(1 for pnl in pnls if pnl > 0) / len(pnls)


def profit_factor(pnls: Sequence[Decimal]) -> float | None:
    """Total gains over total losses; `None` with no losing trade."""
    losses = -sum((pnl for pnl in pnls if pnl < 0), Decimal(0))
    if losses == 0:
        return None
    return float(sum((pnl for pnl in pnls if pnl > 0), Decimal(0)) / losses)


def brier(pairs: Sequence[tuple[float, bool]]) -> float | None:
    """Mean squared gap between confidence and outcome; `None` with no trades."""
    if not pairs:
        return None
    return statistics.fmean((confidence - won) ** 2 for confidence, won in pairs)


def calibration(pairs: Sequence[tuple[float, bool]], bins: int) -> list[CalibrationBin]:
    """(confidence, won) pairs grouped into equal-width confidence bins; empty
    bins are left out."""
    grouped: dict[int, list[tuple[float, bool]]] = {}
    for confidence, won in pairs:
        grouped.setdefault(min(int(confidence * bins), bins - 1), []).append((confidence, won))
    return [
        CalibrationBin(
            low=index / bins,
            high=(index + 1) / bins,
            count=len(members),
            mean_confidence=statistics.fmean(c for c, _ in members),
            win_share=sum(1 for _, won in members if won) / len(members),
        )
        for index, members in sorted(grouped.items())
    ]


def hypothetical_trade(
    order: SizedOrder,
    *,
    submitted_on: date,
    bars: Sequence[Bar],
    cash: Decimal,
    slippage_pct: Decimal,
) -> Trade:
    """`order` alone in an empty account, run through the simulated broker over
    `bars` (the sessions after `submitted_on`, oldest first) and closed at the
    last one if still open. Uses the M6 fill rules (ADR-0005)."""
    broker = SimBroker(starting_cash=cash, slippage_pct=slippage_pct, assets={})
    broker.submit_bracket_order(
        order, client_order_id=_HYPOTHETICAL_ORDER_ID, submitted_on=submitted_on
    )
    for bar in bars:
        broker.on_session(bar.date, {order.ticker: bar}, {})
    broker.end_window(bars[-1].date)
    return broker.get_order(_HYPOTHETICAL_ORDER_ID)


def no_trade_value(trades: Sequence[Trade]) -> NoTradeValue:
    """Summarises the hypothetical trades; one that never entered is left out."""
    entered = [trade for trade in trades if trade.entry_price is not None]
    pnls = [trade.pnl for trade in entered if trade.pnl is not None]
    return NoTradeValue(
        count=len(entered),
        wins=sum(1 for trade in entered if trade.status == "closed" and (trade.pnl or 0) > 0),
        losses=sum(1 for trade in entered if trade.status == "closed" and (trade.pnl or 0) < 0),
        open_at_end=sum(1 for trade in entered if trade.status == "open_at_end"),
        pnl=sum(pnls, Decimal(0)),
    )


def tokens_per_request(
    calls: Sequence[CallRow], original: Mapping[str, int], requests: int
) -> TokenCost:
    """Input, output and reasoning tokens over the run's requests. A cache hit
    counts at the tokens of the call that made the entry (`original`, by cache
    key), otherwise a replayed run would look free (D-M7-8)."""
    total = sum(
        original.get(call.cache_key, 0)
        if call.cache_hit
        else call.input_tokens + call.output_tokens + call.reasoning_tokens
        for call in calls
    )
    return TokenCost(
        total=total, requests=requests, per_request=total / requests if requests else 0.0
    )


def buy_and_hold(first_open: Decimal, last_close: Decimal, slippage_pct: Decimal) -> float:
    """Buying at the first session's open plus slippage and holding to the last
    decision day's close."""
    entry = round_cent(first_open * (1 + slippage_pct))
    return float(last_close / entry - 1)
