# M11.4: Remove the Backtests page: specs and plan

| | |
|---|---|
| **Status** | **Revision 1, 2026-10-06. Built.** Approved by the owner in chat ("we should not show the backtest page on the dashboard, instead save it as an md file in docs"). Checked: 429 tests, ruff, mypy, ESLint and the build clean; a browser pass showed three pages, `/backtests` redirecting to Trades History and `/backtests` and `/results` answering 404 on the API |
| **Size** | S. One `specs-plan.md` by the owner's instruction |
| **Branch** | `m11.4-remove-backtests-page`, cut from `m11.3-live-pnl-market` |
| **Depends on** | M11.2 (the page set it changed). Deviation **D21**, architecture **v2.9** |

## 1. Goal
The dashboard keeps only the live tool: Account & Wallet, Trades History and Portfolio. Backtest results are the Markdown file `docs/results/results.md` (with its three charts), which `bullpit eval` already writes and the README already links. The Backtests page only rendered that file plus a read-only table of runs, so nothing new is written.

## 2. Scope
**In:** delete the page; the sidebar and Ctrl+K entries; the four read-only endpoints `GET /backtests`, `GET /backtests/{run_id}/results`, `GET /results`, `GET /results/files/{name}` and their schemas and helpers; the two web dependencies only the page used (`react-markdown`, `remark-gfm`); the matching test assertions; a redirect from `/backtests`; the docs.
**Out:** the backtest runner, `bullpit eval`, `docs/results/`, `Settings.results_dir`, the journal tables, `GET /equity`, `GET /trades`, `GET /portfolio` (Portfolio uses them).

## 3. Requirements and acceptance
- **FR-1** The sidebar and the Ctrl+K palette list three pages: Account & Wallet, Trades History, Portfolio. (AC-1)
- **FR-2** `/backtests` redirects to `/trades`. (AC-2)
- **FR-3** The four endpoints are gone (404) and nothing in `web/` or `bullpit/api/` references them. (AC-3)
- **FR-4** `bullpit eval` still writes `docs/results/results.md`; the README still links it. (AC-4)
- **FR-5** The existing suite passes with only the removed endpoints' assertions deleted; ruff, mypy, ESLint and the build are clean; OpenAPI and generated types are regenerated. (AC-5)

## 4. Decisions
| # | Decision |
|---|---|
| D-M11.4-1 | Old `/backtests` links redirect to Trades History (a clean 404 was the other option) |
| D-M11.4-2 | The runs table and a run's trades are no longer shown anywhere in the UI; they stay in the journal, and `bullpit backtest` prints a summary |
| D-M11.4-3 | `Settings.results_dir` stays: it is where `bullpit eval` writes |

## 5. Plan and verification
Docs first (D21, v2.9, this file), then the API and tests, then the web app, then the checks: pytest, ruff, mypy, ESLint, build; a browser pass on a second API and dev server (three pages, redirect, no console errors, `/api/backtests` is 404); the real `docs/results/results.md` is still there.
