# M11.2: Dashboard restructure: specs and plan

| | |
|---|---|
| **Status** | **Revision 2, 2026-10-06 (the Backtests page it left unchanged was removed later by M11.4, D21).** Revision 1 was approved by the owner and built. Revision 2 records what the build changed (§16): a thirteenth state *No decision* found in the real journal, the approved and rejected counts, and where two pieces of code live. D19, D20 and architecture v2.8 are in `dev-plan.md` and `architecture.md` |
| **Date** | 2026-10-06 |
| **Size** | L. One `specs-plan.md` on the owner's instruction, as M11.1 did. `task.md` follows once this is approved |
| **Name** | "M11.2" is a label (M9 stays reserved for polish, README and the results write-up; there is no M10 or M11). It reorganises the dashboard that M8 and M11.1 built |
| **Branch** | `m11.2-dashboard-restructure`, cut from `master` |
| **Depends on** | M11.1 (tagged `m11.1`, merged to `master`). It does not depend on M8's open acceptance items |
| **Owner decisions (2026-10-06)** | Trades History lists **everything**; the watchlist is an **S&P 100 snapshot**; liked stocks live **in the journal**; the account header shows **"Alpaca Paper", a masked account number and a "Demo" badge** |
| **Sources** | [architecture Part 13, Part 14, Part 15](../../architecture.md), [dev-plan §3, §5 (M8, M9, C10), §7](../../dev-plan.md), [M8 specs-plan](../M8-live-mode/specs-plan.md) (FR-18 to FR-22), [M11.1 specs-plan](../M11.1-report-and-order-box/specs-plan.md), [system walkthrough](../../system-walkthrough.md) |

Part A says **what** M11.2 delivers. Part B says **how**. Neither restates the architecture; they link to it.

---

# Part A: Specs

## 1. Goal

The dashboard has four sidebar pages (New request, History, Trades, Backtests). History and Trades overlap, the home page offers no stock list, and no page shows the account as a whole. M11.2 makes it:

| Sidebar | URL | What it is |
|---|---|---|
| **Account & Wallet** | `/` | Broker, Demo badge, live balance; ticker box and Start; liked stocks; watchlist |
| **Trades History** | `/trades` | History and Trades merged: one row per analysis, from "analysing" to "closed" |
| **Portfolio** | `/portfolio` | The equity chart, account statistics, a short description of Bull Pit, a disclaimer |
| **Backtests** | `/backtests` | Unchanged |

Clicking a row in Trades History opens the stored analysis (`/requests/[id]`, which already exists), now with a link back.

**Done when:** the owner starts an analysis from a watchlist stock, sees it in Trades History as it runs and when it waits for a decision, approves it, sees it become an open trade, opens its analysis and returns with the back link, and sees the balance on the home page and the statistics and chart on Portfolio all agree with Alpaca and the journal.

## 2. Scope

### 2.1 In scope
- Rename and rebuild the home page as Account & Wallet (balance, ticker box, liked stocks, watchlist).
- Merge `/requests` (History) into `/trades` as Trades History; delete the old History page; redirect `/requests` to `/trades`.
- New `/portfolio` page; the equity chart moves there.
- Back link on the analysis page `/requests/[id]`.
- API: `GET /history`, `GET /account`, `GET /portfolio`, `GET /watchlist`, `PUT /watchlist/{symbol}`, `DELETE /watchlist/{symbol}`; one journal table `liked_stocks` (migration `0009`); an S&P 100 data file.
- Sidebar and Ctrl+K palette updated.

### 2.2 Out of scope
- No order, approval, sizing, graph, LLM or report change. The paper-only guard is untouched.
- No live prices for stocks (the owner chose names only). No watchlist editing beyond like and unlike. No custom tickers in the watchlist (the ticker box still accepts any ticker).
- No sell, no portfolio management, no per-position view of Alpaca holdings.
- No Backtests page change. No new theme, no mobile layout (C10 stands for those).
- No scheduler: the table and the balance refresh by polling while the tab is visible.

## 3. Functional requirements

