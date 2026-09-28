# ADR-0001: Package manager: uv

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-09-28 |

## Context

Bull Pit is developed on Windows 11 and runs its CI on `ubuntu-latest`
([dev-plan.md §6.6](../dev-plan.md#66-platform)). It needs reproducible
installs across both platforms, a committed lockfile so a fresh clone gets
exactly the dependency versions development was done against, and fast
installs so CI stays quick (dev-plan.md NFR: CI finishes in about 5 minutes).
The owner decided this in the planning phase (dev-plan.md §10, Q5) before
M0 started; this ADR records the decision formally, as
[dev-plan.md §1.3](../dev-plan.md#13-architecture-decision-records-adrs)
expects for the package manager.

Alternatives considered: `pip` + `venv` + `pip-tools` (no single lockfile
covering dev and runtime dependencies together without extra tooling; slow
resolution); `poetry` (mature, but slower installs and a heavier resolver
than uv); `pdm` (similar to uv but with a smaller ecosystem and less
momentum at the time of writing).

## Decision

Use **`uv`** for dependency management, virtual environments and running
project commands (`uv run ...`). `pyproject.toml` is the single source of
truth for dependencies and tool configuration; `uv.lock` is committed and
CI installs with `uv sync --locked`, so a lockfile out of step with
`pyproject.toml` fails the build rather than silently drifting.

## Consequences

- Every command in this repo's docs and CI is `uv run <tool>`, not a bare
  `<tool>` — this keeps local runs, pre-commit and CI using the exact same
  pinned versions (dev-plan.md D-M0-2).
- Adding or upgrading a dependency always goes through `uv add` /
  `uv lock`, so `uv.lock` stays authoritative and reviewable in diffs.
- `uv` is a fast-moving tool; its own version isn't pinned in this repo, so
  a future `uv` release could change resolution behaviour. If that ever
  causes a problem, the fix is to pin `uv` itself (e.g. via a documented
  minimum version), not to change package managers.
