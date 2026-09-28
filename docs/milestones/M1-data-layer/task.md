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
| [ ] | M1-T-1 | **Docs.** Commit `specs.md`, `plan.md`, this file and ADR-0003 on the new branch | `docs/milestones/M1-data-layer/*`, `docs/adr/0003-point-in-time-prices.md` | — | Branch exists; docs committed | — |
| [ ] | M1-T-2 | **Dependencies and settings.** `uv add pandas pyarrow pandas-market-calendars`; `uv add --dev hypothesis pandas-stubs`; mypy override for `pandas_market_calendars`; ruff `TID251` exemption for `bullpit/clock.py` only; the three settings in `config.py` and `.env.example` | `pyproject.toml`, `uv.lock`, `bullpit/config.py`, `.env.example` | FR-17, plan §6 | `uv sync --locked` succeeds; the four checks are clean; `Settings()` shows the three defaults | — |
| [ ] | M1-T-3 | **Calendar and clock.** `data/calendar.py` and `clock.py` (plan §3.1–3.2) | `bullpit/data/calendar.py`, `bullpit/clock.py`, `tests/data/__init__.py`, `tests/data/test_calendar.py` | FR-1–3, AC-6 | `test_known_dates` passes; a scratch `date.today()` in `bullpit/data/` still fails ruff (then deleted) | — |
| [ ] | M1-T-4 | **Guard and cache.** `drop_after`, `CacheEntry`, `load`/`save` (atomic), `complete_through`, `missing_ranges`, `read_through`; `settings` fixture in `conftest.py` | `bullpit/data/guard.py`, `bullpit/data/cache.py`, `tests/conftest.py`, `tests/data/test_guard.py` | FR-5–7, FR-15–16, AC-2 (unit half) | `test_drop_after` passes (later row dropped and logged; `NaT` raises `LookaheadViolation`) | — |
| [ ] | M1-T-5 | **Record fixtures.** Throwaway script in the session scratchpad (not committed) saves the files in plan §8; the hand-built `sec/restated.json` | `tests/fixtures/**` | AC-3, AC-9, AC-10 | Files present, under about 300 KB in total; gitleaks passes; no SEC email or account ID in them (searched); the recording commands and date are pasted below | — |
| [ ] | M1-T-6 | **Prices and market context.** `prices.py` (plan §3.5); `DataClients` gains the corporate-actions client | `bullpit/data/prices.py`, `bullpit/broker/clients.py`, `tests/data/test_prices.py` | FR-8–10, AC-9, AC-10 | `test_point_in_time_split` and `test_prices_and_market_context` pass | — |
| [ ] | M1-T-7 | **SEC.** `sec.py` (plan §3.6); `sec_user_agent` moved from `doctor.py`, with the version from `bullpit.__version__` | `bullpit/data/sec.py`, `bullpit/doctor.py`, `tests/data/test_sec.py` | FR-11–13, AC-3, AC-10 | `test_point_in_time_facts` and `test_parses_recorded_companyfacts` pass; `uv run bullpit doctor` still all OK | — |
| [ ] | M1-T-8 | **News.** `news.py` (plan §3.7) | `bullpit/data/news.py`, `tests/data/test_news.py` | FR-14, AC-10 | `test_parses_recorded_news` passes | — |
| [ ] | M1-T-9 | **Leak tests across tools.** Leaky fakes for all three tools; the fixed-date test and the hypothesis property test; the cache-file injection test | `tests/data/test_guard.py` | AC-1, AC-2 | All four guard tests pass; the whole suite still runs in under about a minute | — |
| [ ] | M1-T-10 | **Manual checks against real services.** AC-4, AC-5, AC-7, AC-11 as in plan §9; mark M0 findings C2 and C3 answered (pointing to FR-14 and ADR-0003) | `docs/milestones/M0-foundations/findings.md`, this file | AC-4, 5, 7, 11 | Outputs pasted below; every check as expected | — |
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

*(filled in as tasks are done)*

## Retrospective

*(written at acceptance)*
