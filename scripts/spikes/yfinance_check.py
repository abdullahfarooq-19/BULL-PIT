"""M0 spike: verify yfinance assumptions A16 (specs-plan.md sec11.2).

Daily bars for AAPL, SPY and ^VIX from 2024-07-01, the installed version,
and the current default for `auto_adjust`.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import yfinance as yf
from _common import save_json, section

START = "2024-07-01"
END = "2024-07-15"


def check_ticker(symbol: str) -> dict[str, Any]:
    section(f"A16: {symbol} daily bars, {START} to {END}")
    ticker = yf.Ticker(symbol)
    bars = ticker.history(start=START, end=END, interval="1d")
    result = {
        "symbol": symbol,
        "row_count": len(bars),
        "columns": list(bars.columns),
        "first_date": str(bars.index[0]) if len(bars) else None,
        "last_date": str(bars.index[-1]) if len(bars) else None,
    }
    print(f"  rows: {result['row_count']}, columns: {result['columns']}")
    print(f"  range: {result['first_date']} .. {result['last_date']}")
    return result


def main() -> None:
    import importlib.metadata

    version = importlib.metadata.version("yfinance")
    print(f"yfinance version: {version}")

    results: dict[str, Any] = {"yfinance_version": version}
    for symbol in ("AAPL", "SPY", "^VIX"):
        results[symbol] = check_ticker(symbol)

    section("auto_adjust default")
    # yfinance>=0.2.x defaults auto_adjust=True in Ticker.history(); recorded
    # explicitly here since the architecture's adjustment ADR depends on it.
    aapl_adjusted = yf.Ticker("AAPL").history(start=START, end=END, interval="1d")
    aapl_unadjusted = yf.Ticker("AAPL").history(
        start=START, end=END, interval="1d", auto_adjust=False
    )
    same = aapl_adjusted["Close"].equals(aapl_unadjusted["Close"])
    print(f"  default Close == auto_adjust=False Close: {same} (False means default IS adjusted)")
    results["auto_adjust_default_is_adjusted"] = not same

    save_json("yfinance_check", results)
    print("\nDone. Check scripts/spikes/output/yfinance_check.json for the full record.")


if __name__ == "__main__":
    main()
