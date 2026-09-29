# ADR-0002: Bracket order time-in-force and leg behaviour

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-09-29 |

## Context

Every buy Bull Pit places is a bracket order: a market entry plus a
stop-loss and take-profit leg that the broker manages on its own
(architecture Part 14, §9). For live mode (M8) to place these correctly,
M0 needed to confirm, against the real Alpaca paper API rather than its
docs alone: which `time_in_force` keeps a bracket's exit legs alive for as
long as a trade is open, whether those legs actually survive a market
close unchanged, how leg prices are validated, and whether Alpaca's
`client_order_id` uniqueness check gives the idempotency the architecture
relies on (Part 14: "a retry can't create a duplicate").

This was tested with the `scripts/spikes/alpaca_bracket.py` spike, in
four steps, against the owner's real Alpaca paper account:

- `validate` (2026-09-28, market closed): fractional-quantity and
  inverted-exit brackets, and a GTC bracket submitted and immediately
  cancelled while the market was closed.
- `place` (2026-09-28, market open): a real 1-share GTC market bracket on
  F (Ford), filled at $12.57, plus a duplicate-`client_order_id` retry.
- `inspect` (2026-09-29, market closed, after a full overnight close):
  read the same order back to see whether its legs had changed.

Full raw findings: [`findings.md`](../milestones/M0-foundations/findings.md)
(A7, A8, A9).

## Decision

- **Time-in-force: `GTC`** for every bracket order Bull Pit places (both
  the entry and its two legs, submitted as one bracket). A `DAY` bracket
  would need re-submitting every session, which defeats "the broker
  handles the exits on its own" (architecture Part 14); `GTC` needs no
  such babysitting.
- **Whole shares only.** A fractional quantity (0.5) on a bracket order is
  rejected outright (`"fractional orders must be simple orders"`). This
  matches the architecture's own "whole shares, since advanced order
  types may not support fractional shares" and needs no extra guard in
  `bullpit/risk/sizing.py` beyond the floor-to-int it already does.
- **Leg price validation is symmetric and immediate.** Alpaca rejects a
  bracket at submission time if `take_profit.limit_price <=
  stop_loss.stop_price`, regardless of which side of the current price
  either one is on. `bullpit/risk/exits.py`'s ATR-based stop and target
  (Part 11) already keep target above stop by construction, so no
  separate pre-check is needed before submission — but the broker's
  rejection message must still be surfaced clearly if it ever fires (a
  stale reference price, for instance).
- **Orders placed while the market is closed are accepted and queued**,
  not rejected: legs come back `HELD` (or `NEW` once armed) rather than
  an error. Bull Pit's order-placement code doesn't need to check market
  hours itself before submitting.
- **GTC legs survive a market close unchanged.** The take-profit and
  stop-loss legs read back identically before and after a full overnight
  close (same IDs, same prices, same statuses). The fill check (M8,
  `runners/fill_check.py`) can trust that an order it hasn't touched
  hasn't silently changed shape overnight.
- **`client_order_id` uniqueness is enforced by Alpaca itself.** Retrying
  a submission with the same `client_order_id` is rejected
  (`"client_order_id must be unique"`), never silently accepted as a
  duplicate order. Bull Pit's own deterministic `client_order_id` (derived
  from `request_id`, per CLAUDE.md) is therefore a real idempotency
  guarantee, not just a convention Bull Pit has to enforce by itself.

## Consequences

- `bullpit/broker/alpaca.py` (M8's write side) always submits brackets
  with `time_in_force=TimeInForce.GTC` and lets `client_order_id`
  collisions surface as `BrokerRejected` rather than treating them as a
  new order.
- The fill check (M8) doesn't need a "did the legs get dropped overnight"
  safety check of its own; Alpaca's own behaviour already guarantees they
  didn't, for a GTC bracket.
- The live spike position (1 share of F) is closed manually once the
  market is next open (M0-T-18), which also records the trade's actual
  exit and profit or loss as the last piece of this ADR's evidence.
