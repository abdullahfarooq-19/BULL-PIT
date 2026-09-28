# ADR-0004: LLM response cache storage

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-09-28 |
| **Milestone** | M2 ([specs-plan §7 D-M2-4](../milestones/M2-llm-gateway/specs-plan.md#7-decisions-made-in-this-document)) |

## Context

Architecture Part 3 requires a response cache "keyed by model, prompt, temperature, and a run seed. Repeated calls cost zero tokens." It doesn't say where the cache lives: "stored on disk (SQLite table or files)."

Two things already exist that a new choice has to fit alongside:

- The journal database (`journal.db`, M2) is meant to hold structured, queryable rows (`llm_calls`, and later `requests`, `signals`, and so on). A cached reply body isn't a row anyone queries; it's a blob looked up by one exact key.
- The data layer's cache (`bullpit/data/cache.py`, M1) already stores fetched data as files under `data_cache/`, one file per (dataset, symbol), written atomically (temp file then rename) so a crash mid-write can't corrupt an entry.

## Decision

1. **Files, not a database table.** Each cache entry is one JSON file at `data_cache_dir / "llm" / <model slug> / <cache key>.json`. The cache key is the SHA-256 hex digest of `(model, rendered prompt, temperature, seed, prompt_version, reasoning_effort)`.
2. **The stored value is the validated reply**, not the raw provider payload: `{"value": <response_model as JSON>, "input_tokens": ..., "output_tokens": ..., "reasoning_tokens": ...}`. A cache hit therefore skips schema validation as well as the network call.
3. **Writes are atomic** (write to a temp file, then rename), the same pattern `data/cache.py` already uses.
4. **Only a real, valid reply is cached.** A flagged fallback (both attempts failed validation) is never written, so a transient bad reply can't poison future calls with a wrong answer.
5. **`llm_calls.cache_key` records the same hash**, so any row is traceable back to the file that answered it (or would answer a future identical call).

## Consequences

- The journal DB (`journal.db`) stays small and query-shaped; large reply bodies live as files, consistent with how price and news data are already cached.
- A corrupted or stale cache file (for example after a schema change) is treated as a cache miss, not an error: the gateway re-validates on load and falls through to a real call if validation fails.
- Clearing the LLM cache is `rm -rf data_cache/llm`, the same operational pattern as clearing the price cache.
- The cache key includes `reasoning_effort` so that changing a role's effort setting can't silently return a reply generated at a different effort level.
