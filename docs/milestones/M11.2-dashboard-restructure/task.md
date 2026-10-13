# M11.2: Dashboard restructure: tasks

| | |
|---|---|
| **Status** | Written 2026-10-06 after the owner approved [`specs-plan.md`](specs-plan.md) revision 1 ("everything is approved, go ahead"). **Built 2026-10-06, accepted with M11.1 to M11.4 and merged to `master` (merge `e89ad90`), tagged `m11.2`** (see the retrospective) |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) |
| **Branch** | `m11.2-dashboard-restructure`, cut from `master` |

Each task is one commit **when the owner asks for commits** (CLAUDE.md), so ticks carry no hash yet. After every Python task the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit`, `uv run pytest`) are clean; after every web task `npm run lint` and `npm run build` in `web/` are clean too. The diff is re-read for anything the task doesn't need. Only T-3 (AC-11) and T-9 touch real services (Alpaca **paper**, SEC); nothing calls an LLM except the real request in T-9.

- [x] **T-1 Docs.** D19, D20 (dev-plan §3, §4, §5, §8, revision 9) and architecture v2.8; this file. (AC: docs agree with specs-plan §7)
- [x] **T-2 Journal.** Branch; `LikedStock` model; migration `0009_liked_stocks`. The existing "upgrade head matches the models" test passes with `0009` in its range. (AC-13)
- [x] **T-3 Watchlist data.** `bullpit/data/sp100.json` (symbol, name, snapshot date). One-off scratchpad script checks every symbol against Alpaca's asset lookup and the SEC filings lookup; the result is pasted here. (AC-11)
- [x] **T-4 API.** `AlpacaBroker.get_account_summary`; the schemas of specs-plan §5; `GET /history`, `GET /account`, `GET /portfolio`, `GET /watchlist`, `PUT` and `DELETE /watchlist/{symbol}`; pure `history_state` and `portfolio_stats`; tests of specs-plan §13; `web/openapi.json` and the generated types regenerated. (AC-2, AC-3, AC-6, AC-10, AC-12, AC-13)
- [x] **T-5 Shell.** Sidebar and Ctrl+K entries; `/requests` redirects to `/trades`; tones for the new states in `status.tsx`. (AC-1)
- [x] **T-6 Trades History and the analysis page.** Merged table, chips, polling; old History page deleted; back link on `/requests/[id]`. (AC-2 to AC-5)
- [x] **T-7 Portfolio.** Statistics, equity chart, description, disclaimer. (AC-6, AC-7)
- [x] **T-8 Account & Wallet.** Account card with polling hook, ticker box, liked stocks, watchlist. (AC-8 to AC-10)
- [x] **T-9 Regression and real run.** Dead-code sweep; full suite without assertion changes; scratchpad browser check; real run against the paper account (balance, 5 s refresh, a real request through every state, Cancel from the table); `docs/progress.md` and `docs/system-walkthrough.md` refreshed; retrospective below. (AC-1 to AC-13)

## Retrospective

(Written 2026-10-06, when the build ended, before the commit and merge.)

**Built.** Everything in the specs-plan: migration `0009` and `LikedStock`; `AlpacaBroker.get_account_summary`; `GET /history`, `/account`, `/portfolio`, `/watchlist` (+ `PUT` and `DELETE`); the S&P 100 file; Account & Wallet, Trades History (History deleted, `/requests` redirects), Portfolio, the back link, sidebar and palette; deviations D19, D20 and architecture v2.8. **Numbers:** 426 tests (407 before; 19 added, no existing assertion changed) in about 50 s; ruff, ruff format, mypy, ESLint and the web build clean; OpenAPI and generated types regenerated.

**Checked on the real paper account and the real journal** (a second API on port 8001 and a dev web server on 3001, so the owner's running servers were not touched; browser script in the session scratchpad, not in the repo): sidebar order and names; the balance read from Alpaca (it moved from $99,460.35 to $99,460.38 while the market was open), masked number, Demo badge; the account polled twice in 12.5 s while visible, **0 times while the tab was hidden**, and once when it became visible again; with `/account` failing, the card keeps the last figures marked stale and the rest of the page works; with the API stopped, every page shows "The API isn't reachable"; the watchlist filter, like, reload, select (fills the ticker box, focus moves to Start, no request started) and unlike; Trades History columns, chips and counts on the 19 real rows; the ticker link opens the stored analysis and the back link returns; `/requests` redirects to `/trades`; Portfolio shows the chart, 3 approved, 0 rejected, 2 ongoing, the description and the disclaimer; Backtests opens. **A real request** (KO, from the watchlist, about 15K Groq tokens) showed in Trades History as *Analysing* at 02:35:58 and became *No trade* at 02:37:13 on its own, with no manual refresh. A mocked `/history` with one row in every state checked the rendering: the expiry chip and plan numbers on *Decision pending*, "waiting at $98.00" on a limit order, the Override badge, Cancel only on the two waiting orders, signed P&L, the chip counts. No console errors.

**What changed from the plan** (specs-plan §16): a thirteenth state *No decision* (two completed GOOGL buy reports in the real journal have no approval row); approved and rejected counted over live requests; a shared `use-polling.ts` and the account hook inside `account-card.tsx`; `signedMoney` added, `money()` untouched; the watchlist has 98 names (BK is not tradable on Alpaca paper).

**Not done or only partly checked**

- **A real *Decision pending* row.** KO ended in no trade, so a real buy waiting for a decision was not produced (it costs another request); the state is covered by the table-driven test, the API happy-path test (plan numbers, expiry, then *Order placed*, *Open*, *Rejected by you*) and the mocked-row browser check.
- **The owner's own click-through** of the four pages, including keyboard-only use and the narrow window, has not happened.
- **The owner's servers (ports 8000 and 3000) still run the old code.** The production build in `web/.next` was rebuilt, so restart both (`bullpit serve`, `npm run start`) to see the new dashboard. The journal was upgraded to `0009` by the test API; the old API ignores the new table.
- The test KO report and its journal row, a real no-trade analysis, stay in the journal.

**Carry-overs.** The walkthrough's Q&A and §13 are otherwise as they were on 2026-09-30; only the dashboard table (section 8) and the progress table were refreshed.
