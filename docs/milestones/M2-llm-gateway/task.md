# M2 — LLM gateway + journal bootstrap: tasks

| | |
|---|---|
| **Status** | T-1 to T-11a done; T-12 (acceptance) awaiting the owner |
| **Date** | 2026-09-28 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (approved 2026-09-28; pre-development corrections in its §7.1) |
| **Branch** | `m2-llm-gateway`, from `master` |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. After every task: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` are clean, and the diff has been re-read for anything the task doesn't need.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | M2-T-1 | **Docs.** Create `m2-llm-gateway` from `master`; commit `specs-plan.md`, this file, and ADR-0004 with status `Proposed` | `docs/milestones/M2-llm-gateway/*`, `docs/adr/0004-llm-response-cache-storage.md` | §16 | Branch exists; docs committed | `0d72b71` |
| [x] | M2-T-2 | **Dependencies, settings, errors.** `uv add sqlalchemy alembic jinja2` (not `langfuse`, D-M2-9); the 14 settings in specs-plan §5.1 in `config.py` and `.env.example`; `PromptTooLarge` and `LLMUnavailable` in `errors.py` | `pyproject.toml`, `uv.lock`, `bullpit/config.py`, `.env.example`, `bullpit/errors.py` | §5.1, §5.5; D-M2-1, D-M2-7, D-M2-9 | `uv sync --locked` succeeds; the four checks are clean; `Settings()` shows every new default; both exceptions are `BullPitError` subclasses | `c3695eb` |
| [x] | M2-T-3 | **Journal bootstrap.** `journal/db.py` (`make_engine`, `make_sessions`, `journal_url`; WAL and foreign-keys pragmas); `journal/models.py` (`Base`, `Request`, `LLMCall`, with the `(model, created_at)` index); `alembic.ini`, `migrations/env.py`, `script.py.mako`, revision `0001_requests_llm_calls`; mypy exclude for `bullpit/journal/migrations/` | `bullpit/journal/db.py`, `bullpit/journal/models.py`, `bullpit/journal/migrations/**`, `alembic.ini`, `pyproject.toml`, `tests/journal/__init__.py`, `tests/journal/test_db.py` | FR-12, FR-13; §9.5, §10; D-M2-5 | `test_db.py` passes (insert and read back one `Request` and one `LLMCall` in memory); `uv run alembic upgrade head` creates both tables in a temp DB (full schema comparison in T-12) | `c982711` |
| [x] | M2-T-4 | **Schemas and the measurement prompt.** `llm/schemas.py` (`Evidence`, `Signal`); `llm/prompts/measurement_probe.md` (compact technical-analyst-shaped prompt asking for `direction` and `confidence` as JSON) | `bullpit/llm/schemas.py`, `bullpit/llm/prompts/measurement_probe.md` | FR-3 (template file); §5.3 | The four checks are clean; the template renders with `StrictUndefined` from a Python shell | `62b56d1` |
| [x] | M2-T-5 | **Fake provider.** Implements `CompletionFn`: a queue of `CompletionReply`s or exceptions (`RateLimited`, `ProviderTransient`) returned in order; records every `CompletionRequest`; fails loudly if called more times than scripted | `tests/llm/__init__.py`, `tests/llm/fake_provider.py` | FR-15; D-M2-6 | ruff and mypy clean; exercised by T-6's tests (no test of its own) | `c790e0e` |
| [x] | M2-T-6 | **Gateway core.** In `gateway.py`: `Role`, `LLMResult`, `CompletionRequest`/`CompletionReply`/`CompletionFn`, `RateLimited`/`ProviderTransient`, `litellm_completion` (JSON mode, Groq key, usage mapping, exception mapping); `call_llm` steps 1, 2, 6 (single attempt for now), 7 and 8 (`llm_calls` row only, in its own transaction) from specs-plan §9.2; `max_tokens` = allowance; `created_at` from `clock.utc_now()` | `bullpit/llm/gateway.py`, `tests/conftest.py` (journal fixture), `tests/llm/test_gateway.py` | FR-1, 2, 3, 4, 4a, 10, 11, 11a; D-M2-2, D-M2-8; AC-1, AC-4, AC-8 | Tests for AC-1 (routing, effort, `max_tokens`), AC-4 (retry with error, fallback flagged, tokens summed, empty content counts as invalid) and AC-8 (`PromptTooLarge`, provider never called) pass | `8238552` |
| [x] | M2-T-7 | **Response cache.** Step 3 and the cache write in step 8: key includes `reasoning_effort`; file under `data_cache_dir / "llm"`, atomic write; valid replies only; a stored reply that fails validation counts as a miss | `bullpit/llm/gateway.py`, `tests/llm/test_gateway.py` | FR-5, FR-6; D-M2-4; AC-2 | AC-2 tests pass (hit: 0 tokens, `cache_hit` row, provider called once; new seed: provider called again); the flagged-fallback test confirms nothing was cached | `8238552` |
| [x] | M2-T-8 | **Backoff and token bucket.** Step 6's retry loop (specs-plan §11.3) with the injected `sleep`; persistent `RateLimited` → `QuotaExhausted`, persistent `ProviderTransient` → `LLMUnavailable`; step 5's per-model RPM/TPM bucket (`time.monotonic`), plus a fixture that resets the buckets between tests | `bullpit/llm/gateway.py`, `tests/conftest.py`, `tests/llm/test_gateway.py` | FR-7, FR-8; AC-3 | AC-3 tests pass: two 429s then success give two recorded waits, the second longer; 429 on every attempt raises `QuotaExhausted`; no real sleeping (suite time unchanged) | `8238552` |
| [x] | M2-T-9 | **Daily budget.** Step 4: rolling-24-hour sum over non-cache-hit `llm_calls` rows for the model (specs-plan §11.2), `QuotaExhausted` before any call; a cache hit is still served over budget | `bullpit/llm/gateway.py`, `tests/llm/test_gateway.py` | FR-9; D-M2-3; AC-5, AC-6 | AC-6 tests pass (seeded rows at now: `QuotaExhausted`, provider never called; the same rows 25 h old: call goes through); AC-5 test passes (hit, success and flagged fallback each write exactly one row) | `8238552` |
| [x] | M2-T-10 | **Langfuse toggle.** Register LiteLLM's Langfuse callback once, on the first `call_llm`, only when `langfuse_enabled`; pass host and keys from `Settings`; `ConfigError` for a missing key or package | `bullpit/llm/gateway.py` | FR-14; D7 | Manual check below: defaults leave `litellm.success_callback` empty; enabled without keys raises `ConfigError` naming the variable | `8238552` |
| [x] | M2-T-11 | **Measurement run.** `scripts/spikes/measure_tokens.py` (specs-plan §9.6); run once against real Groq, both pinned models | `scripts/spikes/measure_tokens.py`, this file (evidence) | FR-16; D-M2-10; AC-7 | Output pasted below; neither call flagged; both real totals below `llm_tpm_limit` | `4c685dc` |
| [x] | M2-T-11a | **Pre-acceptance review fixes.** Groq's `json_validate_failed` rejection handled as an invalid reply (worst-case charge; no empty assistant turn on retry); 500/502/503 → `ProviderTransient`, any other provider error → `LLMUnavailable`; `llm_timeout_seconds` setting passed on every call; Langfuse keys checked before the package, naming exactly what's missing; `measure_tokens.py` uses `journal_url` | `bullpit/llm/gateway.py`, `bullpit/config.py`, `.env.example`, `bullpit/errors.py`, `tests/llm/test_gateway.py`, `scripts/spikes/measure_tokens.py`, `specs-plan.md` §7.2 | specs-plan §7.2 R11–R14; §12; architecture Part 3, Part 8 | Adapter and every-attempt tests pass; a Groq-rejected generation returns the flagged safe default through the real gateway; AC-7 re-run unchanged; Langfuse manual check shows the missing variable | `d9a7cdc` |
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
| M0 finding C4 | T-6 (behaviour), T-11a (Groq's JSON-mode rejection), T-12 (marked answered) |
| specs-plan §7.2 R11–R14 | T-11a |

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

Re-run after the T-11a fix (keys are now checked before the package):

| Case | Result |
|---|---|
| Defaults | `litellm.success_callback == []`; `langfuse` never imported |
| Enabled, no keys | `ConfigError: LANGFUSE_ENABLED is true but these are not set: LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY` |
| Enabled, secret key missing | `ConfigError: LANGFUSE_ENABLED is true but these are not set: LANGFUSE_SECRET_KEY` |
| Enabled, keys set, package not installed | `ConfigError: … the \`langfuse\` package isn't installed (it's not a project dependency, D-M2-9). Run \`uv add langfuse\` to enable tracing.` |

No callback was registered in any case.

### M2-T-11: token measurement (AC-7)

`uv run python scripts/spikes/measure_tokens.py`, one representative analyst-sized
prompt (`measurement_probe.md`, the technical-analyst-shaped probe from T-4) against
both pinned models, real Groq calls, journal and cache in a throwaway temp dir:

```
=== small: openai/gpt-oss-20b ===
  input=241 output=21 reasoning=59 total=321 latency_ms=687 flagged=False

=== large: openai/gpt-oss-120b ===
  input=241 output=21 reasoning=55 total=317 latency_ms=483 flagged=False

Done. Both calls within llm_tpm_limit and not flagged.
```

Neither call flagged; both real totals (321, 317) are far below `llm_tpm_limit` (8000).
Reasoning (55-59 tokens) is 4-6 times M0's figure at `low` effort (A4: 9-16 tokens), which
used a one-line prompt; this prompt carries an indicator table and a decision to make.
`llm_output_allowance_tokens` (2000) still leaves wide headroom past real reasoning plus
visible output on both models. Re-run after the T-11a fixes: identical token counts
(latency 1156 / 1046 ms), exit 0.

### M2-T-11a: pre-acceptance review fixes

**Groq's JSON-mode failure behaviour** (throwaway probe, two real calls on the small
model with `response_format={"type": "json_object"}`): a reply cut off by
`max_tokens=40`, and a prompt asking for plain-text output, both came back as
`litellm.BadRequestError` (400) with code `json_validate_failed`
(`"Failed to generate JSON… 'failed_generation': 'max completion tokens reached before
generating a valid document'"`). Groq never returns the malformed text as content, so
before this fix the validation retry and safe default could never run for bad JSON.

**The rejected path through the real gateway** (throwaway script,
`llm_output_allowance_tokens` forced to 30 so reasoning overruns the cap):

```
value: direction='neutral' confidence=0.0 flagged: True cache_hit: False
tokens charged: input 247 output 60
llm_calls rows: 1 flagged: [True]
cache files written: 0
```

Both attempts were rejected by Groq; `call_llm` returned the safe default, flagged,
wrote exactly one row charged at the worst case (2 × the 30-token cap), and cached
nothing. Before the fix this call raised a raw `BadRequestError`.

**Tests:** `test_provider_errors_are_mapped` (503 → `ProviderTransient`; bad key and bad
request → `LLMUnavailable`), `test_json_rejected_by_provider_is_an_empty_reply_charged_worst_case`
(also checks the timeout is sent) and the `ProviderTransient` case of
`test_failure_on_every_attempt_raises_after_retries` all pass. All four checks are clean;
the suite is 86 tests.

### M2-T-12: Alembic schema check

`JOURNAL_DB_PATH` pointed at a temp file, `uv run alembic upgrade head` ran clean
(`Running upgrade  -> 0001, requests_llm_calls`). The resulting SQLite schema
(inspected via `sqlite_master`) matches `journal/models.py` exactly:

- `llm_calls`: 13 columns (`id` PK autoincrement, `request_id`, `role`, `model`,
  `prompt_version`, `cache_hit`, `cache_key`, `input_tokens`, `output_tokens`,
  `reasoning_tokens`, `latency_ms`, `flagged`, `created_at`), indexes
  `ix_llm_calls_model_created_at` (`model`, `created_at`) and
  `ix_llm_calls_request_id` (`request_id`).
- `requests`: 4 columns (`id` PK, `mode`, `as_of`, `created_at`), no extra index.

No drift between the migration and the declarative models.

## Retrospective

**Delivered:** one controlled door for every LLM call (`call_llm`), with role
routing, a per-call size ceiling, a file-backed response cache (ADR-0004),
exponential backoff with jitter, a per-model in-memory RPM/TPM bucket, a
rolling-24-hour daily budget backed by the journal, JSON-mode structured
output with one validation retry and a flagged safe-default fallback, and an
optional Langfuse toggle. The journal (`journal.db`, SQLAlchemy 2.0 models,
Alembic) is bootstrapped with `requests` (minimal) and `llm_calls`. All 8 ACs
pass: AC-1 to AC-6 and AC-8 by `tests/llm/test_gateway.py` (16 tests, run in
under half a second, no network), AC-7 by the real measurement run above.

**AC-7 numbers vs. architecture §14:** the measurement probe (a compact,
analyst-shaped prompt asking for `direction`/`confidence`) cost 321 total
tokens on the small model (241 input, 21 output, 59 reasoning) and 317 on the
large model (241 input, 21 output, 55 reasoning) — both at `low` reasoning
effort (D-M2-7). That's far under the 8K TPM ceiling per model and a small
slice of architecture §14's ~25-30K-token full-request estimate; reasoning
cost (55-59 tokens) is modest next to the 2000-token `llm_output_allowance_tokens`,
confirming M0 finding A4/C4's low-effort choice leaves ample headroom. Real
per-call cost is well inside architecture §14's per-request budget, so the
5-8 live requests/day and short-backtest-window guidance there still holds;
M3-M5's own per-agent measurements (dev-plan C14) will refine it further once
real prompts exist.

**What changed from the original plan:** the pre-development review
(specs-plan §7.1, R1-R10) caught real bugs before any code was written — the
wrong clock for the daily budget and backoff sleep (R1), an unanswered M0
finding (R2), unnamed constants (R3), an under-counted validation retry
(R4), a caller-rollback risk to spent-token accounting (R5), a cache key
blind to `reasoning_effort` (R6), unspecified error mapping (R7), a
duplicated cache-root setting (R8), an unjustified Langfuse dependency with
eager registration (R9), and a few file-location slips (R10). Implementation
found one more: `tempfile.TemporaryDirectory()` cleanup failed on Windows
because SQLite kept the journal file's handle open after the measurement
script finished; fixed with an explicit `engine.dispose()` before the temp
directory is removed.

The pre-acceptance review (specs-plan §7.2, R11-R14, task T-11a) found the
most important bug of the milestone: in JSON mode Groq rejects a bad
generation server-side (`json_validate_failed`) rather than returning it, so
the validation-retry-and-safe-default path could never run for malformed
JSON, and the raw LiteLLM error would have crashed an analyst request. The
fake provider couldn't expose this, because it returns invalid content
directly, which the real provider never does. The lesson for later
milestones is to exercise failure paths against the real provider once, not
only the happy path. The same review mapped the remaining LiteLLM errors
(nothing now escapes the adapter), added a per-call timeout (LiteLLM's
default was 6000 s), and fixed the Langfuse check order.

**Nothing else deviated from `specs-plan.md`.** No scope was added or cut.

**Carry-overs:**

- *Pacing is conservative.* The per-minute bucket counts each call's full
  estimate, including the 2000-token output allowance, so each model gets at
  most 2-3 calls a minute even though a real call used about 320 tokens. This
  matches the spec and architecture §14 ("a request takes a few minutes").
  M3 should revisit the allowance once real agent prompts are measured (C14).
- *A small budget under-count remains.* If the first reply is invalid and the
  validation retry then runs out of retries (`QuotaExhausted` or
  `LLMUnavailable`), the first attempt's tokens aren't logged. This needs an
  invalid reply followed by six provider failures in a row, and Groq's own 429
  still stops us, so it's accepted as is.
- *Flagged rows from a Groq rejection show `output_tokens` equal to the cap.*
  That's the worst-case charge, not tokens the model actually produced.
