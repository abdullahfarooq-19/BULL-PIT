# ADR-0005: Simulated broker fill rules

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-09-29 |
| **Milestone** | M6 ([specs-plan D-M6-3, D-M6-7 to D-M6-12](../milestones/M6-backtest/specs-plan.md#7-decisions-made-in-this-document)) |

## Context

Architecture Part 14 (simulated broker) gives four fill rules in prose: enter at the next open plus 0.05% slippage; check each later day's low and high, with the stop first when both are hit; a gap past an exit fills at the open; open trades at the end are valued at the last close. Daily bars can't tell what happened inside a day, so every unstated case (the entry day, gaps past the target, cash, splits) is a choice that biases every backtest. This ADR fixes them, line by line against Part 14. `broker/sim.py` implements exactly this, with one hand-built bar fixture per rule (M6-AC-1).

## Decision

Each session, for the tickers with a pending or open trade, in this order:

1. **Entries at the open.** A pending order fills at `open × (1 + sim_slippage_pct)`, to the cent, on the first session the runner hands the broker after the order was submitted. Holidays are skipped because the runner only hands it real sessions.
2. **Cash.** An order reserves `shares × reference_price` when submitted. At the fill it is **downsized** to the whole shares the remaining cash buys (cash minus the other pending orders' reservations); 0 shares cancels it. It is never enlarged, so cash never goes negative and every M4 limit stays true. Entries use the cash as it stood before that day's exits, because a market order fills at the open, before any exit that day.
3. **Exits, for every open trade, including one that entered today** (deviation D12):
   - open ≤ stop: exit at the open (gap past the stop; worse than the stop);
   - open ≥ take-profit: exit at the open (gap past the target). Part 14 only says gaps past "an exit level" fill at the open. A take-profit is a limit sell, which fills at the better price, the open, so the same reading applies;
   - otherwise low ≤ stop: exit at the stop; otherwise high ≥ take-profit: exit at the take-profit. **Both in one day: the stop wins.**
4. **Marks** at the close, and one equity snapshot per session.

Exits fill at their exact price with no slippage: Part 14 gives slippage for the entry only. Prices are rounded to the cent.

**The entry day is checked.** A daily bar's low and high are the regular session's, which starts at the open, so the whole range happens after the fill and while the bracket is live. Skipping it would miss stops hit on day one, an optimistic bias.

**Window end.** After the last decision day's requests, pending orders are cancelled (`window ended before entry`) and open trades are marked at the last close with status `open_at_end` and exit reason `window_end`, reported separately from closed trades.

**Data the broker can't use.** A missing bar, or a split ex-date, for a ticker with a pending or open trade stops the run with `DataUnavailable`. Guessing a fill (skipping the day, carrying the last close) or adjusting shares and exit prices for a split would be a silent bias or rarely exercised money code. ADR-0006 confirms the chosen stocks have no split in the window (ADR-0003's request that M6 say how splits are handled).

## Consequences

- A gap up past the take-profit on the **entry day** exits at the open, which is below the entry (entry pays the slippage, the exit doesn't), so a `target` exit can show a loss of about 0.05%. It is what the rules say, and negligible.
- The stop-first rule and the entry-day check both err toward worse results, never better. Real fills inside a day are unknowable from daily bars.
- Asset status for the run comes from today's Alpaca lookup, not the window's (D-M6-14).
