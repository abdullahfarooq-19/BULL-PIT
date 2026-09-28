# M4 — Debate, trader, risk manager: tasks

| | |
|---|---|
| **Status** | Green light given 2026-09-29; implementation in progress |
| **Date** | 2026-09-29 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (Part A and Part B approved 2026-09-29; full offline test coverage, D-M4-14) |
| **Branch** | `m4-debate-trader-risk`, from `master` |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. **Code and its tests land in the same task.** After every task, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` ("four checks") are clean, and the diff has been re-read for anything the task doesn't need.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [ ] | M4-T-1 | **Docs.** Create `m4-debate-trader-risk` from `master`. Commit `specs-plan.md`, this file, and dev-plan §5 M4's file names (`agents/debate.py` + `bull.md`/`bear.md`; `risk/sizing.py` + `rules.py`) plus its status line | `docs/milestones/M4-debate-trader-risk/*`, `docs/dev-plan.md` | D-M4-1, D-M4-2, D-M4-14 | Branch exists; docs committed | |
| [ ] | M4-T-2 | **Settings.** Add the FR-20 settings to `config.py` (sizing inputs as `Decimal`) and `.env.example`, plus `test_config.py` | `bullpit/config.py`, `.env.example`, `tests/test_config.py` | FR-20; D-M4-13; AC-15 | `test_config.py` passes | |
| [ ] | M4-T-3 | **Exits and sizing.** Add `ExitStyle`, `SizeLimit` and `SizedOrder` to `domain.py`. Write `risk/sizing.py` (`exit_prices`, `share_limits`, `build_order`) and `test_sizing.py`: the worked example, the property test, the exit table, holding and tie-break | `bullpit/domain.py`, `bullpit/risk/sizing.py`, `tests/risk/__init__.py`, `tests/risk/test_sizing.py` | FR-7, FR-8; D-M4-8; AC-1, AC-2 | `test_sizing.py` passes; mypy strict clean on `risk/` | |
| [ ] | M4-T-4 | **Rules.** Write `risk/rules.py` (`stage_a` with the FR-9 rules in order, `shrink`, `loss_warning`) and `test_rules.py`: every hard rule, rule order, shrink, loss warning | `bullpit/risk/rules.py`, `tests/risk/test_rules.py` | FR-9, FR-10, FR-12; D-M4-9, D-M4-10; AC-3, AC-5, AC-9 | `test_rules.py` passes; `risk/` imports only `domain`, the stdlib and Pydantic | |
| [ ] | M4-T-5 | **Schemas, state, agent fixtures.** Add `DebatePoint`, `DebateReply`, `TraderReply` and `RiskReviewReply` (shrink needs `shares`). Add `CheckedPoint`, `DebateTurn`, `Recommendation`, `RiskVerdict`, `TradeAttempt` and the new `RequestState` fields. Write `tests/agents/conftest.py`: a board-ready state and a scripted completion fake | `bullpit/llm/schemas.py`, `bullpit/state.py`, `tests/agents/__init__.py`, `tests/agents/conftest.py` | §5; D-M4-5, D-M4-10; NFR-5 | Four checks clean; M3's tests still pass | |
| [ ] | M4-T-6 | **Debate.** Write `agents/debate.py` (`bull_node` and `bear_node` over a shared `_turn`: ID normalisation and the unsupported check, word count, flagged → empty turn and warning, transcript with `[unsupported]`), `bull.md` and `bear.md` (plan §9.5, no `include`s), and `test_debate.py` | `bullpit/agents/debate.py`, `bullpit/llm/prompts/bull.md`, `bullpit/llm/prompts/bear.md`, `tests/agents/test_debate.py` | FR-2 to FR-4; D-M4-1, D-M4-3, D-M4-4; AC-11 | `test_debate.py` passes | |
| [ ] | M4-T-7 | **Trader.** Write `agents/trader.py`: prompt inputs, including earlier vetoes with the vetoed size; ticker filled by code; weight clamp and decisive-ID filter with warnings; no-trade and flagged outcomes. Plus `trader.md` and `test_trader.py` | `bullpit/agents/trader.py`, `bullpit/llm/prompts/trader.md`, `tests/agents/test_trader.py` | FR-5, FR-6; D-M4-5, D-M4-6, D-M4-7; AC-11 | `test_trader.py` passes | |
| [ ] | M4-T-8 | **Risk review.** Write `agents/risk_review.py` (plan §11.2: approve, shrink through `rules.shrink`, the clamp logged as `risk_review_clamped`, veto, final veto, flagged), `risk_review.md` and `test_risk_review.py` | `bullpit/agents/risk_review.py`, `bullpit/llm/prompts/risk_review.md`, `tests/agents/test_risk_review.py` | FR-11 to FR-14; D-M4-7, D-M4-11; AC-5, AC-11 | `test_risk_review.py` passes | |
| [ ] | M4-T-9 | **Prompt tests.** Write `test_prompts.py`: the four templates render from the agents' variable code, start with their fixed first line and have no `include`; the worst-case prompt estimates stay under the ceiling | `tests/llm/test_prompts.py` | AC-13; NFR-3 | `test_prompts.py` passes | |
| [ ] | M4-T-10 | **Graph.** Add the Stage A `risk_sizing` node in `graph.py` (settings → `stage_a`; `Decimal(str(x))` for ATR and weight). The brain sets the no-trade outcome (FR-1). Wire the plan §9.4 edges, replacing `brain → END` | `bullpit/graph.py` | FR-1, FR-15, FR-16; NFR-2 | Four checks clean (the M3 graph tests are updated to the new ending in T-13) | |
| [ ] | M4-T-11 | **Journal and runner.** Add `Request.outcome` and `no_trade_reason`, `DebateTurnRecord` and `RecommendationRecord`; migration `0003_debate_recommendations` (batch mode); `_finalize` writes the M4 rows in the same transaction. Plus `test_migrations.py` | `bullpit/journal/models.py`, `bullpit/journal/migrations/versions/0003_debate_recommendations.py`, `bullpit/runners/request.py`, `tests/journal/test_migrations.py` | FR-17, FR-19; §10; AC-10 | `test_migrations.py` passes (no schema diff after `0001`–`0003`) | |
| [ ] | M4-T-12 | **CLI.** `bullpit request` prints the turns, the attempts and the `OUTCOME:` line (FR-18). Plus `test_cli.py` | `bullpit/cli.py`, `tests/test_cli.py` | FR-18; AC-14 | `test_cli.py` passes | |
| [ ] | M4-T-13 | **Graph tests.** `RecordingLLM` answers the four M4 templates with per-test scripts and counts calls per template; the graph tests' settings raise `llm_tpm_limit`. Tests: buy path (with a `T99` citation), weak signals, veto limit, trader no-trade, Stage A block, flagged debate turn, M4 node exception, each with its journal rows | `tests/test_graph.py` | AC-4, AC-6, AC-8, AC-12 | All graph tests pass; the whole suite runs in under a minute | |
| [ ] | M4-T-14 | **Real runs and tokens.** AC-7: AAPL, MSFT and JPM at 2024-10-18 (backtest) plus one live request. Read one transcript in full; get per-template tokens from `llm_calls`; compare the per-request large-model total with §14; re-derive `llm_output_allowance_tokens` per FR-21 (`test_prompts.py` re-checks the ceiling with the new value); re-run one request to confirm nothing is flagged. AC-10: paste one request's M4 rows | `bullpit/config.py`, `.env.example`, `tests/test_config.py` (if the allowance default is asserted), this file (evidence) | AC-7, AC-10; FR-21; C14 | Evidence pasted below; every check passes | |
| [ ] | M4-T-15 | **Acceptance.** Add what a full request prints to the README quick start. Write the retrospective (token numbers against §14, veto and flag rates, test count and suite time, carry-overs). Then, when the owner asks: push, CI green, merge to `master`, tag `m4` | `README.md`, this file | DoD §1.5 | Owner accepts | |

## Traceability

| AC | Tasks |
|---|---|
| AC-1, AC-2 | T-3 |
| AC-3, AC-9 | T-4 |
| AC-4 | T-6, T-13 |
| AC-5 | T-4, T-8 |
| AC-6 | T-8, T-10, T-13 |
| AC-7 | T-14 |
| AC-8 | T-10, T-11, T-13 |
| AC-10 | T-11, T-14 |
| AC-11 | T-5 to T-8 |
| AC-12 | T-10, T-11, T-13 |
| AC-13 | T-9, T-14 |
| AC-14 | T-12 |
| AC-15 | T-2 |

| Requirement | Task |
|---|---|
| FR-1 | T-10 |
| FR-2 to FR-4 | T-6 |
| FR-5, FR-6 | T-7 |
| FR-7, FR-8 | T-3 |
| FR-9, FR-10 | T-4 |
| FR-11 to FR-14 | T-4, T-8 |
| FR-15, FR-16 | T-10 |
| FR-17, FR-19 | T-11 |
| FR-18 | T-12 |
| FR-20 | T-2 |
| FR-21 | T-14 |

---

## Evidence

*(Filled in during T-14.)*

## Retrospective

*(Written in T-15.)*
