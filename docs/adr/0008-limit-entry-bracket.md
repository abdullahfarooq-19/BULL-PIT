# ADR-0008: Limit-entry bracket orders

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-10-05 |
| **Milestone** | M11.1 ([specs-plan](../milestones/M11.1-report-and-order-box/specs-plan.md) FR-14, FR-21, FR-22, AC-8; deviations D16, D17) |

## Context

M11.1 lets the owner buy at a price they set. ADR-0002 proved only the market-entry bracket. Before any code depends on a GTC **limit**-entry bracket, `scripts/spikes/alpaca_limit_entry.py` was run against the real Alpaca paper account (2026-10-05, market closed, F, 1 share, limit 20% below the last trade of $12.11).

## Decision

Bull Pit places a limit-entry bracket as a `LimitOrderRequest`: buy, `order_class` bracket, `time_in_force` GTC, whole shares, `limit_price` set, with the same two exit legs as the market bracket.

Observed on Alpaca paper:

- **Accepted and queued.** Entry `accepted`, type `limit`, `limit_price` 9.69, `filled_qty` 0. The take-profit leg is `limit` (10.27) and the stop leg `stop` (9.30), both `held`. `live_order` reads it as `pending` with exits active.
- **Leg validation is against the limit price.** Alpaca rejects at submission (HTTP 422, code 42210000): `take_profit.limit_price must be >= base_price + 0.01` and `stop_loss.stop_price must be <= base_price - 0.01`, where `base_price` is the limit. So `stop < limit < take_profit` is required, which the gate's `0 < stop < entry < take_profit` check already guarantees.
- **Cancel.** Cancelling the parent cancels both legs. Read back: parent and legs `canceled`, `filled_qty` 0. `live_order` maps this to `cancelled` with reason `entry canceled`, so a cancelled unfilled entry is never read as a manual close (M8 D-M8-10 reads only `open` trades).
- **No probe order left open** afterwards. No fill was needed: a limit order fills at its limit by Alpaca's design.

Real responses are saved as `tests/fixtures/alpaca/order_limit_pending.json` and `order_limit_cancelled.json`.

## Consequences

- `AlpacaBroker.submit_bracket_order` builds a market or a limit bracket from one `limit_price` argument; the idempotent `client_order_id` lookup is unchanged.
- A pending limit order has no expiry of its own (GTC); the owner cancels it from the dashboard (D17).
- Not tested: a limit above the market (it would fill at once, at the market price) and a partial fill of a limit entry; the fill check's existing partial-fill warning covers the latter.
