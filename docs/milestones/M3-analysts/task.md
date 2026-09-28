# M3 — Request check, three analysts, signals board, brain: tasks

| | |
|---|---|
| **Status** | Draft, awaiting the owner's green light |
| **Date** | 2026-09-28 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (Part A approved 2026-09-28, Q1 = A; Part B awaiting approval) |
| **Branch** | `m3-analysts`, from `master` |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. After every task: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` are clean, and the diff has been re-read for anything the task doesn't need.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [ ] | M3-T-1 | **Docs.** Create `m3-analysts` from `master`; commit `specs-plan.md`, this file, dev-plan §3 D10–D11 (revision 5) and `architecture.md` v2.2 | `docs/milestones/M3-analysts/*`, `docs/dev-plan.md`, `docs/architecture.md` | §8; D10, D11 | Branch exists; docs committed | |
| [ ] | M3-T-2 | **Dependency and settings.** `uv add langgraph`; the FR-22 settings in `config.py` and `.env.example` | `pyproject.toml`, `uv.lock`, `bullpit/config.py`, `.env.example` | FR-22; D-M3-12, D-M3-14 | `uv sync --locked` succeeds; four checks clean; `Settings()` shows every new default | |
| [ ] | M3-T-3 | **Data-layer additions.** `PriceHistory.splits` (ex-dates ≤ `as_of` within the window, from the cached `split_ratio`); `_CIK_OVERRIDES = {"XOM": 34088}` in `data/sec.py`, applied in `get_cik` | `bullpit/data/prices.py`, `bullpit/data/sec.py` | FR-6, FR-10; D-M3-11, D-M3-16; §7.1 C-2 | M1's tests still pass; by hand: NVDA at 2024-07-12 lists `(2024-06-10, 10.0)`; `get_sec_facts("XOM", 2024-10-18)` returns facts | |
| [ ] | M3-T-4 | **Domain and broker.** `domain.py` (`Account`, `Position`, `Asset`); `broker/base.py` (`Broker` protocol); `broker/alpaca.py` (`AlpacaBroker`: 404 → `None`, other SDK errors → `BrokerRejected`); `tests/broker/fake_broker.py` | `bullpit/domain.py`, `bullpit/broker/base.py`, `bullpit/broker/alpaca.py`, `tests/broker/fake_broker.py` | FR-4, FR-7; §12 | mypy strict clean; by hand against the paper account: account, AAPL position (or `None`), unknown asset `None` | |
| [ ] | M3-T-5 | **Indicators.** `Indicators`, `compute_indicators` (plan §11.1) and its test | `bullpit/tools/indicators.py`, `tests/tools/__init__.py`, `tests/tools/test_indicators.py` | FR-8; D-M3-10; AC-2 | `test_indicators.py` passes | |
| [ ] | M3-T-6 | **Fundamentals maths.** `FundamentalsMetrics`, `compute_fundamentals` (plan §11.2) and its four tests | `bullpit/tools/fundamentals.py`, `tests/tools/test_fundamentals.py` | FR-10; D-M3-11; §7.1 C-1; AC-3 | `test_fundamentals.py` passes | |
| [ ] | M3-T-7 | **Sentiment tools.** `select_headlines`, `weighted_sentiment` (plan §11.3) | `bullpit/tools/sentiment.py` | FR-13, FR-14; D-M3-8 | Four checks clean; exercised by T-15 | |
| [ ] | M3-T-8 | **Schemas, state, prompts.** `Signal` extended, `AnalystVerdict`, `HeadlineScore(s)`; `state.py`; `technical.md`, `fundamentals.md`, `sentiment.md` (plan §9.6) | `bullpit/llm/schemas.py`, `bullpit/state.py`, `bullpit/llm/prompts/*.md` | §5; FR-9, FR-11, FR-14; D-M3-1, D-M3-4 | Four checks clean; each template renders with `StrictUndefined` from a shell; the fundamentals template has no price, P/E or date | |
| [ ] | M3-T-9 | **Thread safety.** Lock the gateway's token buckets and Langfuse latch (plan §9.8); the journal test fixture moves to a temp file | `bullpit/llm/gateway.py`, `tests/conftest.py` | NFR-2 | M2's gateway tests still pass | |
| [ ] | M3-T-10 | **Analyst agents.** `technical.py`, `fundamentals.py`, `sentiment.py`: tool results → evidence facts (plan §9.5) → `call_llm` → `Signal`; flagged reply → neutral flagged signal; no LLM call when fundamentals are unavailable or there's no news | `bullpit/agents/technical.py`, `bullpit/agents/fundamentals.py`, `bullpit/agents/sentiment.py` | FR-8 to FR-14; D10, D11 | Four checks clean; exercised by T-15 | |
| [ ] | M3-T-11 | **Signals board and brain.** `build_board` (score, conflict, registry), `choose_route`, `data_warnings` (plan §11.4) | `bullpit/agents/signals_board.py`, `bullpit/agents/brain.py` | FR-16, FR-17; D-M3-3, D-M3-7 | Four checks clean; exercised by T-15 | |
| [ ] | M3-T-12 | **Request check.** The node: asset, SEC, prices, account, in order, with the FR-5 messages (plan §12) | `bullpit/request_check.py` | FR-4 to FR-6; D-M3-2, D-M3-6 | Four checks clean; exercised by T-15 and AC-4 | |
| [ ] | M3-T-13 | **Journal.** `Request` columns and `SignalRecord` in `models.py`; migration `0002_request_lock_signals` (batch mode, partial unique index) | `bullpit/journal/models.py`, `bullpit/journal/migrations/versions/0002_request_lock_signals.py` | FR-21; §10 | `alembic upgrade head` on a temp DB gives a schema matching `models.py` (checked again in T-16) | |
| [ ] | M3-T-14 | **Graph, runner, CLI.** `graph.py` (`Deps`, `build_graph`, the analyst failure wrapper); `runners/request.py` (plan §9.7: cutoff, lock, run, record); the `request` command with auto-migrate | `bullpit/graph.py`, `bullpit/runners/request.py`, `bullpit/cli.py` | FR-1 to FR-3, FR-15, FR-18 to FR-20; D-M3-5, D-M3-9, D-M3-13; §7.1 C-5 | `uv run bullpit request AAPL --mode backtest --as-of 2024-07-12` completes against the real services and prints signals and a route | |
| [ ] | M3-T-15 | **Graph tests.** Record AAPL `NetIncomeLoss` and `EarningsPerShareDiluted` into the companyfacts fixture; `test_graph.py` (the four tests in plan §13) | `tests/fixtures/sec/aapl_companyfacts.json`, `tests/test_graph.py` | AC-1 (automated), AC-5, AC-6, AC-7, AC-9 | All four pass; whole suite still runs in under a minute | |
| [ ] | M3-T-16 | **Real runs.** AC-1 (5 tickers × 3 dates + one live); AC-3 revenue table; AC-4 rejections; AC-8 parallel start times; AC-11 journal rows, stale lock and Alembic schema | this file (evidence) | AC-1, AC-3, AC-4, AC-8, AC-11 | Evidence pasted below; every check passes | |
| [ ] | M3-T-17 | **Tokens and allowance.** Per-template token figures from `llm_calls` over the T-16 runs; set `llm_output_allowance_tokens` per FR-23; re-run one request to confirm nothing is flagged | `bullpit/config.py`, `.env.example`, this file | FR-23; AC-10; C14 | Figures and the new default recorded; the re-run has no flagged reply | |
| [ ] | M3-T-18 | **Acceptance.** README quick start gains a first `bullpit request`; retrospective (token numbers vs architecture §14, route split for D-M3-7, carry-overs); then, when the owner asks: push, CI green, merge to `master`, tag `m3` | `README.md`, this file | DoD §1.5 | Owner accepts | |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-14, T-15 (automated), T-16 (real) |
| AC-2 | T-5 |
| AC-3 | T-6 (fixture), T-16 (table) |
| AC-4 | T-12, T-14, T-16 |
| AC-5 | T-14, T-15 |
| AC-6 | T-11, T-15 |
| AC-7 | T-11, T-15 |
| AC-8 | T-14, T-16 |
| AC-9 | T-3, T-12, T-15 |
| AC-10 | T-17 |
| AC-11 | T-13, T-14, T-16 |

| Requirement | Task |
|---|---|
| FR-1 to FR-3 | T-14 |
| FR-4 to FR-6 | T-3, T-12 |
| FR-7 | T-4 |
| FR-8, FR-9 | T-5, T-10 |
| FR-10 to FR-12 | T-3, T-6, T-10 |
| FR-13, FR-14 | T-7, T-10 |
| FR-15 | T-14 |
| FR-16, FR-17 | T-11 |
| FR-18 to FR-20 | T-14 |
| FR-21 | T-13 |
| FR-22 | T-2 |
| FR-23 | T-17 |
| NFR-2 | T-9 |
| D10, D11 | T-1 (docs), T-8, T-10 |

---

## Evidence

*(filled in as tasks complete)*

## Retrospective

*(written at T-18)*
