# M4 — Debate, trader, risk manager: specs and plan

| | |
|---|---|
| **Status** | Part A (specs) and Part B (plan) approved by the owner on 2026-09-29, after the D-M4-1 revision (separate `bull.md` / `bear.md` prompts); then full offline test coverage added on the owner's instruction (D-M4-14, AC-11 to AC-15). See [`task.md`](task.md) for the tasks |
| **Date** | 2026-09-29 |
| **Size** | L. Normally `specs.md` + `plan.md` ([dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents)); the owner asked for them combined in one file, as for M3 |
| **Branch** | `m4-debate-trader-risk` |
| **Depends on** | M3 (request check, analysts, signals board, brain, graph, runner). Accepted, tagged `m3` |
| **Sources** | [dev-plan §5 M4](../../dev-plan.md#m4--debate-trader-risk-manager), [§7](../../dev-plan.md#7-testing-strategy), [§8](../../dev-plan.md#8-data-model-evolution), [§10.1](../../dev-plan.md#101-scope-review-revision-4) (C14, C16); [architecture Parts 9–11](../../architecture.md#part-9--bull-vs-bear-debate-llm), [§5](../../architecture.md#5-one-request-step-by-step), [§14](../../architecture.md#14-free-tier-budget); M0 [findings](../M0-foundations/findings.md) A5, A13; M3 [retrospective carry-overs](../M3-analysts/task.md#retrospective) |

Part A says **what** M4 delivers and how it's accepted. Part B says **how** it gets built. Neither restates the architecture or the dev plan; they link to them.

---

## Contents

**Part A: Specs**: [1 Goal](#1-goal) · [2 Scope](#2-scope) · [3 Functional requirements](#3-functional-requirements) · [4 Non-functional requirements](#4-non-functional-requirements) · [5 Interfaces](#5-interfaces) · [6 Acceptance criteria](#6-acceptance-criteria) · [7 Decisions](#7-decisions-made-in-this-document) · [8 Open questions](#8-open-questions-for-the-owner)

**Part B: Plan**: [9 Module design](#9-module-design) · [10 Data model](#10-data-model) · [11 Key algorithms](#11-key-algorithms) · [12 Error handling](#12-error-handling) · [13 Tests and checks](#13-test-and-verification-plan) · [14 Work order](#14-work-order) · [15 Risks](#15-risks)

---

# Part A: Specs

## 1. Goal

The second half of the decision runs end to end. A debated request goes through bull vs bear (2 rounds), the trader, Stage A (code: exits, sizing, hard rules) and Stage B (LLM review, with the veto loop), and ends in **a sized order with stop-loss and take-profit, or "no trade" with a reason**. The architecture's done-when: *"A complete sized recommendation with stop-loss and take-profit."*

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | Bull and bear debate: 2 rounds, evidence-ID check, word count, concessions, final convictions | Part 9 |
| S2 | Trader: buy or no trade, target weight, exit style, decisive evidence | Part 10 |
| S3 | Stage A in code: ATR exits, four-limit sizing, hard rules; the loss-warning function (C16) | Part 11 A |
| S4 | Stage B: LLM review (approve, shrink, veto); only-shrink enforced by code; veto loop (at most 2 trips back) | Part 11 B |
| S5 | Graph wiring from the brain's `debate` route to the outcome (architecture §5) | Part 0, §5 |
| S6 | Journal: `debate_turns`, `recommendations`; `requests.outcome` and `no_trade_reason` (migration `0003`) | Part 15, dev-plan §8 |
| S7 | `bullpit request` prints the debate, the trader's recommendation(s), the risk verdict and the outcome | D6 |
| S8 | Real token measurement of the debate, trader and review prompts; allowance revised | C14; M3 carry-over |

### 2.2 Out of scope

- The report and its number check (M5). M4 records the facts M5 needs (concessions, convictions, which limit set the size, verdict reasons); it doesn't write any prose for the owner.
- The approval gate, staleness check, expiry and order placement (M6 sim, M8 Alpaca). M4 ends at the recommendation.
- Feeding the loss warning with real equity history (M6 simulated, M8 live; C16).
- A simulated account: backtest-mode requests still size against today's Alpaca paper account until M6 (D-M3-6, carried; D-M4-12).

## 3. Functional requirements

**Routing**

- **M4-FR-1** The brain's `no_trade` route ends the request with outcome `no_trade` and the reason `Signals too weak for a debate (board score {s:+.2f}, no conflict).` It makes no large-model call. The `debate` route starts the debate.

**Debate (Part 9)**

- **M4-FR-2 Turns.** `debate_rounds` rounds (2), bull first in each: bull 1, bear 1, bull 2, bear 2. Each turn is one large-model call on its side's own template, `bull.md` or `bear.md` (D-M4-1), which gets a round task chosen by code:

  | Turn | Task given to the model |
  |---|---|
  | Bull, round 1 | State your three strongest points for buying |
  | Bear, round 1 | Rebut each bull point and add counter-evidence |
  | Bull, round 2 | Answer the bear's attacks |
  | Bear, round 2 | Give your final response |

  Both sides see the same inputs: ticker and company, the signals summary (per analyst: direction, confidence, flagged), board score and conflict, **every evidence fact with its ID** (the board's registry), and the transcript so far. Rules in the prompt: cite evidence IDs for every point, use no number that isn't in the facts, address the opponent's strongest point, conceding is allowed, at most `debate_turn_max_words` words.
- **M4-FR-3 Reply and code checks.** The reply is `DebateReply` (§5). Code then:
  - normalises each cited ID (trimmed, upper-case, so `" t1"` counts as `T1`), then marks a point **unsupported** if it cites no ID, or any ID it cites isn't in the registry (D-M4-4). Unsupported points stay in the transcript, labelled `[unsupported]` in every later prompt;
  - counts the words over all claims and concessions; above `debate_turn_max_words` the turn is flagged `over_word_limit` and kept as is (not truncated, D-M4-3);
  - replaces a flagged reply (invalid after the gateway's retry) with an empty turn (no points, conviction 0, `flagged`), adds a warning, and continues the debate.
- **M4-FR-4 Hand-over.** `state.debate` holds the 4 turns in order. Each side's **final conviction** is its last turn's; **the bull's concessions** are the concessions across the bull's turns. M5 reads both from `state.debate`.

**Trader (Part 10)**

- **M4-FR-5 Prompt.** `trader.md` (large model) gets: the signals summary and board score, the evidence facts, the transcript (with `[unsupported]` labels) and both final convictions, the account (equity, cash, the existing position's value and its % of equity), the maximum target weight (`max_position_pct`), what each exit style means in ATR multiples, and, on a retry, **every earlier veto**: what was recommended (weight, exit style), the shares Stage A sized it to, and the reviewer's reason (D-M4-6).
- **M4-FR-6 Reply.** `TraderReply` has the architecture's Part 10 format without `ticker`, which code fills in from the request (D-M4-5). Code then:
  - converts `target_weight` to `Decimal` and clamps it to [0, `max_position_pct`]. A clamp is logged and added to the warnings;
  - drops `decisive_evidence` IDs that aren't in the registry, with a warning;
  - `action = no_trade` ends the request: outcome `no_trade`, reason `Trader recommended no trade: {reasoning}`;
  - a flagged reply ends the request: outcome `no_trade`, reason `Trader reply was invalid.` (D-M4-7).

**Risk manager, Stage A (Part 11, code)**

- **M4-FR-7 Exits.** With `m` the stop multiple of the exit style (`exit_stop_atr_tight` 1.5, `_normal` 2, `_wide` 3) and `r` = `exit_reward_risk` (1.5): stop = ref − m × ATR, take-profit = ref + r × m × ATR. That reproduces the architecture's table (tight 1.5/2.25, normal 2/3, wide 3/4.5). `ref` is the snapshot's reference price and ATR is `indicators.atr_14`, both as `Decimal`. Both exit prices are rounded to the cent, half up (D-M4-8).
- **M4-FR-8 Sizing.** Four limits, each floored to whole shares:

  | Limit | Shares |
  |---|---|
  | `target` | ⌊target_weight × equity ÷ ref⌋ |
  | `risk` | ⌊`risk_per_trade_pct` × equity ÷ (ref − stop)⌋ |
  | `cap` | ⌊(`max_position_pct` × equity − existing position value) ÷ ref⌋ |
  | `cash` | ⌊cash ÷ ref⌋ (cash, never buying power: findings A13) |

  Shares = the smallest. **The limit that set the size** is the first one with that value, in the order above. The `SizedOrder` records every limit's share count, the cost, the maximum loss (shares × (ref − stop)) and the possible gain (shares × (take-profit − ref)).
- **M4-FR-9 Hard rules**, checked in this order. The first one that fails ends the request with outcome `no_trade` and its reason:

  | Rule | Reason |
  |---|---|
  | ATR missing or ≤ 0, or reference price ≤ 0 | `ATR or price not available.` |
  | Cash ≤ 0 or equity ≤ 0 | `No cash available.` |
  | Existing position ≥ `max_position_pct` of equity | `Per-stock cap reached: {T} is already {p:.1f}% of equity (cap {c:.0f}%).` |
  | Stop ≤ 0, or stop ≥ reference, after rounding | `Exit prices invalid (stop {stop}).` |
  | Shares = 0 | `Size rounds to 0 shares (set by the {limit} limit).` |

- **M4-FR-10 Loss warning (C16).** A pure function over an equity history: `True` if equity at `as_of` is more than `loss_warning_pct` (5%) below the latest snapshot dated on or before `as_of − loss_warning_days` (7), `False` if not, `None` if the history has no such snapshot. It is built and tested in M4 and first called by M6 (simulated) and M8 (live) (D-M4-9).

**Risk manager, Stage B (Part 11, LLM)**

- **M4-FR-11 Review.** It runs only when Stage A passes. `risk_review.md` (large model) gets: the signals summary, the transcript, the trader's recommendation (action, weight, style, confidence, decisive evidence, reasoning) and the Stage A order (shares, cost, % of equity, stop, take-profit, maximum loss and gain, the limit that set it) (D-M4-11). It replies with `RiskReviewReply`: `approve`, `shrink` (with `shares` ≥ 1) or `veto`, plus a reason.
- **M4-FR-12 Only shrink.** `approve` keeps the Stage A order. `shrink` to fewer shares rebuilds the order at that size: same exits, with cost, loss and gain recomputed. A `shrink` to at least the Stage A shares is **clamped** to the Stage A order, logged as `risk_review_clamped` and added to the warnings. A shrink can only lower risk, so no hard rule can newly fail.
- **M4-FR-13 Veto loop.** A veto goes back to the trader with its reason (FR-5). After `risk_max_vetoes` (2) trips back, another veto ends the request: outcome `no_trade`, reason `Risk manager vetoed {n} times: {last reason}`. A retry that the trader turns into `no_trade`, or that Stage A blocks, ends the request there. A flagged review reply ends the request: outcome `no_trade`, reason `Risk review reply was invalid.` (D-M4-7).
- **M4-FR-14 Outcome.** Every request that passes the request check ends with exactly one of these: outcome `buy` with the final `state.sized_order`, or outcome `no_trade` with `state.no_trade_reason`.

**Errors**

- **M4-FR-15** From the debate on, an invalid LLM reply is handled by the safe defaults above. **Any exception** (`LLMUnavailable`, `QuotaExhausted`, `PromptTooLarge`, a bug) fails the request: status `failed`, lock released, re-raised. That's unlike the analysts, where one failed analyst still leaves two signals. With a failed trader or reviewer nothing sound is left to recommend (D-M4-7).

**Graph, runner, CLI, journal**

- **M4-FR-16 Graph.** `brain` → (`no_trade`: end) → `bull` → `bear` → (rounds left: `bull`; otherwise `trader`) → (`no_trade`: end) → `risk_sizing` → (blocked: end) → `risk_review` → (veto with trips left: `trader`; otherwise end). Nodes run one after another, so each returns whole new lists for `debate`, `attempts` and `warnings`. No reducers are needed.
- **M4-FR-17 Runner.** `_finalize` also writes one `debate_turns` row per turn, one `recommendations` row per trader attempt, and `requests.outcome` and `no_trade_reason`, in the same single transaction as M3's rows.
- **M4-FR-18 CLI.** After M3's output, `bullpit request` prints each debate turn (side, round, points with their IDs and `[unsupported]` labels, concessions, conviction, flags), each attempt (recommendation, Stage A order or block reason, review decision and reason), then `OUTCOME: BUY 32 AAPL @ ref 182.00, stop 174.00, take-profit 194.00, max loss 256.00, gain 384.00 (set by target)` or `OUTCOME: NO TRADE: {reason}`.
- **M4-FR-19 Journal (migration `0003`).** New tables `debate_turns` and `recommendations`, and new columns `requests.outcome` and `requests.no_trade_reason` ([§10](#10-data-model)).

**Settings**

- **M4-FR-20** New settings (in `config.py` and `.env.example`). Each default is the architecture's value:

  | Setting | Default | Source |
  |---|---|---|
  | `debate_rounds` | 2 | Part 9 |
  | `debate_turn_max_words` | 150 | Part 9 |
  | `risk_per_trade_pct` | 0.01 | Part 11 |
  | `max_position_pct` | 0.10 | Part 11 |
  | `exit_stop_atr_tight` / `_normal` / `_wide` | 1.5 / 2 / 3 | Part 11 table |
  | `exit_reward_risk` | 1.5 | Part 11 table |
  | `risk_max_vetoes` | 2 | Part 11 |
  | `loss_warning_pct` | 0.05 | Part 11 |
  | `loss_warning_days` | 7 | Part 11 |

  Percentages and multiples that feed sizing are `Decimal`.

**Tokens (C14) and the M3 carry-over**

- **M4-FR-21** The real tokens (input, output, reasoning) of `bull.md`, `bear.md`, `trader.md` and `risk_review.md` are measured from `llm_calls` over the AC-7 runs and compared with [architecture §14](../../architecture.md#14-free-tier-budget). `llm_output_allowance_tokens` is then re-derived with M3's rule: 3 × the largest measured output + reasoning of any M3 or M4 call, never below 500. It must also leave the largest measured large-model prompt under the 8K per-call ceiling. The change is recorded in the retrospective.

## 4. Non-functional requirements

- **M4-NFR-1 (tests)** **Full offline coverage** (D-M4-14). Every M4 behaviour that can run without the network has an automated test:
  - the risk maths and rules;
  - each agent node's branches;
  - every graph path;
  - prompt rendering and size;
  - the migration;
  - the CLI output;
  - the setting defaults.

  Only real-model quality and real token counts are checked by hand. Nothing touches the network, and the whole suite stays under about a minute.
- **M4-NFR-2 (pure core)** `risk/` imports only `domain`, the standard library and Pydantic: no settings, I/O or `llm/`. It passes mypy `strict`. All money and every sizing input is `Decimal`, and share counts are `int`.
- **M4-NFR-3 (tokens)** Debate, trader and review use the large model at `low` reasoning effort. Each prompt stays well under the 8K per-call ceiling (target: estimate ≤ 3,500 tokens including the allowance). A debated request makes at most 4 + 3 × 2 = **10** large-model calls (4 turns, then up to 3 trader calls and 3 reviews). A `no_trade` route makes none.
- **M4-NFR-4 (time)** No wall-clock reads outside `clock.py`. Per-minute pacing makes a debated request take a few minutes (architecture §14). That's expected, and it stays well inside the 30-minute lock timeout.
- **M4-NFR-5 (state)** Everything new in `RequestState` is a Pydantic model or a primitive, so it stays serialisable for M8's checkpointer.

## 5. Interfaces

```python
# bullpit/domain.py (+)
ExitStyle = Literal["tight", "normal", "wide"]
SizeLimit = Literal["target", "risk", "cap", "cash"]
class SizedOrder(BaseModel, frozen=True):
    ticker: str
    shares: int
    reference_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    exit_style: ExitStyle
    cost: Decimal
    max_loss: Decimal
    max_gain: Decimal
    limit: SizeLimit                     # which limit set the Stage A size
    limit_shares: dict[SizeLimit, int]   # all four, for the report

# bullpit/llm/schemas.py (+): LLM replies
class DebatePoint(BaseModel):
    claim: str
    evidence_ids: list[str]
class DebateReply(BaseModel):
    points: list[DebatePoint]
    concessions: list[str]
    conviction: float = Field(ge=0.0, le=1.0)
class TraderReply(BaseModel):            # architecture Part 10 minus `ticker` (D-M4-5)
    action: Literal["buy", "no_trade"]
    target_weight: float = Field(ge=0.0, le=1.0)
    exit_style: Literal["tight", "normal", "wide"]
    confidence: float = Field(ge=0.0, le=1.0)
    decisive_evidence: list[str]
    reasoning: str
class RiskReviewReply(BaseModel):        # model validator: `shrink` requires `shares`
    decision: Literal["approve", "shrink", "veto"]
    shares: int | None = Field(default=None, ge=1)
    reason: str

# bullpit/state.py (+)
class CheckedPoint(DebatePoint, frozen=True):
    unsupported: bool
class DebateTurn(BaseModel, frozen=True):
    side: Literal["bull", "bear"]
    round: int
    points: list[CheckedPoint]
    concessions: list[str]
    conviction: float
    word_count: int
    over_word_limit: bool
    flagged: bool
class Recommendation(BaseModel, frozen=True):   # built by code from TraderReply
    ticker: str
    action: Literal["buy", "no_trade"]
    target_weight: Decimal                      # clamped
    exit_style: ExitStyle
    confidence: float
    decisive_evidence: list[str]                # registered IDs only
    reasoning: str
    flagged: bool
class RiskVerdict(BaseModel, frozen=True):
    decision: Literal["approve", "shrink", "veto"]
    reason: str
    requested_shares: int | None
    clamped: bool
    flagged: bool
class TradeAttempt(BaseModel, frozen=True):     # one trader call and what followed
    recommendation: Recommendation
    sized_order: SizedOrder | None = None       # Stage A
    blocked_reason: str | None = None           # Stage A hard rule
    verdict: RiskVerdict | None = None          # Stage B
class RequestState(BaseModel):                  # M3 fields, plus:
    debate: list[DebateTurn] = []
    attempts: list[TradeAttempt] = []
    sized_order: SizedOrder | None = None       # final order (after any shrink); set iff outcome == "buy"
    outcome: Literal["buy", "no_trade"] | None = None
    no_trade_reason: str | None = None

# bullpit/risk/sizing.py: pure maths
def exit_prices(reference: Decimal, atr: Decimal, *, stop_atr: Decimal,
                reward_risk: Decimal) -> tuple[Decimal, Decimal]: ...        # (stop, take_profit)
def share_limits(*, reference: Decimal, stop: Decimal, target_weight: Decimal, equity: Decimal,
                 cash: Decimal, held_value: Decimal, risk_pct: Decimal,
                 cap_pct: Decimal) -> dict[SizeLimit, int]: ...
def build_order(ticker: str, shares: int, *, reference: Decimal, stop: Decimal,
                take_profit: Decimal, exit_style: ExitStyle, limit: SizeLimit,
                limit_shares: dict[SizeLimit, int]) -> SizedOrder: ...        # cost, loss, gain

# bullpit/risk/rules.py: pass, block, shrink
def stage_a(*, ticker: str, reference: Decimal, atr: Decimal | None, exit_style: ExitStyle,
            target_weight: Decimal, account: Account, held_value: Decimal,
            stop_atr: Decimal, reward_risk: Decimal, risk_pct: Decimal,
            cap_pct: Decimal) -> SizedOrder | str: ...                        # str = block reason
def shrink(order: SizedOrder, shares: int) -> tuple[SizedOrder, bool]: ...  # (order, clamped)
def loss_warning(history: Sequence[tuple[date, Decimal]], as_of: date, *,
                 drop_pct: Decimal, days: int) -> bool | None: ...
```

In the architecture's Part 0 naming, `recommendation` and `risk_verdict` are the last attempt's fields (`attempts[-1]`), and `sized_order` is the final order. The list keeps every veto round for the journal and the trader's retry prompt.

## 6. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| **M4-AC-1** | The architecture's worked example (equity $100,000, cash $96,000, reference $182, ATR $4, normal, 6% target, nothing held) gives exactly stop $174.00, take-profit $194.00, **32 shares**, cost $5,824.00, max loss $256.00, gain $384.00, set by `target`, with limit shares 32 / 125 / 54 / 527 | **Automated** |
| **M4-AC-2** | Property test over random valid inputs, for every exit style: shares ≥ 0; cost ≤ cash; shares × (ref − stop) ≤ 1% of equity; held value + cost ≤ 10% of equity; take-profit − ref within $0.02 of 1.5 × (ref − stop) (cent rounding) | **Automated** (hypothesis) |
| **M4-AC-3** | Each hard rule blocks with its FR-9 reason: a holding at or above the cap gives "Per-stock cap reached…"; also no cash, missing ATR, a stop at or below 0, and a size that rounds to 0 shares | **Automated** (parametrised) |
| **M4-AC-4** | A debate point citing an unregistered ID (or none) is marked unsupported in the state's transcript and in `debate_turns` | **Automated** (graph) |
| **M4-AC-5** | A Stage B `shrink` to more shares than Stage A is clamped to the Stage A order with `clamped = True` and a warning; a real shrink recomputes cost, loss and gain | **Automated** (rules unit test) |
| **M4-AC-6** | A scripted veto, veto, veto run ends in `no_trade` after exactly 2 trips back to the trader: 3 trader calls, 3 reviews, 3 `recommendations` rows, the FR-13 reason | **Automated** (graph) |
| **M4-AC-7** | Real runs on the pinned models (AAPL, MSFT, JPM at 2024-10-18 backtest, plus one live request) each end in a `SizedOrder` or "no trade" with a reason. The debate transcripts are read by hand for quality. The real tokens of `bull.md`, `bear.md`, `trader.md` and `risk_review.md` are recorded and compared with §14, and the allowance is revised per FR-21 | Manual: output and `llm_calls` query pasted |
| **M4-AC-8** | On recorded fixtures, the graph's buy path gives outcome `buy`, a final `SizedOrder`, 4 `debate_turns` rows, 1 `recommendations` row, and `requests.outcome = 'buy'`. The weak-signals path gives `no_trade` with no large-model call | **Automated** (graph) |
| **M4-AC-9** | The loss-warning function returns `True` for a drop above 5% over 7 days, `False` for a smaller drop, and `None` with no history old enough | **Automated** (rules unit test) |
| **M4-AC-10** | `alembic upgrade head` on an empty DB gives a schema matching `models.py`, and after a real run the M4 rows of one request are complete | **Automated** (migration test) + Manual (rows pasted) |
| **M4-AC-11** | Each agent node's branches behave as specified. **Debate:** ID normalisation, a point with no IDs, the word-limit flag, a flagged reply giving an empty turn and a warning, `[unsupported]` in later prompts. **Trader:** ticker from the request, weight clamp and decisive-ID filter each with a warning, `no_trade` and flagged outcomes, the retry prompt listing each vetoed size and reason. **Review:** approve, shrink, clamp (with the `risk_review_clamped` log event), veto, the final veto, flagged | **Automated** (node tests) |
| **M4-AC-12** | Every graph path ends as specified: buy; weak signals; trader `no_trade`; Stage A block (no review call); veto limit; a flagged debate turn (the debate continues); an exception in an M4 node (request `failed`, lock released, re-raised). Each path's journal rows are checked | **Automated** (graph) |
| **M4-AC-13** | Each M4 template renders with `StrictUndefined` and starts with its fixed first line. A worst-case prompt (15 headlines, a full transcript of 150-word turns, 2 earlier vetoes) estimates under the per-call ceiling with the current allowance | **Automated** |
| **M4-AC-14** | `bullpit request` prints the FR-18 debate, attempts and `OUTCOME:` line for a buy and for a no trade, with exit code 0 | **Automated** (CLI test, `run_request` replaced by a fixed state) |
| **M4-AC-15** | Every FR-20 setting defaults to its architecture value | **Automated** |

AC-1 to AC-7 are the dev-plan's drafts, made concrete. AC-8 is §7.2's graph happy path, AC-9 covers C16, AC-10 covers the journal, and AC-11 to AC-15 are the full-coverage additions (D-M4-14).

## 7. Decisions made in this document

The owner approves these with this document. None of them changes the system's behaviour, so neither `architecture.md` nor dev-plan §3 needs a new deviation.

| # | Decision | Reason |
|---|---|---|
| D-M4-1 | **Two agents, two prompts, one module.** Bull and bear each get their own prompt template (`bull.md`, `bear.md`); their Python lives in one `agents/debate.py` (the `bull` and `bear` nodes and the code checks they share), not in `bull.py` + `bear.py` as dev-plan §5 names them | The prompt is where an agent's role lives, so each side gets its own, with no `if bull … else …` branching the model has to read past. Separate templates also give separate `prompt_version` hashes, and `llm_calls` measures tokens per template (M3-T-17), so bull and bear costs stay separately measurable (FR-21). The Python for the two sides is identical (same call, same ID and word checks, same turn record); split across `bull.py` and `bear.py` it would need a third module for the shared part (CLAUDE.md: one place for each fact, no one-function modules). The shared rules text is repeated in both templates on purpose: a Jinja `include` wouldn't change the including template's version hash. Architecture §15 lists agents, not files; nothing in the system's behaviour changes. T-1 updates dev-plan §5's file names |
| D-M4-2 | **`risk/sizing.py` (exits + share limits, pure maths) and `risk/rules.py` (Stage A pass/block, only-shrink, loss warning)**; no separate `exits.py` | Exits are one 5-line function and stay so: M6's exit *fills* belong to `broker/sim.py`, and M8's anchoring decision changes no code here. A module for it would break CLAUDE.md's no-one-function-modules rule. Maths and decisions are still split |
| D-M4-3 | The 150-word limit is in the prompt and **measured by code and flagged, not enforced with `max_tokens`** | A low `max_tokens` starves gpt-oss's reasoning and returns nothing (findings A5). The flag makes overruns visible in the journal; truncating would cut arguments mid-point |
| D-M4-4 | "Unsupported" also covers a point that **cites no ID**; unsupported points stay in the transcript, labelled | Part 9 says both sides *must* cite IDs. Keeping the label (not deleting the point) lets the bear, trader and reviewer discount it, and M7 can count them |
| D-M4-5 | The trader's reply has no `ticker`: code fills it; `target_weight` is clamped to [0, 10%]; unknown decisive IDs are dropped with a warning | The LLM can't name a different stock (same principle as D11). The dev-plan asked for the clamp and "IDs must exist"; dropping keeps a sound recommendation instead of discarding it for one bad citation |
| D-M4-6 | **Each earlier veto (what was vetoed and why) goes into the trader's retry prompt** | Calls run at temperature 0 with a cached response: an unchanged prompt would return the identical cached reply, so the loop would be pointless. Showing the vetoed size too lets the trader actually respond ("too big for this confidence" means little without it). The retry prompt is still deterministic, so M6 backtests stay repeatable from the cache |
| D-M4-7 | An **invalid** trader or review reply → "no trade", marked `flagged` in `recommendations`; any **exception** after the brain fails the request | This is architecture Part 3's rule (safe default, flagged) with "no trade" as the safe default: a missing trader or reviewer can't be replaced by a neutral guess the way a missing analyst can. The flag lets M7 tell a glitch from a real "no trade" decision, so glitches don't pass as good judgment. An outage or quota error recorded as "no trade" would do exactly that, so it fails the request (M6 pauses on quota) |
| D-M4-8 | Exit prices are rounded to the cent (half up), and sizing uses the rounded stop; ties between limits go to the first in the order target, risk, cap, cash | Brokers take cents. Sizing against the rounded stop keeps the 1% loss limit exact. The tie rule makes "which limit set the size" deterministic |
| D-M4-9 | The loss warning is built and tested now but **first called in M6/M8** | Approved in dev-plan C16: it's risk logic, so it's written and tested with the rest of the risk rules, and both brokers' equity histories feed the same function later. Calling it now with an empty history would only add a permanent "unknown" warning. M5's report shows it as "not available" until then |
| D-M4-10 | `shrink` needs `shares ≥ 1` (the schema checks it, so a bad reply gets the gateway's retry); a shrink to ≥ Stage A shares is clamped, not refused | The dev-plan asks for a clamp (M4-AC-5). A "shrink to 0" is really a veto, and the model has a word for that |
| D-M4-11 | The reviewer sees the signals summary and transcript, not the raw evidence list; the trader sees the evidence list (it must cite decisive IDs) | Keeps both large-model prompts compact under the 8K per-minute limit. The debate already puts the evidence into words for the reviewer |
| D-M4-12 | Backtest-mode sizing reads today's Alpaca paper account until M6 (D-M3-6, carried) | No simulated account exists before M6; M4's backtest numbers are for checking the logic, not results |
| D-M4-13 | Exit multiples and the reward-to-risk ratio are **settings**, unlike M3's indicator periods (D-M3-10) | Architecture §6 calls them "starting values you can tune", and CLAUDE.md lists ATR multipliers as settings. Stop multiple × reward-to-risk keeps every style at 1.5 by construction |
| D-M4-14 | **Full offline test coverage for M4**, on the owner's instruction (2026-09-29): automated tests go beyond [dev-plan §7](../../dev-plan.md#7-testing-strategy) to cover every M4 behaviour that can run without the network. §7 is unchanged for other milestones unless the owner says otherwise | The owner asked for everything to be covered. Only what no offline test can judge stays manual: the real model's argument quality and real token counts (AC-7) |

**Noted, not changed:** Stage A checks cash at the reference price, but the entry fills at the next open. A gap up could make the cost exceed cash. M6's sim reserves cash and downsizes (M6-AC-3). For live, M8's staleness check (2%) limits the gap, and the approval step must re-check cash, because the Alpaca account has margin buying power that would silently cover the difference (findings A13).

## 8. Open questions for the owner

None. Every choice above is a default with its reason; say if you want any changed.

---

# Part B: Plan

## 9. Module design

### 9.1 Files created or changed

```text
.env.example                     + FR-20 settings
bullpit/
  config.py                      + FR-20 settings
  domain.py                      + ExitStyle, SizeLimit, SizedOrder
  state.py                       + CheckedPoint, DebateTurn, Recommendation, RiskVerdict, TradeAttempt; RequestState fields
  graph.py                       + risk_sizing node, the M4 edges; brain sets the no_trade outcome (FR-1)
  risk/sizing.py                 new: exit_prices, share_limits, build_order
  risk/rules.py                  new: stage_a, shrink, loss_warning
  agents/debate.py               new: bull_node, bear_node, the evidence-ID and word checks
  agents/trader.py               new: trader_node
  agents/risk_review.py          new: risk_review_node
  llm/schemas.py                 + DebatePoint, DebateReply, TraderReply, RiskReviewReply
  llm/prompts/bull.md            new
  llm/prompts/bear.md            new
  llm/prompts/trader.md          new
  llm/prompts/risk_review.md     new
  journal/models.py              + Request.outcome, no_trade_reason; DebateTurnRecord, RecommendationRecord
  journal/migrations/versions/0003_debate_recommendations.py   new
  runners/request.py             _finalize writes the M4 rows
  cli.py                         prints the M4 part (FR-18)
tests/
  risk/__init__.py               new
  risk/test_sizing.py            new: AC-1, AC-2
  risk/test_rules.py             new: AC-3, AC-5, AC-9
  agents/__init__.py             new
  agents/conftest.py             new: a board-ready RequestState and a scripted completion fake
  agents/test_debate.py          new: AC-11 (debate)
  agents/test_trader.py          new: AC-11 (trader)
  agents/test_risk_review.py     new: AC-11 (review)
  llm/test_prompts.py            new: AC-13
  journal/test_migrations.py     new: AC-10 (schema)
  test_cli.py                    new: AC-14
  test_config.py                 new: AC-15
  test_graph.py                  RecordingLLM answers the M4 templates; AC-4, AC-6, AC-8, AC-12
docs/dev-plan.md                 §5 M4 file names (D-M4-1, D-M4-2); status line
README.md                        quick start: what a full request now prints
```

`bullpit/risk/` already exists as an empty package from M0.

### 9.2 Dependency direction

```text
graph ──► agents/debate, trader, risk_review ──► llm/gateway, state
  └────► risk/rules ──► risk/sizing ──► domain          (pure, mypy strict)
```

The Stage A node sits in `graph.py`, like M3's board and brain nodes: it reads settings, maps the exit style to its stop multiple and calls `stage_a`. `risk/` never sees `Settings` (NFR-2).

### 9.3 Nodes

| Node | Reads | Writes | Calls |
|---|---|---|---|
| `brain` (changed) | board | `route`, `warnings`; on `no_trade` also `outcome`, `no_trade_reason` | — |
| `bull`, `bear` | board, `debate` | `debate` (+1 turn), `warnings` | `call_llm(LARGE, "bull.md" / "bear.md")` |
| `trader` | board, `debate`, account, position, `attempts` | `attempts` (+1), `warnings`; on `no_trade`/flagged: `outcome`, `no_trade_reason` | `call_llm(LARGE, "trader.md")` |
| `risk_sizing` | last attempt, prices, indicators, account, position | last attempt's `sized_order` or `blocked_reason`; if blocked: `outcome`, `no_trade_reason` | `stage_a` |
| `risk_review` | last attempt, board, `debate` | last attempt's `verdict`, `warnings`; on approve/shrink: `sized_order`, `outcome = buy`; on final veto or flagged: `outcome`, `no_trade_reason` | `call_llm(LARGE, "risk_review.md")`, `shrink` |

The bull and bear nodes share one `_turn(side, state, deps)` function; the side picks the template. The round is `len(state.debate) // 2 + 1`.

### 9.4 Graph wiring

```python
graph.add_conditional_edges("brain", lambda s: "bull" if s.route == "debate" else END, ["bull", END])
graph.add_edge("bull", "bear")
graph.add_conditional_edges("bear", _after_bear, ["bull", "trader"])          # len(debate) < 2 × rounds
graph.add_conditional_edges("trader", _after_trader, ["risk_sizing", END])    # outcome set → END
graph.add_conditional_edges("risk_sizing", _after_sizing, ["risk_review", END])
graph.add_conditional_edges("risk_review", _after_review, ["trader", END])    # veto, trips left
```

"Trips left" means the vetoes so far are ≤ `risk_max_vetoes`, counted from `attempts`. The M3 edge `brain → END` is replaced. LangGraph's default recursion limit (25) covers the longest path (≈ 16 steps).

### 9.5 Prompts

Four compact Jinja2 templates (M2's loader, no `include`s, D-M4-1), each with a one-line role, the inputs of FR-2 / FR-5 / FR-11, the reply format and "JSON only". The first lines are fixed so the test fake can tell them apart: `You are the bull researcher`, `You are the bear researcher`, `You are the trader`, `You are the risk manager`. Facts are listed as `ID: fact`. Transcript lines look like `Bull, round 1: claim (T1, F2) [unsupported]`. The trader's exit styles are described as `tight: stop 1.5 ATR below, target 2.25 ATR above` and so on, rendered from the settings. The retry section lists `Veto 1: you recommended 6% normal, sized to 32 shares; the risk manager said: {reason}`.

## 10. Data model

Migration `0003_debate_recommendations` (batch mode for the `requests` columns, as in `0002`):

| Table | Column | Type | Notes |
|---|---|---|---|
| `requests` | `outcome` | `TEXT` | `buy` \| `no_trade`; null when rejected or failed |
| | `no_trade_reason` | `TEXT` | |
| `debate_turns` | `id` | `INTEGER PK` | |
| | `request_id` | `TEXT NOT NULL`, FK, indexed | |
| | `round`, `side` | `INTEGER`, `TEXT` | |
| | `points` | `JSON` | `[{claim, evidence_ids, unsupported}]` |
| | `concessions` | `JSON` | |
| | `conviction` | `FLOAT` | |
| | `word_count`, `unsupported_count` | `INTEGER` | |
| | `over_word_limit`, `flagged` | `BOOLEAN` | |
| `recommendations` | `id` | `INTEGER PK` | One row per trader attempt |
| | `request_id` | `TEXT NOT NULL`, FK, indexed | |
| | `attempt` | `INTEGER` | 1, 2, 3 |
| | `action`, `exit_style` | `TEXT` | |
| | `target_weight` | `TEXT` | `Decimal` as a string (SQLite has no exact decimal) |
| | `confidence` | `FLOAT` | M7's Brier score |
| | `decisive_evidence` | `JSON` | |
| | `reasoning` | `TEXT` | |
| | `flagged` | `BOOLEAN` | Trader reply invalid |
| | `sized_order` | `JSON` | Stage A order, `Decimal`s as strings; null when blocked or not reached |
| | `blocked_reason` | `TEXT` | |
| | `review_decision`, `review_reason` | `TEXT` | |
| | `review_shares` | `INTEGER` | Requested by a shrink |
| | `review_clamped`, `review_flagged` | `BOOLEAN` | |
| | `final_order` | `JSON` | Set only on the attempt that produced outcome `buy` |

ORM classes are `DebateTurnRecord` and `RecommendationRecord` (M3's `SignalRecord` convention).

## 11. Key algorithms

### 11.1 Stage A (`risk/rules.stage_a`)

```text
if atr is None or atr <= 0 or reference <= 0:  return "ATR or price not available."
if cash <= 0 or equity <= 0:                    return "No cash available."
if held_value >= cap_pct × equity:              return "Per-stock cap reached: …"
stop, tp = exit_prices(reference, atr, stop_atr, reward_risk)      # each rounded to 0.01, half up
if stop <= 0 or stop >= reference:              return "Exit prices invalid (stop …)."
limits = share_limits(...)                      # each floor(…), never below 0
shares = min(limits.values());  limit = first of (target, risk, cap, cash) equal to shares
if shares == 0:                                 return "Size rounds to 0 shares (set by the … limit)."
return build_order(...)                         # cost = shares × ref; loss = shares × (ref − stop); gain = shares × (tp − ref)
```

Every input is already `Decimal`: the reference price comes from the snapshot, and ATR and the target weight are converted with `Decimal(str(x))` in the node, which is the one float-to-money boundary (dev-plan §2.2).

### 11.2 Stage B (`risk_review_node`)

```text
reply flagged                 → verdict(flagged); outcome no_trade "Risk review reply was invalid."
approve                       → sized_order = stage A; outcome buy
shrink, shares < stage A      → sized_order = shrink(stage A, shares); outcome buy
shrink, shares ≥ stage A      → sized_order = stage A; clamped; log risk_review_clamped; warning; outcome buy
veto, vetoes ≤ max            → back to trader (edge)
veto, vetoes > max            → outcome no_trade "Risk manager vetoed {n} times: {reason}"
```

### 11.3 Debate checks

```text
unsupported(point) = not point.evidence_ids or any(id not in board.evidence for id in point.evidence_ids)
word_count(turn)   = Σ len(text.split()) over every claim and concession
```

### 11.4 Loss warning

```text
base = latest (d, e) in history with d <= as_of − days;  none → None
now  = latest (d, e) in history with d <= as_of;         none → None
return (base.e − now.e) / base.e > drop_pct
```

## 12. Error handling

| Where | Error | Result |
|---|---|---|
| Debate turn | Flagged reply | Empty flagged turn, warning, the debate continues (FR-3) |
| Trader | Flagged reply | `no_trade` "Trader reply was invalid." |
| Trader | `target_weight` over the cap; unknown decisive IDs | Clamped / dropped, warning (FR-6) |
| Stage A | Hard rule fails | `no_trade` with the FR-9 reason |
| Stage B | Flagged reply | `no_trade` "Risk review reply was invalid." |
| Stage B | Shrink not below Stage A | Clamped, logged, warning (FR-12) |
| Any M4 node | Any exception (`LLMUnavailable`, `QuotaExhausted`, `PromptTooLarge`, bug) | Request `failed`, lock released, re-raised; the CLI prints it and exits 1 (FR-15) |

## 13. Test and verification plan

Full offline coverage (D-M4-14). Everything runs without the network, in seconds. No real Groq, Alpaca, SEC or yfinance call is made (`pytest-socket`).

**`tests/risk/test_sizing.py`**

| Test | AC |
|---|---|
| `test_worked_example` | AC-1: every number of the architecture's example, exactly |
| `test_limits_hold_for_any_input` | AC-2: hypothesis over reference $1–$5,000, ATR from $0.01 to reference ÷ 4, equity $1,000–$10M, cash 0–equity, held value 0–15% of equity, target weight 0–0.10, every exit style; blocked inputs are skipped, and each passed order satisfies the five invariants |
| `test_exit_table` (parametrised) | FR-7: with reference $100 and ATR $2, tight / normal / wide give stop and take-profit at 1.5 / 2.25, 2 / 3 and 3 / 4.5 ATR; a price needing rounding rounds half up to the cent |
| `test_existing_holding_and_tie_break` | FR-8: a held value lowers the cap shares; when two limits give the same count, the first in the order target, risk, cap, cash is reported |

**`tests/risk/test_rules.py`**

| Test | AC |
|---|---|
| `test_hard_rules_block` (parametrised) | AC-3: price ≤ 0, ATR `None` or 0, no cash, equity ≤ 0, cap reached, stop ≤ 0 (ATR huge), stop rounding up to the reference (ATR $0.001), 0 shares (reference above equity × 10%) → each FR-9 reason |
| `test_first_failing_rule_wins` | FR-9 order: inputs that break both the cash and the cap rule give the cash reason |
| `test_shrink_only_lowers` | AC-5: a shrink to 40 on a 32-share order is clamped (`clamped = True`, same order); a shrink to 20 recomputes cost $3,640, loss $160, gain $240 |
| `test_loss_warning` | AC-9: a 6% drop → `True`, a 4% drop → `False`, exactly 5% → `False`, history too short → `None` |

**`tests/agents/`**: node tests (AC-11). `conftest.py` builds a `RequestState` that has passed the board (fixed signals, evidence T1–T6, F1–F5, S1–S3; account $100,000 / $96,000; reference $182; ATR $4) and a scripted completion fake that returns queued replies and records prompts. Each node is called directly with the M3 `settings` and `sessions` fixtures.

| File | Tests |
|---|---|
| `test_debate.py` | IDs `" t1"`, `"F2 "` normalised and supported; a point with no IDs and one citing `T99` are unsupported, and `unsupported_count` = 2; a 170-word turn is kept with `over_word_limit`; a flagged reply → empty turn, conviction 0, `flagged`, a warning; round and side follow the turn count; the bear's prompt shows the bull's unsupported point labelled `[unsupported]` |
| `test_trader.py` | `ticker` comes from the request; weight 0.25 → clamped to 0.10 with a warning; decisive `["T1", "X9"]` → `["T1"]` with a warning; `no_trade` → outcome and the FR-6 reason; flagged → outcome `no_trade`, `Trader reply was invalid.`, `flagged`; on a retry the prompt lists each earlier veto with its weight, style, shares and reason |
| `test_risk_review.py` | approve → `sized_order` = Stage A, outcome `buy`; shrink 20 → recomputed order; shrink 40 → Stage A order, `clamped`, a warning and a `risk_review_clamped` log event (structlog `capture_logs`); a veto with trips left → verdict recorded, no outcome; the third veto → outcome `no_trade` with the FR-13 reason; flagged → `Risk review reply was invalid.` |

**`tests/llm/test_prompts.py`** (AC-13): each of `bull.md`, `bear.md`, `trader.md` and `risk_review.md` renders from the agents' own variable-building code with `StrictUndefined`, starts with its fixed first line, and contains no `{% include`. A worst-case state (15 headlines of 120 characters, 3 transcript turns of 150 words each, 2 earlier vetoes) gives a gateway estimate (`_estimate_tokens`) under `llm_tpm_limit` for every template.

**`tests/journal/test_migrations.py`** (AC-10): `alembic upgrade head` on an empty temp-file DB, then Alembic's `compare_metadata` against `Base.metadata` returns no differences. This covers `0001`–`0003`.

**`tests/test_cli.py`** (AC-14): typer's `CliRunner` with `run_request`, the Alembic upgrade and the broker factory patched out. A fixed buy state prints the turns, the attempt and `OUTCOME: BUY 32 AAPL @ ref 182.00, stop 174.00, take-profit 194.00, max loss 256.00, gain 384.00 (set by target)`; a fixed no-trade state prints `OUTCOME: NO TRADE: {reason}`. Both exit with code 0.

**`tests/test_config.py`** (AC-15): `Settings(_env_file=None)` has every FR-20 default.

**`tests/test_graph.py`**: the M3 fixtures and fake broker are unchanged. `RecordingLLM` also answers `bull.md`, `bear.md`, `trader.md` and `risk_review.md` (recognised by the first line) with scripted replies, and counts calls per template. The graph tests' settings raise `llm_tpm_limit` so the gateway's real per-minute pacing doesn't sleep through the 6–10 large calls; this is a test-only setting override, with no code change.

| Test | AC |
|---|---|
| M3's debate-route test, extended to `test_buy_path` | AC-8, AC-4: the bull's round-1 reply cites `T99` in one point. Checks outcome `buy`, a `SizedOrder` matching Stage A on the fixture's close and ATR, 4 turns (the `T99` point unsupported in state and in `debate_turns`), 1 `recommendations` row with `final_order`, `requests.outcome = 'buy'` |
| M3's weak-signals test, extended | AC-8: outcome `no_trade` with the FR-1 reason, 0 calls to the M4 templates |
| `test_veto_limit` | AC-6: the reviewer always vetoes. Checks outcome `no_trade` with the FR-13 reason, 3 trader and 3 review calls, 3 `recommendations` rows; the 2nd and 3rd trader prompts contain the earlier veto reasons |
| `test_trader_no_trade` | AC-12: outcome `no_trade`, 0 review calls, 1 `recommendations` row with no `sized_order` |
| `test_stage_a_block` | AC-12: the fake broker holds AAPL worth 12% of equity. Checks outcome `no_trade` "Per-stock cap reached…", 0 review calls, `blocked_reason` in the row |
| `test_flagged_debate_turn` | AC-12: the bear's round-1 reply is invalid twice. Checks that the debate still has 4 turns (one `flagged`), the request completes, and the row has `flagged = 1` |
| `test_m4_node_exception` | AC-12: the trader call raises `LLMUnavailable`. Checks that `run_request` re-raises, status is `failed`, the debate rows are still recorded, and a new request for the ticker isn't refused (lock released) |

Not tested automatically: the real models' argument quality and real token counts (AC-7), since both need real Groq calls. Everything else in M4 has an automated test.

**Manual checks** (evidence pasted into `task.md`):

| Check | How |
|---|---|
| AC-7 | `bullpit request` for AAPL, MSFT, JPM `--mode backtest --as-of 2024-10-18` and one live request: outcomes pasted, one transcript read in full and judged (cites IDs? addresses the other side? invents numbers?); `llm_calls` per template (input, output, reasoning: max and mean); the per-request large-model total against §14's 18–22K; the new allowance and its ceiling check |
| AC-10 | One real request's `debate_turns` and `recommendations` rows pasted (the schema itself is tested) |

## 14. Work order

`task.md` breaks this into tasks, in this order:

1. Docs on the new branch (this file, `task.md`, dev-plan §5 names).
2. Settings.
3. `domain.SizedOrder`, `risk/sizing.py` and `test_sizing.py`.
4. `risk/rules.py` and `test_rules.py`.
5. Schemas and state; the agents' test fixtures.
6. Debate: nodes, checks, `bull.md`, `bear.md`, `test_debate.py`.
7. Trader: node, `trader.md`, `test_trader.py`.
8. Risk review: node, `risk_review.md`, `test_risk_review.py`.
9. Prompt tests; settings-defaults test.
10. Graph wiring, the Stage A node, the brain's outcome.
11. Journal models and migration `0003`; runner `_finalize`; migration test.
12. CLI output and its test.
13. Graph tests.
14. Real runs, transcripts, tokens and the allowance (AC-7, AC-10).
15. Acceptance: README, retrospective, then merge and tag when the owner asks.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Large-model replies (reasoning included) are bigger than the 1,869-token allowance | `json_validate_failed`, so flagged turns or no trade | Measured in AC-7; FR-21 re-derives the allowance; flagged counts are checked over the real runs |
| Prompts plus allowance approach the 8K per-call ceiling (15 headlines + transcript) | `PromptTooLarge` fails the request | NFR-3's target; the largest prompt is measured in AC-7. If it's too big, shorten the headline facts in the debate prompt (a prompt change, not a scope change) |
| The reviewer always approves, or always vetoes | Stage B adds nothing, or costs extra calls | Measured and noted in the retrospective, not tuned (dev-plan M4 risks); M7 measures it properly |
| The models ignore the ID-citation or word rules | Many unsupported points or overruns | They're flagged and counted in the journal; the prompt wording is adjusted once if the AC-7 transcripts are poor |
| Per-minute pacing makes a debated request take 3–5 minutes | Slow manual checks | Expected (architecture §14); the response cache makes re-runs free |
| Rounding at the per-share-risk edge | The 1% limit is broken by a cent | `Decimal`, sizing on the rounded stop, and the property test |
