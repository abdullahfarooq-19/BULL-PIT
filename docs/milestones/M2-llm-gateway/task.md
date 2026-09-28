# M2 — LLM gateway + journal bootstrap: tasks

| | |
|---|---|
| **Status** | T-1 to T-3 done |
| **Date** | 2026-09-28 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (approved 2026-09-28; pre-development corrections in its §7.1) |
| **Branch** | `m2-llm-gateway`, from `master` |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. After every task: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` are clean, and the diff has been re-read for anything the task doesn't need.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | M2-T-1 | **Docs.** Create `m2-llm-gateway` from `master`; commit `specs-plan.md`, this file, and ADR-0004 with status `Proposed` | `docs/milestones/M2-llm-gateway/*`, `docs/adr/0004-llm-response-cache-storage.md` | §16 | Branch exists; docs committed | `0d72b71` |
| [x] | M2-T-2 | **Dependencies, settings, errors.** `uv add sqlalchemy alembic jinja2` (not `langfuse`, D-M2-9); the 14 settings in specs-plan §5.1 in `config.py` and `.env.example`; `PromptTooLarge` and `LLMUnavailable` in `errors.py` | `pyproject.toml`, `uv.lock`, `bullpit/config.py`, `.env.example`, `bullpit/errors.py` | §5.1, §5.5; D-M2-1, D-M2-7, D-M2-9 | `uv sync --locked` succeeds; the four checks are clean; `Settings()` shows every new default; both exceptions are `BullPitError` subclasses | pending |
| [x] | M2-T-3 | **Journal bootstrap.** `journal/db.py` (`make_engine`, `make_sessions`, `journal_url`; WAL and foreign-keys pragmas); `journal/models.py` (`Base`, `Request`, `LLMCall`, with the `(model, created_at)` index); `alembic.ini`, `migrations/env.py`, `script.py.mako`, revision `0001_requests_llm_calls`; mypy exclude for `bullpit/journal/migrations/` | `bullpit/journal/db.py`, `bullpit/journal/models.py`, `bullpit/journal/migrations/**`, `alembic.ini`, `pyproject.toml`, `tests/journal/__init__.py`, `tests/journal/test_db.py` | FR-12, FR-13; §9.5, §10; D-M2-5 | `test_db.py` passes (insert and read back one `Request` and one `LLMCall` in memory); `uv run alembic upgrade head` creates both tables in a temp DB (full schema comparison in T-12) | pending |
| [ ] | M2-T-4 | **Schemas and the measurement prompt.** `llm/schemas.py` (`Evidence`, `Signal`); `llm/prompts/measurement_probe.md` (compact technical-analyst-shaped prompt asking for `direction` and `confidence` as JSON) | `bullpit/llm/schemas.py`, `bullpit/llm/prompts/measurement_probe.md` | FR-3 (template file); §5.3 | The four checks are clean; the template renders with `StrictUndefined` from a Python shell | pending |
| [ ] | M2-T-5 | **Fake provider.** Implements `CompletionFn`: a queue of `CompletionReply`s or exceptions (`RateLimited`, `ProviderTransient`) returned in order; records every `CompletionRequest`; fails loudly if called more times than scripted | `tests/llm/__init__.py`, `tests/llm/fake_provider.py` | FR-15; D-M2-6 | ruff and mypy clean; exercised by T-6's tests (no test of its own) | pending |
| [ ] | M2-T-6 | **Gateway core.** In `gateway.py`: `Role`, `LLMResult`, `CompletionRequest`/`CompletionReply`/`CompletionFn`, `RateLimited`/`ProviderTransient`, `litellm_completion` (JSON mode, Groq key, usage mapping, exception mapping); `call_llm` steps 1, 2, 6 (single attempt for now), 7 and 8 (`llm_calls` row only, in its own transaction) from specs-plan §9.2; `max_tokens` = allowance; `created_at` from `clock.utc_now()` | `bullpit/llm/gateway.py`, `tests/conftest.py` (journal fixture), `tests/llm/test_gateway.py` | FR-1, 2, 3, 4, 4a, 10, 11, 11a; D-M2-2, D-M2-8; AC-1, AC-4, AC-8 | Tests for AC-1 (routing, effort, `max_tokens`), AC-4 (retry with error, fallback flagged, tokens summed, empty content counts as invalid) and AC-8 (`PromptTooLarge`, provider never called) pass | pending |
| [ ] | M2-T-7 | **Response cache.** Step 3 and the cache write in step 8: key includes `reasoning_effort`; file under `data_cache_dir / "llm"`, atomic write; valid replies only; a stored reply that fails validation counts as a miss | `bullpit/llm/gateway.py`, `tests/llm/test_gateway.py` | FR-5, FR-6; D-M2-4; AC-2 | AC-2 tests pass (hit: 0 tokens, `cache_hit` row, provider called once; new seed: provider called again); the flagged-fallback test confirms nothing was cached | pending |
| [ ] | M2-T-8 | **Backoff and token bucket.** Step 6's retry loop (specs-plan §11.3) with the injected `sleep`; persistent `RateLimited` → `QuotaExhausted`, persistent `ProviderTransient` → `LLMUnavailable`; step 5's per-model RPM/TPM bucket (`time.monotonic`), plus a fixture that resets the buckets between tests | `bullpit/llm/gateway.py`, `tests/conftest.py`, `tests/llm/test_gateway.py` | FR-7, FR-8; AC-3 | AC-3 tests pass: two 429s then success give two recorded waits, the second longer; 429 on every attempt raises `QuotaExhausted`; no real sleeping (suite time unchanged) | pending |
| [ ] | M2-T-9 | **Daily budget.** Step 4: rolling-24-hour sum over non-cache-hit `llm_calls` rows for the model (specs-plan §11.2), `QuotaExhausted` before any call; a cache hit is still served over budget | `bullpit/llm/gateway.py`, `tests/llm/test_gateway.py` | FR-9; D-M2-3; AC-5, AC-6 | AC-6 tests pass (seeded rows at now: `QuotaExhausted`, provider never called; the same rows 25 h old: call goes through); AC-5 test passes (hit, success and flagged fallback each write exactly one row) | pending |
| [ ] | M2-T-10 | **Langfuse toggle.** Register LiteLLM's Langfuse callback once, on the first `call_llm`, only when `langfuse_enabled`; pass host and keys from `Settings`; `ConfigError` for a missing key or package | `bullpit/llm/gateway.py` | FR-14; D7 | Manual check below: defaults leave `litellm.success_callback` empty; enabled without keys raises `ConfigError` naming the variable | pending |
| [ ] | M2-T-11 | **Measurement run.** `scripts/spikes/measure_tokens.py` (specs-plan §9.6); run once against real Groq, both pinned models | `scripts/spikes/measure_tokens.py`, this file (evidence) | FR-16; D-M2-10; AC-7 | Output pasted below; neither call flagged; both real totals below `llm_tpm_limit` | pending |
| [ ] | M2-T-12 | **Acceptance.** Alembic schema check against `models.py`; ADR-0004 → `Accepted`; README quick start gains `uv run alembic upgrade head`; M0 finding C4 marked answered (pointing to M2-FR-4a); retrospective with the AC-7 numbers compared to architecture §14; then, when the owner asks: push, CI green, merge to `master`, tag `m2` | `docs/adr/0004-llm-response-cache-storage.md`, `README.md`, `docs/milestones/M0-foundations/findings.md`, this file | DoD §1.5; AC-7 | Owner accepts | pending |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-6 |
| AC-2 | T-7 |
| AC-3 | T-8 |
| AC-4 | T-6 |
| AC-5 | T-9 (after T-6 and T-7 add the success, fallback and hit branches) |
| AC-6 | T-9 |
| AC-7 | T-11, T-12 |
| AC-8 | T-6 |

| Requirement | Task |
|---|---|
| FR-1, 2, 3, 4, 4a, 10, 11, 11a | T-6 |
| FR-5, 6 | T-7 |
| FR-7, 8 | T-8 |
| FR-9 | T-9 |
| FR-12, 13 | T-3 |
| FR-14 | T-10 |
| FR-15 | T-5 |
| FR-16 | T-11 |
| §5.1 settings, §5.5 errors | T-2 |
| §5.3 schemas | T-4 |
| D-M2-1, 7, 9 | T-2 |
| D-M2-2, 8 | T-6 |
| D-M2-3 | T-9 |
| D-M2-4 | T-7 |
| D-M2-5 | T-3 |
| D-M2-6 | T-5 |
| D-M2-10 | T-11 |
| M0 finding C4 | T-6 (behaviour), T-12 (marked answered) |

---

## Evidence

*(filled in as tasks complete)*

### M2-T-3: Alembic smoke run

`JOURNAL_DB_PATH` pointed at a temp file, `uv run alembic upgrade head` ran clean
(`Running upgrade  -> 0001, requests_llm_calls`), and the resulting SQLite schema
matches `journal/models.py` exactly: `llm_calls` (13 columns, PK `id`, indexes
`ix_llm_calls_model_created_at` and `ix_llm_calls_request_id`) and `requests`
(4 columns, PK `id`). `tests/journal/test_db.py` passes against an in-memory engine.

### M2-T-10: Langfuse off by default

*(pending)*

### M2-T-11: token measurement (AC-7)

*(pending)*

### M2-T-12: Alembic schema check

*(pending)*

## Retrospective

*(written at acceptance)*
