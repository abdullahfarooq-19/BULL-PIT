# M7 — Evaluation and baselines: tasks

| | |
|---|---|
| **Status** | T-1 to T-13 built and run 2026-09-29/30; nothing committed yet (the owner hasn't asked for commits); T-14 waits for the owner's acceptance |
| **Date** | 2026-09-29 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (revision 3; Q5 = Qwen only; D13; necessary testing, D-M7-17) |
| **Branch** | `m7-evaluation`, from `master` (M6 merged and tagged `m6`) |

Each task is small, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. **Code and its tests land in the same task.** After every code task, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` ("four checks") are clean, and the diff has been re-read for anything the task doesn't need. **Only M7-T-4 and M7-T-13 call a real model**, both on OpenRouter's free Qwen route (50 requests per day, [specs-plan §11.5](specs-plan.md#115-request-budget-50-per-day)). The OpenRouter key is in `.env` only (git-ignored).

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | M7-T-1 | **Docs and branch.** Check `master` holds the `m6` merge; create `m7-evaluation`; commit `specs-plan.md` and this file. `dev-plan.md`: status line, deviation **D13** in §3, an M7 row in §8 (migration `0006`), §10 entry for Q5 (Qwen-only pilot; full runs, repeat seeds and debate impact carried over). `architecture.md` **v2.5**: §12 (pilot on a post-release window), §13 (second provider for M7's AI runs), §16 (M7 done-when). `CLAUDE.md`: one line on the D13 exception under the pinned models | `docs/milestones/M7-evaluation/*`, `docs/dev-plan.md`, `docs/architecture.md`, `CLAUDE.md` | DoR §1.4; D13 | Branch exists; docs committed | |
| [x] | M7-T-2 | **Settings and dependency.** Add `baseline_target_weight` (0.06), `baseline_exit_style` (`normal`), `eval_calibration_bins` (5), `llm_provider` (`groq`), `openrouter_api_key` (secret; blank is unset; known to `settings.require`) to `config.py` and `.env.example` (names only), defaults in `test_config.py`. `uv add matplotlib` | `bullpit/config.py`, `.env.example`, `tests/test_config.py`, `pyproject.toml`, `uv.lock` | FR-15; D-M7-15 | Four checks clean | |
| [x] | M7-T-3 | **OpenRouter route.** `litellm_completion` routes by `llm_provider` (§11.4): `openrouter/<model>`, `OPENROUTER_API_KEY`, no `seed`, no `response_format`; the same exception mapping; Groq unchanged. `test_openrouter_route` in `test_gateway.py` | `bullpit/llm/gateway.py`, `tests/llm/test_gateway.py` | FR-13; AC-6 | Four checks clean; existing gateway tests unchanged | |
| [x] | M7-T-4 | **Qwen probe (2 real requests).** A throwaway scratchpad script calls `call_llm` with `LLM_PROVIDER=openrouter` and `qwen/qwen3.8-27b:free` twice, with the technical and trader prompts rendered from the test fixtures, into a temporary journal. Record: parameters accepted, reply valid JSON or fenced, input/output/reasoning tokens against `llm_output_allowance_tokens`, latency, requests left (`GET /api/v1/key`). Then, if needed: the fence rule in `_validate` (with one test case), and the allowance/TPM run settings for T-13. Delete the script | this file (+ `bullpit/llm/gateway.py`, `tests/llm/test_gateway.py` if the fence rule is needed) | FR-13; D-M7-13; AC-7 | Findings pasted; route adjusted; four checks clean | |
| [x] | M7-T-5 | **Metrics.** `eval/metrics.py` (§5, §11.1, §11.2) and `tests/eval/test_metrics.py`: one hand-built fixture, each value computed by hand in the docstring; the `None` cases; `hypothetical_trade` (entry at next open × 1.0005, a stop exit); `buy_and_hold`; tokens with a cache hit at its original cost | `bullpit/eval/metrics.py`, `tests/eval/__init__.py`, `tests/eval/test_metrics.py` | FR-6 to FR-10; D-M7-6 to D-M7-8; AC-1, AC-3 | Tests pass; `metrics.py` imports no journal, data, CLI or settings module | |
| [x] | M7-T-6 | **Baselines.** `eval/baselines.py` (§5, §11.3) and `tests/eval/test_baselines.py`: always buy; MA above, below, not available; replayed decision for buy, veto, Stage A block, trader no trade; fixed weight and style | `bullpit/eval/baselines.py`, `tests/eval/test_baselines.py` | FR-3; D-M7-4, D-M7-5; AC-5 | Tests pass; pure | |
| [x] | M7-T-7 | **Single agent.** Make the trader's reply checks public (`recommendation_from_reply`, `exit_style_descriptions`; `trader_node` uses them, behaviour unchanged). Write `single_agent.md` and `agents/single_agent.py` (D-M7-3). Prompt-size test in `test_prompts.py` (15 headlines, every fact) | `bullpit/agents/trader.py`, `bullpit/agents/single_agent.py`, `bullpit/llm/prompts/single_agent.md`, `tests/llm/test_prompts.py` | FR-4; D-M7-3; AC-7 | Four checks clean; trader and prompt tests pass | |
| [x] | M7-T-8 | **Journal.** `BacktestRun.policy` and `source_run_id`; migration `0006_evaluation` (existing runs → `bullpit`) | `bullpit/journal/models.py`, `bullpit/journal/migrations/versions/0006_evaluation.py` | FR-1; AC-9 | `test_migrations.py` passes, no schema diff | |
| [x] | M7-T-9 | **Graph.** `build_graph(deps, *, policy, buy_decisions)`: the policy graph (§9.3); the default build is the M6 graph, unchanged | `bullpit/graph.py` | FR-2 to FR-5; D-M7-1, D-M7-2 | Four checks clean; `test_graph.py` unchanged and passing | |
| [x] | M7-T-10 | **Runner, CLI, runner tests.** `start_backtest` takes `policy` and `source_run` (refusals in §12); `run_backtest` builds the run's graph and, for `bullpit_fixed`, loads the source's decisions. `bullpit backtest --policy --source-run`. `test_policies_happy_path` in `test_backtest.py` (§13) | `bullpit/runners/backtest.py`, `bullpit/cli.py`, `tests/runners/test_backtest.py` | FR-1, FR-3; AC-5 | Tests pass; suite under a minute | |
| [x] | M7-T-11 | **Evaluation report.** `eval/report.py` (`evaluate`: load and check runs, metrics, the table with buy and hold, code-written comparison sentences, limits, three PNGs with `Agg`) and `bullpit eval --runs … [--out docs/results]`. `test_eval_happy_path` in `tests/eval/test_report.py` | `bullpit/eval/report.py`, `bullpit/cli.py`, `tests/eval/test_report.py` | FR-11, FR-12; D-M7-14, D-M7-16; AC-2 | Tests pass; four checks clean | |
| [x] | M7-T-12 | **ADR-0006 addendum.** `MSFT`, `BRK.B` for 2026-08-17 to 2026-08-28 (plus the next week's bars the evaluation reads): no split, prices under $10,000, checked through the data layer; tradable on Alpaca | `docs/adr/0006-backtest-stock-selection.md` | FR-14; D-M7-11 | Addendum written | |
| [x] | M7-T-13 | **Pilot runs.** Settings for the AI runs: `LLM_PROVIDER=openrouter`, `LLM_SMALL_MODEL=LLM_LARGE_MODEL=qwen/qwen3.8-27b:free`, both cutoffs `2026-08-14`, a low `LLM_RPM_LIMIT`, plus T-4's allowance values. (a) `--start 2026-08-14` must be refused. (b) `bullpit backtest --tickers MSFT,BRK.B --start 2026-08-17 --weeks 2 --seed 1`. (c) The same with `--policy single_agent`. Then with default settings: `--policy always_buy`, `--policy ma_rule`, `--policy bullpit_fixed --source-run <b>`. (d) `bullpit eval --runs <all five>`; commit `docs/results/`. Record each run's output, tokens (single-agent tokens for C14), row counts, requests left; one run's tokens per request from a journal query; any real entry or exit against its bar. If the limit runs out: the pause, then `MSFT` only (§11.5) | this file, `docs/results/*` | FR-14; AC-2, AC-3, AC-7, AC-8 | Every run `completed`; evidence pasted; results committed | |
| [ ] | M7-T-14 | **Acceptance.** The owner reads `docs/results/results.md` (AC-4). README: running the evaluation and the Qwen settings, link to the results. Retrospective: what changed, test count and suite time, requests and tokens used, and the **carry-over commands** for the full gpt-oss evaluation (26 weeks × 3 stocks, 3 seeds × 13 weeks, debate impact). Then, when the owner asks: push, CI green, merge, tag `m7` | `README.md`, this file | DoD §1.5; AC-4 | Owner accepts | |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-5 |
| AC-2 | T-11, T-13 |
| AC-3 | T-5, T-13 |
| AC-4 | T-11, T-14 |
| AC-5 | T-6, T-9, T-10 |
| AC-6 | T-3 |
| AC-7 | T-4, T-7, T-13 |
| AC-8 | T-13 |
| AC-9 | T-8 |

| Requirement | Task |
|---|---|
| FR-1, FR-2 | T-8, T-9, T-10 |
| FR-3 | T-6, T-9, T-10 |
| FR-4 | T-7, T-9 |
| FR-5 | T-9 |
| FR-6 to FR-10 | T-5, T-11 |
| FR-11, FR-12 | T-11 |
| FR-13 | T-3, T-4 |
| FR-14 | T-12, T-13 |
| FR-15 | T-2 |

---

## Evidence

**T-4 probe (2026-09-29, `qwen/qwen3.8-27b:free`, temporary journal).** The route accepted `max_tokens`, `reasoning_effort` and `temperature` (no `seed`, no `response_format`). Both replies were bare JSON with no code fence, so no fence rule was added. Technical prompt: 226 in / 17 out / 240 reasoning tokens, 4.1 s. Trader prompt: 537 in / 125 out / 405 reasoning, 12.4 s, valid, not flagged. Reasoning stayed far below `llm_output_allowance_tokens` (1,830). The probe also found a real bug: the gateway's cache directory was named from the model ID, and `:free` is illegal in a Windows path (`NotADirectoryError`); fixed in `_cache_path` with a test. OpenRouter's shared free pool answered 429 ("rate-limited upstream") for long stretches; those calls don't count against the 50 requests per day.

**T-13 pilot.** Run settings: `LLM_PROVIDER=openrouter`, both models `qwen/qwen3.8-27b:free`, both cutoffs `2026-08-14`, `LLM_RPM_LIMIT=10`, `LLM_OUTPUT_ALLOWANCE_TOKENS=3000`, `LLM_TPM_LIMIT=12000`, `LLM_MAX_RETRIES=8`, `LLM_BACKOFF_BASE_SECONDS=2`.

- (a) `--start 2026-08-14` refused: `Backtest dates must be after the models' training cutoff: use 2026-08-15 or later.`, exit 2.
- (b) `bullpit` `5d1c7dc0`: paused many times on the upstream 429, resumed with `--resume` until complete (the calls already made replayed from the cache). 2026-08-21 `BRK.B NO TRADE, MSFT BUY 10`; 2026-08-28 `BRK.B NO TRADE, MSFT BUY 9`; end equity 100,300.80; 1 trade open at the window end (MSFT 10 @ 483.45, marked 513.53, P&L 300.80), 1 cancelled order (the last-day buy).
- (c) `single_agent` `12899784`: 4 requests, 4 calls, none flagged; end equity 100,487.32; 2 trades open at the end.
- `always_buy` `dae66a55`: end equity 100,440.40. `ma_rule` `cd4e83e5`: 100,360.96. `bullpit_fixed` `412fab72` (source `5d1c7dc0`): 100,360.96, buying only where Bull Pit decided to buy, with no LLM call.
- (d) `bullpit eval --runs 5d1c7dc0,12899784,dae66a55,cd4e83e5,412fab72` wrote `docs/results/` (`results.md`, `equity.png`, `drawdown.png`, `calibration.png`).

**Tokens (AC-3, AC-7).** Journal query: `5d1c7dc0` 34 real calls, 84,210 tokens over 4 requests (21,052 per request; the page shows 21,361 because a few distinct cache hits count at their original cost); 97 further rows were resume replays. `12899784` 4 calls, 9,285 tokens, so **2,321 tokens per request** for the single-agent prompt (C14). The first version of the metric counted every resume replay again (54,071 per request); it now counts each distinct call once per request. In all, 38 real Qwen calls in the journal, plus about 3 for the probe and a connectivity check: about 41 of the day's 50.

**AC-8.** MSFT entry 2026-08-24: real open 483.2099 x 1.0005 = 483.45, matching the trade row. The open-at-end mark 513.53 equals the 2026-08-28 close.

**AC-9.** `alembic upgrade head` (migration `0006`) applied to the real journal and the migration test passes.

## Retrospective

**What changed from the plan.** (1) The gateway cache path now replaces `:`. (2) `technical.py` exposes `bars_frame`; `trader.py` shares `recommendation_from_reply`, `invalid_recommendation` and `attempt_update` with the single agent; the runner's `trade_from_row` is public. (3) The eval counts each distinct LLM call once per request, so a resumed run isn't charged twice. (4) The results page infers "pinned models or not" from the models recorded on the run, since the provider isn't stored.

**Tests.** 270 pass in about 35 s (244 before M7). Ruff, ruff format and mypy are clean.

**Cost.** About 41 of the day's 50 OpenRouter requests. Most wall-clock time went on Qwen's upstream throttling (hours of waiting), not tokens.

**Carry-over (the full evaluation, gpt-oss on Groq):**

```bash
# 26 weeks x 3 stocks, seed 1 (headline run); then the other policies on the same window
uv run bullpit backtest --tickers MSFT,BRK.B,LLY --start 2024-07-01 --weeks 26 --seed 1
uv run bullpit backtest --tickers MSFT,BRK.B,LLY --start 2024-07-01 --weeks 26 --policy single_agent
uv run bullpit backtest --tickers MSFT,BRK.B,LLY --start 2024-07-01 --weeks 26 --policy always_buy
uv run bullpit backtest --tickers MSFT,BRK.B,LLY --start 2024-07-01 --weeks 26 --policy ma_rule
uv run bullpit backtest --tickers MSFT,BRK.B,LLY --start 2024-07-01 --weeks 26 --policy bullpit_fixed --source-run <bullpit run ID>
# repeats: seeds 2 and 3 over the first 13 weeks (--weeks 13 --seed N) for each AI policy
uv run bullpit eval --runs <run IDs> --out docs/results
```

Debate impact (the counterfactual trader call, C7) is not built; it needs one more large-model call per debated request on the headline run. Repeat seeds need a provider that accepts a seed (Groq does; the free Qwen route does not).
