"""Hand-computed indicator checks (M3-AC-2).

Both fixtures' expected values were worked out with an independent script
(not the module under test): a plain Wilder-smoothing loop and NumPy's
population-free (`ddof=1`) standard deviation, run once outside this file
and the results pasted in as literals below.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
import pandas as pd
import pytest

from bullpit.tools.indicators import compute_indicators


def _bars(closes: list[float], *, high_pad: float = 1.0, low_pad: float = 1.0) -> pd.DataFrame:
    closes_arr = np.array(closes, dtype=float)
    dates = pd.bdate_range("2024-01-02", periods=len(closes))
    frame = pd.DataFrame(
        {
            "open": closes_arr - 0.5,
            "high": closes_arr + high_pad,
            "low": closes_arr - low_pad,
            "close": closes_arr,
            "volume": np.full(len(closes), 1_000_000.0),
        },
        index=dates,
    )
    frame.index.name = "date"
    return frame


class TestLinearRamp:
    """21 bars, closes 100..120 (+1 each day): SMA, returns and RSI have
    closed forms (a strictly rising series has no losses, so RSI is 100).
    """

    def setup_method(self) -> None:
        self.bars = _bars([100.0 + i for i in range(21)])
        self.indicators = compute_indicators(self.bars)

    def test_close_and_sma20(self) -> None:
        assert self.indicators.close == 120.0
        assert self.indicators.sma_20 == pytest.approx(110.5)
        assert self.indicators.above_sma_20 is True

    def test_sma50_not_available(self) -> None:
        assert self.indicators.sma_50 is None
        assert self.indicators.above_sma_50 is None

    def test_rsi_is_100_for_a_pure_uptrend(self) -> None:
        assert self.indicators.rsi_14 == pytest.approx(100.0)

    def test_atr_constant_true_range(self) -> None:
        # high = close+1, low = close-1, close rises by 1/day: true range is
        # a constant 2 every day, so Wilder-smoothed ATR is exactly 2.
        assert self.indicators.atr_14 == pytest.approx(2.0)

    def test_volatility(self) -> None:
        assert self.indicators.volatility == pytest.approx(0.00788051569153714)

    def test_return_1w(self) -> None:
        assert self.indicators.return_1w == pytest.approx(0.04347826086956519)

    def test_return_1m_not_available(self) -> None:
        assert self.indicators.return_1m is None

    def test_return_3m_not_available_with_60_bars(self) -> None:
        bars_60 = _bars([100.0 + i for i in range(60)])
        indicators = compute_indicators(bars_60)
        assert indicators.return_3m is None


class TestGapsSeries:
    """20 bars with real ups and downs, hand-worked."""

    CLOSES: ClassVar[list[float]] = [
        100.0, 102.0, 101.0, 103.0, 105.0, 104.0, 106.0, 108.0, 107.0, 109.0,
        111.0, 110.0, 112.0, 114.0, 113.0, 115.0, 117.0, 116.0, 118.0, 120.0,
    ]  # fmt: skip

    def setup_method(self) -> None:
        self.bars = _bars(self.CLOSES, high_pad=1.5, low_pad=1.0)
        self.indicators = compute_indicators(self.bars)

    def test_sma20(self) -> None:
        assert self.indicators.sma_20 == pytest.approx(109.55)
        assert self.indicators.above_sma_20 is True

    def test_rsi14(self) -> None:
        assert self.indicators.rsi_14 == pytest.approx(81.78644716631482)

    def test_atr14(self) -> None:
        assert self.indicators.atr_14 == pytest.approx(3.19185338910658)

    def test_volatility_needs_21_bars(self) -> None:
        assert self.indicators.volatility is None

    def test_return_1w(self) -> None:
        assert self.indicators.return_1w == pytest.approx(0.06194690265486735)

    def test_return_1m_and_3m_not_available(self) -> None:
        assert self.indicators.return_1m is None
        assert self.indicators.return_3m is None
