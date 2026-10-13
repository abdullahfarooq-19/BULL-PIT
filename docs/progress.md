# Bull Pit: progress from M0 to M8

Written 2026-09-30, refreshed 2026-10-06. A plain summary of what each milestone built and what is
still open. The sources of truth stay [`architecture.md`](architecture.md),
[`dev-plan.md`](dev-plan.md) and each milestone's folder under
[`milestones/`](milestones/); if this page disagrees with them, they win.

## At a glance

| Milestone | What it built | State |
|---|---|---|
| M0 | Foundations: scaffold, paper-only guard, `doctor`, CI, spikes | Done, tagged `m0` |
| M1 | Data layer, date guard, cache | Done, tagged `m1` |
| M2 | LLM gateway | Done, tagged `m2` |
| M3 | Request check, three analysts, signals board, brain | Done, tagged `m3` |
| M4 | Debate, trader, risk manager | Done, tagged `m4` |
| M5 | Report generator | Done, tagged `m5` |
| M6 | Simulated broker, journal, backtest runner | Done, tagged `m6` |
| M7 | Evaluation, baselines, pilot results | Done, tagged `m7` |
| M8 | Live mode: API, dashboard, approval, bracket orders, fill check | Done, tagged `m8` (accepted 2026-10-06) |
| M11.1 | Report explanations, order box, cancel, advanced mode | Done, tagged `m11.1` |
| M11.2 | Dashboard restructure: Account & Wallet, Trades History, Portfolio | Done, tagged `m11.2` |
| M11.3 | Live P&L, market and connection badges, logo and motto | Done, tagged `m11.3` |
| M11.4 | Backtests page removed (results are `docs/results/results.md`) | Done, tagged `m11.4` |
| M9 | Dashboard polish, README, results write-up | Done, tagged `m9` (accepted 2026-10-14; the first push and CI, and a second reader of the README, are carried over, see its `task.md`) |

## What each milestone delivered

**M0, foundations.** Repository scaffold managed with `uv`; typed settings; the
domain exception hierarchy; structured logging; the injected `Clock`. The
**paper-only guard** refuses any Alpaca URL except `paper-api.alpaca.markets`
before any network call. `bullpit doctor` checks config and every external
service without printing a secret. CI (lint, format, types, tests, secret scan)
and pre-commit hooks. Spikes against the real services confirmed the Alpaca
bracket-order rules (GTC keeps the exit legs alive, whole shares only,
`client_order_id` is unique, legs come back `HELD` when the market is closed);
recorded in ADR-0001 and ADR-0002 and `findings.md`.

**M1, data layer.** The only door to the outside world. Daily prices from
yfinance with Alpaca as backup, SEC EDGAR filings with filing dates, Alpaca
news, the NYSE trading calendar, and a Parquet cache. The **date guard** filters
every request and every response by `as_of`, with tests proving nothing after
`as_of` leaks. Prices are point-in-time (splits applied only once they had
happened; ADR-0003).

**M2, LLM gateway.** Every model call goes through one place: routing to the
pinned models, a response cache, rate limiting and backoff, JSON validation
with one retry and a safe default, a daily token budget, and token logging to
the journal. Real token costs were measured (ADR-0004 covers cache storage).

**M3, request check and analysts.** The request check (tradable, enough data,
account snapshot, duplicate lock). Technical, fundamentals and sentiment
analysts: code computes indicators, ratios and evidence facts, the LLM only
judges direction and confidence. The signals board and the brain's
debate-or-skip routing (code, no LLM). The `bullpit request` CLI.

**M4, debate, trader, risk manager.** Bull and bear debate for two rounds with
evidence-ID checks; the trader (buy or no trade, weight, exit style); the risk
manager: ATR-based stop-loss and take-profit, share count as the smallest of
four limits (target, 1% risk, 10% per-stock cap, cash), hard rules, an LLM
review that can only shrink or veto, and the loss-warning function.

**M5, report.** A structured report with the ten sections of architecture §7,
rendered to Markdown. Code writes every number; a small model writes only the
plain-language sentences, and a number check rejects any it invents.

**M6, simulated broker and backtest runner.** The journal (SQLAlchemy,
Alembic): requests, signals, debate, recommendations, reports, approvals,
trades, equity snapshots, backtest runs. A simulated broker with bracket exits
(entry at the next open plus slippage, exits from daily lows and highs, stop
first). A resumable backtest runner that pauses and resumes when the free daily
quota runs out (ADR-0005 fixes the fill rules, ADR-0006 the stock selection).

**M7, evaluation.** Baselines that share the same broker and sizing (always
buy, moving-average rule, single agent, Bull Pit's own buys replayed);
metrics (return, Sharpe, drawdown, win rate, profit factor, "no trade" value,
Brier score, tokens per request); a results page with three charts. The
**pilot** (2 stocks, 2 weeks, one seed, on the free Qwen model) is in
[`results/results.md`](results/results.md). It shows the pipeline works end to
end and states plainly that it cannot say any approach is better.

**M8, live mode** (accepted 2026-10-06):

- Alpaca write side: one idempotent bracket order per approval, order lookup by
  `client_order_id`, manual-close detection, equity history.
- Approval gate (pure code): shares can only go down, 2% staleness check,
  one-trading-day expiry, loss-warning confirmation, cash and per-stock cap
  re-checked at the latest price and counted **net of orders that haven't
  filled yet**.
- The graph pauses for the owner (LangGraph `interrupt`, SQLite checkpointer
  with a strict list of allowed state types) and survives an API restart; a
  recorded approval is never lost to expiry without asking Alpaca.
- Fill check (`bullpit fill-check`, `POST /fill-check`, run when the dashboard
  opens) records entries, exits, manual closes, partial-fill warnings and live
  equity snapshots. It only records.
- FastAPI app bound to `127.0.0.1` only (`bullpit serve`); OpenAPI schema
  written by `bullpit openapi`.
- Next.js dashboard (as built in M8; M11.2 later turned it into Account & Wallet, Trades History,
  and Portfolio; the Backtests page was removed in M11.4): New request, report and decide (bracket price ladder,
  signal gauges, hold-to-approve, stale/loss/rules sheets), History, Trades
  (TradingView Lightweight Charts), Backtests (since removed); loading, error and empty states;
  Ctrl+K palette. Types are generated from the OpenAPI schema; CI has a web
  job.
- Automated tests, ruff, mypy, ESLint and the web build are clean (429 tests after M11.4).

## Decisions worth remembering

- **Code for math, LLMs for judgment**; no LLM output is ever used as a number.
- **Paper only**, with a guard that cannot be switched off.
- **A person approves every live trade**; `bullpit request` never places an
  order, only the dashboard does.
- Models are pinned (Groq `gpt-oss-20b` small, `gpt-oss-120b` large); M7's
  pilot used the free Qwen model on OpenRouter (deviation D13).
- The live equity chart uses TradingView Lightweight Charts, not Recharts
  (deviation D14, architecture v2.6).
- M8 dropped `AlpacaBroker.get_order` (a trade needs the report's reference
  price, which only the journal holds).

## What is left

| Item | Needs |
|---|---|
| The first push (nothing since M0 is on `origin`) and a green CI run; a second person following the README | The owner |
| The full gpt-oss evaluation (26 weeks, three stocks, repeat seeds, debate impact): commands in the M7 retrospective | Paid or large model quota |
| The M11.3 Close button | A new spec and deviation |
