# M1 — Data layer, date guard, cache, calendar: tasks

| | |
|---|---|
| **Status** | Draft, waiting for owner approval. Implementation starts after M0 is accepted and merged (dev-plan §1.4) |
| **Date** | 2026-09-28 |
| **Specs and plan** | [`specs.md`](specs.md) (approved 2026-09-28), [`plan.md`](plan.md) |
| **Branch** | `m1-data-layer`, from `master` after M0's merge |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. After every task: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` are clean, and the diff has been re-read for anything the task doesn't need.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | M1-T-1 | **Docs.** Commit `specs.md`, `plan.md`, this file and ADR-0003 on the new branch | `docs/milestones/M1-data-layer/*`, `docs/adr/0003-point-in-time-prices.md` | — | Branch exists; docs committed | already committed pre-branch: `e4f0aeb` (m0-foundations); branch cut from there |
| [x] | M1-T-2 | **Dependencies and settings.** `uv add pandas pyarrow pandas-market-calendars`; `uv add --dev hypothesis pandas-stubs`; mypy override for `pandas_market_calendars`; ruff `TID251` exemption for `bullpit/clock.py` only; the three settings in `config.py` and `.env.example` | `pyproject.toml`, `uv.lock`, `bullpit/config.py`, `.env.example` | FR-17, plan §6 | `uv sync --locked` succeeds; the four checks are clean; `Settings()` shows the three defaults | `434857e` |
| [x] | M1-T-3 | **Calendar and clock.** `data/calendar.py` and `clock.py` (plan §3.1–3.2) | `bullpit/data/calendar.py`, `bullpit/clock.py`, `tests/data/__init__.py`, `tests/data/test_calendar.py` | FR-1–3, AC-6 | `test_known_dates` passes; a scratch `date.today()` in `bullpit/data/` still fails ruff (then deleted) | `2e4ecee` |
| [x] | M1-T-4 | **Guard and cache.** `drop_after`, `CacheEntry`, `load`/`save` (atomic), `complete_through`, `missing_ranges`, `read_through`; `settings` fixture in `conftest.py` | `bullpit/data/guard.py`, `bullpit/data/cache.py`, `tests/conftest.py`, `tests/data/test_guard.py` | FR-5–7, FR-15–16, AC-2 (unit half) | `test_drop_after` passes (later row dropped and logged; `NaT` raises `LookaheadViolation`) | `ed5c14d` |
| [x] | M1-T-5 | **Record fixtures.** Throwaway script in the session scratchpad (not committed) saves the files in plan §8; the hand-built `sec/restated.json` | `tests/fixtures/**` | AC-3, AC-9, AC-10 | Files present, under about 300 KB in total; gitleaks passes; no SEC email or account ID in them (searched); the recording commands and date are pasted below | `98ab195` |
| [x] | M1-T-6 | **Prices and market context.** `prices.py` (plan §3.5); `DataClients` gains the corporate-actions client | `bullpit/data/prices.py`, `bullpit/broker/clients.py`, `tests/data/test_prices.py` | FR-8–10, AC-9, AC-10 | `test_point_in_time_split` and `test_prices_and_market_context` pass | `828d91b` |
| [x] | M1-T-7 | **SEC.** `sec.py` (plan §3.6); `sec_user_agent` moved from `doctor.py`, with the version from `bullpit.__version__` | `bullpit/data/sec.py`, `bullpit/doctor.py`, `tests/data/test_sec.py` | FR-11–13, AC-3, AC-10 | `test_point_in_time_facts` and `test_parses_recorded_companyfacts` pass; `uv run bullpit doctor` still all OK | `06d8056` |
| [x] | M1-T-8 | **News.** `news.py` (plan §3.7) | `bullpit/data/news.py`, `tests/data/test_news.py` | FR-14, AC-10 | `test_parses_recorded_news` passes | `e1d8b5b` |
| [x] | M1-T-9 | **Leak tests across tools.** Leaky fakes for all three tools; the fixed-date test and the hypothesis property test; the cache-file injection test | `tests/data/test_guard.py` | AC-1, AC-2 | All four guard tests pass; the whole suite still runs in under about a minute | `d0f8caa` |
| [x] | M1-T-10 | **Manual checks against real services.** AC-4, AC-5, AC-7, AC-11 as in plan §9; mark M0 findings C2 and C3 answered (pointing to FR-14 and ADR-0003) | `docs/milestones/M0-foundations/findings.md`, this file | AC-4, 5, 7, 11 | Outputs pasted below; every check as expected | pending |
| [ ] | M1-T-11 | **Acceptance and retrospective.** Push; CI green (AC-8); walk through AC-1 to AC-11 with the evidence; write the retrospective; after owner acceptance, merge to `master` and tag `m1` | this file | DoD §1.5, AC-8 | Owner accepts | — |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-9 |
| AC-2 | T-4, T-9 |
| AC-3 | T-5, T-7 |
| AC-4 | T-4, T-10 |
| AC-5 | T-6, T-10 |
| AC-6 | T-3 |
| AC-7 | T-7, T-10 |
| AC-8 | T-2, T-11 |
| AC-9 | T-5, T-6 |
| AC-10 | T-5, T-6, T-7, T-8 |
| AC-11 | T-10 |

