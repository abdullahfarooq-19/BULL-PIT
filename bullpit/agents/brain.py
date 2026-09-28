"""Brain: debate-or-skip routing, computed entirely by code, plus the data
warnings attached to the report (architecture Part 4; M3-FR-17; D8). No LLM
call on either route.
"""

from __future__ import annotations

from typing import Literal

from bullpit.state import RequestState, SignalsBoard

_INDICATOR_FIELDS = (
    "sma_20",
    "sma_50",
    "rsi_14",
    "atr_14",
    "volatility",
    "return_1w",
    "return_1m",
    "return_3m",
)
_FUNDAMENTALS_FIELDS = ("revenue_growth_yoy", "net_margin", "ttm_eps", "pe")


def choose_route(board: SignalsBoard, *, min_abs_score: float) -> Literal["debate", "no_trade"]:
    if abs(board.score) < min_abs_score and not board.conflict:
        return "no_trade"
    return "debate"


def data_warnings(state: RequestState, *, thin_articles: int) -> list[str]:
    warnings: list[str] = []

    for signal in (state.technical_signal, state.fundamentals_signal, state.sentiment_signal):
        if signal is not None and signal.flagged:
            warnings.append(f"{signal.analyst} analyst flagged: {signal.note}")

    if state.sentiment_signal is not None and not state.sentiment_signal.flagged:
        headline_count = len(state.sentiment_signal.evidence)
        if headline_count == 0:
            warnings.append("no news in the lookback window")
        elif headline_count < thin_articles:
            warnings.append(f"only {headline_count} news headlines found (thin)")

    if state.indicators is not None:
        missing = [name for name in _INDICATOR_FIELDS if getattr(state.indicators, name) is None]
        if missing:
            warnings.append(f"technical indicators not available: {', '.join(missing)}")

    if state.fundamentals is not None:
        missing_metrics = [
            name for name in _FUNDAMENTALS_FIELDS if getattr(state.fundamentals, name) is None
        ]
        if missing_metrics:
            warnings.append(f"fundamentals metrics not available: {', '.join(missing_metrics)}")

    if state.prices is not None and state.prices.source == "alpaca":
        warnings.append("prices came from the Alpaca backup, not yfinance")

    return warnings