**Account & Wallet**
- **FR-1** The page shows the broker (`Alpaca Paper`), the account number with all but the last four characters hidden, the account status, and a **Demo** badge. The badge is always Demo: the Alpaca client refuses any other endpoint, so "Live" cannot occur.
- **FR-2** It shows the balance (Alpaca's `equity`), cash, and the day change in dollars and percent (`equity - last_equity`). The balance comes from the broker, never from adding journal P&L: Alpaca's equity already counts every position, including ones Bull Pit did not place.
- **FR-3** The balance refreshes every 5 seconds while the tab is visible, stops while it is hidden, and refreshes once when the tab becomes visible. If Alpaca can't be read the card says so and keeps the last good number marked stale; the ticker box and lists still work.
- **FR-4** Below the balance: the ticker box and Start button, as today (validation, the request check's rejection message, redirect to the report).
- **FR-5** Under the ticker box, **Liked stocks**: the owner's saved stocks, always shown, in the order liked. Empty state: one line saying how to like a stock.
- **FR-6** Below that, the **Watchlist**: the S&P 100 names (symbol and company name, no prices), scrollable, with a filter box that matches symbol or name. Each row has a star button (like or unlike) and a select action.
- **FR-7** Selecting a stock from either list puts its symbol in the ticker box and moves focus to Start. It never starts an analysis by itself.
- **FR-8** Likes persist in the journal: they survive a reload, an API restart and another browser.

**Trades History**
- **FR-9** One row per live request (all of: running, awaiting approval, completed, rejected by the request check, failed, expired), newest first. Columns: Date, Ticker, Status, Shares, Entry, TP, SL, P&L, Exit, and an actions cell.
- **FR-10** Status is one label from this lifecycle, computed by code (§11.1): *Analysing, Decision pending, Rejected by you, Order placed, Waiting at limit, Open, Closed (target, stop or manual), Cancelled, Expired, No decision, No trade, Rejected by check, Failed* (*No decision*: a buy report that completed with no recorded decision, see §16). *Decision pending* carries the expiry chip. The order-type and Override badges from M11.1 stay.
- **FR-11** Shares, TP and SL come from the trade, else from the recorded approval, else from the report's suggested order, so a row that waits for a decision already shows the plan. Entry shows the fill price once there is one, "waiting at $X" for a pending limit order, otherwise the plan's reference price marked as a plan. A no-trade, rejected or failed row shows dashes.
- **FR-12** P&L shows for closed trades only (realised), coloured; Exit shows price and date with the reason.
- **FR-13** Filter chips: All, Decision pending, Ongoing, Closed, Rejected, No trade, Failed. Counts are shown on each chip. The default is All.
- **FR-14** The table reloads every 5 seconds while the tab is visible and any row is Analysing, Decision pending, Order placed or Waiting at limit, and after every fill check. A new request therefore appears without a manual refresh, and its row changes as it moves along.
- **FR-15** The ticker is a link to `/requests/[id]`. A waiting order keeps its Cancel button (the M11.1 component and rules). "Check fills" stays on this page.
- **FR-16** Empty and error states as on the other pages (loading skeleton, "The API isn't reachable").

**Analysis page**
- **FR-17** `/requests/[id]` shows a "← Trades History" link at the top in every state (running, failed, report ready). The page is otherwise unchanged. The old `/requests` list URL redirects to `/trades`.

**Portfolio**
- **FR-18** Statistics from the journal's live trades and approvals: **Approved** (orders you approved), **Rejected** (reports you rejected), **Ongoing** (trades `pending` or `open`), **Closed**, **Total profit** (sum of closed trades with a gain), **Total loss** (sum of closed trades with a loss), **Net P&L** (their sum). All realised; unrealised P&L lives in the balance on Account & Wallet. The page says so in one line.
- **FR-19** The equity chart (TradingView Lightweight Charts, with entry and exit markers and its "show as table" toggle) moves here, unchanged.
- **FR-20** After the statistics and chart: a short, factual description of Bull Pit (about 80 words: what it does, that you approve every trade, that it uses a paper account), then the disclaimer: AI can make mistakes; this is research, not financial advice; paper trading with simulated money. No performance claim appears in the description.

## 4. Non-functional requirements
- **NFR-1** Money is `Decimal` in the API and shown with the existing `money()` formatter. The portfolio sums and the lifecycle label are plain Python (CLAUDE.md: code for math).
- **NFR-2** `GET /account` polls at most every 5 s from one open page (about 12 calls a minute against Alpaca's 200). Nothing polls while the tab is hidden.
- **NFR-3** No new dependency, no new page beyond `/portfolio`, no change to existing endpoints' behaviour. Existing tests pass unchanged.
- **NFR-4** Keyboard and screen-reader behaviour as in M8: the star and the select actions are separate buttons with labels; status is words, not colour alone; every chip and card is reachable by keyboard.
- **NFR-5** The API stays bound to `127.0.0.1`, no auth (dev-plan Q6). The account number is masked server-side.

## 5. Interfaces

```python
# bullpit/api/schemas.py (+)
class AccountOut(BaseModel, frozen=True):
    broker: str                      # "Alpaca Paper"
    account_type: Literal["demo"]
    account_number: str              # masked: "••••1234"
    status: str                      # Alpaca's account status
    equity: Decimal
    cash: Decimal
    last_equity: Decimal
    day_change: Decimal
    day_change_pct: Decimal | None   # None when last_equity is 0

class HistoryRow(BaseModel, frozen=True):
    id: str; ticker: str; created_at: datetime; as_of: date
    state: HistoryState              # the lifecycle label (§11.1)
    outcome: str | None              # buy | no_trade
    status_reason: str | None
    expires_at: datetime | None
    order_type: str | None; overrides: list[str]
    shares: int | None; plan_price: Decimal | None; entry_price: Decimal | None
    limit_price: Decimal | None
    take_profit: Decimal | None; stop_loss: Decimal | None
    exit_price: Decimal | None; exit_date: date | None; exit_reason: str | None
    pnl: Decimal | None

class PortfolioStats(BaseModel, frozen=True):
    approved: int; rejected: int; ongoing: int; closed: int
    total_profit: Decimal; total_loss: Decimal; net_pnl: Decimal

class WatchlistStock(BaseModel, frozen=True):
    symbol: str; name: str; liked: bool        # GET returns the list in file order;
    liked_at: datetime | None                  # the page orders liked ones by liked_at
```

```python
# bullpit/broker/alpaca.py (+)
class AlpacaBroker:
    def get_account_summary(self) -> AccountSummary: ...  # equity, cash, last_equity, account_number, status
# `Account` and the Broker protocol are unchanged: the simulated broker and the sizing code use them.
```

| Endpoint | Answers | Errors |
|---|---|---|
| `GET /account` | `AccountOut` | 502 `broker_unavailable` |
| `GET /history?limit=` | `list[HistoryRow]` (default 200, max 500), newest first; runs the same `sweep()` expiry as `/requests` | none |
| `GET /portfolio` | `PortfolioStats` | none |
| `GET /watchlist` | `list[WatchlistStock]` | none |
| `PUT /watchlist/{symbol}` | the updated `WatchlistStock` (idempotent) | 404 `not_found` if the symbol is not in the list |
| `DELETE /watchlist/{symbol}` | the updated `WatchlistStock` (idempotent) | 404 as above |

## 6. Acceptance criteria

- **AC-1** The sidebar and Ctrl+K list Account & Wallet, Trades History, Portfolio and Backtests, in that order; `/requests` redirects to `/trades`; `/requests/[id]` still opens any past analysis. (FR-17)
- **AC-2** `GET /history` returns one row per live request, and the state of each of the thirteen cases in §11.1 is correct on seeded data. (FR-9, FR-10)
- **AC-3** A request that waits for a decision shows shares, TP and SL from the report, entry marked as plan, status Decision pending with its expiry chip. After approval the same row shows the order's numbers; after the fill, the fill price. (FR-11)
- **AC-4** A request started from the dashboard appears in Trades History within 5 s without a manual refresh and moves from Analysing to Decision pending (or No trade) on its own. (FR-14)
- **AC-5** Clicking a row opens its stored analysis; the back link returns to Trades History; the old links still work. (FR-15, FR-17)
- **AC-6** `GET /portfolio` equals hand-computed values on seeded data: approved, rejected, ongoing, closed counts and total profit, total loss, net P&L to the cent; backtest trades and requests are not counted. (FR-18)
- **AC-7** The Portfolio page shows the same equity chart as the old Trades page, the statistics, the description and the disclaimer. (FR-19, FR-20)
- **AC-8** On the real paper account the balance equals Alpaca's equity within one refresh, the Demo badge shows, only the last four account digits show, and the number refreshes every 5 s while the tab is visible and stops while it is hidden. (FR-1 to FR-3)
- **AC-9** With the API stopped, each page shows its error state; with Alpaca unreachable, the balance card shows its stale/error state and the rest of the page works. (FR-3, FR-16)
- **AC-10** A liked stock is still liked after a reload and after an API restart; unliking removes it; a symbol outside the list is refused. Selecting a stock from either list fills the ticker box and does not start a request. (FR-5 to FR-8)
- **AC-11** Every watchlist symbol passes the request check's asset and SEC-filings tests (a one-off check, recorded in `task.md`). (FR-6)
- **AC-12** The Backtests page, every existing endpoint's behaviour, the approval flow and the order box are unchanged: the existing suite passes without edits to its assertions. (NFR-3)
- **AC-13** `uv run pytest`, ruff, ruff format, mypy, `npm run lint` and `npm run build` are clean; the OpenAPI file and generated types are regenerated and committed.

## 7. Decisions made in this document

| # | Decision | Why |
|---|---|---|
| D-M11.2-1 | **One Status column, not Status plus Decision.** The decision is one stage of the same lifecycle, so the label says it all (FR-10) | Two columns would show pairs that contradict each other (a trade "Open" with decision "—"); the owner left this to me |
| D-M11.2-2 | **A Date column is added** to the owner's column list | Rows are otherwise indistinguishable when the same ticker is analysed twice |
| D-M11.2-3 | **Everything is listed**, with filter chips (owner's choice) | Nothing the owner ran disappears from the dashboard |
| D-M11.2-4 | **Balance is Alpaca's equity**, not a sum of journal P&L (FR-2) | It includes trades Bull Pit didn't place (the M0 F test, MSFT) and unrealised P&L, so it matches what Alpaca shows |
| D-M11.2-5 | **The analysis page is reused**, with a back link; no new detail page | `/requests/[id]` already shows the stored report, debate and decision for any request |
| D-M11.2-6 | **Portfolio statistics are realised only and computed by the API** (Python, `Decimal`) | Money maths stays in code and under test; unrealised P&L is the balance's job |
| D-M11.2-7 | **"Net profit" and "net loss" are shown as Total profit, Total loss and Net P&L** | "Net" twice is ambiguous; three labelled numbers can't be misread |
| D-M11.2-8 | **Liked stocks are stored in the journal** (`liked_stocks`), only for symbols in the list (owner's choice) | One source of truth, survives browser changes; limiting to the list keeps every liked name analysable |
| D-M11.2-9 | **The watchlist is a committed file `bullpit/data/sp100.json`** (symbol, name, snapshot date); the loader is a small function in `api/app.py` | Alpaca's full asset list is ~10,000 mostly unusable names (ETFs fail the SEC-filings check). S&P 100 membership changes over time; the file records its date and is a convenience list, not a recommendation |
| D-M11.2-10 | **The account header shows "Alpaca Paper" plus the masked account number**; Alpaca's API returns no personal name | Owner's choice. "Live" can't appear because of the paper-only guard |
| D-M11.2-11 | **`get_account_summary()` is a new method on `AlpacaBroker`**; `Account` is not widened | `Account` is used by sizing, the sim broker and the gate; adding fields there would touch all of them |
| D-M11.2-12 | **Polling, visibility-aware, 5 s**, for balance and table (the order box's pattern) | Simplest thing that meets "live or every 5 s"; no websocket, no scheduler |
| D-M11.2-13 | **Milestone label M11.2**; deviations **D19** (dashboard restructure: Trades History, Portfolio, back link; overrides C10's "no new pages") and **D20** (live balance and watchlist: `liked_stocks`, new endpoints); **architecture v2.8** | CLAUDE.md: a behaviour change needs a deviation and an architecture entry |
| D-M11.2-14 | **Testing follows dev-plan §7** (§13): tests only where money or state could be wrong; web checked by hand and by a scratchpad browser script | Project policy; the owner may ask for more |

## 8. Open questions for the owner
None block the start. Defaults apply unless you say otherwise: Q1 the likes are limited to list symbols; Q2 Trades History shows 200 rows (a "load more" is not built); Q3 the promo text is mine, for you to edit at T-6.

---

# Part B: Plan

## 9. Module design

### 9.1 Files created or changed

| File | Change |
|---|---|
| `bullpit/journal/models.py` | `LikedStock` (`symbol` PK, `created_at`) |
| `bullpit/journal/migrations/versions/0009_liked_stocks.py` | create the table |
| `bullpit/broker/alpaca.py` | `AccountSummary`, `get_account_summary()` |
| `bullpit/api/schemas.py` | the models of §5 |
| `bullpit/api/app.py` | the six endpoints; a pure `history_state(...)` and `portfolio_stats(...)`; watchlist loader |
| `bullpit/data/sp100.json` | symbol and name, snapshot date |
| `web/openapi.json`, `web/src/api/` (generated) | regenerated by `bullpit openapi` |
| `web/src/components/app-shell.tsx`, `palette.tsx` | nav list; palette entries |
| `web/next.config.ts` | redirect `/requests` to `/trades` |
| `web/src/app/page.tsx` | Account & Wallet |
| `web/src/lib/use-polling.ts` | one hook that calls a function every few seconds while the tab is visible; used by the account card and Trades History |
| `web/src/components/account-card.tsx` | the account card and the hook that reads `/account` |
| `web/src/app/trades/page.tsx` | Trades History |
| `web/src/app/requests/page.tsx` | **deleted** |
| `web/src/app/requests/[id]/page.tsx` | back link |
| `web/src/app/portfolio/page.tsx` | new page (reuses `components/equity-chart.tsx`) |
| `web/src/components/status.tsx` | tones for the new states |
| `tests/api/test_app.py`, `tests/journal/test_migrations.py` | tests of §13 |

No new component file unless a piece is used twice. Nothing in `graph.py`, `approval/`, `risk/`, `report/`, `runners/` or `broker/sim.py` changes.

### 9.2 Dependency direction
`api/` reads the journal and the Alpaca broker; the pure functions take plain values, no I/O. The web app talks only to the API through the generated client.

## 10. Data model
`liked_stocks(symbol TEXT PRIMARY KEY, created_at DATETIME NOT NULL)`, naive UTC like the other tables. No change to existing tables. Migration `0009` creates the table; the existing "upgrade head equals the models" test covers it.

## 11. Key algorithms

### 11.1 Lifecycle state (`history_state`, pure)
Inputs: the request's `status`, `outcome`, the approval's `decision` (or none), the trade's `status` and `order_type` (or none). First match wins:

| # | Condition | State |
|---|---|---|
| 1 | status `running` | Analysing |
| 2 | status `failed` | Failed |
| 3 | status `rejected` | Rejected by check |
| 4 | status `awaiting_approval` | Decision pending |
| 5 | trade `open` | Open |
| 6 | trade `closed` | Closed |
| 7 | trade `cancelled` | Cancelled |
| 8 | trade `pending`, limit order | Waiting at limit |
| 9 | trade `pending`, market order | Order placed |
| 10 | approval `rejected` | Rejected by you |
| 11 | status `expired` | Expired |
| 12 | outcome `buy` (a report that completed with no decision recorded) | No decision |
| 13 | otherwise (outcome `no_trade`) | No trade |

A completed request with an approval, no trade yet (the moment between the recorded approval and the order) has no row of its own in the table above; it maps to Order placed. Chips: Decision pending = state 4; Ongoing = 8, 9, 5; Closed = 6; Rejected = 3, 10; No trade = 13; Failed = 2; Cancelled, Expired and No decision show under All only.

### 11.2 Row numbers (`GET /history`)
One query joins `requests` (live), `approvals`, `trades`, `reports`. Shares, TP, SL: the trade, else the approval (`approved_shares`, `take_profit`, `stop_loss`), else `Report.order`. `plan_price` is `Report.order.reference_price`. Reports are parsed only for rows that wait for a decision or never had an approval. P&L, exit fields: the trade, as `trade_from_row` gives them.

### 11.3 Portfolio statistics (`portfolio_stats`, pure over rows)
Over live requests only (`mode == "live"`): approved and rejected from `approvals.decision` of requests with `mode == "live"` (backtest approvals belong to backtest requests); ongoing from trades `pending` or `open`; closed from trades `closed` with a P&L; total profit is the sum of positive P&L, total loss the sum of negative P&L (a negative number), net their sum.

### 11.4 Account
`get_account_summary()` reads Alpaca's account object: equity, cash, `last_equity`, `account_number`, `status`. The API masks all but the last four characters of the number, sets `broker = "Alpaca Paper"` and `account_type = "demo"`, and derives the day change. Errors become `BrokerRejected`, then a 502 `Problem`.

### 11.5 The home page
State: `ticker` (the input), `liked`, `filter`. Selecting a stock calls `setTicker(symbol)` and focuses Start. The star calls PUT or DELETE and updates the list from the answer. The balance hook polls every 5 s while `document.visibilityState === "visible"`.

## 12. Error handling
| Case | Behaviour |
|---|---|
| Alpaca unreachable on `/account` | 502; the balance card shows "Balance unavailable" with the last good number marked stale; the rest of the page works |
| API down | each page's existing error panel with retry |
| Like a symbol not in the list | 404 `not_found`; the star does nothing and a toast says so |
| Like or unlike twice | idempotent, no error |
| `last_equity` is 0 | `day_change_pct` is `None`; the card shows the dollar change only |
| A pre-M11.1 request with no report order | shares, TP, SL show dashes |

## 13. Test and verification plan

**Automated (dev-plan §7, necessary only)**
- `history_state`: all twelve rows of §11.1 (a table-driven test; it decides what the owner reads as a trade's status).
- `portfolio_stats`: wins, losses, rejected, ongoing, live-only filtering; to the cent (money).
- One happy path each for `GET /history` (a seeded request in each state through the fake broker), `GET /account` (fake broker), and the watchlist (like, list, unlike, unknown symbol, persists across a new app on the same journal).
- Migration `0009`: the existing "upgrade head matches the models" test.

**By hand, and a scratchpad browser script (not in the repo)**
- Real run, as in the plan's verification section: balance against Alpaca, 5 s refresh and the hidden-tab stop, a real request through Analysing, Decision pending, Open, the back link, a Cancel from the table.
- Empty journal, every filter chip, API stopped, keyboard-only pass, no console errors, old URLs, narrow window.
- AC-11: a one-off script in the scratchpad checks every watchlist symbol against Alpaca's asset lookup and the SEC filings lookup; the result is pasted into `task.md`.

**Regression:** the full existing suite passes with no assertion changed (AC-12); the Backtests page is compared before and after.

## 14. Work order
1. Docs (this file, then `task.md`, D19, D20, architecture v2.8): stop for approval after each.
2. Branch, journal table, migration.
3. API endpoints, regenerated OpenAPI and types, tests.
4. Shell, palette, redirect.
5. Trades History; delete History; back link.
6. Portfolio.
7. Account & Wallet.
8. Dead-code sweep; refresh `docs/progress.md` and `docs/system-walkthrough.md` (both out of date).
9. Regression, real run, retrospective. Commit and merge only when the owner asks.

## 15. Risks
| Risk | Mitigation |
|---|---|
| The S&P 100 file goes stale or holds a symbol the request check refuses | AC-11 checks every symbol once; the file carries its date; the ticker box still takes any ticker |
| `/history` is slow with many requests | one joined query, reports parsed only where needed, a limit of 200 |
| Alpaca's equity doesn't move outside market hours, and looks "stuck" | the card shows the update time; the day change is Alpaca's own |
| The merged page drops something History or Trades showed | §11.1 and the column list were checked against both old pages; the "reason" text appears in the Status cell's tooltip, the Expiry chip moves to Status |
| Deleting `/requests` breaks old bookmarks | redirect in `next.config.ts` |
| Packaging misses the JSON file | the app runs from source; the loader is exercised by the test and the real run |

## 16. Changes found while building (revision 2)

- **A thirteenth state, *No decision*.** The real journal holds two completed `buy` reports with no approval row (GOOGL requests from M11.1's development, made before the approval step could place orders). Specs §11.1 would have labelled them *No trade*, which is wrong. They now read *No decision*, show their plan muted, and appear under the All chip only (D-M11.2-15).
- **Approved and rejected are counted over live requests** (their `mode`), not by `decided_by == "owner"`: the two give the same numbers, and the live filter is the one the other endpoints use.
- **`signedMoney`** (`web/src/lib/format.ts`) writes a P&L as `+$198.00` or `-$102.00`, zero without a sign. `money()` is unchanged, so the Backtests page is identical.
- **The watchlist has 98 names**, not 100: AC-11's check found BK (The Bank of New York Mellon) not tradable on the Alpaca paper account, so it was dropped. Every other name passed the asset and SEC-filings tests (T-3).
- **Two web files instead of one hook file** (§9.1 amended): `use-polling.ts` is shared by two pages; the account hook sits with its card.

| # | Decision |
|---|---|
| D-M11.2-15 | A completed buy report with no recorded decision is shown as *No decision*, not *No trade* |
