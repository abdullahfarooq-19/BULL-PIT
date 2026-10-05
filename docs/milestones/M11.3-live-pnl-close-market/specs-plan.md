# M11.3: Live P&L, close an open trade, market status: specs and plan

| | |
|---|---|
| **Status** | **Revision 3, 2026-10-06: the market status became a green or red badge in a new header band on Account & Wallet (logo, name, motto, with an Alpaca Connected or Offline badge beside it), and the order box scrolls on its own; neither changes behaviour.** **Revision 2: reduced scope, built.** The owner asked for the live P&L (FR-1 to FR-5) and the market status (FR-12, FR-13) only. **The Close button (FR-6 to FR-11, AC-4 to AC-8, D-M11.3-4 to D-M11.3-8, D-M11.3-11, D-M11.3-12, migration `0010`, Q1, Q2) is deferred and not built**; those parts stay here for when it is asked for. Both built parts only display numbers, so no deviation or architecture change is needed |
| **Size** | M. One `specs-plan.md` + `task.md` |
| **Branch** | `m11.3-live-pnl-close-market`, cut from `m11.2-dashboard-restructure` (M11.2 is built but not merged) |
| **Depends on** | M11.2 (Trades History, Account & Wallet). Reuses M8's fill check and M11.1's cancel pattern |
| **Sources** | [architecture Part 14 and §9](../../architecture.md), [M11.1 specs-plan](../M11.1-report-and-order-box/specs-plan.md) (FR-21, ADR-0008), [M11.2 specs-plan](../M11.2-dashboard-restructure/specs-plan.md), [dev-plan §3, §7](../../dev-plan.md) |

---

# Part A: Specs

## 1. Goal
Three things the owner asked for, in the dashboard:

1. **Live P&L.** Trades History shows the current profit or loss of every **open** trade, updated every 5 seconds.
2. **Close from the dashboard.** An open trade has a **Close** button, behind a confirmation with a disclaimer.
3. **Market status.** Account & Wallet shows whether the US market is open or closed and the time of the next change.

Items 1 and 3 only display numbers. **Item 2 places an order**, so it changes the architecture's rule that the system never touches a filled trade: the owner may now close one (D21).

## 2. Scope
**In:** `GET /history` gains the live price and unrealised P&L of open rows; a Close column on Trades History; `POST /trades/{request_id}/close`; `GET /market`; a market-status line on Account & Wallet; D21, architecture v2.9; tests of the close flow and the P&L maths; one real probe on the Alpaca paper account.
**Out:** closing part of a trade; closing trades Bull Pit did not place; selling a position you hold from elsewhere; short selling; intraday charts; streaming prices (polling only); any change to the graph, sizing, approval, buy orders, the fill check's rules or Backtests.

## 3. Functional requirements

**Live P&L**
- **FR-1** For a row in state *Open*, `GET /history` returns `current_price` (Alpaca's price for the symbol, from the account's positions, read once per call) and `unrealised_pnl = (current_price - entry_price) x shares`, `Decimal`, to the cent. Every other row has both `None`.
- **FR-2** The P&L column shows the realised P&L for closed rows as today, and for open rows the unrealised value, with the word "live" beside it and the current price underneath, so it can't be mistaken for a closed result.
- **FR-3** The table reads again every 5 seconds while the tab is visible and an open trade is on screen (the M11.2 polling hook; *Open* joins the list of moving states).
- **FR-4** If Alpaca's prices can't be read, the history still loads; open rows show "—" with the reason as a tooltip. A failed price read is never an error page.
- **FR-5** Portfolio's statistics stay realised only.

**Close an open trade**
- **FR-6** An open row has a **Close** button in the actions column (the column that holds Cancel for waiting orders). It opens a confirmation that states: the ticker and share count, that a **market sell** will be placed now at the price available then (which may differ from the price shown), that the stop-loss and take-profit orders for this trade will be cancelled, that it ends the trade at a possible gain or loss, and that it cannot be undone. The button inside the dialog says "Sell N shares now".
- **FR-7** `POST /trades/{request_id}/close` closes only **this trade's** shares, not the whole position of that symbol. It refuses (409, a stable `code`) when the trade is not `open`, when the market is closed (`market_closed`), or when a close is already in progress.
- **FR-8** The order of events: record the owner's request (journal, before any order, as with approvals); cancel the trade's two exit legs; place one market sell for the trade's shares with a deterministic `client_order_id` derived from the request ID (so a repeated click cannot sell twice); answer.
- **FR-9** The fill check records the sell as it records any close made outside Bull Pit: the exit price and date from the fill, the exit reason *manual*, P&L from the fill. The page runs a fill check right after a successful close, so the row turns *Closed* without a refresh.
- **FR-10** A close that fails halfway is safe to repeat: if the legs were cancelled and the sell was not placed, the trade is still `open`, the API says so in plain words ("the exit orders were cancelled but the sell was not placed: the position has no stop-loss until you retry"), and pressing Close again completes it.
- **FR-11** The paper-only guard is unchanged: every call goes through the same Alpaca client.

