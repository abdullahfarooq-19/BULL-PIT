# ADR-0003: Point-in-time prices (split handling, no dividend adjustment)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-09-28 |
| **Milestone** | M1 ([specs D-M1-2, D-M1-3](../milestones/M1-data-layer/specs.md#7-decisions-made-in-this-document)) |

## Context

Architecture Part 2 requires data "exactly as it was known" at `as_of`. Price histories from our sources aren't:

- yfinance's default (`auto_adjust=True`) adjusts past prices for every split **and dividend** up to today. Even with `auto_adjust=False`, its `Close` is still split-adjusted (M0 findings C3). Checked on 2026-09-28: NVDA's 2024-06-07 close comes back as 120.888, but it traded at 1,208.88 that day, before its 10:1 split on 2024-06-10.
- Adjusted history changes after every new split or dividend. A cached copy and a fresh copy of the same window would differ, so backtests wouldn't be reproducible.
- Live brackets (M8) are priced in real quoted prices, so the backtest should see the same kind of prices.

Alpaca's free plan returns raw SIP daily bars (`adjustment=raw`), and its corporate-actions endpoint lists splits with `old_rate`/`new_rate` (both checked on 2026-09-28).

## Decision

1. **Store raw prices.** The cache holds unadjusted open, high, low, close and volume per session, plus a `split_ratio` column (the split ratio on an ex-date, otherwise 1.0).
   - Alpaca: raw bars, with splits from corporate actions for the same window (`new_rate / old_rate`; reverse splits give a ratio below 1).
   - yfinance: `history(auto_adjust=False, actions=True)`, then undo Yahoo's split adjustment by multiplying each bar's prices (and dividing its volume) by the product of every split ratio after that bar, taken from `Ticker.splits`. This is the one place that reads split events later than `as_of`. It uses them only to reverse Yahoo's own adjustment, and they never leave the function.
2. **Adjust per request, as of `as_of`.** For each returned bar, divide prices (and multiply volume) by the product of the split ratios with ex-date after that bar and on or before `as_of`. Splits after `as_of` are ignored.
3. **Never adjust for dividends.** Prices drop on ex-dividend days, as they did in the market.

## Consequences

- No split or dividend after `as_of` affects any price, indicator or ATR, and a cached history never changes after the fact.
- yfinance and the Alpaca backup give the same prices for the same `as_of` (M1-AC-5, M1-AC-9).
- Returns and the 1-week/1-month/3-month figures are price returns, not total returns. For dividend payers, a return window that crosses an ex-date is slightly lower than the total return. Accepted: it's what the market showed and what a trader would see.
- **For M6:** a simulated trade's later days must use the same raw bars. A split during an open trade changes the share count and exit prices the way a broker adjusts open orders; the M6 specs must say how the simulated broker handles it.
