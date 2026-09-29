# M7 — Evaluation and baselines: specs and plan

| | |
|---|---|
| **Status** | Revision 3, 2026-09-29. The owner must finish the project **tonight** and chose **Qwen only** for every AI run (Q5). M7 becomes a **pilot evaluation** that fits one day's free quota; the full evaluation (26 weeks, repeat seeds, debate impact) is a documented carry-over. Deviation **D13**. Waiting for the owner's green light |
| **Date** | 2026-09-29 |
| **Size** | M: one `specs-plan.md` ([dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents)) |
| **Branch** | `m7-evaluation`, from `master` (M6 merged and tagged `m6`) |
| **Depends on** | M6 (simulated broker, journal, backtest runner): accepted, tagged `m6`. M7 also calls M3–M5 code directly (the analysts' fact builders, the trader's reply checks, Stage A, the graph). M0's close-out (M0-T-18, M0-T-25) is still open and blocked on market hours; M7 doesn't touch it |
| **Sources** | [dev-plan §5 M7](../../dev-plan.md#m7--evaluation-and-baselines), [§2.2](../../dev-plan.md#22-code-conventions), [§3](../../dev-plan.md#3-deviations-from-the-architecture-roadmap) (D9), [§7](../../dev-plan.md#7-testing-strategy), [§8](../../dev-plan.md#8-data-model-evolution), [§10](../../dev-plan.md#10-decisions-log) (Q8, Q8a, Q10a, Q11, D-M6-22), [§10.1](../../dev-plan.md#101-scope-review-revision-4) (C6, C7, C8, C14); [architecture Part 16](../../architecture.md#part-16--evaluation-code), [§12](../../architecture.md#12-evaluation), [§10](../../architecture.md#10-backtest-mode), [§11](../../architecture.md#11-look-ahead-protection), [§14](../../architecture.md#14-free-tier-budget), [Part 10](../../architecture.md#part-10--trader-llm), [Part 11](../../architecture.md#part-11--risk-manager-both); [ADR-0005](../../adr/0005-sim-fill-rules.md), [ADR-0006](../../adr/0006-backtest-stock-selection.md); M5 [retrospective](../M5-report/task.md#retrospective); M6 [specs-plan](../M6-backtest/specs-plan.md) (D-M6-5, D-M6-10, D-M6-13, D-M6-17) and [retrospective](../M6-backtest/task.md#retrospective); OpenRouter's model list and key endpoint, and `llm_calls`, checked 2026-09-29 08:37 UTC ([§7.1](#71-facts-that-shape-this-revision)) |

Part A says **what** M7 delivers and how it's accepted. Part B says **how** it gets built. Neither restates the architecture or the dev plan; they link to them.

---

## Contents

**Part A: Specs**: [1 Goal](#1-goal) · [2 Scope](#2-scope) · [3 Functional requirements](#3-functional-requirements) · [4 Non-functional requirements](#4-non-functional-requirements) · [5 Interfaces](#5-interfaces) · [6 Acceptance criteria](#6-acceptance-criteria) · [7 Decisions](#7-decisions-made-in-this-document) · [8 Open questions](#8-open-questions-for-the-owner)

**Part B: Plan**: [9 Module design](#9-module-design) · [10 Data model](#10-data-model) · [11 Key algorithms](#11-key-algorithms) · [12 Error handling](#12-error-handling) · [13 Tests and checks](#13-test-and-verification-plan) · [14 Work order](#14-work-order) · [15 Risks](#15-risks)

---

# Part A: Specs

## 1. Goal

Build the complete evaluation machinery and run it once, today, as a pilot. Every approach runs through the **same backtest runner, simulated broker and sizing rules**; only the buy decision differs. Code computes every metric from the journal and writes a results page with charts and the architecture's stated limits. The AI approaches run on **Qwen 3.8 27B (free, OpenRouter)** over a window after that model's release, so it can't have seen the prices it's tested on.

The pilot is small (2 stocks × 2 weeks), so its results page says clearly that it proves the pipeline, not that one approach beats another. The architecture's done-when (*"a results table for all four approaches, with repeat runs"*) is met for the table; the repeat runs can't be done on this model (it takes no seed) and move to a carry-over with the full-length run (D-M7-9).

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | `eval/metrics.py`: total return, Sharpe, max drawdown, win rate, profit factor, "no trade" value, Brier score and calibration bins, tokens per request. Pure | Part 16, §12 |
| S2 | `eval/baselines.py`: always buy, moving-average rule, and Bull Pit's replayed decision (for the fixed-sizing variant). Pure | §12 baselines; Q8, Q8a |
| S3 | `agents/single_agent.py` + `llm/prompts/single_agent.md`: one call with all three analysts' **data**, the trader's reply schema | §12 baseline 3 |
| S4 | A **policy** on every backtest run (`bullpit`, `single_agent`, `always_buy`, `ma_rule`, `bullpit_fixed`), run by the same runner and broker | dev-plan M7 |
| S5 | Migration `0006`: `backtest_runs.policy`, `backtest_runs.source_run_id` | dev-plan §8 |
| S6 | `eval/report.py` and `bullpit eval`: `results.md` and three PNGs in `docs/results/` | C6, C8 |
| S7 | **OpenRouter** as a second LLM provider in the gateway, chosen by `llm_provider` (Groq stays the default) | Q5; D13 |
| S8 | The pilot runs: every policy on `MSFT, BRK.B`, 2 weeks from 2026-08-17, AI on Qwen; then `bullpit eval` | Q5 |
| S9 | ADR-0006 addendum: the same stocks for the new window (no split, price under the cap) | C5 |

### 2.2 Out of scope (carry-over, listed in the retrospective)

- **The full evaluation:** 26 weeks × 3 stocks, and 3 seeds × 13 weeks (Q11). Needs about 300 AI requests, and one day of free quota covers about 5 (§7.1).
- **Repeat seeds:** the free Qwen route accepts no `seed` (§7.1), so repeats can't be made on it.
- **Debate impact** (the counterfactual trader call, C7): it costs one more call per debated request, which the pilot can't afford. Not built (no code without a run to use it).
- Any run on the 2024 window with Qwen (it was released 2026-08-14 and has seen that period).
- Groq runs in M7. The pinned gpt-oss models stay the default for live mode and every other command (D13).
- Dashboard pages (M8), an `eval_runs` table (C8), LLM-written conclusions, tuning anything from the results.

## 3. Functional requirements

**Policies (architecture §12; Q8, Q8a)**

- **M7-FR-1 Run policy.** `bullpit backtest` takes `--policy` (default `bullpit`), stored on the run and used again on `--resume`.
- **M7-FR-2 Fair comparison.** Every policy goes through the same request check, the same Stage A (four limits, ATR exits), the same simulated broker, stocks, window and slippage. Only the decision, and for Bull Pit and the single agent the target weight and exit style, differ.
- **M7-FR-3 Code policies** make no LLM call and size every buy at `baseline_target_weight` (6%) and `baseline_exit_style` (normal), with the other three limits applied by Stage A (Q8):
  - `always_buy`: buy every week.
  - `ma_rule`: buy when the close is above SMA 50; no trade when below or when SMA 50 isn't available.
  - `bullpit_fixed` (Q8a): buy exactly when the **source run** (`--source-run RUN_ID`, a completed `bullpit` run with the same tickers, start and weeks) decided to buy that day (§11.3).
- **M7-FR-4 Single agent.** One large-role call per request that passes the request check. It sees the code-written facts from all three analysts' data (technical `T1–T6`, fundamentals `F1–F5` including P/E, headlines as `S*` facts without scores), the account, the per-stock cap and the exit styles, and replies in the trader's schema. The trader's code checks apply (weight clamped, unknown evidence IDs dropped); an invalid reply is "no trade", flagged. Stage A sizes it; no Stage B review, no report (D-M7-2).
- **M7-FR-5 Bull Pit** runs the unchanged M6 graph.

**Metrics (architecture §12; [§11.1](#111-metric-definitions))**

- **M7-FR-6** Per run: total return, Sharpe, max drawdown, win rate and profit factor (closed trades), `open_at_end` trades separately, buy decisions and trades entered, "no trade" value, Brier score (AI policies only), tokens per request.
- **M7-FR-7 "No trade" value**: for every completed "no trade" request (not on the last decision day), the trade the fixed defaults would have placed, simulated with the M6 fill rules to the window end (§11.2).
- **M7-FR-8 Tokens per request** from `llm_calls`; a cache hit counts at its original call's tokens (architecture §14's convention).
- **M7-FR-9 Buy and hold** per stock: first session's open × (1 + slippage) to the last decision day's close.
- **M7-FR-10** Buys on the last decision day can't enter (D-M6-10); they count as buy decisions, not trades.

**Results page (Part 16; C6, C8)**

- **M7-FR-11** `bullpit eval --runs ID,… [--out docs/results]` checks every run is `completed` and all share tickers and start date, then writes `results.md` and `equity.png`, `drawdown.png`, `calibration.png`: setup (stocks, window, models, provider, run IDs, commits), one results table (every policy, plus buy and hold per stock), charts, and a **limits** section that always states: pilot size (trade count shown), one seed and why, the model used and that it isn't the pinned one, approximate fills, survivorship-friendly stocks (ADR-0006), mostly-cash portfolios versus fully invested buy and hold.
- **M7-FR-12** Code writes the only comparison sentences: for total return, each policy is above, below or equal to each other and to buy and hold, followed by "a 2-week, 2-stock pilot can't tell skill from luck". Nothing else is concluded.

**Second provider (Q5; D13)**

- **M7-FR-13** `litellm_completion` sends each call to the provider named by `llm_provider`: `groq/<model>` with `GROQ_API_KEY` (unchanged), or `openrouter/<model>` with `OPENROUTER_API_KEY`, with only the parameters that model accepts (the free Qwen route lists neither `seed` nor `response_format`; the T-4 probe confirms). Cache, pacing, budget, validation and `llm_calls` are unchanged.

**Pilot runs (Q5)**

- **M7-FR-14** All with `MSFT, BRK.B` (the first two ADR-0006 stocks), `--start 2026-08-17 --weeks 2` (decision days 2026-08-21, 2026-08-28), seed 1. AI runs use `LLM_PROVIDER=openrouter`, both models `qwen/qwen3.8-27b:free`, both cutoffs 2026-08-14: `bullpit`, then `single_agent`. Code runs: `always_buy`, `ma_rule`, and `bullpit_fixed` from the Bull Pit run. Then `bullpit eval` over all five → `docs/results/`.

**Settings**

- **M7-FR-15** New in `config.py` and `.env.example` (names only): `baseline_target_weight` = 0.06, `baseline_exit_style` = `normal`, `eval_calibration_bins` = 5, `llm_provider` = `groq`, `openrouter_api_key` (secret, unset by default).

## 4. Non-functional requirements

- **M7-NFR-1 (tests)** Dev-plan §7 exactly: one hand-computed fixture for the metrics (§7.1), one test per decision rule (they can silently corrupt the comparison), one gateway test for the new route (§7.1 gateway behaviour), a prompt-size test for the new prompt, one happy path for the new policies through the runner and one for `bullpit eval` (§7.2). No network; the suite stays under about a minute.
- **M7-NFR-2 (pure core)** `eval/metrics.py` and `eval/baselines.py` do no I/O and read no settings. `eval/report.py` is the evaluation's only I/O edge.
- **M7-NFR-3 (code for math)** No LLM call in `bullpit eval`; every number and sentence on the page comes from code.
- **M7-NFR-4 (no leak)** The AI runs start after Qwen's release date, enforced by the runner's existing cutoff check with both cutoffs at 2026-08-14. The evaluation reads prices only up to each run's last decision day, through the date guard.
- **M7-NFR-5 (money)** Trade and equity values stay `Decimal` until a metric makes a ratio. Hypothetical trades use the M6 simulated broker.
- **M7-NFR-6 (quota)** Everything fits one day of OpenRouter's free limit: about 45 of 50 requests (§11.5). Code policies use none.
- **M7-NFR-7 (secrets)** The OpenRouter key lives only in `.env`; `.env.example` has the name only.

## 5. Interfaces

```python
# bullpit/eval/baselines.py (pure)
Policy = Literal["bullpit", "single_agent", "always_buy", "ma_rule", "bullpit_fixed"]
CODE_POLICIES: frozenset[Policy]            # always_buy, ma_rule, bullpit_fixed
def always_buy(indicators: Indicators) -> bool: ...
def ma_rule(indicators: Indicators) -> bool: ...                 # above_sma_50 is True
def bullpit_wanted_buy(last_action: str, review_decision: str | None) -> bool: ...
def fixed_recommendation(ticker: str, buy: bool, *, weight: Decimal,
                         exit_style: ExitStyle, reason: str) -> Recommendation: ...

# bullpit/eval/metrics.py (pure; ratios as float)
def total_return(start: Decimal, end: Decimal) -> float: ...
def weekly_returns(start: Decimal, decision_equity: Sequence[Decimal]) -> list[float]: ...
def sharpe(weekly: Sequence[float]) -> float | None: ...
def max_drawdown(curve: Sequence[Decimal]) -> float: ...
def win_rate(pnls: Sequence[Decimal]) -> float | None: ...
def profit_factor(pnls: Sequence[Decimal]) -> float | None: ...
def brier(pairs: Sequence[tuple[float, bool]]) -> float | None: ...     # (confidence, won)
def calibration(pairs: Sequence[tuple[float, bool]], bins: int) -> list[CalibrationBin]: ...
def hypothetical_trade(order: SizedOrder, *, submitted_on: date, bars: Sequence[Bar],
                       cash: Decimal, slippage_pct: Decimal) -> Trade: ...   # via SimBroker
def no_trade_value(trades: Sequence[Trade]) -> NoTradeValue: ...
def tokens_per_request(calls: Sequence[CallRow], original: Mapping[str, int],
                       requests: int) -> TokenCost: ...
def buy_and_hold(first_open: Decimal, last_close: Decimal, slippage_pct: Decimal) -> float: ...

# bullpit/agents/trader.py: the reply checks become public and shared
def recommendation_from_reply(reply: TraderReply, *, ticker: str,
                              registry: Mapping[str, Evidence], settings: Settings
                              ) -> tuple[Recommendation, list[str]]: ...
def exit_style_descriptions(settings: Settings) -> list[str]: ...

# bullpit/agents/single_agent.py
def single_agent_node(state: RequestState, *, settings: Settings,
                      sessions: sessionmaker[Session], completion_fn: CompletionFn
                      ) -> dict[str, object]: ...

# bullpit/graph.py (+)
def build_graph(deps: Deps, *, policy: Policy = "bullpit",
                buy_decisions: Mapping[tuple[date, str], bool] | None = None) -> ...: ...

# bullpit/runners/backtest.py (+ keyword arguments)
def start_backtest(..., policy: Policy = "bullpit", source_run: str | None = None) -> str: ...

# bullpit/config.py (+)
llm_provider: Literal["groq", "openrouter"] = "groq"
openrouter_api_key: SecretStr | None = None

# bullpit/eval/report.py
def evaluate(run_ids: Sequence[str], out_dir: Path, *, settings: Settings,
             sessions: sessionmaker[Session]) -> Path: ...        # returns results.md
```

CLI: `bullpit backtest … [--policy P] [--source-run ID]` and `bullpit eval --runs ID,… [--out DIR]`. Exit codes as M6: 0 done, 1 error, 2 usage, 3 paused.

## 6. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| **M7-AC-1** | Each metric matches a hand-computed value on one fixture: total return, weekly returns and Sharpe, max drawdown, win rate, profit factor (and `None` with no loss), Brier, calibration bins, tokens per request with a cache hit at its original tokens, buy and hold, and the "no trade" value, whose hypothetical trade enters at the next open × 1.0005 and exits by the M6 rules | **Automated** |
| **M7-AC-2** | All four approaches, the Bull Pit (fixed sizing) variant and buy and hold run over the same stocks and window, and `bullpit eval` produces the table | **Automated** happy path (fixture runs of every policy → `results.md` with every row and three PNGs) + **manual**: the pilot runs and `docs/results/` committed |
| **M7-AC-3** | Tokens per request are reported for every approach from `llm_calls` (0 for the code policies) | **Automated** (AC-1) + **manual**: one run's figure rechecked with a journal query |
| **M7-AC-4** | The results page states its limits (pilot size, one seed and why, non-pinned model) and makes no claim the data doesn't support | **Manual**: the owner reads it |
| **M7-AC-5** | Fair comparison: on fixtures, `always_buy`, `ma_rule` and `bullpit_fixed` make **no** LLM call and size every buy through Stage A at 6% / normal; `single_agent` makes exactly **one** large-role call per request that passes the check; `bullpit_fixed` buys exactly where its source decided to buy. Each decision rule gives its documented answer (always buy; MA above, below, not available; replayed decision for buy, veto, Stage A block, trader no trade) | **Automated** |
| **M7-AC-6** | With `llm_provider = openrouter`, a call goes to `openrouter/<model>` with the OpenRouter key and only the confirmed parameters; the default Groq call is unchanged | **Automated** |
| **M7-AC-7** | The Qwen route works for real: the T-4 probe's findings recorded (parameters accepted, JSON valid, tokens including reasoning); a start on 2026-08-14 with the Qwen cutoffs is refused; both AI pilot runs complete; the single-agent prompt's real tokens are recorded (C14) | **Manual**: CLI output and `llm_calls` queries in `task.md` |
| **M7-AC-8** | If a pilot trade enters (or exits), it is checked by hand against the real bar: entry = next open × 1.0005 to the cent; exit by the M6 rules (M6 carry-over) | **Manual**, or "no trade entered" recorded |
| **M7-AC-9** | `alembic upgrade head` on an empty DB matches `models.py` (the existing migration test, now covering `0006`) | **Automated** |

The dev-plan's draft AC-3 ("3 seeded runs per LLM approach") can't be met on the free Qwen route and moves to the carry-over with the full run (D-M7-9).

## 7. Decisions made in this document

**D13 (deviation, dev-plan §3, architecture v2.5):** M7's AI runs use `qwen/qwen3.8-27b:free` on OpenRouter for both roles, over a window after its release. The pinned gpt-oss models stay the default everywhere else. Architecture §12, §13 and §16 (M7 done-when: a pilot table; full runs and repeats carried over) get a revision entry; `CLAUDE.md` gets one line.

| # | Decision | Reason |
|---|---|---|
| D-M7-1 | **The policy is a property of the run.** Bull Pit uses the unchanged graph; the other policies use a short graph from the same `build_graph`: request check → indicators → decide → Stage A → accept (§9.3) | "Plugged into the same backtest runner" (dev-plan M7): one runner, broker, request check and Stage A, so only the decision can differ |
| D-M7-2 | **Baselines get no Stage B review and no report** | They aren't parts of a baseline's decision; the architecture's single agent is "one LLM call". A report would spend a scarce request on text nobody reads |
| D-M7-3 | **The single agent sees code-written facts from the analysts' data**, headlines without scores, the same schema and checks as the trader | §12: "all three analysts' data … the same recommendation format, using the same model". Scores are the sentiment analyst's LLM judgment |
| D-M7-4 | **Code policies record `confidence` 0 and are left out of the Brier score** | A rule has no confidence |
| D-M7-5 | **`bullpit_fixed` replays the source run's decision:** buy iff the last trader attempt was `buy` and the review didn't veto it; a Stage A block in the source still counts as a buy decision | A Stage A block is sizing in the source's account, which the variant replaces; a veto is a judgment |
| D-M7-6 | **Metric definitions as in §11.1** (sample standard deviation; `None` where a ratio has no denominator; closed trades only for win rate and profit factor) | The edge cases decided once, so every run is scored the same way |
| D-M7-7 | **"No trade" value:** Stage A at 6% / normal on an empty account with that day's equity, simulated alone with `SimBroker` | "What the same trade would have done", measuring the decision, not the rest of the account |
| D-M7-8 | **Tokens per request count a cache hit at its original tokens** | Otherwise a replayed run looks free |
| D-M7-9 | **Pilot: 2 stocks × 2 weeks, one seed; full runs, repeat seeds and debate impact carried over** | One day of OpenRouter's free tier is 50 requests; a debated Bull Pit request is ~10 calls. 2 weeks is the shortest window in which a buy can enter (week-1 buys fill in week 2). The free route takes no seed |
| D-M7-10 | **Qwen's cutoff = its release date, 2026-08-14; window from 2026-08-17** | Qwen publishes no training cutoff; a model can't be trained on data after its release, so this is a safe upper bound, and the look-ahead rule (§11) is kept |
| D-M7-11 | **`MSFT` and `BRK.B`, the first two ADR-0006 stocks**, re-checked for splits and price in the new window (ADR addendum) | Chosen with 2024 information, which is before the new start, so the rule holds; the first two keep the ADR's order |
| D-M7-12 | **One Qwen model for both roles** | The only free model available |
| D-M7-13 | **OpenRouter's daily limit is handled by the existing pause**: a 429 is retried, then `QuotaExhausted` pauses the run with no partial week (M2, M6). `LLM_RPM_LIMIT` is set low for the runs so the per-minute limit isn't hit | No new budget code; `QuotaExhausted` is the one error every analyst re-raises, so a limit can't become a degraded signal |
| D-M7-14 | **Results in `docs/results/`**, committed; code-only comparison sentences | C6, C8; "code for math" |
| D-M7-15 | **`matplotlib` added** (named by dev-plan M7), `Agg` backend | Static PNGs (C6) |
| D-M7-16 | **`eval/report.py` is the evaluation's I/O edge**; metrics and baselines stay pure; `hypothetical_trade` uses the pure `broker/sim.py` | Testable math on plain data |
| D-M7-17 | **Testing follows dev-plan §7** | Owner instruction for M5 onward |

### 7.1 Facts that shape this revision

| Fact (checked 2026-09-29 08:37 UTC) | Value | Consequence |
|---|---|---|
| Groq, last 24 h of `llm_calls` | large model 141,972 of 200K used; small 80,459 | Only ~5 debated requests left today; the older usage frees only after 23:00 UTC |
| OpenRouter key | Free tier, **50 free-model requests per day**, 50 left; expires 2026-10-29 | The pilot's whole AI budget (§11.5) |
| `qwen/qwen3.8-27b:free` | Created 2026-08-14; parameters listed: `max_tokens`, `reasoning`, `reasoning_effort`, `structured_outputs`, `temperature`, …; **no `seed`, no `response_format`** | Cutoff bound (D-M7-10); no repeats (D-M7-9); no Groq-style JSON mode (FR-13) |

## 8. Open questions for the owner

None open. Answered on 2026-09-29:

| # | Question | Answer |
|---|---|---|
| Q5 | How to finish M7 tonight | **Qwen only** (owner). Replaces Q1–Q4 of revision 2: Q1 (seed probe) and Q2 (12-day plan) no longer apply; Q3 and Q4 are folded into this plan |

---

# Part B: Plan

## 9. Module design

### 9.1 Files created or changed

```text
pyproject.toml, uv.lock                  + matplotlib
.env.example                             + BASELINE_TARGET_WEIGHT, BASELINE_EXIT_STYLE, EVAL_CALIBRATION_BINS,
                                           LLM_PROVIDER, OPENROUTER_API_KEY (names only)
bullpit/
  config.py                              + the five settings
  llm/gateway.py                         litellm_completion: provider route (FR-13)
  eval/baselines.py                      new (pure)
  eval/metrics.py                        new (pure)
  eval/report.py                         new: evaluate()
  agents/trader.py                       recommendation_from_reply, exit_style_descriptions public
  agents/single_agent.py                 new
  llm/prompts/single_agent.md            new
  graph.py                               + policy graph (§9.3)
  runners/backtest.py                    + policy, source run decisions
  journal/models.py                      + BacktestRun.policy, source_run_id
  journal/migrations/versions/0006_evaluation.py   new
  cli.py                                 + backtest --policy/--source-run; eval command
tests/
  eval/__init__.py, eval/test_metrics.py, eval/test_baselines.py, eval/test_report.py   new
  llm/test_gateway.py                    + the OpenRouter route
  llm/test_prompts.py                    + single_agent.md under the ceiling
  runners/test_backtest.py               + policies happy path
  test_config.py                         + the new defaults
docs/results/                            generated: results.md, equity.png, drawdown.png, calibration.png
docs/adr/0006-backtest-stock-selection.md   + addendum (D-M7-11)
docs/dev-plan.md                         status; D13 (§3); §8 row; §10 Q5
docs/architecture.md                     v2.5 (D13: §12, §13, §16)
CLAUDE.md                                one line: the D13 exception to the pinned models
README.md                                running the evaluation
```

### 9.2 Dependency direction

```text
cli ──► runners/backtest ──► graph ──► agents/single_agent ──► agents/trader (shared checks), llm, data
  │            │               └────► eval/baselines (pure) ──► state, domain, tools/indicators
  │            └──► journal (source run decisions)
  └──► eval/report ──► eval/metrics (pure) ──► broker/sim (pure), risk/rules (Stage A)
             ├──► journal, data/prices (up to each run's last decision day)
             └──► matplotlib, files
```

### 9.3 Policy graph

| Node | Code |
|---|---|
| `request_check` | Unchanged; a rejection ends the request |
| `indicators` | `compute_indicators` on the snapshot's bars |
| `decide` | Code policies: `fixed_recommendation(...)` as one `TradeAttempt`. `single_agent`: `single_agent_node`. "No trade" ends |
| `risk_sizing` | Unchanged Stage A |
| `accept` | Not blocked → `outcome = buy`, `sized_order` = the attempt's order |

Rows written: `requests`, `recommendations`, and `approvals`/`trades` for buys; no signals, debate or report.

## 10. Data model

Migration `0006_evaluation`, columns only (C8):

| Table | Column | Type | Notes |
|---|---|---|---|
| `backtest_runs` | `policy` | `TEXT NOT NULL`, default `bullpit` | Existing M6 runs become `bullpit` |
| `backtest_runs` | `source_run_id` | `TEXT NULL` FK → `backtest_runs.id` | `bullpit_fixed` only |

Dev-plan §8 gets an M7 row.

## 11. Key algorithms

### 11.1 Metric definitions

`S` = starting cash, `E_1 … E_n` = equity at each decision day's close, daily snapshots as the curve.

| Metric | Definition |
|---|---|
| Total return | `E_n / S − 1` (open trades marked at the last close) |
| Weekly returns | `E_1/S − 1, E_2/E_1 − 1, …` |
| Sharpe | `mean / stdev × √52`, sample standard deviation, risk-free 0; `None` with fewer than 2 returns or a zero standard deviation |
| Max drawdown | Largest `(peak − value) / peak` over `[S, daily equity…]` |
| Win rate | Closed trades with `pnl > 0` ÷ closed trades; `None` with none |
| Profit factor | Σ positive `pnl` ÷ the absolute value of Σ negative `pnl`; `None` with no losing trade |
| Open at end | Count and marked `pnl` of `open_at_end` trades, separate |
| Brier | Mean `(confidence − won)²` over closed buys; AI policies only |
| Calibration | Closed buys in `eval_calibration_bins` equal-width confidence bins: count, mean confidence, win share |
| Tokens per request | Σ input + output + reasoning over the run's requests' `llm_calls`, a hit at its original tokens, ÷ requests |

### 11.2 "No trade" value

```text
for each completed no_trade request, as_of D < run.end_date:
    ind   = compute_indicators(get_prices(ticker, D, price_history_sessions))
    order = stage_a(close at D, ind.atr_14, "normal", 0.06, account=(equity, equity) at D, held 0)
    block reason → counted as "not sizeable"
    trade = hypothetical_trade(order, submitted_on=D, bars in (D, end_date], cash=equity, slippage)
summary: count, wins, losses, open at end, Σ pnl
```

### 11.3 Replayed decision (`bullpit_fixed`)

The source's last `recommendations` row per request: buy iff `action == "buy"` and `review_decision != "veto"`. A request with no row (rejected, or no debate) is "no trade".

### 11.4 The OpenRouter route

```text
groq:       unchanged
openrouter: litellm.completion(model=f"openrouter/{model}", api_key=OPENROUTER_API_KEY,
                               messages, temperature, max_tokens, reasoning_effort,
                               + only what T-4 confirms)       # no seed, no json_object
            same exception mapping (429 → RateLimited, 5xx/timeouts → ProviderTransient, else LLMUnavailable)
```

If T-4 shows fenced JSON, `_validate` parses the text between the first `{` and the last `}` (a Groq reply is already exactly that). If reasoning doesn't fit the output allowance, the runs set `LLM_OUTPUT_ALLOWANCE_TOKENS` (and `LLM_TPM_LIMIT`, Groq's per-call figure) higher as run settings.

### 11.5 Request budget (50 per day)

| Step | Requests |
|---|---|
| T-4 probe | 2 |
| `bullpit`: 2 stocks × 2 weeks, ~10 calls each for a debated request, week 2's fundamentals verdict from the cache | ≤ 38 |
| `single_agent`: 4 requests × 1 call | 4 |
| Margin (a validation retry, a veto) | ~6 |

A skipped debate costs 4 calls, not 10. If the limit is reached anyway, the run pauses cleanly and the pilot shrinks to what completed: the unfinished run is restarted as `MSFT` only (D-M7-9's order), recorded in `task.md`.

## 12. Error handling

| Where | Error | Result |
|---|---|---|
| Start | `bullpit_fixed` without a matching completed `bullpit` source | `ConfigError`; nothing written |
| Start | `llm_provider = openrouter` without `OPENROUTER_API_KEY` | `ConfigError` from `settings.require`, before any call |
| Start | Start on or before 2026-08-14 with the Qwen cutoffs | `ConfigError` (M6-AC-5 unchanged) |
| Week | Single agent: `QuotaExhausted`, `LLMUnavailable` | Run paused (M6-FR-11) |
| Week | Single agent: invalid reply after the retry | "No trade", flagged |
| Week | `ma_rule` with SMA 50 not available | "No trade" with the reason |
| Week | OpenRouter daily limit (429 after retries) | `QuotaExhausted` → paused, no partial week (D-M7-13) |
| Eval | A run not `completed`; different tickers or start | `ConfigError` naming the run |
| Eval | Missing snapshot or bars | `DataUnavailable`; nothing written |

## 13. Test and verification plan

Dev-plan §7 exactly (D-M7-17). No network.

| File | Tests | AC | §7 category |
|---|---|---|---|
| `eval/test_metrics.py` | One hand-built fixture (4-week equity, 5 trades: 2 wins, 2 losses, 1 `open_at_end`; 4 confidences; `llm_calls` rows with a cache hit), each value computed by hand in the docstring; the `None` cases; `hypothetical_trade` on hand-built bars; `buy_and_hold` | AC-1, AC-3 | 7.1 evaluation metrics |
| `eval/test_baselines.py` | always buy; MA above, below, not available; replayed decision for buy, veto, Stage A block, trader no trade; fixed weight and style | AC-5 | 7.1 (silent corruption) |
| `llm/test_gateway.py` (+) | `test_openrouter_route`: patched `litellm.completion` gets `openrouter/<model>`, the OpenRouter key, no `seed` or `response_format`; the Groq tests unchanged | AC-6 | 7.1 gateway behaviour |
| `llm/test_prompts.py` (+) | `single_agent.md` with 15 headlines and every fact stays under the per-call ceiling | AC-7 | 7.1 gateway (size ceiling) |
| `runners/test_backtest.py` (+) | `test_policies_happy_path` (parametrised: `always_buy`, `ma_rule`, `single_agent`, `bullpit_fixed` from a fixture `bullpit` run; 3 weeks, 2 tickers): complete; 0 LLM calls for code policies, 1 per checked request for the single agent; buys at 6% / normal; `bullpit_fixed` on the source's buy days | AC-5 | 7.1 + 7.2 happy path |
| `eval/test_report.py` | `test_eval_happy_path`: fixture runs of every policy → `results.md` with every row, buy and hold, limits; three PNGs | AC-2 | 7.2 happy path |
| `test_config.py` (+) | The new defaults | FR-15 | — |

**Manual checks** (evidence in `task.md`): the T-4 probe; the refused 2026-08-14 start; each pilot run's CLI output, tokens and row counts; one run's tokens per request from a journal query; any real entry or exit against its bar; the owner reads `docs/results/results.md`.

## 14. Work order

`task.md` breaks this into tasks, in this order. Everything is built and tested before any real request is spent, except the 2-call probe, which comes early so the route is built on observed behaviour.

1. Docs and branch (this file, `task.md`, dev-plan, architecture v2.5, `CLAUDE.md`).
2. Settings, `matplotlib`.
3. OpenRouter route and its test.
4. Qwen probe (2 real calls), then any route fix it calls for.
5. Metrics. 6. Baselines. 7. Single agent. 8. Journal. 9. Graph. 10. Runner, CLI, runner tests. 11. `bullpit eval`.
12. ADR-0006 addendum.
13. Pilot runs and `bullpit eval`; `docs/results/` committed.
14. Acceptance: README, retrospective with the carry-over commands; merge and tag `m7` when the owner asks.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The pilot is tiny (8 AI decisions, a handful of trades at most) | Results can't show one approach is better | The page says so in code-written text (FR-11, FR-12); the full run is a carry-over with its commands |
| The free Qwen route behaves differently from Groq (no JSON mode, long reasoning) | Flagged replies, wasted requests | The 2-call probe before any run; fence rule and allowance set from what it shows |
| The 50 requests run out mid-run | A run can't complete tonight | §11.5's margin; clean pause; fallback to `MSFT` only |
| Qwen is not the pinned model | The pilot says little about Bull Pit on gpt-oss | Stated on the page; D13 keeps gpt-oss as the default; the full gpt-oss run is the first carry-over |
| Free routes may log prompts | Prompt text leaves the machine | Prompts hold only public market data; no keys or account IDs |
| Implementation time tonight | M7 not finished tonight | Scope cut to what the pilot needs (no counterfactual, no seeds, no repeat tables); tests limited to §7 |
