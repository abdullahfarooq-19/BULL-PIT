# M5 — Report generator: tasks

| | |
|---|---|
| **Status** | Written 2026-09-29; waiting for the owner's green light. Nothing implemented yet |
| **Date** | 2026-09-29 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (reviewed and corrected 2026-09-29, §7.1; necessary testing, D-M5-11) |
| **Branch** | `m5-report`, from `master` **after M4 is merged and tagged `m4`** (M4-T-15) |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. **Code and its tests land in the same task.** After every task, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` ("four checks") are clean, and the diff has been re-read for anything the task doesn't need.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [ ] | M5-T-1 | **Docs and branch.** Check that M4 is merged into `master` and tagged `m4`; if not, stop and ask the owner. Create `m5-report` from `master`. Commit `specs-plan.md`, this file, and dev-plan's status line (M5 in progress) | `docs/milestones/M5-report/*`, `docs/dev-plan.md` | DoR §1.4 | Branch exists; docs committed | |
| [ ] | M5-T-2 | **Settings, reply schema, shared SMA.** Add `vix_low_threshold` (15.0) and `vix_high_threshold` (25.0) to `config.py` and `.env.example`, plus their defaults in `test_config.py`. Add `ReportProse` to `llm/schemas.py`. Rename `tools.indicators._sma` to public `sma` (callers updated, no behaviour change) | `bullpit/config.py`, `.env.example`, `tests/test_config.py`, `bullpit/llm/schemas.py`, `bullpit/tools/indicators.py` | FR-13; D-M5-6, D-M5-7; AC-6 (defaults) | Four checks clean; `test_indicators.py` unchanged and passing | |
| [ ] | M5-T-3 | **Number check.** Write `report/number_check.py` (§11.1): ID and ISO-date extraction, number tokens with units, the rounding and one-significant-digit rules, `allowed_numbers`, `check_text`, `mask_unknown_numbers`. Plus `test_number_check.py`: every AC-4 accept and reject case, `T99`, masking | `bullpit/report/number_check.py`, `tests/report/__init__.py`, `tests/report/test_number_check.py` | FR-6; D-M5-3; AC-4, AC-3 (check level) | `test_number_check.py` passes; module imports only the stdlib | |
| [ ] | M5-T-4 | **Report model.** Write `report/model.py` (`Report`, `DebateSummary`, `AttemptRow`, `MarketContext`, `DataNotes`, `ReportOutcome`, `ProseSource`; §5) and add `RequestState.report` | `bullpit/report/model.py`, `bullpit/state.py` | FR-1, FR-2; D-M5-9; NFR-4 | Four checks clean; `report/model.py` imports only `domain` and `llm/schemas` | |
| [ ] | M5-T-5 | **Builder (pure) and Markdown.** In `report/builder.py`: `market_context` with the explanation table (§11.2), `build_report` with the FR-1 section rules, FR-2 reason split and quote masking (§11.5), `fallback_prose` (§11.3), `render_markdown` (§11.4) over `report/templates/report.md`. Plus `test_builder.py`: example card, sections per outcome, traceability, market context | `bullpit/report/builder.py`, `bullpit/report/templates/report.md`, `tests/report/test_builder.py` | FR-1 to FR-4; D-M5-7, D-M5-8, D-M5-12, D-M5-13; AC-1, AC-2 (auto), AC-5, AC-6 | `test_builder.py` passes | |
| [ ] | M5-T-6 | **Writing step.** Write `llm/prompts/report.md` (§9.5; first line `You are the report writer`; `rejected` section) and `report_node` in `builder.py` (§9.3 steps 2–6: masked transcript, first call, check, one retry naming the rejected tokens, fallback on a second failure, a flagged reply, `LLMUnavailable` or `PromptTooLarge`). Plus `test_report_node.py` and the `report.md` case in `test_prompts.py` (render and worst-case ceiling) | `bullpit/llm/prompts/report.md`, `bullpit/report/builder.py`, `tests/report/test_report_node.py`, `tests/llm/test_prompts.py` | FR-5, FR-7, FR-9; D-M5-2, D-M5-4, D-M5-5; NFR-2; AC-3, AC-10 (ceiling) | Both test files pass | |
| [ ] | M5-T-7 | **Graph.** Add `_report_node` in `graph.py` (market-context fetch through `get_market_context`, the `DataUnavailable` fallback and warning, skipped for rejections; `utc_now()` for the report time). Every router that returned `END` now returns `"report"`; `report → END`. Give `RecordingLLM` in `test_graph.py` a default `report.md` reply (clean, cites `T1`) so the existing graph tests keep passing. **Note:** `test_graph.py`'s `_patch_prices()` fake ignores the requested symbol and always returns the AAPL fixture (85 sessions, April–July 2024), so SPY's mocked history is also under 200 sessions there — `market.spy_above` comes back `None` in every graph test by construction, not by a new fixture. That's expected and needs no new fixture; `report/test_builder.py` (T-5) is where the 200-and-more-session case is actually exercised, with a synthetic close series | `bullpit/graph.py`, `tests/test_graph.py` | FR-4, FR-8, FR-9; D-M5-1; NFR-5 | Four checks clean; every existing graph test passes | |
| [ ] | M5-T-8 | **Journal and runner.** Add `ReportRecord` (§10), migration `0004_reports`, and the `reports` row in `_finalize` (same transaction) | `bullpit/journal/models.py`, `bullpit/journal/migrations/versions/0004_reports.py`, `bullpit/runners/request.py` | FR-10, FR-12; D-M5-10; AC-9 | `test_migrations.py` passes with no schema diff after `0001`–`0004` | |
| [ ] | M5-T-9 | **CLI.** `bullpit request` prints `=== REPORT ===` and `render_markdown(result.report)` after the M4 output. Add the buy-with-report case to `test_cli.py` | `bullpit/cli.py`, `tests/test_cli.py` | FR-11; AC-10 | `test_cli.py` passes | |
| [ ] | M5-T-10 | **Graph tests.** Existing path tests each check `state.report` and one `reports` row. New: a request-check rejection (no LLM call, report `rejected`, no market fetch); `LLMUnavailable` on `report.md` (fallback, `completed`); `QuotaExhausted` on `report.md` (`failed`, lock released) | `tests/test_graph.py` | AC-8 | All graph tests pass; whole suite under a minute | |
| [ ] | M5-T-11 | **Real runs, tracing, tokens.** Run `bullpit request` for JPM and AAPL `--mode backtest --as-of 2024-10-18`, XOM `--as-of 2024-07-12`, and SPY. Read each report; trace every number of the JPM report by hand; record each `prose_source`. Measure per-request tokens per model (FR-14); update architecture §14 and add revision v2.3; re-derive `llm_output_allowance_tokens` (and `test_config.py` if it asserts it); re-run one request to confirm nothing is flagged. Paste the evidence below | `docs/architecture.md`, `bullpit/config.py`, `.env.example`, this file | AC-2, AC-7; FR-14; C14 | Evidence pasted; four checks clean | |
| [ ] | M5-T-12 | **Acceptance.** Add the report to the README quick start. Write the retrospective (tokens vs §14, `prose_source` rates, test count and suite time, carry-overs). Then, when the owner asks: push, CI green, merge to `master`, tag `m5` | `README.md`, this file | DoD §1.5 | Owner accepts | |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-5 |
| AC-2 | T-5, T-11 |
| AC-3 | T-3, T-6 |
| AC-4 | T-3 |
| AC-5 | T-5 |
| AC-6 | T-2, T-5 |
| AC-7 | T-11 |
| AC-8 | T-7, T-8, T-10 |
| AC-9 | T-8 |
| AC-10 | T-6, T-9 |

| Requirement | Task |
|---|---|
| FR-1 to FR-3 | T-4, T-5 |
| FR-4 | T-5, T-7 |
| FR-5 | T-6 |
| FR-6 | T-3 |
| FR-7 | T-6 |
| FR-8 | T-7 |
| FR-9 | T-6, T-7 |
| FR-10, FR-12 | T-8 |
| FR-11 | T-9 |
| FR-13 | T-2 |
| FR-14 | T-11 |

---

## Evidence

*(filled in during T-11)*

## Retrospective

*(written in T-12)*
