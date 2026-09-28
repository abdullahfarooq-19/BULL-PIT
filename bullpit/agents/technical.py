"""Technical analyst: code computes the indicators and writes the evidence
facts; the LLM only judges direction and confidence (architecture Part 5;
M3-FR-8, FR-9; D-M3-1, D11).
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.llm.gateway import CompletionFn, Role, call_llm, litellm_completion
from bullpit.llm.schemas import AnalystVerdict, Evidence, Signal
from bullpit.state import Bar, RequestState
from bullpit.tools.indicators import Indicators, compute_indicators

_TEMPLATE = "technical.md"
_SAFE_DEFAULT = AnalystVerdict(direction="neutral", confidence=0.0)


def _bars_frame(bars: list[Bar]) -> pd.DataFrame:
    frame = pd.DataFrame(
        {
            "open": [bar.open for bar in bars],
            "high": [bar.high for bar in bars],
            "low": [bar.low for bar in bars],
            "close": [bar.close for bar in bars],
            "volume": [bar.volume for bar in bars],
        },
        index=[bar.date for bar in bars],
    )
    frame.index.name = "date"
    return frame


def _pct(value: float | None) -> str:
    return "not available" if value is None else f"{value * 100:+.1f}%"


def _sma_fact(close: float, sma: float | None, above: bool | None, period: int) -> str:
    if sma is None or above is None:
        return f"SMA {period} is not available"
    relation = "above" if above else "below"
    return f"Close {close:.2f} is {relation} SMA {period} ({sma:.2f})"


def _atr_fact(close: float, atr: float | None) -> str:
    if atr is None:
        return "ATR 14 is not available"
    return f"ATR 14 is {atr:.2f} ({atr / close * 100:.1f}% of the close)"


def evidence_from_indicators(indicators: Indicators) -> list[Evidence]:
    return [
        Evidence(
            id="T1",
            fact=_sma_fact(indicators.close, indicators.sma_20, indicators.above_sma_20, 20),
        ),
        Evidence(
            id="T2",
            fact=_sma_fact(indicators.close, indicators.sma_50, indicators.above_sma_50, 50),
        ),
        Evidence(
            id="T3",
            fact=(
                f"RSI 14 is {indicators.rsi_14:.1f}"
                if indicators.rsi_14 is not None
                else "RSI 14 is not available"
            ),
        ),
        Evidence(id="T4", fact=_atr_fact(indicators.close, indicators.atr_14)),
        Evidence(
            id="T5",
            fact=(
                f"20-day volatility is {indicators.volatility * 100:.1f}% a year"
                if indicators.volatility is not None
                else "20-day volatility is not available"
            ),
        ),
        Evidence(
            id="T6",
            fact=(
                f"Returns: 1 week {_pct(indicators.return_1w)}, "
                f"1 month {_pct(indicators.return_1m)}, "
                f"3 months {_pct(indicators.return_3m)}"
            ),
        ),
    ]


def technical_node(
    state: RequestState,
    *,
    settings: Settings,
    sessions: sessionmaker[Session],
    completion_fn: CompletionFn = litellm_completion,
) -> dict[str, object]:
    if state.prices is None:
        raise ValueError("technical_node runs after request_check populates prices")

    indicators = compute_indicators(_bars_frame(state.prices.bars))
    evidence = evidence_from_indicators(indicators)

    result = call_llm(
        Role.SMALL,
        _TEMPLATE,
        {
            "ticker": state.ticker,
            "company_name": state.company_name,
            "evidence": [item.model_dump() for item in evidence],
        },
        AnalystVerdict,
        safe_default=_SAFE_DEFAULT,
        request_id=state.request_id,
        settings=settings,
        sessions=sessions,
        completion_fn=completion_fn,
    )

    if result.flagged:
        signal = Signal(
            ticker=state.ticker,
            analyst="technical",
            direction="neutral",
            confidence=0.0,
            evidence=evidence,
            flagged=True,
            note="LLM reply invalid after retry",
        )
    else:
        signal = Signal(
            ticker=state.ticker,
            analyst="technical",
            direction=result.value.direction,
            confidence=result.value.confidence,
            evidence=evidence,
        )

    return {"indicators": indicators, "technical_signal": signal}
