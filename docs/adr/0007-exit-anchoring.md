# ADR-0007: Exit anchoring

| | |
|---|---|
| **Status** | Accepted; the AC-13 probe ran on 2026-10-12 (see "Addendum") |
| **Date** | 2026-10-06 |
| **Milestone** | M8 ([specs-plan](../milestones/M8-live-mode/specs-plan.md) S2, D-M8-28, D-M8-29, AC-13); changed by M11.1 (D16) |

## Context

Every buy is a bracket order: an entry plus a stop-loss and a take-profit leg. The dev plan (M8) asked for one rule on **what price the exits are measured from**, the same in backtest and live, checked against how Alpaca validates the legs:

- Alpaca validates the legs against a base price: the take-profit must be above it and the stop below it (M0 finding A7; ADR-0002).
- The report's exits are computed from ATR around the report's **reference price**, the last close at `as_of`. By the time the owner approves, the real entry price can differ (a gap at the open, or a move since the report).

## Decision

1. **The plan's exits are anchored to the reference price** (the last close at `as_of`), in both modes, so a backtest and a live request size and place the same plan (dev plan, M8). This is how `risk/sizing.py` builds every `SizedOrder`.
2. **At approval, in live mode, the exits follow the entry (M11.1, D16).** Code keeps the plan's stop and target distances and moves them to the price the owner sees (buy now) or sets (limit): `stop = entry - (reference - plan stop)`, `take-profit = entry + (plan take-profit - reference)`, to the cent (`risk/sizing.reprice`). For the same ATR and exit style this is the architecture's rule applied at the real entry, so a gap cannot leave a stop or target on the wrong side of the fill. A backtest still enters at the next open plus slippage with the plan's exits (ADR-0005).
3. **The gate refuses an order whose exits Alpaca would reject or exit at once** (D-M8-28): the latest price must be strictly between the stop and the take-profit for a market order; a limit order checks the stop side against its limit (M11.1 amended AC-7(c)). So the dashboard never sends a bracket Alpaca may reject or fill and stop out in the same moment.
4. **Remaining case, accepted:** an overnight gap past an exit between approval and the open. A market order placed after hours fills at the open; if the open is beyond a leg, that leg's behaviour is Alpaca's (a stop below the open fills at once at the market). The 2% staleness check and the one-trading-day expiry limit how stale the plan can be; they cannot remove the gap. The fill check records what happened.

## Evidence

Real Alpaca paper observations that support the rule:

- **Legs are validated against a base price, both sides.** Inverted exits are rejected (`take_profit.limit_price must be > stop_loss.stop_price`, M0 A7). For a limit-entry bracket Alpaca rejected the order with HTTP 422, code 42210000: `take_profit.limit_price must be >= base_price + 0.01` and `stop_loss.stop_price must be <= base_price - 0.01`, with the limit as the base price (ADR-0008, 2026-10-05).
- **Exits repriced from the seen price are accepted in market hours.** On 2026-10-05 (US session open) a real GOOGL buy-now order was approved at a seen price of $345.09 with exits repriced from the plan's distances to $327.08 and $372.10. Alpaca accepted it, the entry filled at $345.11, the take-profit leg went `new` and the stop leg `held` at exactly those prices, and the fill check recorded it `open` (M11.1 task, T-17(b)).
- **Legs survive the overnight close unchanged** (M0 A7; ADR-0002).

## Not yet observed (when this ADR was written; see the Addendum)

AC-13 asked for one more real probe: a 1-share **market** bracket on a low-priced stock whose stop is **above** the current price, submitted through `AlpacaBroker` during a US session, to see whether Alpaca rejects it or accepts it and fills both sides at once. It needs the market open and was not run when this ADR was written (the market was closed). The limit-order evidence above shows Alpaca rejects a stop above the base price at submission; the market-order case, where the base price is the live price, is expected to behave the same but is unconfirmed. **Either outcome keeps the decision**: the gate (point 3) already keeps that case away from the dashboard. When the probe is run, its result is added here as an addendum.

## Addendum: the AC-13 probe (2026-10-12)

Run during the US session (Alpaca's clock said open) from a throwaway script through `AlpacaBroker.submit_bracket_order`, on the paper account. One share of F, latest price $12.01, a **market** bracket with the stop **above** the price ($12.37) and the take-profit above the stop ($12.73).

- **Result: rejected at submission**, HTTP 422, code 42210000: `stop_loss.stop_price must be <= base_price - 0.01` (`base_price` 12.0101, the live price). `submit_bracket_order` raised `BrokerRejected("Alpaca rejected the order: …")`, which the API shows as the request's `failed` message.
- **Nothing was filled or left open:** the order was never created, and a check afterwards found no open F orders.
- **Meaning:** for a market entry Alpaca checks the legs against the live price exactly as it does against a limit for a limit entry (ADR-0008): the stop must be at least one cent below the base price. The "expected but unconfirmed" market-order case above is now confirmed. The decision stands, and the gate's price-between-exits check (D-M8-28) still keeps this case from the dashboard, so the rejection is a second line of defence rather than the first.

## Consequences

- One rule for the plan (reference price) and one for live approval (follow the entry), both tested (`tests/risk`, `tests/approval`, `tests/api`).
- The dashboard cannot place an order whose exits sit on the wrong side of the price it shows.
- A gap past an exit between approval and the open is possible and is reported by the fill check rather than prevented.
