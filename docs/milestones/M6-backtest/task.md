# M6 — Simulated broker, journal, backtest runner: tasks

| | |
|---|---|
| **Status** | Done and accepted by the owner on 2026-09-29; merged to `master` and tagged `m6` |
| **Date** | 2026-09-29 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (approved 2026-09-29; necessary testing, D-M6-20) |
| **Branch** | `m6-backtest`, from `master` (M5 merged and tagged `m5`) |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. **Code and its tests land in the same task.** After every task, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` ("four checks") are clean, and the diff has been re-read for anything the task doesn't need. Tasks 1 to 12 use no LLM quota; only task 13 calls Groq.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | M6-T-1 | **Docs and branch.** Check that `master` holds the `m5` merge; create `m6-backtest`. Commit `specs-plan.md` and this file. In `dev-plan.md`: status line (M6 in progress), deviation **D12** in §3 (entry-day exits, Q1), and a §10 entry for **D-M6-22** (M6's real run is 2 weeks × 1 stock, the 26-week run moves to M7), with M6's draft AC-6 updated to match. In `architecture.md`: revision **v2.4**, Part 14's "each later day" → "the entry day and each later day", §16's M6 done-when → a resumable backtest proven on the pinned models (26-week run in M7) | `docs/milestones/M6-backtest/*`, `docs/dev-plan.md`, `docs/architecture.md` | DoR §1.4; D-M6-3, D-M6-22 | Branch exists; docs committed | 7d7384a |
| [x] | M6-T-2 | **Settings and domain types.** Add `sim_slippage_pct` (0.0005), `backtest_starting_cash` (100000), `backtest_weeks` (26) to `config.py` and `.env.example`, with their defaults in `test_config.py`. Move `Bar` from `state.py` to `domain.py` (state imports it). Add `Trade`, `TradeStatus`, `ExitReason` to `domain.py`. Make `risk/sizing.py`'s `_round_cent` and `_floor_shares` public (callers updated, no behaviour change) | `bullpit/config.py`, `.env.example`, `tests/test_config.py`, `bullpit/domain.py`, `bullpit/state.py`, `bullpit/risk/sizing.py` | FR-16; D-M6-21 | Four checks clean; `test_sizing.py` unchanged and passing | 62a64b1 |
| [x] | M6-T-3 | **Calendar helpers.** Add `sessions_between(after, through)` and `decision_days(start, weeks)` (§11.3) to `data/calendar.py`. Tests: 2024-07-01 × 26 weeks → 2024-07-05 … 2024-12-27; the Good Friday week → 2025-04-17; `sessions_between(2024-07-03, 2024-07-05)` → `[2024-07-05]` | `bullpit/data/calendar.py`, `tests/data/test_calendar.py` | FR-8; AC-2 | `test_calendar.py` passes | 287c7f2 |
| [x] | M6-T-4 | **Simulated broker.** Add `OrderBroker` and `client_order_id` to `broker/base.py`. Write `broker/sim.py` (§5, §11.2): account and positions (FR-1), submission with reservation and duplicate-ID refusal (FR-2), `on_session` (entries at the open with slippage and fill-time downsizing, then exits with the gap and stop-first rules, entry day included), `valuation`, `end_window`, split and missing-bar stops (FR-5); rebuild from `trades` (§11.4). Plus `tests/broker/test_sim.py`: one hand-built bar fixture per exit rule (stop, target, both same day, gap down, gap up, entry-day stop), entry at open × 1.0005 to the cent, fill downsized when cash is short, window end (open → `open_at_end`, pending → cancelled), split and missing bar stop. Write **ADR-0005** (fill rules, including the gap-past-target reading and D-M6-3, D-M6-8, D-M6-9) | `bullpit/broker/base.py`, `bullpit/broker/sim.py`, `tests/broker/test_sim.py`, `docs/adr/0005-sim-fill-rules.md` | FR-1 to FR-5; D-M6-2, D-M6-3, D-M6-7 to D-M6-12; AC-1, AC-2, AC-3 (fill), AC-10 | `test_sim.py` passes; `sim.py` imports only `domain`, `broker/base`, `errors`, `risk/sizing` and the stdlib | 76a0ac0 |
| [x] | M6-T-5 | **Approval gate.** Write `approval/gate.py`: `ApprovalDecision` and `backtest_policy` (approve as sized). No test of its own (one line of logic; the runner's happy path covers it) | `bullpit/approval/gate.py` | FR-6; D-M6-4 | Four checks clean; imports only `domain` | 1c749db |
| [x] | M6-T-6 | **Journal.** Add `BacktestRun`, `ApprovalRecord`, `TradeRecord`, `EquitySnapshot` and `Request.run_id` to `journal/models.py` (§10), and migration `0005_backtest` | `bullpit/journal/models.py`, `bullpit/journal/migrations/versions/0005_backtest.py` | FR-15; AC-9 | `test_migrations.py` passes with no schema diff after `0001`–`0005` | bc1e4c9 |
| [x] | M6-T-7 | **Shared row-writer.** Split `_finalize`'s row-writing in `runners/request.py` into `add_request_rows(session, row, *, result, error, settings)` (no commit); `_finalize` loads the row, calls it and commits, as before | `bullpit/runners/request.py` | D-M6-5 | Every existing graph and CLI test passes unchanged | dde59d4 |
| [x] | M6-T-8 | **Loss warning in state.** Add `RequestState.loss_warning`; `report/builder.py` reads it instead of the constant `None` | `bullpit/state.py`, `bullpit/report/builder.py` | FR-12; D-M6-16 | Four checks clean; `test_builder.py` passes unchanged | e29c8fb |
| [x] | M6-T-9 | **Backtest runner.** Write `runners/backtest.py` (§9.3, §11.1): `start_backtest` (cutoff check, asset lookup, `backtest_runs` row; refusals raise `ConfigError` and write nothing), `run_backtest` (pinned-model guard, seed override, broker rebuilt from `trades`, one graph build, the week-atomic loop with bars through `get_prices(ticker, day, 1)`, loss warning from `equity_snapshots`, deterministic request IDs, approval and submission, window end, checkpoint), stop handling (`QuotaExhausted`/`LLMUnavailable` → `paused`, anything else → `stopped`, both after rollback), `WeekSummary` and `RunResult` | `bullpit/runners/backtest.py` | FR-6 to FR-14; D-M6-5, D-M6-6, D-M6-13 to D-M6-16 | Four checks clean | 23b665c |
| [x] | M6-T-10 | **CLI.** Add `bullpit backtest` (`--tickers`, `--start`, `--weeks`, `--seed`, `--cash`, or `--resume RUN_ID`): schema upgrade, Alpaca asset lookup only at start, one line per week, the final summary with `open_at_end` trades separate (FR-14), the pause message, exit codes 0 / 1 / 2 / 3. No test (CLI wiring is checked by hand, dev-plan §7.3; T-13 runs it) | `bullpit/cli.py` | FR-7, FR-11, FR-14 | Four checks clean; `bullpit backtest --help` lists the options | 22d8695 |
| [x] | M6-T-11 | **Runner tests.** `tests/runners/test_backtest.py`, reusing `test_graph.py`'s fixture patches and `RecordingLLM` (scripted by ticker): `test_happy_path` (3 weeks, 2 tickers, one buy: requests, reports, snapshots, checkpoint, `approvals` and `trades` rows, loss warning `False` from week 2); `test_same_day_buys_share_cash` (small starting cash); `test_resume_matches_uninterrupted` (parametrised: `QuotaExhausted` from a low budget, `RuntimeError` from the fake, both mid-week 2; compared with the §11.5 helper; the stopped week leaves no rows); `test_start_before_cutoff_refused`; `test_resume_after_model_change_refused`. If AC-4 shows unstable warning order from the parallel analysts, sort warnings where they're merged and note it here | `tests/runners/__init__.py`, `tests/runners/test_backtest.py` | AC-3, AC-4, AC-5, AC-7, AC-8 | All pass; whole suite under a minute | e19ce62 |
| [x] | M6-T-12 | **ADR-0006: stock selection.** Apply Q2's rule with data from 2024-06-28 or earlier (S&P 500 sector weights, market caps): the three largest sectors, the largest company in each that passes the request check on 2024-07-01 and is priced under $10,000. Confirm with `get_prices` that none has a split in 2024-07-01 … 2024-12-31. Record the rule, sources, data and tickers; the first ticker (largest sector) is AC-6's stock | `docs/adr/0006-backtest-stock-selection.md` | FR-17; D-M6-11; AC-10 | ADR written; owner reads it | 612450d |
| [x] | M6-T-13 | **Real run (AC-6).** `bullpit doctor`. Check the last 24 hours of `llm_calls`: at least 30K large-model tokens left. Start `bullpit backtest --tickers <first ADR-0006 stock> --start 2024-07-01 --weeks 2 --seed 1` with `LLM_DAILY_TOKEN_BUDGET` = small-model tokens used in the last 24 h + 4,000 → it must pause in week 1 (exit 3, resume message). `--resume` with the default budget → completes; the week's earlier calls are `cache_hit = 1`. Read the reports; check any trade's entry against the real next open × 1.0005 and any exit against that day's bar. Paste the output, tokens used and one row count per table below | this file | AC-6; M6-NFR-6 | Evidence pasted; run `completed` | (evidence in this file) |
| [x] | M6-T-14 | **Acceptance.** README: running a backtest (start, pause, resume). Retrospective: what changed from the plan, test count and suite time, tokens of the real run, carry-overs for M7 (the 26-week, 3-stock run on the ADR-0006 stocks with seed 1). Then, when the owner asks: push, CI green, merge to `master`, tag `m6` | `README.md`, this file | DoD §1.5 | Owner accepts | f6f9201 |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-4 |
| AC-2 | T-3, T-4 |
| AC-3 | T-4, T-11 |
| AC-4 | T-9, T-11 |
| AC-5 | T-9, T-11 |
| AC-6 | T-10, T-12, T-13 |
| AC-7 | T-9, T-11 |
| AC-8 | T-5, T-6, T-7, T-8, T-9, T-11 |
| AC-9 | T-6 |
| AC-10 | T-4, T-12 |

| Requirement | Task |
|---|---|
| FR-1 to FR-5 | T-4 |
| FR-6 | T-5, T-9 |
| FR-7 to FR-11, FR-13 | T-9, T-10 |
| FR-12 | T-8, T-9 |
| FR-14 | T-9, T-10 |
| FR-15 | T-6 |
| FR-16 | T-2 |
| FR-17 | T-12 |

---

## Evidence

(Filled in by T-13.)

Run `9f7e293e`: `bullpit backtest --tickers MSFT --start 2024-07-01 --weeks 2 --seed 1`, run 2026-09-29.

**Before:** `bullpit doctor` all OK. Last 24 h of `llm_calls`: large model 120,191 used (79,809 left, above the 30K needed), small model 68,602. Forced-pause budget = 68,602 + 4,000 = **72,602**.

**Start with `LLM_DAILY_TOKEN_BUDGET=72602`** (the three week-1 analyst calls ran, then the first large-model call was refused):

```text
Paused: openai/gpt-oss-120b: 120191 tokens used in the last 24h, budget is 72602. Resume with: bullpit backtest --resume 9f7e293e
exit code 3
```

**Resume with the default budget** (`bullpit backtest --resume 9f7e293e`, exit 0):

```text
2024-07-05: MSFT NO TRADE | equity 100,000.00
2024-07-12: MSFT BUY 12 | equity 100,000.00
run 9f7e293e completed: end equity 100,000.00
closed trades: 0 (0 wins), P&L 0.00
open at window end: 0
cancelled orders: 1
```

**Resume was free for the calls already made.** Week 1's request has 13 `llm_calls` rows, 3 of them `cache_hit = 1` (the three analysts, replayed). Week 2 has 10 rows, 1 cache hit (the fundamentals verdict, cached per filing).

**Tokens used by the run (real calls only, including the paused attempt):** small model 11,857; large model 21,781. Week 1 request 17,459; week 2 request 16,179 (two debated requests, about 10.9K large-model tokens each, in line with architecture §14).

**Row counts for the run:**

| Table | Rows |
|---|---|
| `backtest_runs` | 1 (`completed`, checkpoint 2024-07-12) |
| `requests` | 2 (both `completed`, both routed to the debate) |
| `signals` | 6 |
| `debate_turns` | 8 |
| `recommendations` | 2 |
| `reports` | 2 |
| `approvals` | 1 (`approved`, 12 of 12 shares, `backtest_policy`, decided 2024-07-12 20:00 UTC, the close) |
| `trades` | 1 |
| `equity_snapshots` | 9 (2024-07-01 to 2024-07-12, every session) |

**The trade:** `bullpit-20240712-MSFT-9f7e293e`, 12 shares, reference 453.55, stop 439.02, take-profit 475.35 (12 x 453.55 = 5,442.60, 5.4% of equity, as the report shows). The buy came on the last decision day, so the order could not enter inside the window and was cancelled with `window ended before entry` (D-M6-10). Its recommendation stays in the journal for M7. Equity stayed at 100,000 because nothing entered.

**Reports read:** the week-1 no-trade report (loss warning `not available`: no history 7 days back yet) and the week-2 buy report (loss warning `False`, so the equity history reaches the report, M6-FR-12). Both read correctly.

**Not checked by hand:** an entry against the real next open and an exit against a real bar, because no order entered in this run. Those rules are covered by the automated fixtures (M6-AC-1, AC-2), and M7's 26-week run will exercise them on real data.

## Retrospective

(Written in T-14.)

**What was built:** exactly the specs-plan's files and tasks. Suite: 244 tests (221 at the start of M6, so 23 new: 3 in `test_config`/calendar, 14 in `test_sim`, 6 in `test_backtest`), about 22 seconds. Four checks clean.

**Changes from the plan, found while implementing:**

1. **A week is written in one transaction at the end, not flushed as it goes (specs-plan sec11.1).** The LLM gateway commits its own `llm_calls` rows on other connections. A runner holding a flushed write while the graph runs would block those inserts on SQLite. So the runner now simulates the week's sessions and runs every request in memory, then writes snapshots, requests, approvals, trades and the checkpoint together. Same atomicity (M6-FR-9, AC-4), no requirement changed. The loss warning reads the committed history plus the week's in-memory snapshots.
2. **`Trade.pnl` is a property** on `domain.Trade` (one place for the profit rule, used by the journal row and the CLI summary); `RunResult` carries the run's trades, and the CLI does the counting.
3. **Small refactors in M4/M5 code:** `runners/request.py`'s `git_commit`, `naive_utc_now` and `earliest_backtest_date` became public (the backtest runner needs them); `add_request_rows` flushes the request row before its children, because the models have no relationships to order the inserts. `RequestState.loss_warning` was added in T-2 with the other type changes (T-8 then wired the report to it).
4. **One M1 bug fixed in `data/news.py`.** An empty news fetch parsed to seconds, and merging it with cached microsecond dates turned the column into objects, which the date guard rejected (`LookaheadViolation`). It would stop any real backtest on the first ticker-week with no headlines after a week that had some. The runner's happy-path test now covers it (the fixture has no news after 2024-07-07).
5. **ADR-0006 picks `MSFT`, `BRK.B`, `LLY`** (not the `AAPL, JPM, LLY` of the spec's CLI example, which was only an example). Berkshire must be typed `BRK.B`: Alpaca refuses `BRK-B`. The exact sector weights at 2024-06-28 could not be found online, and the ADR says so; Berkshire's market cap is an estimate with a wide margin.
6. **Test detail:** AC-4's uninterrupted run is executed last, so it replays cached replies (the cache key doesn't include the request ID); the interrupted run and its resume share one scripted LLM so the queued buy isn't replayed. AC-3's same-day test raises `max_position_pct` and `risk_per_trade_pct` so cash is the binding limit.
7. **The real run's week-2 buy was cancelled at the window end** (last decision day), so `trades` and `approvals` hold real rows but no fill (see Evidence).

**Carry-overs for M7:**

- The 26-week, 3-stock run: `bullpit backtest --tickers MSFT,BRK.B,LLY --start 2024-07-01 --weeks 26 --seed 1`. The first two weeks of MSFT come back from the cache. At the measured ~16-17K real tokens per debated request (about 11K on the large model), 78 requests are roughly 5 days of the large model's free quota.
- Check an entry against the real next open and an exit against a real bar on the first real fill.
- Buys on the last decision day never enter; M7 should count them as recommendations, not trades.
