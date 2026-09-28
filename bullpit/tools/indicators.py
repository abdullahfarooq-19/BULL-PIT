"""Technical indicators, code-computed (architecture Part 5; M3-FR-8).

Pure over a bars DataFrame: no I/O, no settings (dev-plan.md sec2.2: pure
core; NFR-3). Periods are named constants, not settings (D-M3-10): they
define what "SMA 50" or "RSI 14" *means*, not a tunable limit. Each value
needs a minimum number of bars and is `None` below it, so a thin history
degrades a signal instead of crashing it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

_SMA_SHORT = 20
_SMA_LONG = 50
_RSI_PERIOD = 14
_ATR_PERIOD = 14
_VOLATILITY_WINDOW = 20
_TRADING_DAYS_PER_YEAR = 252
_RETURN_SESSIONS = {"1w": 5, "1m": 21, "3m": 63}


class Indicators(BaseModel, frozen=True):
    close: float
    sma_20: float | None
    sma_50: float | None
    above_sma_20: bool | None
    above_sma_50: bool | None
    rsi_14: float | None
    atr_14: float | None
    volatility: float | None
    return_1w: float | None
    return_1m: float | None
    return_3m: float | None


def _sma(closes: np.ndarray, period: int) -> float | None:
    if len(closes) < period:
        return None
    return float(closes[-period:].mean())


def _wilder_rsi(closes: np.ndarray, period: int) -> float | None:
    if len(closes) < period + 1:
        return None
    changes = np.diff(closes)
    gains = np.where(changes > 0, changes, 0.0)
    losses = np.where(changes < 0, -changes, 0.0)
    avg_gain = float(gains[:period].mean())
    avg_loss = float(losses[:period].mean())
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - 100 / (1 + rs))


def _wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> float | None:
    if len(close) < period + 1:
        return None
    prev_close = close[:-1]
    true_range = np.maximum(
        np.maximum(high[1:] - low[1:], np.abs(high[1:] - prev_close)),
        np.abs(low[1:] - prev_close),
    )
    atr = float(true_range[:period].mean())
    for i in range(period, len(true_range)):
        atr = (atr * (period - 1) + true_range[i]) / period
    return float(atr)


def _volatility(closes: np.ndarray, window: int) -> float | None:
    if len(closes) < window + 1:
        return None
    tail = closes[-(window + 1) :]
    returns = np.diff(tail) / tail[:-1]
    return float(returns.std(ddof=1) * np.sqrt(_TRADING_DAYS_PER_YEAR))


def _return(closes: np.ndarray, sessions: int) -> float | None:
    if len(closes) < sessions + 1:
        return None
    return float(closes[-1] / closes[-1 - sessions] - 1)


def compute_indicators(bars: pd.DataFrame) -> Indicators:
    """`bars` is the point-in-time frame from `data/prices.py`: indexed by
    date, columns open/high/low/close/volume, oldest first, through as_of.
    """
    closes = bars["close"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    close = float(closes[-1])

    sma_20 = _sma(closes, _SMA_SHORT)
    sma_50 = _sma(closes, _SMA_LONG)

    return Indicators(
        close=close,
        sma_20=sma_20,
        sma_50=sma_50,
        above_sma_20=None if sma_20 is None else close > sma_20,
        above_sma_50=None if sma_50 is None else close > sma_50,
        rsi_14=_wilder_rsi(closes, _RSI_PERIOD),
        atr_14=_wilder_atr(highs, lows, closes, _ATR_PERIOD),
        volatility=_volatility(closes, _VOLATILITY_WINDOW),
        return_1w=_return(closes, _RETURN_SESSIONS["1w"]),
        return_1m=_return(closes, _RETURN_SESSIONS["1m"]),
        return_3m=_return(closes, _RETURN_SESSIONS["3m"]),
    )
