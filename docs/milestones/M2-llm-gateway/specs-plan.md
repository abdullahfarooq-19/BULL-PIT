# M2 — LLM gateway + journal bootstrap: specs and plan

| | |
|---|---|
| **Status** | Approved by the owner on 2026-09-28. Pre-development review the same day corrected the points listed in [§7.1](#71-pre-development-review-corrections) |
| **Date** | 2026-09-28 |
| **Size** | M (specs and plan share this file, [dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents)) |
| **Branch** | `m2-llm-gateway` |
| **Depends on** | M0 (config, errors, logging), M1 (`clock.utc_now`, the one wall-clock accessor) |
| **Sources** | [dev-plan §5 M2](../../dev-plan.md#m2--llm-gateway--journal-bootstrap), [§2](../../dev-plan.md#2-engineering-standards), [§3 D3, D7](../../dev-plan.md#3-deviations-from-the-architecture-roadmap), [§7](../../dev-plan.md#7-testing-strategy), [§8](../../dev-plan.md#8-data-model-evolution), [§10.1 C14, C15](../../dev-plan.md#101-scope-review-revision-4); [architecture Part 3](../../architecture.md#part-3--llm-gateway-code), [§14](../../architecture.md#14-free-tier-budget); [M0 findings](../M0-foundations/findings.md) A1–A6, C4

Part A says **what** M2 delivers and how it's accepted. Part B says **how** it gets built. Neither restates the architecture or the dev plan; they link to them.

---

## Contents

**Part A: Specs**

1. [Goal](#1-goal)
2. [Scope](#2-scope)
3. [Functional requirements](#3-functional-requirements)
4. [Non-functional requirements](#4-non-functional-requirements)
5. [Interfaces](#5-interfaces)
6. [Acceptance criteria](#6-acceptance-criteria)
7. [Decisions made in this document](#7-decisions-made-in-this-document)
8. [Open questions for the owner](#8-open-questions-for-the-owner)

**Part B: Plan**

9. [Module design](#9-module-design)
10. [Data model](#10-data-model)
11. [Key algorithms](#11-key-algorithms)
12. [Error handling](#12-error-handling)
13. [Test and verification plan](#13-test-and-verification-plan)
14. [Work order](#14-work-order)
15. [Risks](#15-risks)
16. [ADRs](#16-adrs)

---

# Part A: Specs

## 1. Goal

One controlled door through which every LLM call in Bull Pit passes: routed to the right pinned model, cached, rate-limited, budget-tracked, and validated into typed replies. The architecture's M2 done-when: *"Routing, cache, retries, validation, token logging work; real token counts measured."*

M2 also bootstraps the journal database (D3), because token logging needs somewhere durable to write, and every later milestone's tables build on it.

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | `llm/gateway.py`: role routing, reasoning-effort setting, per-call token-size ceiling, response cache, rate limiter with backoff, daily token-budget tracker, structured-output validation with one retry and a safe default | architecture Part 3 |
| S2 | `llm/schemas.py`: the base `Evidence` and `Signal` schemas every M3+ agent schema extends | architecture Part 3, Part 5 |
| S3 | `llm/prompts/`: versioned prompt templates (content-hash version); one representative template for M2's own measurement | dev-plan M2 |
| S4 | Journal bootstrap: `journal/db.py` (SQLAlchemy engine/session), `journal/models.py` (`Request`, `LLMCall`), Alembic setup and the first migration | dev-plan D3, §8 |
| S5 | A fake completion function for tests: deterministic, scriptable replies, including invalid JSON and 429s | dev-plan M2 |
| S6 | Optional Langfuse tracing behind a setting, off by default (D7) | dev-plan D7 |
| S7 | `scripts/spikes/measure_tokens.py`: one representative analyst-sized prompt run on each pinned model, real tokens (including reasoning) recorded | dev-plan M2, C14 |

### 2.2 Out of scope

- Any agent, prompt, or schema beyond the one representative measurement template (M3 onward writes the real ones and measures them again, C14).
- `requests` table beyond the minimal columns M2 needs to satisfy the foreign key from `llm_calls`; M3 fills in the rest (config snapshot, git commit, status, request lock).
- The pinned-model resume guard (moved to M6, C15).
- Any UI, API, or CLI command beyond the measurement script.

## 3. Functional requirements

**Routing and prompts**

- **M2-FR-1** `call_llm(role=Role.SMALL | Role.LARGE, ...)` sends the call to `settings.llm_small_model` or `settings.llm_large_model` respectively. The mapping is config, not a literal in the gateway.
- **M2-FR-2** Each role has its own `reasoning_effort` setting (default `"low"` for both, per M0 finding A4), passed to the provider on every call for that role.
- **M2-FR-3** A prompt template is a file in `llm/prompts/`, rendered with Jinja2 (`StrictUndefined`). Its version is the first 12 hex characters of the SHA-256 of the template file's content (before rendering), so the version changes when the template is edited, not per call.

**Per-call ceiling and output cap**

- **M2-FR-4** Before sending, the gateway estimates the call's total tokens: the rendered prompt's estimated size plus `llm_output_allowance_tokens`. If the estimate exceeds `llm_tpm_limit`, the gateway raises `PromptTooLarge` naming the prompt template, its version and the estimated size, and makes no network call.
- **M2-FR-4a** Every call sends `max_tokens = llm_output_allowance_tokens`, so reasoning plus visible output can never exceed what the ceiling check allowed for. A reply whose content is empty (reasoning used up the cap, M0 finding A5) counts as an invalid reply under M2-FR-10. This answers M0 finding C4.

**Response cache**

- **M2-FR-5** Every call is looked up first by a cache key: the SHA-256 of `(model, rendered prompt, temperature, seed, prompt_version, reasoning_effort)`. A hit returns the stored reply with zero tokens spent and is logged to `llm_calls` as a cache hit. A miss calls the provider and, on a valid reply, stores it. A hit is served even when the daily budget is used up, since it costs nothing.
- **M2-FR-6** The cache stores the *validated* reply (the Pydantic model's JSON), not the raw provider payload. A stored reply that no longer validates against the caller's model (for example after a schema change) is treated as a miss, not an error. A flagged fallback is never cached.

**Rate limiting and retries**

- **M2-FR-7** A 429, a timeout or a connection error is retried with exponential backoff and jitter: wait `llm_backoff_base_seconds × 2^attempt` plus a random jitter below `llm_backoff_base_seconds`, up to `llm_max_retries` retries. The wait goes through a `sleep` callable injected into `call_llm` (default `time.sleep`), so the automated suite never really sleeps. Any other provider error is not retried.
- **M2-FR-8** A token bucket per model enforces `llm_rpm_limit` and `llm_tpm_limit` *within this process*, so the gateway paces its own calls before Groq has to reject them.

**Daily budget**

- **M2-FR-9** After a cache miss and before sending, the gateway sums that model's non-cache-hit tokens in `llm_calls` over the **last 24 hours of real time** (from `clock.utc_now()`, never `SimClock.as_of`, since Groq's quota runs on real time even during a backtest) and adds the call's estimate. If the total would exceed `llm_daily_token_budget`, it raises `QuotaExhausted` and makes no network call. A rolling 24 hours is used because Groq's reset time isn't published; it can only over-count, never under-count.

**Structured output**

- **M2-FR-10** Every call asks the provider for JSON mode (`response_format={"type": "json_object"}`, confirmed working in M0 finding A3) and validates the reply against a caller-supplied Pydantic model in code. An invalid reply is retried exactly once, with the validation error added to the conversation. A second failure returns the caller's `safe_default` and marks the result `flagged=True`; no exception is raised, since callers (M3+) already handle a flagged neutral signal (architecture Part 8).

**Token logging**

- **M2-FR-11** Every completed `call_llm` — cache hit, success or flagged fallback — writes exactly one `LLMCall` row: role, model, prompt version, input/output/reasoning tokens (0 for a cache hit; **summed over both attempts** when the validation retry ran, so the budget never under-counts), latency, `cache_hit`, `cache_key`, `request_id`, `flagged`, `created_at` (from `clock.utc_now()`). A call refused by `PromptTooLarge` or `QuotaExhausted` writes no row, since nothing was spent.
- **M2-FR-11a** The gateway commits each `LLMCall` row in its own short transaction (it takes a `sessionmaker`, not the caller's session), so spent tokens stay recorded even when the caller's own transaction rolls back (for example M6's per-week commit after a crash).

**Journal bootstrap**

- **M2-FR-12** `journal/db.py` creates a SQLite engine at `settings.journal_db_path` (WAL mode, foreign keys on) and a session factory. Alembic is configured against the same models, with one migration that creates `requests` and `llm_calls`.
- **M2-FR-13** `journal/models.py` defines `Request` (minimal: `id`, `mode`, `as_of`, `created_at`) and `LLMCall`, as SQLAlchemy 2.0 declarative models. `LLMCall.request_id` is a plain string column with an index (not a hard foreign-key constraint yet), since M2 callers such as the measurement script have no real `Request` row to point to; M3 starts creating real ones.

**Langfuse (optional)**

- **M2-FR-14** When `settings.langfuse_enabled` is `true`, the first `call_llm` registers LiteLLM's Langfuse callback once, passing the keys and host from `Settings`. A missing key, or the `langfuse` package not being installed, raises `ConfigError` naming what's missing (the package isn't a project dependency, D-M2-9). When it's `false` (the default), no callback is registered and nothing Langfuse-related runs.

**Fake provider and measurement**

- **M2-FR-15** `tests/llm/fake_provider.py` implements the gateway's `CompletionFn` protocol (§5.2): a queue of canned `(content, usage)` replies or exceptions, consumed in order, recording every request it receives so tests can assert the model, `max_tokens` and messages sent.
- **M2-FR-16** `scripts/spikes/measure_tokens.py` runs one representative analyst-sized prompt (the `measurement_probe` template) against both pinned models through the real gateway, with a journal DB in a temporary folder, prints input/output/reasoning tokens and latency for each, and exits non-zero if either call's real total is above `llm_tpm_limit`.

## 4. Non-functional requirements

- **M2-NFR-1 (no network in tests)** The automated suite uses only the fake completion function; `pytest-socket` (already active from M0) backs this up.
- **M2-NFR-2 (speed)** The gateway's own test suite runs in a couple of seconds; no real sleeping (M2-FR-7).
- **M2-NFR-3 (quota)** `measure_tokens.py` spends at most one call per model (well under the 8K-token per-call ceiling and the 200K daily budget).
- **M2-NFR-4 (types)** `bullpit.llm` is not in mypy's strict list ([dev-plan §2.1](../../dev-plan.md#21-toolchain)); `bullpit.journal` likewise stays standard mypy, since both do I/O at the edge.
- **M2-NFR-5 (money rule doesn't apply here)** No `Decimal` values cross the gateway; `target_weight` and `confidence` stay `float` until M4/M5 validate and bound them (CLAUDE.md's rule is about *using* LLM numbers, not about this module).

## 5. Interfaces

### 5.1 Settings added in M2

| Field | Env variable | Type | Default | Notes |
|---|---|---|---|---|
| `llm_reasoning_effort_small` | `LLM_REASONING_EFFORT_SMALL` | `str` | `"low"` | Passed for every `Role.SMALL` call |
| `llm_reasoning_effort_large` | `LLM_REASONING_EFFORT_LARGE` | `str` | `"low"` | Passed for every `Role.LARGE` call |
| `llm_rpm_limit` | `LLM_RPM_LIMIT` | `int` | `30` | Per model, from architecture §14 |
| `llm_tpm_limit` | `LLM_TPM_LIMIT` | `int` | `8000` | Per model. Drives the per-call ceiling (M2-FR-4) |
| `llm_output_allowance_tokens` | `LLM_OUTPUT_ALLOWANCE_TOKENS` | `int` | `2000` | Sent as `max_tokens`; covers reasoning + visible output (M2-FR-4a, §11.1) |
| `llm_daily_token_budget` | `LLM_DAILY_TOKEN_BUDGET` | `int` | `200000` | Per model, rolling 24 h, architecture §14 |
| `llm_max_retries` | `LLM_MAX_RETRIES` | `int` | `5` | 429 / transient-error retry cap |
| `llm_backoff_base_seconds` | `LLM_BACKOFF_BASE_SECONDS` | `float` | `1.0` | First backoff wait; doubles per retry (M2-FR-7) |
| `llm_seed` | `LLM_SEED` | `int` | `1` | Default seed; callers may override per call |
| `journal_db_path` | `JOURNAL_DB_PATH` | `Path` | `journal.db` | SQLite file, relative to the working directory; git-ignored by the existing `*.db` rule |
| `langfuse_enabled` | `LANGFUSE_ENABLED` | `bool` | `false` | D7 |
| `langfuse_host` | `LANGFUSE_HOST` | `str` | `https://cloud.langfuse.com` | Only read when enabled |
| `langfuse_public_key` | `LANGFUSE_PUBLIC_KEY` | `SecretStr \| None` | `None` | Only read when enabled |
| `langfuse_secret_key` | `LANGFUSE_SECRET_KEY` | `SecretStr \| None` | `None` | Only read when enabled |

The response cache has no setting of its own: it lives at `data_cache_dir / "llm"` (§9.4), so there's one place for the cache root and the existing test fixture isolates it automatically.

### 5.2 `gateway.py`

```python
class Role(str, Enum):
    SMALL = "small"
    LARGE = "large"

@dataclass(frozen=True)
class LLMResult(Generic[T]):
    value: T
    flagged: bool
    cache_hit: bool
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    latency_ms: int

def call_llm(
    role: Role,
    template_name: str,
    variables: Mapping[str, object],
    response_model: type[T],
    *,
    safe_default: T,
    request_id: str,
    settings: Settings,
    sessions: sessionmaker[Session],
    seed: int | None = None,
    temperature: float = 0.0,
    completion_fn: CompletionFn = litellm_completion,
    sleep: Callable[[float], None] = time.sleep,
) -> LLMResult[T]:
    """Render, check ceiling, cache, budget, pace, call, validate, log.
    Never raises for an invalid reply (returns safe_default, flagged=True);
    raises PromptTooLarge or QuotaExhausted before any network call."""
```

```python
@dataclass(frozen=True)
class CompletionRequest:
    model: str
    messages: list[dict[str, str]]
    temperature: float
    seed: int
    reasoning_effort: str
    max_tokens: int

@dataclass(frozen=True)
class CompletionReply:
    content: str
    input_tokens: int
    output_tokens: int        # visible output only
    reasoning_tokens: int

class CompletionFn(Protocol):
    def __call__(self, request: CompletionRequest) -> CompletionReply: ...

class RateLimited(Exception): ...        # gateway-internal: provider returned 429
class ProviderTransient(Exception): ...  # gateway-internal: timeout or connection error
```

`litellm_completion` is the only code that touches LiteLLM: it adds JSON mode and the Groq key, calls `litellm.completion`, maps usage (reasoning tokens from `completion_tokens_details.reasoning_tokens`, defaulting to 0), and turns LiteLLM's rate-limit exception into `RateLimited` and its timeout and connection exceptions into `ProviderTransient`. `fake_provider.py` implements `CompletionFn` directly and raises the same two to simulate failures.

Neither internal exception leaves the gateway. If retries run out, a persistent `RateLimited` becomes **`QuotaExhausted`** (Groq is still refusing, most likely because its own daily quota is spent, possibly by calls outside Bull Pit; M6's runner then pauses and resumes exactly as for our own budget), and a persistent `ProviderTransient` becomes **`LLMUnavailable`**.

### 5.3 `schemas.py`

```python
class Evidence(BaseModel):
    id: str            # e.g. "T1", assigned by code, never by the LLM
    fact: str

class Signal(BaseModel):
    ticker: str
    analyst: str
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence]
```

M3's per-analyst schemas subclass or compose these; M2 defines them here because they're shared, not because M2 uses them itself.

### 5.4 Journal models (`journal/models.py`)

```python
class Base(DeclarativeBase): ...

class Request(Base):
    __tablename__ = "requests"
    id: Mapped[str] = mapped_column(primary_key=True)
    mode: Mapped[str]
    as_of: Mapped[date]
    created_at: Mapped[datetime]

class LLMCall(Base):
    __tablename__ = "llm_calls"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(index=True)
    role: Mapped[str]
    model: Mapped[str]
    prompt_version: Mapped[str]
    cache_hit: Mapped[bool]
    cache_key: Mapped[str]
    input_tokens: Mapped[int]
    output_tokens: Mapped[int]
    reasoning_tokens: Mapped[int]
    latency_ms: Mapped[int]
    flagged: Mapped[bool]
    created_at: Mapped[datetime]
```

### 5.5 Exception hierarchy addition

```text
BullPitError
├── PromptTooLarge   the estimated call size exceeds the per-minute token limit (used from M2)
└── LLMUnavailable   the provider kept timing out or refusing connections through every retry (used from M2)
```

Added to `errors.py` alongside the existing declarations ([§7](#7-decisions-made-in-this-document) D-M2-1). `QuotaExhausted` and `ValidationFailed` (declared in M0) are unchanged: `QuotaExhausted` gets its first real behaviour here; `ValidationFailed` stays unused by the gateway, because an invalid reply degrades to the safe default instead of raising (M2-FR-10).

## 6. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| **M2-AC-1** | A call with role `small` goes to the configured small model and `large` to the large one | **Automated:** `tests/llm/test_gateway.py`, through the fake provider |
| **M2-AC-2** | A repeated identical call is served from the cache with 0 tokens used and logged as a cache hit; changing the seed forces a new call | **Automated** |
| **M2-AC-3** | A 429 is retried with increasing waits and succeeds when the provider recovers | **Automated**, fake provider + recording `sleep` (two 429s, then success: two waits, the second longer) |
| **M2-AC-4** | An invalid JSON reply is retried once with the error included; a second failure returns the safe default and the reply is flagged | **Automated** |
| **M2-AC-5** | Every call, including cache hits, writes a row to `llm_calls` | **Automated** |
| **M2-AC-6** | Once the daily budget is exceeded, the next call raises `QuotaExhausted` and makes no network call | **Automated**, seeding `llm_calls` with prior usage |
| **M2-AC-7** | Real token counts (including reasoning tokens) for one representative analyst-sized prompt are measured on both pinned models and recorded in the retrospective | Manual: `scripts/spikes/measure_tokens.py` output pasted into `task.md` |
| **M2-AC-8** | A call whose estimated size is above the per-call ceiling is refused before any network call, with an error naming the prompt and its estimated size | **Automated** |

These are the dev plan's drafted M2 ACs verbatim ([dev-plan §5 M2](../../dev-plan.md#m2--llm-gateway--journal-bootstrap)); nothing added or removed.

## 7. Decisions made in this document

| # | Decision | Reason |
|---|---|---|
| D-M2-1 | Add two leaves to `errors.py`: `PromptTooLarge` and `LLMUnavailable` | M0's hierarchy has nothing meaning "this call can't fit under the per-minute ceiling" or "the provider is down". `QuotaExhausted` is reserved for the daily budget (and a persistent 429, §5.2), and reusing it would blur causes an operator needs to tell apart |
| D-M2-2 | Token estimation is a heuristic (`ceil(len(text) / 4)`) plus `llm_output_allowance_tokens`, not a real tokenizer | gpt-oss's tokenizer isn't available offline in a supported form; an estimate that errs high is safe for a ceiling check, and M2-AC-7's real measurement is what calibrates the allowance |
| D-M2-3 | The daily budget sums `llm_calls` in the database; the RPM/TPM buckets are in memory | A backtest spans several processes (resumed after `QuotaExhausted`, M6), so only a durable sum survives. Per-minute pacing only needs to hold within one process |
| D-M2-4 | The response cache stores each validated reply as one JSON file under `data_cache_dir / "llm"`, named by the cache key; `llm_calls.cache_key` records the same key | Same pattern as the data layer's file cache under `data_cache/` (already git-ignored); keeps reply bodies out of the journal DB |
| D-M2-5 | Alembic migrations live under `bullpit/journal/migrations/`, one revision per milestone that changes the schema (dev-plan §8) | Keeps each migration small and reviewable; M2 starts the pattern |
| D-M2-6 | The fake provider lives in `tests/llm/fake_provider.py`, not in the `bullpit` package | It's a test double with no production use; CLAUDE.md's "no extra files" rule is about the `bullpit/` package |
| D-M2-7 | `reasoning_effort` defaults to `"low"` for both roles | M0 finding A4: `low` used single-digit reasoning tokens against 40+ at `medium`, and A5 showed reasoning can starve visible output. Any agent that needs more can raise its role's setting |
| D-M2-8 | JSON mode (`json_object`) plus Pydantic validation in code, not the provider's strict `json_schema` mode | Architecture Part 3 already puts validation in Pydantic. Strict schema mode restricts which schema features are allowed (bounds such as `confidence` 0–1 may be rejected), which would make every agent schema depend on Groq's rules. Both modes worked in M0 (A3) |
| D-M2-9 | New dependencies: `sqlalchemy` and `alembic` (dev-plan §2.1 names both for the journal), `jinja2` (prompt templates, dev-plan M2; LiteLLM already installs it, but the gateway imports it directly so it's declared). **`langfuse` is not added**: tracing is off by default (D7), and enabling it means `uv add langfuse` once, which `ConfigError` says (M2-FR-14) | CLAUDE.md: no dependency the plan doesn't name and justify. Langfuse pulls a large dependency tree for a switched-off debugging aid |
| D-M2-10 | `scripts/spikes/measure_tokens.py`, not `scripts/measure_tokens.py` | CLAUDE.md: one-off scripts live only in `scripts/spikes/`. Later milestones measure from `llm_calls` (C14), so the script isn't reused |

### 7.1 Pre-development review corrections

The owner approved this document on 2026-09-28. A review against the existing code before development found these problems, all corrected above. None changes scope or an acceptance criterion.

| # | Problem | Correction |
|---|---|---|
| R1 | `call_llm` took M1's `Clock` for the budget day and the backoff sleep, but `Clock` only has `as_of()`. In a backtest, `SimClock.as_of` is a past date, so the daily budget would have been counted on the wrong day | Budget and `created_at` use `clock.utc_now()` (real time) over a rolling 24 h; the sleep is an injected callable (M2-FR-7, FR-9, §5.2) |
| R2 | M0 finding C4 (reasoning tokens can starve a small `max_tokens`) was raised for M2 but not answered | `max_tokens` = `llm_output_allowance_tokens` on every call; empty content counts as an invalid reply (M2-FR-4a) |
| R3 | The output allowance (2000), backoff base (1 s) and the response format were unnamed constants or unstated | Settings `llm_output_allowance_tokens`, `llm_backoff_base_seconds`; JSON mode fixed by D-M2-8 |
| R4 | A validation retry spends tokens twice, but only one row was logged, so the budget could under-count | One row with tokens summed over both attempts (M2-FR-11) |
| R5 | `call_llm` took the caller's `Session`; a caller rollback (M6's per-week commit) would erase the record of tokens really spent | The gateway commits `llm_calls` rows in its own transaction (M2-FR-11a) |
| R6 | Changing `reasoning_effort` would have returned an old cached reply | `reasoning_effort` added to the cache key (M2-FR-5) |
| R7 | What a caller sees when retries run out was unspecified | Persistent 429 → `QuotaExhausted`; persistent timeout → `LLMUnavailable` (§5.2) |
| R8 | A separate `llm_cache_dir` setting duplicated the cache root | Derived as `data_cache_dir / "llm"` (§5.1) |
| R9 | `langfuse` was to be added as a dependency without a stated reason; the callback was registered at import time | Not a dependency (D-M2-9); registered lazily on first call (M2-FR-14) |
| R10 | The measurement script was outside `scripts/spikes/`; `alembic.ini` and the mypy exclusion for migrations were missing from the file list | D-M2-10; §9.1 and §9.5 updated |

## 8. Open questions for the owner

None. Every choice needed to start work is either fixed by the architecture/dev-plan or decided above as a low-stakes call (§7).

---

# Part B: Plan

## 9. Module design

### 9.1 Files created or changed in M2

```text
alembic.ini                          script_location = bullpit/journal/migrations
pyproject.toml, uv.lock              sqlalchemy, alembic, jinja2 (D-M2-9); mypy exclude for migrations
.env.example                         the settings in §5.1
bullpit/
  config.py                          + settings from §5.1
  errors.py                          + PromptTooLarge, LLMUnavailable
  llm/
    gateway.py                       call_llm, Role, LLMResult, CompletionRequest/Reply/Fn, litellm_completion
    schemas.py                       Evidence, Signal
    prompts/
      measurement_probe.md
  journal/
    db.py                            make_engine, make_sessions (WAL + foreign-keys pragmas)
    models.py                        Base, Request, LLMCall
    migrations/
      env.py
      script.py.mako
      versions/
        0001_requests_llm_calls.py
scripts/spikes/
  measure_tokens.py
tests/
  llm/
    __init__.py
    fake_provider.py
    test_gateway.py
  journal/
    __init__.py
    test_db.py
docs/adr/0004-llm-response-cache-storage.md
docs/milestones/M2-llm-gateway/task.md
```

`bullpit/llm/__init__.py` and `bullpit/journal/__init__.py` already exist from M0.

### 9.2 `gateway.py` shape

One public entry point, `call_llm` (§5.2). Internally, in call order:

1. **Render** the named template with `variables` (Jinja2, `StrictUndefined`, so a missing variable is an error, not a silent blank) and compute its version (M2-FR-3).
2. **Ceiling check** (M2-FR-4): estimate tokens (§11.1); raise `PromptTooLarge` if above `llm_tpm_limit`.
3. **Cache lookup** (M2-FR-5, FR-6): if the key's file exists under `data_cache_dir / "llm"` and still validates as `response_model`, write a cache-hit `LLMCall` row and return.
4. **Daily budget check** (M2-FR-9, §11.2): raise `QuotaExhausted` if the estimate would push the last 24 hours over `llm_daily_token_budget`.
5. **Pace** (M2-FR-8): the model's token bucket waits, through `sleep`, until the call fits the RPM and TPM limits.
6. **Call** with backoff on `RateLimited` / `ProviderTransient` (M2-FR-7, §11.3).
7. **Validate** the content against `response_model`. On failure (including empty content, M2-FR-4a), retry once with the error added to the conversation; if that fails too, use `safe_default` and set `flagged=True`.
8. **Record**: write the cache file (valid replies only), then the `LLMCall` row in its own transaction (M2-FR-11, FR-11a).

Each step is a small private function (`_render`, `_estimate_tokens`, `_cache_path`, `_usage_last_24h`, `_TokenBucket`, `_with_backoff`, `_validate_or_retry`, `_record`), so `call_llm` reads as the list above. The token buckets live in a module-level dict keyed by model, since pacing is per process (D-M2-3); tests reset it through a fixture.

### 9.3 Time

The gateway never reads `as_of`: LLM quota runs on real time in both modes. `created_at` and the budget window come from `clock.utc_now()` (M1's single wall-clock accessor, so ruff's `TID251` ban stays clean). Token-bucket timing uses `time.monotonic()`, which isn't a calendar clock and isn't banned. Waits go through the injected `sleep`.

### 9.4 Response cache storage

Each entry is one JSON file at `data_cache_dir / "llm" / <model slug> / <cache key>.json`, holding `{"value": <validated reply>, "input_tokens": …, "output_tokens": …, "reasoning_tokens": …}` (the token counts are those of the original call, kept for reference; a hit still logs 0). Writes go to a temp file and are then renamed, the same atomic pattern as `data/cache.py`, so a crash can't leave a half-written entry.

### 9.5 Journal `db.py` and Alembic

```python
def make_engine(url: str) -> Engine:
    """create_engine(url); on connect: PRAGMA journal_mode=WAL, PRAGMA foreign_keys=ON."""

def make_sessions(engine: Engine) -> sessionmaker[Session]: ...

def journal_url(settings: Settings) -> str:
    """sqlite:///{settings.journal_db_path}"""
```

- `migrations/env.py` targets `Base.metadata` and builds its URL with `journal_url(get_settings())`, so `uv run alembic upgrade head` and the app share one schema and one path.
- Tests use `make_engine("sqlite://")` (in memory) with `Base.metadata.create_all`, skipping Alembic for speed; the migration itself is checked by hand once (§13).
- `pyproject.toml` excludes `bullpit/journal/migrations/` from mypy: Alembic's generated files are untyped boilerplate and revision files start with digits, which mypy rejects as module names. ruff still checks them.
- The app doesn't auto-migrate on startup in M2; the journal is created with `uv run alembic upgrade head` (added to the README quick start at T-12). Whether M3's CLI runs migrations itself is M3's decision.

### 9.6 Measurement script

`scripts/spikes/measure_tokens.py` loads the real `Settings`, points `journal_db_path` at a `tempfile.TemporaryDirectory()`, creates the schema with `create_all`, and calls `call_llm` once per role with `measurement_probe.md`: a compact prompt shaped like a real technical-analyst call (a small table of indicator values, an instruction to return `direction` and `confidence` as JSON), validated against a two-field model. It prints one line per role (model, input, output, reasoning, total tokens, latency, flagged) and exits non-zero if either real total is above `llm_tpm_limit`. The seed is fixed and the cache is bypassed by using the temp folder for `data_cache_dir` too, so every run is a real call.

## 10. Data model

| Table | Column | Type | Notes |
|---|---|---|---|
| `requests` | `id` | `TEXT PRIMARY KEY` | `request_id`; M3 defines the format |
| | `mode` | `TEXT` | `"live"` \| `"backtest"` |
| | `as_of` | `DATE` | |
| | `created_at` | `DATETIME` | UTC |
| `llm_calls` | `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | |
| | `request_id` | `TEXT`, indexed | Not a hard FK yet (M2-FR-13) |
| | `role` | `TEXT` | `"small"` \| `"large"` |
| | `model` | `TEXT`, indexed with `created_at` | The budget query filters on both |
| | `prompt_version` | `TEXT` | |
| | `cache_hit` | `BOOLEAN` | |
| | `cache_key` | `TEXT` | |
| | `input_tokens` | `INTEGER` | 0 on a cache hit; summed over attempts |
| | `output_tokens` | `INTEGER` | Visible output |
| | `reasoning_tokens` | `INTEGER` | |
| | `latency_ms` | `INTEGER` | 0 on a cache hit |
| | `flagged` | `BOOLEAN` | |
| | `created_at` | `DATETIME` | UTC, from `clock.utc_now()` |

This is [dev-plan §8](../../dev-plan.md#8-data-model-evolution)'s M2 row: `requests` (minimal) and `llm_calls`.

## 11. Key algorithms

### 11.1 Token estimate

```text
estimate(rendered_prompt) = ceil(len(rendered_prompt) / 4) + llm_output_allowance_tokens
```

With the defaults, a prompt can be about 6,000 estimated tokens (~24,000 characters) before `PromptTooLarge`. The 2,000 allowance is far above the ~10–50 reasoning tokens measured in M0 at `low` effort, leaving room for a real agent's JSON reply; M2-AC-7 and the per-agent measurements (C14) are what would change it.

### 11.2 Daily budget

```text
used = SELECT COALESCE(SUM(input_tokens + output_tokens + reasoning_tokens), 0)
       FROM llm_calls
       WHERE model = :model AND cache_hit = 0 AND created_at >= :now_minus_24h
if used + estimate > llm_daily_token_budget: raise QuotaExhausted(model, used, budget)
```

`:now_minus_24h` is `clock.utc_now() - 24 h`. Cache hits are excluded: they cost nothing (architecture Part 3).

### 11.3 Backoff

```text
for attempt in 0 .. llm_max_retries:
    try: return completion_fn(request)
    except (RateLimited, ProviderTransient) as exc:
        if attempt == llm_max_retries:
            raise QuotaExhausted if RateLimited else LLMUnavailable (from exc)
        sleep(base * 2**attempt + random.uniform(0, base))
```

Any other exception propagates immediately; retrying an auth or bad-request error can't help. The validation retry (step 7) is separate from this loop and happens at most once.

## 12. Error handling

- `PromptTooLarge` and `QuotaExhausted` stop before any network call. `LLMUnavailable` and a persistent-429 `QuotaExhausted` stop after the backoff. Callers (M3 onward) decide what a request does with them; the gateway doesn't catch its own errors.
- An invalid reply never raises: it becomes `safe_default` with `flagged=True` (M2-FR-10), so one bad analyst reply can't crash a request (architecture Part 8).
- `litellm_completion` is the only place LiteLLM exceptions are seen; everything else in `bullpit/` only sees `BullPitError` subclasses (M0 error rule).
- The Groq key is passed per call from `Settings` and never logged (M0 redaction already masks it).

## 13. Test and verification plan

Per [dev-plan §7.1](../../dev-plan.md#71-must-have-automated-tests), the gateway's retries, cache, validation fallback, quota and size ceiling must have automated tests. Everything runs on the fake provider, an in-memory journal, a recording `sleep`, and the existing `settings` fixture (whose temp `data_cache_dir` isolates the response cache).

**`tests/llm/test_gateway.py`**

| Test | AC |
|---|---|
| `Role.SMALL` / `Role.LARGE` reach the configured model, with the role's `reasoning_effort` and `max_tokens` = the allowance | AC-1 |
| Same call twice: second is a hit, 0 tokens, `cache_hit` row, fake provider called once; changing the seed calls the provider again | AC-2 |
| Two `RateLimited` then success: two recorded waits, the second longer, then a normal result; `RateLimited` on every attempt raises `QuotaExhausted` | AC-3 |
| Invalid JSON, then valid: one retry whose messages include the error. Invalid twice: `safe_default`, `flagged=True`, tokens summed over both attempts, nothing cached | AC-4 |
| Hit, success and flagged fallback each write exactly one `llm_calls` row | AC-5 |
| `llm_calls` seeded near the budget (rows at `utc_now()`): the next call raises `QuotaExhausted` and the provider is never called; the same seed rows dated 25 h ago don't count | AC-6 |
| An oversized rendered prompt raises `PromptTooLarge` naming the template and estimate; the provider is never called | AC-8 |

**`tests/journal/test_db.py`**: one happy-path test (dev-plan §7.2): in-memory engine, `create_all`, insert and read back one `Request` and one `LLMCall`.

Not tested automatically, per dev-plan §7.3: the token bucket's pacing (it's a guard against Groq 429s, which backoff already absorbs), Langfuse wiring, Alembic, the measurement script.

**Manual checks**, evidence pasted into `task.md`:

| Check | How |
|---|---|
| AC-7 | `uv run python scripts/spikes/measure_tokens.py` |
| Alembic | `uv run alembic upgrade head` against a throwaway path (`JOURNAL_DB_PATH` set to a temp file), then compare `sqlite3 <file> .schema` with `models.py` |
| Langfuse off by default | A normal gateway call with defaults leaves `litellm.success_callback` empty; with `LANGFUSE_ENABLED=true` and no keys, the call raises `ConfigError` naming the missing variable |

## 14. Work order

`task.md` breaks this into tasks:

1. Docs on the new branch.
2. Dependencies, settings, errors.
3. Journal: `db.py`, `models.py`, Alembic, first migration, `test_db.py`.
4. Schemas and the measurement prompt.
5. Fake provider (used from step 6 onward).
6. Gateway core: render, ceiling, call, validation retry and fallback, `llm_calls` row.
7. Response cache.
8. Backoff and token bucket.
9. Daily budget.
10. Langfuse toggle.
11. Measurement run (real Groq).
12. Manual checks, ADR-0004, README quick-start line, M0 finding C4 marked answered, retrospective, acceptance.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The heuristic under-estimates a real prompt, so a too-large call reaches Groq | A 413/429 instead of a clean `PromptTooLarge` | `max_tokens` still caps output; backoff turns a persistent 429 into `QuotaExhausted`; AC-7 and the M3–M5 measurements (C14) calibrate the allowance |
| Tokens spent outside Bull Pit (the Groq console, other scripts) aren't in `llm_calls` | Our budget under-counts | Groq's own 429 still stops us: a persistent 429 becomes `QuotaExhausted` (§5.2), so the run pauses either way |
| LiteLLM changes where reasoning tokens are reported | Reasoning logged as 0, budget under-counts | Read defensively (default 0); AC-7's real run is the tripwire; LiteLLM is pinned in `uv.lock` |
| SQLite locking with concurrent writers (M8's API) | Not an M2 problem: M2 has one process at a time | WAL is on from the start; revisited in M8 |
| Alembic migrations drift from `models.py` | Schema mismatch in later milestones | One shared `Base.metadata`; the Alembic manual check (§13) is repeated in every milestone that changes the journal |

## 16. ADRs

- **ADR-0004 — LLM response cache storage.** Context: architecture Part 3 leaves the storage open. Decision: one JSON file per cache key under `data_cache_dir / "llm"`, atomic writes, validated replies only, flagged fallbacks never cached, key includes `reasoning_effort` (D-M2-4, M2-FR-5, FR-6). Written as `Proposed` in T-1, `Accepted` at T-12.
