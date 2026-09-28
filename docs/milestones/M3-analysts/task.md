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
| [x] | M3-T-1 | **Docs.** Create `m3-analysts` from `master`; commit `specs-plan.md`, this file, dev-plan §3 D10–D11 (revision 5) and `architecture.md` v2.2 | `docs/milestones/M3-analysts/*`, `docs/dev-plan.md`, `docs/architecture.md` | §8; D10, D11 | Branch exists; docs committed | `0e6eb47` |
| [x] | M3-T-2 | **Dependency and settings.** `uv add langgraph`; the FR-22 settings in `config.py` and `.env.example` | `pyproject.toml`, `uv.lock`, `bullpit/config.py`, `.env.example` | FR-22; D-M3-12, D-M3-14 | `uv sync --locked` succeeds; four checks clean; `Settings()` shows every new default | `6e87355` |
| [x] | M3-T-3 | **Data-layer additions.** `PriceHistory.splits` (ex-dates ≤ `as_of` within the window, from the cached `split_ratio`); `_CIK_OVERRIDES = {"XOM": 34088}` in `data/sec.py`, applied in `get_cik` | `bullpit/data/prices.py`, `bullpit/data/sec.py` | FR-6, FR-10; D-M3-11, D-M3-16; §7.1 C-2 | M1's tests still pass; by hand: NVDA at 2024-07-12 lists `(2024-06-10, 10.0)`; `get_sec_facts("XOM", 2024-10-18)` returns facts | `5b7908b` |
| [x] | M3-T-4 | **Domain and broker.** `domain.py` (`Account`, `Position`, `Asset`); `broker/base.py` (`Broker` protocol); `broker/alpaca.py` (`AlpacaBroker`: 404 → `None`, other SDK errors → `BrokerRejected`); `tests/broker/fake_broker.py` | `bullpit/domain.py`, `bullpit/broker/base.py`, `bullpit/broker/alpaca.py`, `tests/broker/fake_broker.py` | FR-4, FR-7; §12 | mypy strict clean; by hand against the paper account: account, AAPL position (or `None`), unknown asset `None` | `acc3747` |
| [x] | M3-T-5 | **Indicators.** `Indicators`, `compute_indicators` (plan §11.1) and its test | `bullpit/tools/indicators.py`, `tests/tools/__init__.py`, `tests/tools/test_indicators.py` | FR-8; D-M3-10; AC-2 | `test_indicators.py` passes | `e7e5500` |
| [x] | M3-T-6 | **Fundamentals maths.** `FundamentalsMetrics`, `compute_fundamentals` (plan §11.2) and its four tests | `bullpit/tools/fundamentals.py`, `tests/tools/test_fundamentals.py` | FR-10; D-M3-11; §7.1 C-1; AC-3 | `test_fundamentals.py` passes | `b775208` |
| [x] | M3-T-7 | **Sentiment tools.** `select_headlines`, `weighted_sentiment` (plan §11.3) | `bullpit/tools/sentiment.py` | FR-13, FR-14; D-M3-8 | Four checks clean; exercised by T-15 | `7ea1b8e` |
| [x] | M3-T-8 | **Schemas, state, prompts.** `Signal` extended, `AnalystVerdict`, `HeadlineScore(s)`; `state.py`; `technical.md`, `fundamentals.md`, `sentiment.md` (plan §9.6) | `bullpit/llm/schemas.py`, `bullpit/state.py`, `bullpit/llm/prompts/*.md` | §5; FR-9, FR-11, FR-14; D-M3-1, D-M3-4 | Four checks clean; each template renders with `StrictUndefined` from a shell; the fundamentals template has no price, P/E or date | `ed1e9b5` |
| [x] | M3-T-9 | **Thread safety.** Lock the gateway's token buckets and Langfuse latch (plan §9.8); the journal test fixture moves to a temp file | `bullpit/llm/gateway.py`, `tests/conftest.py` | NFR-2 | M2's gateway tests still pass | `37770c3` |
| [x] | M3-T-10 | **Analyst agents.** `technical.py`, `fundamentals.py`, `sentiment.py`: tool results → evidence facts (plan §9.5) → `call_llm` → `Signal`; flagged reply → neutral flagged signal; no LLM call when fundamentals are unavailable or there's no news | `bullpit/agents/technical.py`, `bullpit/agents/fundamentals.py`, `bullpit/agents/sentiment.py` | FR-8 to FR-14; D10, D11 | Four checks clean; exercised by T-15 | `edfeff6` |
| [x] | M3-T-11 | **Signals board and brain.** `build_board` (score, conflict, registry), `choose_route`, `data_warnings` (plan §11.4) | `bullpit/agents/signals_board.py`, `bullpit/agents/brain.py` | FR-16, FR-17; D-M3-3, D-M3-7 | Four checks clean; exercised by T-15 | `eee3f79` |
| [x] | M3-T-12 | **Request check.** The node: asset, SEC, prices, account, in order, with the FR-5 messages (plan §12) | `bullpit/request_check.py` | FR-4 to FR-6; D-M3-2, D-M3-6 | Four checks clean; exercised by T-15 and AC-4 | `b4305a5` |
| [x] | M3-T-13 | **Journal.** `Request` columns and `SignalRecord` in `models.py`; migration `0002_request_lock_signals` (batch mode, partial unique index) | `bullpit/journal/models.py`, `bullpit/journal/migrations/versions/0002_request_lock_signals.py` | FR-21; §10 | `alembic upgrade head` on a temp DB gives a schema matching `models.py` (checked again in T-16) | `377db36` |
| [x] | M3-T-14 | **Graph, runner, CLI.** `graph.py` (`Deps`, `build_graph`, the analyst failure wrapper); `runners/request.py` (plan §9.7: cutoff, lock, run, record); the `request` command with auto-migrate | `bullpit/graph.py`, `bullpit/runners/request.py`, `bullpit/cli.py` | FR-1 to FR-3, FR-15, FR-18 to FR-20; D-M3-5, D-M3-9, D-M3-13; §7.1 C-5 | `uv run bullpit request AAPL --mode backtest --as-of 2024-07-12` completes against the real services and prints signals and a route | `8fd93f6` |
| [x] | M3-T-15 | **Graph tests.** Record AAPL `NetIncomeLoss` and `EarningsPerShareDiluted` into the companyfacts fixture; `test_graph.py` (the four tests in plan §13) | `tests/fixtures/sec/aapl_companyfacts.json`, `tests/test_graph.py` | AC-1 (automated), AC-5, AC-6, AC-7, AC-9 | All four pass; whole suite still runs in under a minute | `c39b3eb` |
| [x] | M3-T-16 | **Real runs.** AC-1 (5 tickers × 3 dates + one live); AC-3 revenue table; AC-4 rejections; AC-8 parallel start times; AC-11 journal rows, stale lock and Alembic schema | this file (evidence) | AC-1, AC-3, AC-4, AC-8, AC-11 | Evidence pasted below; every check passes | (docs-only) |
| [x] | M3-T-17 | **Tokens and allowance.** Per-template token figures from `llm_calls` over the T-16 runs; set `llm_output_allowance_tokens` per FR-23; re-run one request to confirm nothing is flagged | `bullpit/config.py`, `.env.example`, this file | FR-23; AC-10; C14 | Figures and the new default recorded; the re-run has no flagged reply | `pending` |
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