**Market status**
- **FR-12** `GET /market` returns `is_open`, `next_open` and `next_close` from Alpaca's clock. Account & Wallet shows, beside the account card's title or under the balance: **Market open, closes at HH:MM** or **Market closed, opens at HH:MM** (with the weekday when it is not today), in the browser's own time zone, with the exchange time (ET) as a tooltip.
- **FR-13** It re-reads every 30 seconds while the tab is visible. If it can't be read, the line says "Market status unavailable" and nothing else on the page changes.

## 4. Non-functional requirements
- **NFR-1** One Alpaca read per history call for prices (all open symbols in one call), none when no trade is open.
- **NFR-2** Money is `Decimal`; the unrealised P&L is computed in Python, not in the browser.
- **NFR-3** No new dependency, no new page, no new table. One new nullable column (`trades.close_requested_at`, migration `0010`) records the owner's request.
- **NFR-4** Existing tests pass without edits to their assertions.

## 5. Interfaces
```python
# bullpit/broker/alpaca.py (+)
class MarketClock(BaseModel, frozen=True):
    is_open: bool; next_open: datetime; next_close: datetime   # timezone-aware

class AlpacaBroker:
    def last_prices(self) -> dict[str, Decimal]: ...           # symbol -> current price of every open position
    def market_clock(self) -> MarketClock: ...
    def close_trade(self, trade: Trade, *, client_order_id: str) -> None: ...  # cancel the legs, sell trade.shares

# bullpit/api/schemas.py (+)
class HistoryRow: ... current_price: Decimal | None; unrealised_pnl: Decimal | None
class MarketOut(BaseModel, frozen=True): is_open: bool; next_open: datetime; next_close: datetime
```

| Endpoint | Answers | Errors |
|---|---|---|
| `GET /history` | now with `current_price`, `unrealised_pnl` | none (prices degrade to `None`) |
| `POST /trades/{request_id}/close` | the updated `TradeOut` | 404 `not_found`; 409 `not_closable`, `market_closed`; 502 `broker_unavailable` |
| `GET /market` | `MarketOut` | 502 `broker_unavailable` |

## 6. Acceptance criteria
- **AC-1** An open trade's row shows the current price and the unrealised P&L, labelled live; the value equals `(price - entry) x shares` to the cent on seeded data; non-open rows show none. (FR-1, FR-2)
- **AC-2** With a trade open, the row's P&L changes within 5 s of the price changing and stops being re-read while the tab is hidden. (FR-3)
- **AC-3** With Alpaca's prices unreachable, `/history` still returns every row and the open rows show "—". (FR-4)
- **AC-4** Close shows the confirmation text of FR-6; cancelling the dialog places nothing. (FR-6)
- **AC-5** Confirming places **one** market sell for exactly the trade's shares, after its two legs are cancelled and after the request is recorded; double-clicking or repeating the call places one order. (FR-7, FR-8)
- **AC-6** After a close the next fill check records the trade `closed`, reason *manual*, exit price from the fill, P&L correct; Portfolio's realised statistics include it. (FR-9)
- **AC-7** Close is refused for a non-open trade, when the market is closed, and while a close is in progress, each with its own message; a sell that fails after the legs were cancelled leaves the trade open and a retry completes it. (FR-7, FR-10)
- **AC-8** On the real paper account, one real 1-share trade is opened, closed from the dashboard, and read back on Alpaca: legs cancelled, one sell filled, journal row closed. (FR-8, FR-9)
- **AC-9** Account & Wallet shows market open or closed with the next change time in the browser's time zone, and the unavailable state. (FR-12, FR-13)
- **AC-10** Existing suite passes unchanged; ruff, mypy, ESLint, build clean; OpenAPI and types regenerated.

## 7. Decisions made in this document
| # | Decision | Why |
|---|---|---|
| D-M11.3-1 | **Current price comes from Alpaca's positions list**, one call for all open symbols | One call per refresh whatever the number of trades; the account's own mark |
| D-M11.3-2 | **Unrealised P&L is computed from the trade's own entry price and shares**, not Alpaca's per-position figure | A symbol's position may include shares from another trade or from outside Bull Pit |
| D-M11.3-3 | **Polling every 5 s**, not streaming | Meets "every 5 seconds or live, whichever is easier"; the M11.2 hook already does it |
| D-M11.3-4 | **Close sells only this trade's shares**, as a market order with a deterministic ID | Never touches other holdings; a repeat can't sell twice |
| D-M11.3-5 | **Close is refused while the market is closed** (owner may reverse this, Q1) | Cancelling the exit legs and then queueing a sell until the next open would leave the position with no stop-loss overnight |
| D-M11.3-6 | **The owner's close request is recorded before the order** in `trades.close_requested_at` (migration `0010`) | CLAUDE.md: no order without a recorded owner decision |
| D-M11.3-7 | **A failed close is retryable**: the trade stays open and the retry cancels what is left and sells | The only alternative, re-creating exit legs, can't be done on an existing bracket |
| D-M11.3-8 | **The exit reason is *manual*, as for a close made in Alpaca**; no new reason value | No change to the trade model or the evaluation's reading of it |
| D-M11.3-9 | **Market times show in the browser's time zone**, with ET as a tooltip | The owner lives in Pakistan time; the architecture quotes PKT |
| D-M11.3-10 | **The market line shows the *next* change** (open: when it closes; closed: when it opens) | One short line; the owner's wording "opens at / closes at" read as the two cases |
| D-M11.3-11 | **Close sits in the existing actions column**, beside Cancel | Both are per-row actions on a live order; one column keeps the table narrow |
| D-M11.3-12 | **D21** (the owner may close an open trade) and **architecture v2.9** (Part 14, §9) | CLAUDE.md: a behaviour change needs a deviation and an architecture entry |

