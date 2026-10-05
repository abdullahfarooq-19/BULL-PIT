# M8 — Live mode: API, dashboard, approval, bracket orders, fill check: tasks

| | |
|---|---|
| **Status** | Written 2026-09-30, revised twice (see the git history). **Built 2026-09-30. Accepted by the owner 2026-10-06** ("I have tested everything, it is working perfectly fine"), with the carry-overs listed under "Acceptance" in the retrospective. Tagged `m8` |
| **Date** | 2026-09-30 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (revision 4; Q1 = yes, Q2 = TradingView, R1 to R5 decided; necessary testing, D-M8-21, D-M8-26) |
| **Branch** | `m8-live-mode`, from `master` (M7 merged and tagged `m7`, merge `d61985e`) |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. **Code and its tests land in the same task.** After every Python task, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` ("four checks") are clean; after every web task, `npm run lint` and `npm run build` in `web/` are clean too. The diff is re-read for anything the task doesn't need. Pre-commit runs mypy on the whole tree, so a new module is committed together with what it imports (M6 lesson).

**Real services.** Only M8-T-3, M8-T-12 and M8-T-17 touch Alpaca for real, and only the paper account (the guard makes anything else impossible). M8-T-12 and M8-T-17 need US market hours: 18:30–01:00 PKT until 2026-11-01, then 19:30–02:00. Live requests cost about 15K Groq tokens each when debated (architecture §14); nothing else in M8 calls an LLM.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | M8-T-1 | **Docs and branch.** Check `master` holds the `m7` merge; create `m8-live-mode`. Commit `specs-plan.md` and this file. `dev-plan.md`: status line and revision (M8 in progress); deviation **D14** in §3 (TradingView Lightweight Charts, D-M8-22); §2.1 frontend row (Next.js + Lightweight Charts, toolkit in specs-plan §9.6); §2.3 layout `api/` → `bullpit/api/` (D-M8-12); §8 M8 row made exact (request statuses and lock index, `approvals` and `trades` columns, live snapshot index and nullable columns, checkpoints in `checkpoints.db`, D-M8-8); §10.1 C6's "Recharts stays for the live equity chart" → Lightweight Charts. `architecture.md`: revision **v2.6** (D14 and the text alignment in specs-plan §7's intro): §13's dashboard row and database row (checkpoints in their own SQLite file), §15's `api/` → `bullpit/api/`, Part 15's exit reasons + manual. ADR-0002: `risk/exits.py` → `risk/sizing.py` (a wrong path, G4) | `docs/milestones/M8-live-mode/*`, `docs/dev-plan.md`, `docs/architecture.md`, `docs/adr/0002-bracket-order-tif-and-legs.md` | DoR §1.4; D14 | Branch exists; docs committed | 8744387 |
| [x] | M8-T-2 | **Dependencies and settings.** `uv add fastapi uvicorn langgraph-checkpoint-sqlite` (check it resolves against `langgraph-checkpoint` 4.2.0). Settings `approval_staleness_pct` (0.02), `api_port` (8000), `checkpoint_db_path` (`checkpoints.db`), `results_dir` (`docs/results`) in `config.py` and `.env.example`, defaults in `test_config.py`; `bullpit eval --out` defaults to `results_dir`. `.gitignore`: `checkpoints.db*`, `web/node_modules`, `web/.next` | `pyproject.toml`, `uv.lock`, `bullpit/config.py`, `.env.example`, `tests/test_config.py`, `bullpit/cli.py`, `.gitignore` | FR-27; D-M8-15 | Four checks clean | 16ff23c |
| [x] | M8-T-3 | **Real Alpaca shapes (no market hours needed).** A throwaway scratchpad script against the paper account: **only while the market is closed** (the script checks Alpaca's clock and stops if it's open, since a market entry would fill), submit one 1-share GTC bracket with legs about 5% either side of the last close (it queues, A9); re-submit the same `client_order_id` (record the duplicate error); read it back by client ID (**are legs included?**) and by ID with `nested=True`; cancel it and read the cancelled shape (**do the legs carry `canceled_at`?**); list closed orders for the symbol with `nested=True` (**do legs stay inside their parents?**, specs-plan §11.5); an unknown client ID (404 shape); daily portfolio history for the last month (timestamps and fields); the latest IEX trade for one ticker. Also take the M0 spike's filled F order JSON (`scripts/spikes/output/`, filled entry and live legs). Save the responses, with account IDs removed, as `tests/fixtures/alpaca/*.json`, and derive the filled-stop, filled-target, entry-cancelled, legs-cancelled (with a later non-leg sell fill, for the manual close) and partial shapes from them, naming each derived field in a short note in this file. Delete the script | `tests/fixtures/alpaca/*`, this file | FR-2, FR-3, FR-12, FR-14, FR-15; §7.1; memory rule "verify real provider failure paths" | Fixtures committed; findings pasted below; no open test order left on the account | 0eb5b6f |
| [x] | M8-T-4 | **Domain, sizing, journal.** `Trade` gains `order_id`, `stop_order_id`, `take_profit_order_id`; `ExitReason` gains `manual`. `risk/sizing.py`: `cap_shares` and `cash_shares` split out, `share_limits` calls them (§7.1); pure `net_of_pending` (FR-29, D-M8-25; tested in T-7). `journal/models.py` and migration `0007_live` (§10): lock index on `running` and `awaiting_approval`, `approvals.latest_price` and `.confirmations`, the three `trades` ID columns, the live `equity_snapshots` unique index, `cash` and `positions_value` nullable | `bullpit/domain.py`, `bullpit/risk/sizing.py`, `bullpit/journal/models.py`, `bullpit/journal/migrations/versions/0007_live.py` | FR-28; D-M8-20; AC-9 | `test_sizing.py` unchanged and passing; `test_migrations.py` passes with no schema diff after `0001`–`0007` | 36a6031 |
| [x] | M8-T-5 | **Alpaca write side.** In `broker/alpaca.py` (§5, §11.3, §11.4): `submit_bracket_order` (GTC bracket, whole shares, `float()` only when building the request, idempotent lookup through `find_order` on a duplicate ID, timeout, connection error or 5xx), `find_order` (404 → `None`; no `nested` re-read, T-3 showed legs are always included; no `get_order`, owner decision R6), `get_live_order`, pure `live_order` (with `exits_cancelled_at`), `first_sell_fill` (non-leg sells only, D-M8-10), `equity_history`. `FakeOrderBroker` in `tests/broker/fake_broker.py` (records submits, refuses a reused `client_order_id` like Alpaca). `tests/broker/test_alpaca.py` with a fake `TradingClient`: `test_bracket_request_shape`, `test_submit_is_idempotent`, `test_live_order_mapping` (parametrised over T-3's fixtures) | `bullpit/broker/alpaca.py`, `tests/broker/fake_broker.py`, `tests/broker/test_alpaca.py` | FR-1 to FR-4, FR-9 (lookup), FR-14 (shape); D-M8-10, D-M8-19, D-M8-20, D-M8-27; AC-5c, AC-7 (automated) | `test_alpaca.py` passes; `test_paper_guard.py` unchanged and passing; `AlpacaBroker` still built only through `make_trading_client` | c36fa21 |
| [x] | M8-T-6 | **Latest price.** `data/prices.latest_price(symbol, settings=...)`: Alpaca latest trade on the IEX feed through `make_data_clients`, `Decimal(str(price))`; any failure → `DataUnavailable`. No test of its own (a live service, dev-plan §7.3; the gate is tested with a fake price, T-7) | `bullpit/data/prices.py` | FR-12; D-M8-11 | Four checks clean; returns a price for one ticker by hand | 0a8a7e2 |
| [x] | M8-T-7 | **Approval gate.** In `approval/gate.py` (§5, §11.2): `ApprovalDecision` gains `owner`, `latest_price`, `confirmations`; `OwnerDecision`, `ApprovalProblem`, `expires_at`, `check_decision`. `backtest_policy` unchanged. `tests/approval/test_gate.py`: `test_shares_only_go_down`, `test_staleness`, `test_expiry` (2024-11-27 → 2024-11-29 18:00 UTC, one second either side), `test_loss_warning_needs_confirmation`, `test_rules_rechecked` (cash, cap, price at or below the stop and at or above the target even with `confirm_stale`; `max_shares` given), `test_net_of_pending` (T-4's function) | `bullpit/approval/gate.py`, `tests/approval/__init__.py`, `tests/approval/test_gate.py` | FR-6, FR-9, FR-29; D-M8-5, D-M8-7, D-M8-25, D-M8-28; AC-2, AC-3, AC-4, AC-10, AC-15 (gate level) | Tests pass; `gate.py` imports only `domain`, `risk/sizing`, `risk/rules`, `data/calendar`; M6's backtest tests unchanged and passing | f599231, f329abc |
| [x] | M8-T-8 | **Graph.** `RequestState.approval` and `.trade`. `graph.py`: `ApprovalWiring`; the `approval` node (`interrupt()`, no side effect before it) and the `execute` node (checks the committed `approvals` row, `shrink`, submit, upserts the `trades` row and marks the request `completed` in one transaction); after `report`, live buys go to `approval` only when built with `ApprovalWiring` (§9.3) | `bullpit/state.py`, `bullpit/graph.py` | FR-5, FR-7, FR-8; D-M8-2, D-M8-3, D-M8-4 | Four checks clean; `test_graph.py`, `test_backtest.py` and M7's tests unchanged and passing | 3412a7a |
| [x] | M8-T-9 | **Live runner.** In `runners/request.py`: `PendingAwareBroker` (FR-29: live reads net of pending trades; used for every live request, CLI included); `expire_overdue` (§11.1, D-M8-27: a recorded approval with no trade row is looked up by `client_order_id` before anything is expired); `open_request` (cutoff check, `expire_overdue` for the ticker, then the lock; duplicate message for a waiting report, FR-11), `run_live` (live loss warning from live snapshots; invoke with `thread_id`; paused → rows written with status `awaiting_approval`), `resume_live` (§11.1: resume only if an interrupt is pending; `BrokerRejected` → `failed`; a still-waiting request → `completed`); `run_request` rebuilt from `open_request` with unchanged behaviour. `make_checkpointer(settings)`: `SqliteSaver` on `checkpoint_db_path`, `check_same_thread=False`, `JsonPlusSerializer` with a strict msgpack allowlist of the Bull Pit types in `RequestState` (§7.1) | `bullpit/runners/request.py` | FR-5, FR-9 to FR-11, FR-17, FR-29; D-M8-6, D-M8-8, D-M8-17, D-M8-25, D-M8-27 | Four checks clean; every existing graph, CLI and backtest test passes unchanged | 3c69501 |
| [x] | M8-T-10 | **Fill check.** `runners/fill_check.py` (§11.5): live trades in `pending` or `open` → `get_live_order`; manual close from cancelled legs and `first_sell_fill` (FR-14, D-M8-10); warnings for no active exits and partial fills; live snapshots upserted from `equity_history`; returns `FillCheckResult`. `bullpit fill-check` prints changed trades, snapshot count and warnings (exit 1 if Alpaca is unreachable). `tests/runners/test_fill_check.py`: `test_fill_check_happy_path` (a pending trade that filled, an open trade stopped out, one closed by hand while other shares of the ticker are still held, one open without exits → warning only; snapshots upserted; a second run changes nothing) | `bullpit/runners/fill_check.py`, `bullpit/cli.py`, `tests/runners/test_fill_check.py` | FR-13 to FR-16; D-M8-9, D-M8-10; AC-7 (automated), AC-11 | Test passes; four checks clean | 8fbb038 |
| [x] | M8-T-11 | **API.** `bullpit/api/app.py` and `schemas.py` (§9.4): `create_app` (graph with `PendingAwareBroker` in `Deps` and the raw broker in `ApprovalWiring`), every FR-18 endpoint (ticker trimmed and upper-cased; `expire_overdue` on reads), background runs, the approval flow under one lock (§11.1, D-M8-30), problem responses, the results files limited to listed PNGs. `bullpit serve` (schema upgrade, checkpointer, `127.0.0.1` fixed, one worker) and `bullpit openapi --out PATH` (UTF-8, LF endings, D-M8-24). `tests/api/test_app.py` (reusing `test_graph.py`'s fixture patches and `RecordingLLM`, `FakeOrderBroker`, a fixed `now`, a fake `latest_price`, `tmp_path` journal and checkpoint files): `test_endpoints_happy_path` (its approval confirms a stale fake price; the `approvals` row records `latest_price` and `confirmations`), `test_restart_keeps_waiting_request`, `test_more_shares_refused_by_api`, `test_one_order_per_approval` (double send; recorded-then-died resend; resume with no `approvals` row → no submit; recorded-then-died past expiry with and without the order on the fake broker), `test_loss_warning_from_live_snapshots`, `test_expired_frees_lock`, `test_pending_order_counts` (D-M8-26 for why these and no more) | `bullpit/api/__init__.py`, `bullpit/api/app.py`, `bullpit/api/schemas.py`, `bullpit/cli.py`, `tests/api/__init__.py`, `tests/api/test_app.py` | FR-18 to FR-21, FR-26, FR-29; D-M8-12, D-M8-13, D-M8-15 to D-M8-18, D-M8-26, D-M8-27, D-M8-30; AC-1 to AC-5, AC-10, AC-11, AC-15 (automated) | All pass; whole suite under a minute; four checks clean | c7a6cda |
| [ ] | M8-T-12 | **First real session (market hours).** `bullpit doctor`. (a) **AC-13 probe (D-M8-29):** one 1-share bracket on a low-priced stock whose stop is above the current price, submitted through `AlpacaBroker` from a scratchpad script (the gate would refuse it, D-M8-28). Record what happens: a rejection's text and the `failed` message the API would show, or the entry and stop fills; cancel anything left open. Write **ADR-0007** (exits anchored to the reference price in both modes; the observed Alpaca rule; the gate's price-between-exits check; an overnight gap past an exit as the remaining case; this evidence). (b) **AC-6 starts:** `bullpit serve`; `POST /requests` for tickers until one report says buy; while it waits, stop and restart `bullpit serve` and confirm it's still `awaiting_approval` (AC-1 manual); approve through the API; check the order and both legs in Alpaca's dashboard; `POST /fill-check` after the entry fills. (c) Close M0's F spike position (M0-T-18) from Alpaca's dashboard and record it in M0's `task.md`; save that closing sell's closed-orders listing (`nested=True`) to `tests/fixtures/alpaca/` and confirm `first_sell_fill`'s assumptions against it (a real manual sell, G2). Paste commands, responses, order IDs and journal rows below | `docs/adr/0007-exit-anchoring.md`, this file, `docs/milestones/M0-foundations/task.md`, `tests/fixtures/alpaca/*` | AC-1 (manual), AC-6 (start), AC-7 (shape), AC-13; D-M8-4, D-M8-10, D-M8-29 | ADR written; a real bracket is live with its entry recorded; evidence pasted | |
| [x] | M8-T-13 | **Web foundation and design preview.** Scaffold `web/` (Next.js App Router, TypeScript, `src/`), install specs-plan §9.6's dependencies, set up Tailwind v4 with the §9.6 tokens in `globals.css`, Geist fonts, shadcn/ui initialised and restyled; the app shell from `sidebar-07` (sidebar with the five pages, header, `Ctrl+K` palette, toaster); `next.config.ts` rewrite; `package.json` scripts (`dev`/`start` on `127.0.0.1:3000`, `lint` = ESLint with `eslint.config.mjs`, `gen:api`); `src/api/client.ts` (`openapi-fetch`, D-M8-23); generated `openapi.json` and `schema.d.ts`; the fill check once on load. CI: a `web` job (Node 22, `npm ci`, `uv sync --locked`, `npm run gen:api`, `git diff --exit-code` on the two generated files, `npm run lint`, `npm run build`). Check the §9.6 colour pairs against WCAG AA and adjust any that fail. **Design preview:** a static HTML mockup of the Report and decide page (price ladder, gauges, debate, hold-to-approve) built from a real report's JSON, published as a private artifact for the owner, **not** committed. The owner's amendments go into §9.6 before T-14 | `web/*` (except pages), `.github/workflows/ci.yml`, `docs/milestones/M8-live-mode/specs-plan.md` (§9.6 amendments) | FR-23 to FR-25; D-M8-14, D-M8-16; §9.6; AC-8 | `npm run lint` and `npm run build` clean; CI `web` job green; owner has seen the preview and §9.6 is updated | 4d5f5de |
| [x] | M8-T-14 | **New request page and the report page, reading side.** New request: large ticker input (same as the palette), inline rejection and duplicate messages while the request check runs, then navigate. Report page: progress timeline and filling gauges while running; the ten report sections from `Report` (M5-FR-1 skipping, M5-FR-3 number formats in one helper); signature components (§9.6): bracket price ladder, signal gauges, the debate transcript with evidence popovers. Loading, error and empty states; labels, keyboard, focus, reduced motion (C11) | `web/src/app/page.tsx`, `web/src/app/requests/[id]/page.tsx`, `web/src/components/*` | FR-22, FR-23; §9.6; D-M8-31; AC-12 (part) | Lint and build clean | 7863a0e |
| [x] | M8-T-15 | **Report page, deciding side.** Section 10's decision panel (§9.6): share stepper (max = recommended; cost, % of equity, loss and gain update), hold-to-approve, Reject, expiry chip, confirmation sheets for `stale`, `loss_warning` and `rules` (with "Use N shares" and the fill-check hint), `expired` and `not_awaiting` shown with their reasons; the decision and order status afterwards. States and C11 as T-14. **Owner reviews both report-page tasks against the running API before T-16**, and amendments are made here | `web/src/app/requests/[id]/page.tsx`, `web/src/components/*` | FR-6, FR-22, FR-23, FR-29 (display); §9.6; D-M8-31; AC-12 (part) | Lint and build clean; owner has reviewed | 7863a0e |
| [x] | M8-T-16 | **History, Trades and Backtests pages.** History: dense requests table with status, outcome, decision and expiry chip. Trades: open and closed trades table, exit reasons, P&L, "Check fills" button, the TradingView Lightweight Charts equity chart (§9.6: client-only component, tokens applied, entry and exit markers, pan and zoom, text summary and table view). Backtests: runs table, expandable trades, M7's results page rendered with `react-markdown` + `remark-gfm`, the three PNGs. Each with loading, error and empty states (C11) | `web/src/app/requests/page.tsx`, `web/src/app/trades/page.tsx`, `web/src/app/backtests/page.tsx`, `web/src/components/*` | FR-22, FR-23; C6, C11; AC-12 (part) | Lint and build clean | e78c1f3 |
| [x] | M8-T-17 | **Hand checks (market hours for the second trade).** **AC-12:** owner clicks through every page against the running API: loading, error (API stopped), empty (fresh journal), keyboard only, one `stale` and one `loss_warning` confirmation (lowered settings in a scratch `.env` copy), hold-to-approve. **AC-7 (real):** a second small approved buy, closed by hand from Alpaca's dashboard; fill check → `manual`. **AC-14:** `netstat` shows the API only on `127.0.0.1`; logs and one response of each kind contain no key. **AC-6 continues:** fill check after the first trade's exit fills (both legs: one filled, one cancelled). Paste evidence below | this file | AC-6, AC-7, AC-12, AC-14 | Evidence pasted (AC-6 and AC-7 may finish in M9) | |
| [x] | M8-T-18 | **Acceptance.** README: live mode (`bullpit serve`, `npm run start` in `web/`, approving, the fill check, the safety rules), screenshots of the report page. Retrospective: what changed from the plan, test count and suite time, tokens of the real requests, carry-overs (AC-6/AC-7 if unfinished, the M5 warning-masking carry-over, M7's carry-overs). Then, when the owner asks: push, CI green, merge to `master`, tag `m8` | `README.md`, this file | DoD §1.5 | Owner accepts | |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-8, T-9, T-11, T-12 |
| AC-2 | T-7, T-11 |
| AC-3 | T-6, T-7, T-11 |
| AC-4 | T-7, T-11 |
| AC-5 | T-5, T-8, T-9, T-11 |
| AC-6 | T-12, T-17 |
| AC-7 | T-3, T-5, T-10, T-12, T-17 |
| AC-8 | T-11, T-13 |
| AC-9 | T-4 |
| AC-10 | T-7, T-9, T-11 |
| AC-11 | T-10, T-11 |
| AC-12 | T-13, T-14, T-15, T-16, T-17 |
| AC-13 | T-12 |
| AC-14 | T-11, T-17 |
| AC-15 | T-4, T-7, T-9, T-11 |

| Requirement | Task |
|---|---|
| FR-1 to FR-4 | T-3, T-5 |
| FR-5 | T-8, T-9 |
| FR-6 | T-7, T-11, T-15 |
| FR-7, FR-8 | T-8, T-11 |
| FR-9 to FR-11 | T-5, T-7, T-9, T-11 |
| FR-12 | T-6 |
| FR-13 to FR-16 | T-5, T-10, T-12 |
| FR-17 | T-9 |
| FR-18 to FR-21 | T-11 |
| FR-22, FR-23 | T-13, T-14, T-15, T-16 |
| FR-24, FR-25 | T-13 |
| FR-26 | T-10, T-11 |
| FR-27 | T-2 |
| FR-28 | T-4 |
| FR-29 | T-4, T-7, T-9, T-11 |

---

## Evidence

(Filled in by T-3, T-12 and T-17.)

### T-3: real Alpaca shapes (2026-09-29, market closed, paper account, symbol F)

Raw responses were recorded by a throwaway script (deleted) and saved, with nothing to redact (no account ID appears in any order), as `tests/fixtures/alpaca/*.json`. A 1-share GTC bracket at ±5% of the last IEX trade ($12.31) was submitted, re-submitted, read back, cancelled and read again; the account has no test order left (the one open order is the M0 spike's take-profit leg on F).

| Question | Real answer | Effect on the plan |
|---|---|---|
| Duplicate `client_order_id` | HTTP **422**, `{"code":42210000,"message":"client_order_id must be unique"}` (M0 A8 saw the same text with another code) | Match on the message text, as §11.3 says, not on the code |
| Unknown `client_order_id` | HTTP **404**, `{"code":40410000,"message":"order not found for <id>"}` | `find_order` returns `None` on 404 |
| Are legs included by `get_order_by_client_id`? | **Yes**, both legs, with their statuses | The `nested=True` re-read of §7.1 is not needed and is **not written** (no speculative code) |
| Order after submit, market closed | Entry `accepted`; legs `held` (`limit` and `stop` types) | Entry not `filled` → `pending` |
| After cancel | Parent and both legs `canceled`, each with its own `canceled_at` (within a millisecond), `filled_qty` 0 | `exits_cancelled_at` = the later leg `canceled_at` |
| Leg fields | `type` `limit` (take-profit, `limit_price`) or `stop` (`stop_price`); `filled_avg_price`, `filled_at`, `canceled_at`; leg `client_order_id`s are random UUIDs; `Order` has no `parent_order_id` | Legs are told apart by `type` |
| Legs in listings | `get_orders(status=closed, symbols=[F], nested=False)` returns each leg as a **top-level sell** (7 rows); with `nested=True` only the 3 parents, legs inside | `first_sell_fill` lists with `nested=True`, so bracket legs never look like a manual sell |
| Filled entry with live legs (the M0 spike order) | Entry `filled`, `filled_avg_price` 12.57; take-profit leg `new`, stop leg `held` | `exits_active` counts `new`, `accepted`, `held`, `pending_new` |
| Portfolio history (`period=1M`, `timeframe=1D`) | Parallel arrays `timestamp` (epoch seconds), `equity`, `profit_loss`, `profit_loss_pct`, plus `base_value`. Each stamp is **00:00 UTC of the day after the session** (a Friday session is stamped Saturday, a Monday one Tuesday); days before the account was funded have `equity` **0.0** | `equity_history` takes the **New York date** of each stamp (= the session date) and **skips zero-equity points**, since the loss warning divides by the base equity |
| Latest IEX trade | `{"F": {"price": 12.31, "timestamp": ..., "size": 500.0, ...}}` | `Decimal(str(price))` |

Derived fixtures (real shapes with only these fields changed; the M8-AC-6 and AC-7 real runs replace them where they can):

| File | Derived from | Fields changed |
|---|---|---|
| `order_stop_filled.json` | `order_open.json` | stop leg `status` `filled`, `filled_qty` 1, `filled_avg_price` 11.94, `filled_at`; take-profit leg `status` `canceled`, `canceled_at` |
| `order_target_filled.json` | `order_open.json` | take-profit leg `filled` at 13.19 with `filled_at`; stop leg `canceled` with `canceled_at` |
| `order_legs_cancelled.json` | `order_open.json` | both legs `canceled` with `canceled_at` (entry still filled) |
| `order_partial.json` | `order_open.json` | `qty` 2, `status` `partially_filled`, `filled_qty` 1, `filled_at` null; legs `qty` 2, `held` |
| `closed_orders_manual_sell.json` | `order_open.json` | adds a simple market `sell` order, `filled` at 12.40; the M0 spike parent stays |

Real, unchanged: `order_pending.json`, `order_open.json`, `order_entry_cancelled.json`, `error_duplicate_client_order_id.json`, `error_order_not_found.json`, `portfolio_history.json`, `latest_trade.json`, `closed_orders_nested.json`.

### T-11 to T-16: what was checked by hand (2026-09-30, market closed, fake broker)

- `bullpit serve` answered on `127.0.0.1:8000` only (`netstat`); `bullpit fill-check` ran against the real paper account and wrote the three live equity snapshots (2026-09-24, 09-25, 09-28); `bullpit doctor` passed (AC-14, T-12 part).
- Log and schema files scanned for the four key values in `.env`: none found (AC-14).
- The dashboard was driven in headless Chromium over the real API with fixtures, a scripted LLM and a fake broker (a scratch server, not committed): every page renders, no console errors; an early release of the hold cancels; the stepper stops at the recommended count; a 3% price move gives the stale sheet, *Confirm and approve* records `confirmations: [stale]` and one pending trade; the palette starts a request; a ticker the check rejects is shown under the input; the equity chart and its table view show the live snapshots.
- WCAG (section 9.6 pairs, contrast on `--bg` / `--surface` / `--surface-2`): text 15.9 / 14.9 / 13.9; muted 6.3 / 5.9 / 5.5; bull 10.2 / 9.6 / 9.0; bear 6.5 / 6.1 / 5.7; amber 10.7 / 10.1 / 9.4; neutral-signal 5.6 / 5.3 / 4.9; dark text on amber 10.7. All pass AA (4.5), so no colour was changed.

### T-12: not done yet

`bullpit doctor` passed (2026-09-29). The market was closed for the whole build session (next open 2026-09-30 09:30 ET), so the AC-13 probe, ADR-0007, the first real request and approval (AC-6 start), the restart check with a real waiting report, and closing M0's F position (M0-T-18) are still to do in one market session.

## Retrospective

(Written 2026-09-30, before acceptance.)

**Built.** Everything the specs-plan asks for that doesn't need the market, the owner or GitHub: the Alpaca write side, the approval gate, the graph's pause and order nodes, the live runner with restart-safe pause, expiry and pending-order accounting, the fill check, the API, `bullpit serve` / `fill-check` / `openapi`, and the five-page dashboard. 52 new tests (323 in all, about 40 s); ruff, mypy, pytest, `npm run lint` and `npm run build` are clean.

**What changed from the plan** (each is small; the first is the owner's decision R6):

- `AlpacaBroker.get_order` was dropped. A `Trade` needs the report's reference price, which Alpaca doesn't hold, and nothing calls it; `find_order` and `get_live_order` cover every read. The `nested=True` re-read for missing legs wasn't needed either: T-3 showed legs always come back.
- Alpaca's portfolio history stamps each session at 00:00 UTC of the next day and reports 0 before the account existed; `equity_history` takes the New York date of the stamp and drops zeros (found in T-3, would have divided by zero in the loss warning).
- `trade_from_row`, `trade_fields` and a new `trade_record` moved from `runners/backtest.py` to `journal/models.py`, so the graph's `execute` node and the backtest share one mapping without an import cycle. `Trade.pnl` became a pydantic computed field so the API sends it.
- `resume_live` takes the journal sessions, and also picks up a run that stopped inside `execute` (not only one waiting at the pause). `run_request` gained an optional `expiry_broker` so a CLI live request expires overdue waiting ones. `PendingAwareBroker` is used by the CLI's live path too (FR-29).
- The debate section shows the report's `DebateSummary` (strongest points, convictions, evidence chips), not a turn-by-turn transcript: the `Report` holds no turns and FR-18 has no endpoint for them. Serving the turns is a small API addition if you want section 9.6's transcript. The board score under the gauges is missing for the same reason.
- The design preview artifact of T-13 was skipped: the pages themselves were built directly and checked in a browser, so the review is of the real thing.
- The UI toolkit came from the shadcn CLI's `radix-nova` style; two CLI quirks were fixed by hand (an imported package called `cn`, and `next-themes`). `@number-flow/react` was dropped (D-M8-31) and `motion` animates the numbers.

**Tokens.** No real LLM request was made in this session (the tests and the browser check use a scripted LLM), so the live cost is still the M5 figure, about 15K per debated request.

**Still open, and who does it**

| Item | Needs |
|---|---|
| T-12: AC-13 probe and ADR-0007, first real request and approval, restart with a real waiting report, M0-T-18 (close the F position) and M0-T-25 | A market session (from 2026-09-30 18:30 PKT until 2026-11-01) |
| AC-6 (exit fills) and AC-7 real half (a second small trade closed by hand) | Calendar time after that session; may finish in M9 |
| AC-12: click through every page, including an API-stopped and an empty-journal run, and keyboard only | The owner |
| T-13 / T-15 review of the look, and README screenshots of a real report | The owner, after the first real request |
| CI web job green | A push |
| Merge to `master` and tag `m8` | The owner's acceptance |
| Carried over: the M5 warning-masking item and M7's carry-overs (unchanged) | M9 |

### Acceptance (2026-10-06)

The owner clicked through the dashboard against the running API and the real paper account and accepted M8 (T-13, T-15, T-17 and T-18 ticked on that basis; the owner's pass was reported in chat, no screenshots or notes were pasted). Since 2026-09-30 the dashboard has been rebuilt by M11.1, M11.2, M11.3 and M11.4, so the pages AC-12 describes are now Account & Wallet, Trades History, Portfolio and the report page, and the owner's pass covered those. M8's code reached `master` with the M11.1 merge (`m8-live-mode` is an ancestor of `master`); this acceptance adds the tag.

**Done since the retrospective above:** M0's F position was closed and M0 accepted and tagged `m0` (2026-09-30); real requests were approved by the owner and placed as real bracket orders on Alpaca paper (MSFT 2026-09-29/30, two GOOGL on 2026-10-02/05, CSCO 2026-10-05) and recorded `open` or `pending` by the fill check; a limit order was cancelled from the dashboard; `bullpit doctor` passes (2026-10-06); 429 tests pass; the API binds to `127.0.0.1` only (`bullpit serve`).

**Carried over, not done (accepted by the owner as exceptions to DoD §1.5):**

- **M8-AC-13's real probe** (a 1-share market bracket whose stop is above the price, in market hours). **ADR-0007 is written** from the evidence already gathered and says plainly that the probe is outstanding; its result is to be added as an addendum.
- **M8-AC-6, the exit half:** no stop-loss or take-profit has fired on a real Bull Pit trade yet (entries and the open state are recorded).
- **M8-AC-7, the real half:** a Bull Pit trade closed by hand in Alpaca and recorded as *manual*.
- **M8-AC-8, CI:** nothing has been pushed, so the CI web job has never run; the same steps pass locally (`npm run gen:api` output is committed and unchanged, `npm run lint`, `npm run build`).
- **M8-AC-1 (real restart with a real waiting report)** and the README screenshots of a real report were not recorded.
- The per-turn debate transcript the retrospective asked about was added by M11.1 (the report carries the turns).