### M3-T-16: real runs

**AC-1** — 5 reference tickers x 3 backtest dates, plus one live request, all against the real
services (Groq, Alpaca, SEC EDGAR, yfinance). Every run completed with no uncaught error, three
signals and a route:

```
AAPL @ 2024-07-12  technical=neutral(0.55)   fundamentals=bullish(0.70)  sentiment=neutral(0.10)   board=0.233  route=debate
AAPL @ 2024-10-18  technical=bullish(0.70)   fundamentals=bullish(0.80)  sentiment=bullish(0.24)   board=0.580  route=debate
AAPL @ 2025-01-17  technical=bearish(0.70)   fundamentals=bullish(0.80)  sentiment=neutral(0.04)   board=0.033  route=debate (conflict)
MSFT @ 2024-07-12  technical=neutral(0.55)   fundamentals=bullish(0.90)  sentiment=bullish(0.22)   board=0.373  route=debate
MSFT @ 2024-10-18  technical=bearish(0.70)   fundamentals=bullish(0.80)  sentiment=bullish(0.76)   board=0.287  route=debate (conflict)
MSFT @ 2025-01-17  technical=bullish(0.70)   fundamentals=bullish(0.90)  sentiment=bullish(0.37)   board=0.656  route=debate
JPM  @ 2024-07-12  technical=bullish(0.70)   fundamentals=bullish(0.80)  sentiment=bullish(0.22)   board=0.573  route=debate
JPM  @ 2024-10-18  technical=neutral(0.55)   fundamentals=bullish(0.90)  sentiment=bullish(0.26)   board=0.386  route=debate
JPM  @ 2025-01-17  technical=bullish(0.60)   fundamentals=bullish(0.80)  sentiment=bullish(0.57)   board=0.655  route=debate
XOM  @ 2024-07-12  technical=bearish(0.40)   fundamentals=neutral(0.60)  sentiment=neutral(0.15)   board=-0.133 route=no_trade
XOM  @ 2024-10-18  technical=neutral(0.40)   fundamentals=bullish(0.80)  sentiment=neutral(0.03)   board=0.267  route=debate
XOM  @ 2025-01-17  technical=bullish(0.55)   fundamentals=bullish(0.70)  sentiment=bullish(0.50)   board=0.583  route=debate
JNJ  @ 2024-07-12  technical=bullish(0.70)   fundamentals=bullish(0.80)  sentiment=bullish(0.17)   board=0.558  route=debate
JNJ  @ 2024-10-18  technical=bullish(0.70)   fundamentals=bullish(0.80)  sentiment=bullish(0.21)   board=0.569  route=debate
JNJ  @ 2025-01-17  technical=bullish(0.60)   fundamentals=bullish(0.80)  sentiment=bullish(0.44)   board=0.614  route=debate

Live: AAPL, as_of resolved to 2026-09-28 (latest completed NYSE session), request_id
20260928-AAPL-97fabc25, account cash=99422.96 equity=99435.33, three signals produced, route=debate.
```