## 8. Open questions for the owner
- **Q1 Close while the market is closed?** Default: refused (D-M11.3-5). The alternative queues a sell for the next open but leaves the trade with no stop-loss meanwhile.
- **Q2 Real probe.** AC-8 needs one 1-share paper trade bought and sold during a US session (18:30 to 01:00 PKT until 2026-11-01). May I place it? The probe also settles how Alpaca treats cancelling one bracket leg (T-2).

---

# Part B: Plan

## 9. Module design
| File | Change |
|---|---|
| `bullpit/broker/alpaca.py` | `MarketClock`, `last_prices`, `market_clock`, `close_trade` |
| `bullpit/journal/models.py`, migration `0010_close_requested.py` | `TradeRecord.close_requested_at` |
| `bullpit/api/schemas.py`, `api/app.py` | the fields and endpoints of §5; the close handler reuses `fill_check_lock`, `_trade_out`, `Refusal` (as `cancel_trade` does) |
| `web/src/app/trades/page.tsx` | live P&L cell, Close button and dialog (new `components/close-trade.tsx` beside `cancel-order.tsx`) |
| `web/src/components/account-card.tsx` (or the page) | market line, polling at 30 s |
| `web/openapi.json`, `web/src/api/` | regenerated |
| `tests/api/test_app.py`, `tests/broker/fake_broker.py` | tests of §11 |

Dependencies point inward as before: `api/` calls the Alpaca broker; the P&L maths is a small pure function.

## 10. Key algorithms
**Unrealised P&L** `(price - entry) x shares`, rounded to the cent with `round_cent`, `None` unless the row is open with an entry price and a price for its symbol.

**Close (`POST /trades/{request_id}/close`)**, under `fill_check_lock`:
1. Load the live trade row; 404 if none; 409 `not_closable` unless `open` or `close_requested_at` is set and the trade is still open (a retry).
2. Read the clock; 409 `market_closed` if closed.
3. Set `close_requested_at` (if empty) and commit.
4. `broker.close_trade(trade, client_order_id="bullpit-close-" + request_id)`: cancel the stop and take-profit legs (a leg already cancelled is not an error), then submit a market sell of `trade.shares`, `DAY`; a duplicate ID returns the existing order.
5. On `BrokerRejected` after the legs were cancelled, answer 502 with the FR-10 message; the row stays `open`.
6. Answer with the trade; the page runs the fill check, which records the fill as a *manual* close.

## 11. Test and verification plan
**Automated (dev-plan §7: this places an order, so it is tested):** unrealised P&L maths; `/history` with an open trade and prices (and with prices failing); close happy path (legs cancelled, one sell of the right quantity and ID, request recorded first); close twice places one sell; refusals (not open, market closed); sell failing after the legs were cancelled, then a retry; the fill check recording the close as *manual*. All with the fake broker.
**By hand:** the confirmation text and the cancel path; the 5 s refresh and hidden-tab stop; the market line in both states and unavailable; **the real probe** (Q2): buy 1 share with a bracket, close it from the dashboard, read back the orders on Alpaca.

## 12. Work order
1. Docs (this file, `task.md`, D21, architecture v2.9) and stop for approval.
2. The real probe, to settle the leg-cancel behaviour before code depends on it.
3. Migration `0010`, broker methods, API, tests, regenerated types.
4. Trades History: live P&L, Close and its dialog.
5. Account & Wallet: market line.
6. Regression, real run, retrospective.

## 13. Risks
| Risk | Mitigation |
|---|---|
| Alpaca cancels both bracket legs, or neither, when one leg is cancelled | The probe (T-2) records the real behaviour; the close logic is written to it |
| Sell fails after the legs are cancelled: no stop-loss | FR-10: loud message, retry completes it; the market-open rule shortens the exposure |
| Another trade or outside holding in the same symbol | The sell is for this trade's shares only (D-M11.3-4) |
| A fast-moving price makes the confirmation's number differ from the fill | The dialog says the fill price can differ; the fill check records the real one |
| Polling load | One positions call per 5 s while an open trade is on screen; none otherwise |