---

## Evidence

### M1-T-5: fixture recording

Recorded 2026-09-28 with a throwaway script in the session scratchpad
(`record_fixtures.py`, not committed), run as:

```
uv run python <scratchpad>/record_fixtures.py
```

Output:

```
AAPL yfinance: 85 bars, 5 splits
NVDA yfinance: 19 bars, 6 splits
SPY yfinance: 22 bars, 0 splits
^VIX yfinance: 22 bars, 0 splits
NVDA alpaca: 19 bars, 1 splits
sec company_tickers: 3 tickers kept
sec companyfacts: 198 facts kept
news: 58 articles
done
```

Total fixture size: 198 KB. Searched for the configured SEC contact
email and Alpaca/Groq key values in `tests/fixtures/`: no matches.
`pre-commit`'s `gitleaks` hook ran clean on commit `98ab195`.

### M1-T-10: manual checks against the real services (2026-09-28)

**AC-4** — `get_prices("AAPL", as_of, 30, ...)` called twice for the same `as_of`:

```
cache_miss  dataset=prices ranges=[('2026-08-14', '2026-09-25')] symbol=AAPL
price_source  as_of=2026-09-25 source=yfinance symbol=AAPL
cache_hit   dataset=prices start=2026-08-14 as_of=2026-09-25 symbol=AAPL
price_source  as_of=2026-09-25 source=yfinance symbol=AAPL
```

No fetch (no yfinance/Alpaca call) on the second call; `h1.bars.equals(h2.bars)` is `True`.

**AC-5** — yfinance forced to fail (`_download_yfinance` patched to raise):

```
--- normal yfinance run ---
source: yfinance
2026-09-25 close: 341.070007
--- forced yfinance failure (expect alpaca) ---
source: alpaca
2026-09-25 close: 341.07
max abs diff over the 10-session window: 1.34e-05
```

`source == "alpaca"` after the forced failure; closes match the
yfinance run to within 0.01 (well under).

**AC-7** — `get_sec_facts` for AAPL, MSFT, SPY with a cold cache
(`sec_max_requests_per_second` = 10.0):

```
configured User-Agent: BullPit/0.1.0 <configured SEC_CONTACT_EMAIL>

sec_request  url=https://www.sec.gov/files/company_tickers.json        16:27:41.428
sec_request  url=.../companyfacts/CIK0000320193.json (AAPL)            16:27:43.569  (+2.14s)
sec_request  url=.../companyfacts/CIK0000789019.json (MSFT)            16:27:46.609  (+3.04s)
sec_request  url=.../companyfacts/CIK0000884394.json (SPY)             16:27:49.428  (+2.82s)

AAPL OK 12452 facts
MSFT OK 16498 facts
SPY  FAIL 404 (no companyfacts for an ETF, as expected — FR-12)
```

Every gap is several seconds, well over the required 0.1 s minimum at
10 requests/second; every request carries the configured User-Agent.

**AC-11** — AAPL at the latest session and at 2024-07-12; SPY/VIX;
`get_sec_facts` for SPY and an unknown ticker; an AAPL news week with
more than 50 articles:

```
=== prices: AAPL at latest session 2026-09-25 ===
yfinance, 5 bars, last close 341.07

=== prices: AAPL at 2024-07-12 ===
yfinance, 5 bars, last close 230.54

=== market context: SPY / VIX at latest session ===
SPY yfinance 5 bars
VIX yfinance 5 bars

=== sec facts: SPY (ETF) ===
OK raised: SEC request failed for .../CIK0000884394.json: 404

=== sec facts: unknown ticker ===
OK raised: No SEC filings found for this ticker. Try a US company stock.

=== news: AAPL 2024-07-01..2024-07-08 ===
count: 59  (all pages read automatically, M1-FR-14)
first: 2024-07-02T01:39:54Z
last:  2024-07-08T18:50:11Z
```

Every check as expected. M0 findings C2 and C3 marked answered in
`docs/milestones/M0-foundations/findings.md`.

## Retrospective

*(written at acceptance)*