Note XOM's 2024-07-12 result: the brain correctly routes a weak, non-conflicting board to
`no_trade` (board score -0.133, |score| < 0.15) -- confirms the route isn't a stub that always
debates.

**AC-3** — fundamentals evidence (F1-F5) for each reference ticker's latest quarter at
2024-10-18, cross-checked against the real filings:

```
AAPL  quarter ended 2024-06-29  revenue $85.78B (+4.9% YoY)  margin 25.0%  TTM EPS 6.58  P/E 35.7   10-Q filed 2024-08-02
MSFT  quarter ended 2024-06-30  revenue $64.73B (+15.2% YoY) margin 34.0%  TTM EPS 11.80 P/E 35.4   10-K filed 2024-07-30
JPM   quarter ended 2024-06-30  revenue $50.20B (+21.5% YoY) margin 36.2%  TTM EPS 17.94 P/E 12.6   10-Q filed 2024-08-02
XOM   quarter ended 2024-06-30  revenue $93.06B (+12.2% YoY) margin 9.9%   TTM EPS 8.36  P/E 14.4   10-Q filed 2024-08-05
JNJ   quarter ended 2024-06-30  revenue $22.45B (+4.3% YoY)  margin 20.9%  TTM EPS 15.15 P/E 10.9   10-Q filed 2024-07-25
```

AAPL's $85.78B matches Apple's reported Q3 FY2024 revenue exactly. MSFT's $64.73B matches
Microsoft's reported Q4 FY2024 revenue exactly -- and since MSFT's fiscal Q4 is never filed as a
discrete quarter (only in the 10-K), this confirms the Q4 = FY - (Q1+Q2+Q3) derivation (M3-FR-10)
against a real filing, not just the hand-built fixture in T-6. JPM's $50.20B, XOM's $93.06B and
JNJ's $22.45B all match their real reported Q2 2024 figures; XOM's number additionally confirms
the CIK override (D-M3-16, T-3) resolves real filings end to end, not just `get_cik` in isolation.

**AC-4** — each case rejected with the documented message and zero `llm_calls` rows:

```
SPY (ETF):              "No SEC filings found for this ticker. Try a US company stock."          llm_calls=0
Unknown ticker:          "ZZZZZNOTREAL isn't a tradable stock on Alpaca."                          llm_calls=0
Backtest pre-cutoff:     "Backtest dates must be after the models' training cutoff: use 2024-07-01 or later."  llm_calls=0
Duplicate running:       "A backtest request for DUPTEST is already running."                      llm_calls=0
Too little history:      "AAPL has only 300 trading days of prices up to 2024-07-12; at least 100000 are needed."  llm_calls=0
```

**AC-8** — parallel analysts, from the AAPL @ 2024-07-12 run's log (request_id
`20240712-AAPL-7ed21fc0`): all three `LiteLLM completion()` calls (one per analyst) start within
the same wall-clock second, and their `Wrapper: Completed Call` lines land in the same or the
following second -- serial calls at ~0.3-1s latency each would show visibly staggered starts,
not three starting together:

```
02:25:01  LiteLLM completion() model=openai/gpt-oss-20b  (technical)
02:25:01  LiteLLM completion() model=openai/gpt-oss-20b  (fundamentals)
02:25:01  LiteLLM completion() model=openai/gpt-oss-20b  (sentiment)
02:25:01  Wrapper: Completed Call, calling success_handler
02:25:02  Wrapper: Completed Call, calling success_handler
02:25:02  Wrapper: Completed Call, calling success_handler
```

**AC-11** — one `requests` row and its `signals` rows, a hand-inserted stale `running` row, and
the Alembic schema:

```
requests row (20240712-AAPL-7ed21fc0): status=completed route=debate warnings=[]
  price_source=yfinance git_commit=377db36f... config has 0 secret keys
signals rows: technical(neutral,0.55,6 evidence) fundamentals(bullish,0.70,5 evidence) sentiment(neutral,0.095,15 evidence)
llm_calls for that request_id: 3 rows, all role=small model=openai/gpt-oss-20b

Stale lock: a hand-inserted `running` row (STALETEST, created > request_lock_timeout_minutes ago)
  before the next request: status=running
  after the next request:  status=failed, reason="abandoned: running longer than the lock timeout"
  (the new request proceeded to request_check rather than being rejected as a duplicate)
```

Alembic: `alembic upgrade head` on a fresh temp DB, then a second `alembic revision
--autogenerate` pass against the upgraded DB, detects no further diff (empty `upgrade()`/
`downgrade()`) -- the migrated schema matches `models.py` exactly (same check performed in T-13).

### M3-T-17: token measurement and the allowance (AC-10, FR-23)

Real, non-cache-hit `llm_calls` rows over the 16 T-16 runs, grouped by `prompt_version` (one hash
per template file, so this groups exactly by analyst):

| Template | Calls | Input tokens (min/mean/max) | Output tokens (min/mean/max) | Reasoning tokens (min/mean/max) | Largest output+reasoning |
|---|---|---|---|---|---|
| `technical.md` | 16 | 303 / 304.4 / 305 | 20 / 20.8 / 21 | 41 / 69.0 / 105 | 125 |
| `fundamentals.md` | 16 | 283 / 284.4 / 285 | 20 / 20.9 / 21 | 37 / 41.4 / 51 | 71 |
| `sentiment.md` | 16 | 359 / 658.4 / 763 | 81 / 235.1 / 289 | 5 / 129.1 / 334 | 623 |

Overall largest `output_tokens + reasoning_tokens` of any M3 call: **623** (sentiment, the
15-headline case). Per M3-FR-23, `llm_output_allowance_tokens` is lowered to 3x that figure:
3 x 623 = **1869** (`bullpit/config.py`, `.env.example`; was 2000, M2's untuned default).

Sentiment costs 3-4x a single-fact analyst call (technical/fundamentals stay near the M2 probe's
~320-token baseline; sentiment scales with headline count, up to 15). All three stay far under
the 8K TPM per-call ceiling even before this tuning, so the change is about tighter per-minute
pacing (M2's carry-over: the bucket charges the full allowance per call), not correctness.

Confirmation re-run after lowering the default: `bullpit request MSFT --mode backtest --as-of
2024-10-18` against the real services -- no `[FLAGGED]` tag on any of the three signals.

## Retrospective

*(written at T-18)*
