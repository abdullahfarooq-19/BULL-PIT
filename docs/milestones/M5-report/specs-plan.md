# M5 — Report generator: specs and plan

| | |
|---|---|
| **Status** | Reviewed against the M0–M4 code on 2026-09-29 and corrected (§7.1). On the owner's instruction ("if it is good to go, create the task.md"), [`task.md`](task.md) is written. Implementation waits for the owner's green light |
| **Date** | 2026-09-29 |
| **Size** | M: one `specs-plan.md` + `task.md` ([dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents)) |
| **Branch** | `m5-report`, from `master` once M4 is merged and tagged `m4` |
| **Depends on** | M4 (debate, trader, risk manager). All tasks done; merge and tag `m4` pending (M4-T-15) |
| **Sources** | [dev-plan §5 M5](../../dev-plan.md#m5--report-generator), [§6.1](../../dev-plan.md#61-safety), [§7](../../dev-plan.md#7-testing-strategy), [§8](../../dev-plan.md#8-data-model-evolution), [§10.1](../../dev-plan.md#101-scope-review-revision-4) (C2, C3, C14, C16); [architecture Part 12, §7](../../architecture.md#part-12--report-generator-both), [§14](../../architecture.md#14-free-tier-budget); M1 D-M1-6 (`get_market_context`); M4 [specs-plan](../M4-debate-trader-risk/specs-plan.md) D-M4-7, D-M4-9 and [retrospective](../M4-debate-trader-risk/task.md#retrospective) |

Part A says **what** M5 delivers and how it's accepted. Part B says **how** it gets built. Neither restates the architecture or the dev plan; they link to them.

---

## Contents

**Part A: Specs**: [1 Goal](#1-goal) · [2 Scope](#2-scope) · [3 Functional requirements](#3-functional-requirements) · [4 Non-functional requirements](#4-non-functional-requirements) · [5 Interfaces](#5-interfaces) · [6 Acceptance criteria](#6-acceptance-criteria) · [7 Decisions](#7-decisions-made-in-this-document) · [8 Open questions](#8-open-questions-for-the-owner)

**Part B: Plan**: [9 Module design](#9-module-design) · [10 Data model](#10-data-model) · [11 Key algorithms](#11-key-algorithms) · [12 Error handling](#12-error-handling) · [13 Tests and checks](#13-test-and-verification-plan) · [14 Work order](#14-work-order) · [15 Risks](#15-risks)

---

# Part A: Specs

## 1. Goal

Every request that reaches the graph ends with **the report the owner decides from**: a structured object with the architecture's 10 sections, in which code writes every number and a small LLM writes only the plain-language parts, checked so it can't add a number or an evidence ID that isn't already in the report. The architecture's done-when: *"A readable report for both 'buy' and 'no trade'."*

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | `report/model.py`: the `Report` object (JSON-serialisable), sections in architecture §7's order | Part 12, §7 |
| S2 | `report/builder.py`: code fills every number; market context (SPY vs its 200-day average, VIX label); data notes; the report node that runs the LLM writing step | Part 12 |
| S3 | LLM writing (small model, `report.md`): summary, strongest bull and bear points, what the bull conceded, what's unresolved, what would change the view | Part 12 |
| S4 | `report/number_check.py`: numbers and evidence IDs in the LLM text must already be in the report; one retry, then a code-built fallback | Part 12; dev-plan §7.1 |
| S5 | `report/templates/report.md`: the Markdown rendering (no HTML template, C2) | C2 |
| S6 | Graph: a `report` node before `END` on **every** path, including request-check rejections | Part 12 ("every request") |
| S7 | Journal: `reports` table holding the structured report as JSON only (migration `0004`, C3) | Part 15, dev-plan §8 |
| S8 | `bullpit request` prints the Markdown report | D6 |
| S9 | Real token count per request (one buy, one no trade); architecture §14 updated with measured numbers; allowance re-derived | C14 |

### 2.2 Out of scope

- The approval gate, staleness check, expiry, order placement (M6 sim, M8 Alpaca). Section 10 (Actions) is **data only** in M5: the share count the owner may approve up to.
- Feeding the loss warning (M6/M8, C16). M5 shows it as "not available" (D-M4-9).
- Dashboard rendering of the report (M8). A CLI command to re-render a stored report (M8's `GET /requests/{id}/report` is that path).
- Any change to the analysts, debate, trader or risk logic.

## 3. Functional requirements

**Report object and sections (Part 12, §7)**

- **M5-FR-1 Sections.** The `Report` holds the architecture's 10 sections in order. Which ones apply depends on how the request ended:

  | § | Section | Buy | No trade (weak signals) | No trade (after debate: trader, Stage A block, veto limit, invalid reply) | Rejected by request check |
  |---|---|---|---|---|---|
  | 1 | Header: ticker, company, report time, price-data date (`as_of`), mode | ✓ | ✓ | ✓ | ✓ |
  | 2 | Recommendation: outcome, confidence, summary sentence, **the reason** for no trade / rejection | ✓ | ✓ | ✓ | ✓ (code text) |
  | 3 | Suggested order: shares, cost, % of equity, stop, take-profit, max loss, max gain, exit style | ✓ | — | — | — |
  | 4 | Analysts: three signals with direction, confidence, flag, evidence | ✓ | ✓ | ✓ | — |
  | 5 | Debate: strongest bull point, strongest bear point, what the bull conceded, unresolved; final convictions; unsupported-point count | ✓ | — (no debate) | ✓ | — |
  | 6 | Risk manager: which limit set the size (all four limit shares), each attempt's Stage A result and review decision with reasons, loss warning | ✓ | — | ✓ (the attempts that ran) | — |
  | 7 | What would change the view | ✓ | ✓ | ✓ | — |
  | 8 | Market context | ✓ | ✓ | ✓ | — |
  | 9 | Data notes: models used, news headlines used, latest filing (form, date), price source, every warning | ✓ | ✓ | ✓ | ✓ (warnings only) |
  | 10 | Actions: approve up to the order's shares, or reject | ✓ | — | — | — |

  A section that doesn't apply is `None` in the object and absent from the Markdown. Every report ends with the disclaimer line *"Research, not financial advice. Paper trading only."* (dev-plan §6.1).
- **M5-FR-2 Outcome and reason.** Outcome is `buy` or `no_trade` (from `state.outcome`), or `rejected` when the request check rejected the request. The reason is written by code, in one of two ways:
  - **Code-written reasons** (weak signals, trader reply invalid, every Stage A block, review reply invalid, request-check rejection) are copied verbatim from `state.no_trade_reason` or `state.rejection`.
  - **Two M4 reasons quote LLM text**: the trader's no-trade reason and the veto limit. For these, `reason` is the code part (`Trader recommended no trade.` / `Risk manager vetoed {n} times.`) and the quoted text (the trader's `reasoning` / the last veto's reason) goes in `reason_detail`, masked under FR-3.

  Confidence is the last trader attempt's confidence, `None` if the trader never ran. A rejection's `summary` is `Rejected: {rejection}` (code); every other summary is prose (FR-5).
- **M5-FR-3 Code fills every number.** Every number in the report comes from state or settings, formatted by code: money as `$5,824.00`, percentages to one decimal (`5.8%`), confidences to two (`0.62`), shares as integers. `% of equity` = cost ÷ equity. Nothing numeric is ever taken from LLM output. **Text quoted from M4's LLMs** (`reason_detail`, each attempt's `review_reason`) is shown with every number that isn't in the code-written report replaced by `[?]` (D-M5-13). So no unchecked number reaches the owner, even outside the prose.

**Market context (§7 section 8)**

- **M5-FR-4** From `get_market_context(as_of, price_history_sessions)` (data layer, date guard applies):
  - **SPY:** last close vs the simple average of the last 200 closes: `above` or `below`. Fewer than 200 sessions → "not available".
  - **VIX:** last close, labelled `low` (< `vix_low_threshold`, 15), `high` (> `vix_high_threshold`, 25) or `normal` (D-M5-6).
  - **One line** explaining what the combination means, chosen by code from a fixed table (e.g. SPY above and VIX low: *"The broad market is in an uptrend and calm."*).
  - A data failure (`DataUnavailable`) gives a `MarketContext` with every value `None` and the explanation `Market context not available.`, plus a data-notes warning; the request continues. `Report.market` is `None` only for rejections.

**LLM writing (Part 12)**

- **M5-FR-5 Prompt.** One small-model call on `report.md`. It gets the **code-only report** (sections 1–9 rendered as Markdown with the prose left out, quoted LLM text already masked, and no request ID or timestamp) and, if there was a debate, the transcript with every number that isn't in the code-only report replaced by `[?]`. So it only ever sees numbers it's allowed to use (D-M5-2). It replies with `ReportProse` (§5). With no debate, the four debate fields are ignored by code.
- **M5-FR-6 Number and ID check.** Code extracts every number from the reply's text fields and checks it against the **allowed set**: the numbers in the code-only report (algorithm §11.1). Formatting variants of an allowed number pass (`$5,824`, `5824`, `5,824.00`, `5.8%`); a new number fails (`$200` when no $200 is in the report). Every evidence ID cited in the text (`T1`, `F2`, `S3`…) must be in the board's registry.
- **M5-FR-7 Retry, then fallback.** If any field fails, the call is repeated **once** with the rejected tokens listed in the prompt (a changed prompt, so the response cache can't return the same reply). If the retry also fails, or the gateway returned its flagged safe default, **every** prose field is replaced by a code-built template sentence (§11.3) that passes the check by construction. The report records `prose_source`: `llm`, `retry`, `fallback`, or `none` (rejections, which make no LLM call). A fallback adds a data-notes warning naming what was rejected.

**Graph, runner, CLI, journal**

- **M5-FR-8 Graph.** A new `report` node runs last on every path: `request_check` (rejected), `brain` (`no_trade`), `trader`, `risk_sizing` and `risk_review` (outcome set) all go to `report`, then `END`. A rejected request gets a code-only report: no LLM call, no market-context fetch (a bad request still costs nothing, Part 1).
- **M5-FR-9 Errors in the report step** (D-M5-5):
  - `QuotaExhausted` and `LookaheadViolation` fail the request, as everywhere else (M6 pauses on quota and re-runs from the cache).
  - `LLMUnavailable` or `PromptTooLarge` in either writing call (first or retry) → the fallback prose, a warning, and the request completes. The decision is already made; losing it over prose would be worse than a plain sentence.
  - Any other exception (a bug) fails the request.
- **M5-FR-10 Runner.** `_finalize` writes one `reports` row (the report as JSON) in the same transaction as the other rows. A request that failed, or was refused before the graph (training cutoff, duplicate lock), has no report.
- **M5-FR-11 CLI.** `bullpit request` prints the Markdown report after the existing M3/M4 output, under a `=== REPORT ===` line.
- **M5-FR-12 Journal (migration `0004`).** New table `reports` ([§10](#10-data-model)).

**Settings**

- **M5-FR-13** New settings in `config.py` and `.env.example`: `vix_low_threshold` = 15.0 and `vix_high_threshold` = 25.0 (D-M5-6). The 200-session SPY average is a named constant, like M3's indicator periods (D-M3-10).

**Tokens (C14)**

- **M5-FR-14** Per-request tokens (input, output, reasoning; by model) are measured from `llm_calls` for one buy and one no-trade request, counting a cached call at the tokens of the original call with the same `cache_key`. [Architecture §14](../../architecture.md#14-free-tier-budget)'s table is updated with the measured numbers (revision v2.3; no behaviour change, so no deviation). `llm_output_allowance_tokens` is re-derived with M3's rule (3 × the largest output + reasoning of any call, now including `report.md`, never below 500), leaving the largest prompt under the 8K ceiling.

## 4. Non-functional requirements

- **M5-NFR-1 (tests)** Back to [dev-plan §7](../../dev-plan.md#7-testing-strategy)'s necessary-testing policy (D-M5-11): the number check (a §7.1 must-have) gets accept and reject cases; each other behaviour gets **one** test. Nothing touches the network; the suite stays under about a minute.
- **M5-NFR-2 (tokens)** One small-model call per report, plus at most one retry; none for rejections. The worst-case prompt (15 headlines, a full 4-turn transcript, 3 attempts) estimates under the 8K per-call ceiling with the current allowance.
- **M5-NFR-3 (pure where it can be)** `report/number_check.py` and `report/model.py` are pure (no I/O, no settings). The builder's section-building and market-context functions are pure; only the report node calls the gateway, and only `graph.py` calls the data layer.
- **M5-NFR-4 (state)** `Report` is a frozen Pydantic model, serialisable for M8's checkpointer; `Decimal`s dump as strings.
- **M5-NFR-5 (time)** The report time comes from `clock.utc_now()`, the one allowed wall-clock read. It is never shown to the LLM (so the response cache and M3-AC-9's no-future test are unaffected).

## 5. Interfaces

```python
# bullpit/llm/schemas.py (+): LLM reply
class ReportProse(BaseModel):
    summary: str               # one sentence
    strongest_bull: str        # "" when there was no debate
    strongest_bear: str
    bull_conceded: str
    unresolved: str
    would_change_view: str

# bullpit/report/model.py: the structured report (pure)
ReportOutcome = Literal["buy", "no_trade", "rejected"]
ProseSource = Literal["llm", "retry", "fallback", "none"]

class DebateSummary(BaseModel, frozen=True):                       # §5
    strongest_bull: str
    strongest_bear: str
    bull_conceded: str
    unresolved: str
    bull_conviction: float | None
    bear_conviction: float | None
    unsupported_points: int

class AttemptRow(BaseModel, frozen=True):                          # §6, one per trader attempt
    number: int
    action: Literal["buy", "no_trade"]
    target_weight: Decimal
    exit_style: ExitStyle
    confidence: float
    shares: int | None                    # Stage A size; None if blocked or not reached
    blocked_reason: str | None
    review_decision: Literal["approve", "shrink", "veto"] | None
    review_reason: str | None             # LLM text, masked (FR-3)
    review_clamped: bool

class MarketContext(BaseModel, frozen=True):                       # §8
    spy_close: float | None
    spy_sma_200: float | None
    spy_above: bool | None
    vix_close: float | None
    vix_label: Literal["low", "normal", "high"] | None
    explanation: str                      # "Market context not available." on failure

class DataNotes(BaseModel, frozen=True):                           # §9
    models: list[str]                     # the models actually called
    news_headlines: int | None            # headlines the sentiment analyst used; None if it failed
    filing_form: str | None
    filing_date: date | None
    price_source: Literal["yfinance", "alpaca"] | None
    warnings: list[str]

class Report(BaseModel, frozen=True):
    # 1 header
    request_id: str
    ticker: str
    company_name: str | None
    mode: Literal["live", "backtest"]
    as_of: date
    generated_at: datetime                # UTC
    # 2 recommendation
    outcome: ReportOutcome
    confidence: float | None
    summary: str
    reason: str | None                    # code text (FR-2)
    reason_detail: str | None             # quoted LLM text, masked (FR-2, FR-3)
    # 3 suggested order (+ 10 actions: approve up to order.shares)
    order: SizedOrder | None
    order_pct_of_equity: Decimal | None
    # 4 analysts
    signals: list[Signal]
    # 5 debate
    debate: DebateSummary | None
    # 6 risk manager (the limit and limit shares are on `order`)
    attempts: list[AttemptRow]
    loss_warning: bool | None             # None = not available (D-M4-9)
    # 7 what would change the view
    would_change_view: str | None
    # 8 market context
    market: MarketContext | None          # None only for rejections (FR-4)
    # 9 data notes
    data_notes: DataNotes
    prose_source: ProseSource

# bullpit/state.py (+)
class RequestState(BaseModel):            # M3 + M4 fields, plus:
    report: Report | None = None

# bullpit/report/number_check.py (pure)
def allowed_numbers(text: str) -> AllowedNumbers: ...          # from the code-only report
def check_text(text: str, allowed: AllowedNumbers, registry: Collection[str]) -> list[str]: ...
                                                               # rejected tokens; [] = passes
def mask_unknown_numbers(text: str, allowed: AllowedNumbers) -> str: ...   # for the transcript

# bullpit/report/builder.py
def market_context(spy_closes: Sequence[float], vix_close: float | None, *,
                   vix_low: float, vix_high: float) -> MarketContext: ...           # pure
def build_report(state: RequestState, *, prose: ReportProse | None, prose_source: ProseSource,
                 market: MarketContext | None, models: list[str],
                 generated_at: datetime) -> Report: ...        # pure; masks quoted text (§11.5)
def fallback_prose(report: Report) -> ReportProse: ...                               # pure
def render_markdown(report: Report, *, for_prompt: bool = False) -> str: ...        # Jinja
def report_node(state: RequestState, *, settings: Settings, sessions: sessionmaker[Session],
                market: MarketContext | None, completion_fn: CompletionFn = litellm_completion
                ) -> dict[str, object]: ...                                          # the LLM step
```

`AllowedNumbers` is a small frozen type holding the allowed values per unit (money, percent, plain) and the allowed ISO dates (§11.1). `Signal` and `SizedOrder` are reused as they are; `AttemptRow` is a flat copy of `TradeAttempt` because `report/model.py` can't import `state.py` (which imports `Report`).

## 6. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| **M5-AC-1** | A buy report has all 10 sections in order. Each no-trade kind (weak signals, trader no trade, Stage A block, veto limit) and a rejection have exactly the FR-1 sections, and state **why** (the FR-2 reason, with the quoted LLM text in `reason_detail` for the trader and veto-limit cases) | **Automated** (builder, parametrised over states) |
| **M5-AC-2** | Every number in a real report is traceable to state (checked by hand on the JPM 2024-10-18 buy). Automated half: in each test report, the prose and the masked quoted text pass the number check against the code-written report, and an invented number in a quoted veto reason is shown as `[?]` | Manual (pasted) + **Automated** |
| **M5-AC-3** | LLM text with a made-up number (`"target $200"`) or an unknown ID (`T99`) is rejected; the retry prompt names the rejected tokens; a passing retry is used (`prose_source = retry`); a second failure gives the fallback (`fallback`, with a warning) | **Automated** (report node, scripted fake) |
| **M5-AC-4** | Allowed formatting variants pass: `$5,824`, `5824`, `5,824.00`, `5.8%`, `$225` for a $225.37 reference, `+1.2%` / `-1.2%` for a 1.2% return, `2024-10-18` when it's the report's date. Rejected: `$200`, `$226` for $225.37, `5.9%`, `1` for a 0.62 confidence, `$200` even when "200-day" is in the report | **Automated** (parametrised) |
| **M5-AC-5** | The architecture's example card is reproduced from a fixture state: AAPL, Apple Inc., buy, confidence 0.62, 32 shares, $5,824.00, 5.8% of equity, stop $174.00 with max loss $256.00, take-profit $194.00 with gain $384.00, size set by the target limit, signals technical bullish 0.60 / fundamentals neutral 0.40 / sentiment bearish 0.50 | **Automated** |
| **M5-AC-6** | Market context: SPY above / below its 200-day average; VIX `low` / `normal` / `high` at the 15 / 25 settings, each with its explanation line; fewer than 200 SPY sessions → SPY "not available"; a `DataUnavailable` → section "not available" plus a warning. The two settings default to 15 and 25 | **Automated** |
| **M5-AC-7** | Per-request tokens are measured on one real buy and one real no-trade request; architecture §14 is updated with the measured numbers; the allowance is re-derived (FR-14). The real reports (buy, no trade after debate, weak signals, rejection) are read by hand for quality and `prose_source` | Manual: output and `llm_calls` query pasted |
| **M5-AC-8** | On recorded fixtures, every graph path ends with `state.report` and one `reports` row: buy (one `report.md` call); weak signals; a rejection (no LLM call at all); `LLMUnavailable` in the writing step (fallback, request `completed`); `QuotaExhausted` in the writing step (request `failed`, lock released) | **Automated** (graph) |
| **M5-AC-9** | `alembic upgrade head` on an empty DB matches `models.py` (the existing migration test, now covering `0004`) | **Automated** |
| **M5-AC-10** | `bullpit request` prints `=== REPORT ===` and the Markdown report for a buy; the worst-case `report.md` prompt estimates under the per-call ceiling | **Automated** |

AC-1 to AC-7 are the dev-plan's drafts made concrete; AC-8 is §7.2's graph happy path plus the report-step error rules; AC-9 and AC-10 cover the journal, CLI and token ceiling.

## 7. Decisions made in this document

None of these changes the system's behaviour, so neither `architecture.md` nor dev-plan §3 needs a new deviation.

| # | Decision | Reason |
|---|---|---|
| D-M5-1 | **A `report` node runs last on every graph path**, including request-check rejections (code-only, no LLM, no market fetch) | Part 12: a report for **every** request, and dev-plan M5 includes "early rejections that reached the graph". One node at the end means no path can skip it. Rejections stay free (Part 1) |
| D-M5-2 | **The allowed set is the code-written report itself**: sections 1–9 rendered with no prose, no quoted LLM text, no request ID and no timestamp. The LLM's prompt *is* that text (with the masked quotes added back), plus the transcript with unknown numbers masked as `[?]` | One source of truth: the LLM sees exactly the numbers it may use (dev-plan: "It only gets the numbers it's allowed to use"). No second list of "allowed numbers" to keep in sync. Debate text is LLM-written and unchecked, so its numbers are masked rather than trusted |
| D-M5-3 | **Matching rule**: numbers compare as values after removing `$`, `,`, `%` and the sign; a token may be *less* precise than an allowed value (rounded half up), never more; a one-significant-digit token must match exactly; `$` tokens must match money, `%` tokens a percentage, plain tokens anything; ISO dates match whole; evidence IDs are removed before extracting numbers and checked against the registry | Accepts the dev-plan's variants (`$5,824`, `5824`, `5.8%`) and natural rounding (`$225`), while blocking the tricks a loose check would miss: `1` "matching" a 0.62 confidence, or `$200` "matching" the "200-day" average. Signs are dropped because prose says "fell 2.3%" for a −2.3% return |
| D-M5-4 | **Whole-reply retry, whole-reply fallback**; `prose_source` recorded in the report | Dev-plan: the check "rejects the text", retries once, then falls back. Per-field mixing would add code for little gain. The retry prompt differs (rejected tokens listed), so the temperature-0 cache can't just return the same bad reply, and it's still deterministic for M6's replay |
| D-M5-5 | **Report-step errors**: `LLMUnavailable` / `PromptTooLarge` → fallback prose and the request completes; `QuotaExhausted`, `LookaheadViolation` and bugs fail it; market-data `DataUnavailable` → section 8 "not available" | Unlike M4's trader (D-M4-7), the decision already exists and is sound; only the wording is missing, and the fallback is exactly the architecture's "template sentence built by code". Quota must still stop a backtest (M6 resumes from the cache), and a date-guard failure is never quiet |
| D-M5-6 | **VIX thresholds 15 and 25, three labels** (`low`, `normal`, `high`); settings, since the architecture gives no values | Dev-plan M5 asks for "high and low thresholds set in config". A single cut-off would call a VIX of 20 either "high" or "low", which misleads. 15 and 25 bracket VIX's long-run middle (high teens), so "high" means genuinely stressed and "low" genuinely calm |
| D-M5-7 | **The SPY 200-day average reuses `tools.indicators`' SMA** (made public as `sma`); 200 is a named constant | One place for each fact (CLAUDE.md); a period defines the indicator, like M3's SMA 50 (D-M3-10) |
| D-M5-8 | **"What the bull conceded" is written by the report LLM** (number-checked), not copied from the debate | Debate concessions are raw LLM text whose numbers were never checked; copying them would put unchecked numbers in front of the owner |
| D-M5-9 | **`Report` reuses `Signal` and `SizedOrder`; attempts are flattened into `AttemptRow`**; section 10 (Actions) is derived from `order` | Reuse keeps one definition of each fact. `report/model.py` can't import `state.py` (circular), and the report only needs a flat view of each attempt. Actions carry no data beyond the order's share count until M6/M8 |
| D-M5-10 | **`reports` stores the JSON only; the CLI renders Markdown from it; no re-render command** | C3. M8's API endpoint is where stored reports get re-rendered; a CLI command now would be speculative |
| D-M5-11 | **Testing returns to dev-plan §7** (necessary testing), with one test per M5 behaviour and accept/reject cases for the number check | The owner asked for enough testing to prove everything works without spending much time on it (2026-09-29). M4's full coverage (D-M4-14) was M4-only |
| D-M5-12 | **Models listed in data notes are those actually called** (small always; large only if the debate ran) | "Models used" should be true for this request; a weak-signals request never touched the large model |
| D-M5-13 | **M4's LLM-written text shown in the report is masked, not trusted**: the trader's no-trade reasoning and the reviewer's reasons appear with unknown numbers as `[?]`; their code part (`Trader recommended no trade.`) is kept separately in `reason` | Found in review: M4 builds two `no_trade_reason`s by quoting LLM text, and every review reason is LLM text (e.g. the real JPM review cited "RSI 70.1, 21% annualized volatility"). Copied verbatim, those would be unchecked numbers in the owner's report, which is the thing Part 12 forbids. Masking keeps the reasoning readable without changing M4. Numbers the reviewer took from the evidence (RSI 70.1) survive, because they're in the report |

### 7.1 Corrections found in review

A second pass, checking the draft line by line against the M4 code, changed these. None changes scope:

| What | Change |
|---|---|
| M4 quotes LLM text in two `no_trade_reason`s and in every review reason | These were going to be copied into the report verbatim, as if code had written them, which would put unchecked numbers in front of the owner. Now they're split and masked (FR-2, FR-3, D-M5-13, §11.5; `reason_detail` added) |
| Market-data failure | The draft said both "section 8 not available" and `market = None`. Now it's an all-`None` `MarketContext` with the explanation line; `None` means a rejection only (FR-4) |
| The automated traceability test | The full Markdown includes the request ID (hex digits) and the timestamp, so it could never pass the check. The test now checks the prose and the masked quotes, which are the only parts that could carry an unchecked number (AC-2, §13) |
| Retry errors, the `rejected` template variable, the news count when sentiment failed, the rejection summary, where warnings are listed | Made explicit (FR-2, FR-9, §5, §9.3, §11.4) |

**Noted, not changed.** The report's `generated_at` is a wall-clock time, like `requests.created_at`. M6-AC-4 ("exactly the same journal" after resume) must therefore compare journals without wall-clock fields; recorded here so M6's specs pick it up.

## 8. Open questions for the owner

None. Every choice above is a default with its reason; say if you want any changed.

---

# Part B: Plan

## 9. Module design

### 9.1 Files created or changed

```text
.env.example                          + vix_low_threshold, vix_high_threshold
bullpit/
  config.py                           + the two VIX settings
  state.py                            + RequestState.report
  tools/indicators.py                 _sma → public sma (D-M5-7)
  llm/schemas.py                      + ReportProse
  llm/prompts/report.md               new
  report/model.py                     new: Report, DebateSummary, AttemptRow, MarketContext, DataNotes
  report/number_check.py              new: allowed_numbers, check_text, mask_unknown_numbers
  report/builder.py                   new: market_context, build_report, fallback_prose, render_markdown, report_node
  report/templates/report.md          new: Jinja Markdown template
  graph.py                            + report node (fetches market context); every END edge → report
  journal/models.py                   + ReportRecord
  journal/migrations/versions/0004_reports.py   new
  runners/request.py                  _finalize writes the reports row
  cli.py                              prints the Markdown report
tests/
  report/__init__.py                  new
  report/test_number_check.py         new: AC-4, AC-3 (check level)
  report/test_builder.py              new: AC-1, AC-2 (auto), AC-5, AC-6
  report/test_report_node.py          new: AC-3
  llm/test_prompts.py                 + report.md render and worst case (AC-10)
  test_graph.py                       RecordingLLM answers report.md; AC-8
  test_cli.py                         + report printed (AC-10)
  test_config.py                      + VIX defaults (AC-6)
docs/architecture.md                  §14 measured numbers; revision v2.3 (T-last)
docs/dev-plan.md                      status line
README.md                             quick start: the report
```

`bullpit/report/` exists as an empty package from M0. The migration test (`tests/journal/test_migrations.py`) covers `0004` without changes.

### 9.2 Dependency direction

```text
graph ──► report/builder ──► report/model, report/number_check (pure)
  │            └──────────► llm/gateway, state
  └────► data/prices.get_market_context (I/O stays in graph, like risk_sizing's settings)
```

`report/model.py` imports only `domain` and `llm/schemas`; `number_check.py` only the standard library.

### 9.3 The report node

| Step | Code |
|---|---|
| 1 | `graph._report_node`: if not rejected, fetch `get_market_context` and call `market_context(...)` on the SPY closes and the last VIX close. On `DataUnavailable`: the all-`None` `MarketContext` (FR-4), and the warning appended to a copy of the state. Pass `market` to `report_node` |
| 2 | `report_node`: rejected → `build_report(prose=None, prose_source="none")`, no LLM |
| 3 | Otherwise build the code-only report (`prose=None`; quoted text masked inside `build_report`, §11.5), render it `for_prompt=True`, compute `allowed_numbers`, mask the transcript |
| 4 | `call_llm(SMALL, "report.md", …, ReportProse, safe_default=empty)` with `rejected=[]`; flagged → fallback |
| 5 | `check_text` on every field; any rejection → one retry with `rejected` listed; still failing → fallback |
| 6 | `build_report(prose, prose_source, …)`; return `{"report": report, "warnings": …}` |

Fallback, flagged and exception paths all go through `fallback_prose(code_only_report)`, so there is one fallback builder.

### 9.4 Graph wiring

```python
graph.add_node("report", functools.partial(_report_node, deps=deps))
# each router that returned END now returns "report":
#   _route_after_request_check (rejected), _route_after_brain (no_trade),
#   _route_after_trader, _route_after_sizing, _route_after_review (outcome set)
graph.add_edge("report", END)
```

The longest path grows by one step (≈ 17), still under LangGraph's default recursion limit of 25.

### 9.5 The prompt (`report.md`)

Fixed first line `You are the report writer` (so the test fake can recognise it). Then: the code-only report; the masked transcript (if any); the six fields to write, each in one or two sentences; the rules: *use only numbers that appear in the report above, written the same way; cite evidence IDs in brackets like (T1, F2); leave the four debate fields empty if there was no debate; JSON only*. On a retry, one extra section: *"Your previous draft used numbers or IDs that aren't in the report: $200, T99. Write it again without them."*

## 10. Data model

Migration `0004_reports`:

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER PK` | |
| `request_id` | `TEXT NOT NULL`, FK → `requests.id`, **unique** | One report per request |
| `report` | `JSON` | `Report.model_dump(mode="json")`; `Decimal`s as strings (C3: no Markdown stored) |

ORM class `ReportRecord` (the `SignalRecord` convention).

## 11. Key algorithms

### 11.1 Number check (`report/number_check.py`)

```text
IDS    = \b[TFS]\d+\b                      → collected for the registry check, then removed
DATES  = \b\d{4}-\d{2}-\d{2}\b             → compared whole against allowed dates, then removed
NUMBER = [-+−]?\$?(\d{1,3}(,\d{3})+|\d+)(\.\d+)?%?
normalise(token) → (unit: money if "$", percent if "%", else plain;
                    value: abs Decimal without "$ , % sign"; places: digits after ".")

allowed_numbers(code_only_text) = {unit → set of values} ∪ {dates}, via the same extraction

token passes iff  some allowed value a, in a compatible unit (plain matches any unit), has
                  round_half_up(a, places) == value
                  and (significant_digits(value) ≥ 2  or  a == value)
check_text → the list of failing tokens and unknown IDs (empty = passes)
mask_unknown_numbers → each failing token replaced by "[?]"
```

Worked cases (AC-4): `$5,824` → money 5824, matches $5,824.00 ✓. `5.8%` → matches percent 5.8 ✓. `$225` → rounds 225.37 at 0 places ✓ (3 significant digits); `$226` ✗ (that is not a rounding). `1` vs confidence 0.62 → rounds to 1 but has one significant digit and isn't equal ✗. `$200` with "200-day" present → the 200 there is plain, not money ✗.

### 11.2 Market context (`builder.market_context`)

```text
sma = tools.indicators.sma(spy_closes, 200)                 # None below 200 closes
spy_above = None if sma is None else spy_closes[-1] > sma
vix_label = None if vix is None else low if vix < vix_low else high if vix > vix_high else normal
explanation = _EXPLANATIONS[(spy_above, vix_label)]          # fixed table, 12 entries incl. None
```

The explanation table lives in `builder.py` and uses no digits, so it adds nothing to the allowed set by accident.

### 11.3 Fallback prose (`builder.fallback_prose`)

Built only from values already in the code-only report, so it passes the check by construction:

| Field | Buy | No trade |
|---|---|---|
| `summary` | `Buy {shares} shares of {T}: the trader's recommendation passed the risk checks.` | `No trade: {reason}` |
| `strongest_bull` / `strongest_bear` | `The bull's case rests on {IDs cited in its supported points}.` (bear likewise; `No supported points.` if none) | same, when debated |
| `bull_conceded` | `The bull conceded {n} point(s).` | same |
| `unresolved` | `See the debate transcript.` | same |
| `would_change_view` | `A close below {stop} (the stop-loss).` | `Stronger, agreeing analyst signals on a later request.` |

### 11.4 Markdown

`render_markdown` renders `report/templates/report.md` (Jinja, `StrictUndefined`, no autoescape) section by section, skipping `None` sections, formatting with the FR-3 rules. `for_prompt=True` omits the request ID, the report time and every prose field. Section 10 prints `Approve up to {shares} shares, or reject.` The disclaimer is the last line. All warnings are listed once, in section 9 (section 6 shows the loss warning and the attempts; architecture §7's "any warnings" point there rather than repeating them).

### 11.5 Masking quoted text (`build_report`)

```text
base    = the report with reason_detail = None and every review_reason = None
allowed = allowed_numbers(render_markdown(base, for_prompt=True))
report  = base with reason_detail and review_reasons = mask_unknown_numbers(text, allowed)
```

The masked text adds only `[?]` and numbers already allowed, so the allowed set of the final `for_prompt` rendering equals `allowed`. `report_node` can recompute it from the final report and get the same set.

## 12. Error handling

| Where | Error | Result |
|---|---|---|
| Market context | `DataUnavailable` | Section 8 "not available", warning, continue |
| Market context | `LookaheadViolation` | Request fails (never quiet) |
| Writing step | Flagged reply (gateway safe default) | Fallback prose, `prose_source = fallback`, warning |
| Writing step | Number / ID check fails twice | Fallback prose, warning naming the rejected tokens |
| Writing step | `LLMUnavailable`, `PromptTooLarge` | Fallback prose, warning, request completes (D-M5-5) |
| Writing step | `QuotaExhausted` | Request `failed`, lock released, re-raised (M6 pauses) |
| Anywhere in the node | Any other exception | Request `failed`, re-raised (a bug is loud) |

## 13. Test and verification plan

Necessary testing (D-M5-11). No network (`pytest-socket`); the whole suite stays in seconds.

| File | Tests | AC |
|---|---|---|
| `report/test_number_check.py` | `test_accepts_variants` (parametrised: every AC-4 accept case); `test_rejects` (parametrised: `$200`, `5.9%`, `1` vs 0.62, `$200` beside "200-day", `T99`); `test_mask_unknown_numbers` | AC-4, AC-3 |
| `report/test_builder.py` | `test_example_card` (the architecture's card from a fixture state; every AC-5 value in the Markdown); `test_sections_per_outcome` (parametrised: buy, weak signals, trader no trade, Stage A block, veto limit, rejection → exactly the FR-1 sections, the FR-2 reason and `reason_detail`, disclaimer last); `test_every_number_traceable` (for each of those reports, the fallback prose fields and the masked `reason_detail` / `review_reason` pass `check_text` against the code-only rendering; a veto reason citing an invented `$999` shows `[?]`); `test_market_context` (parametrised: above/below × low/normal/high, fewer than 200 closes, no VIX) | AC-1, AC-2, AC-5, AC-6 |
| `report/test_report_node.py` | Scripted fake: a clean reply → `llm`; `$200` then clean → `retry`, and the retry prompt contains `$200`; `T99` twice → `fallback` with a warning; a flagged reply → `fallback` with no retry | AC-3 |
| `llm/test_prompts.py` (+) | `report.md` renders with `StrictUndefined`, starts with its first line; the worst-case state estimates under `llm_tpm_limit` | AC-10 |
| `test_graph.py` (+) | `RecordingLLM` answers `report.md` (default: a clean reply citing `T1`). Existing path tests gain one assertion each: `state.report` set and one `reports` row. New: rejection (no LLM calls, report `rejected`); `LLMUnavailable` in `report.md` (fallback, `completed`); `QuotaExhausted` in `report.md` (`failed`, lock released) | AC-8 |
| `test_cli.py` (+) | The fixed buy state carries a report: output has `=== REPORT ===` and the order line | AC-10 |
| `test_config.py` (+) | VIX defaults 15 and 25 | AC-6 |

The graph fixtures patch every price download with AAPL's 85-session file, so SPY's 200-day average is "not available" there; that path is fine for the graph test, and the labels are tested in `test_builder.py`.

**Manual checks** (evidence pasted into `task.md`):

| Check | How |
|---|---|
| AC-2, AC-7 | `bullpit request` for JPM and AAPL `--mode backtest --as-of 2024-10-18` (M4's buy and no trade; their M3/M4 calls come back from the cache, so only `report.md` is new), XOM `--as-of 2024-07-12` (M3's weak-signals route), and SPY (rejected). Read each report; trace every number of the JPM report to state or the journal by hand; record `prose_source` for each. Per-request tokens per model from `llm_calls` (FR-14); update §14; re-derive the allowance and re-run one request to confirm nothing is flagged |

## 14. Work order

`task.md` breaks this into tasks, in this order:

1. Docs on the new branch (this file, `task.md`, dev-plan status line).
2. Settings; `ReportProse`; `sma` made public.
3. `report/number_check.py` and its tests.
4. `report/model.py`, `RequestState.report`.
5. `report/builder.py` pure parts (`market_context`, `build_report`, `fallback_prose`), the Markdown template, `render_markdown`, and `test_builder.py`.
6. `report.md` prompt and `report_node`; `test_report_node.py`; prompt test.
7. Graph: the `report` node, market-context fetch, END edges rerouted.
8. Journal: `ReportRecord`, migration `0004`, `_finalize`.
9. CLI output and its test.
10. Graph tests.
11. Real runs, number tracing, tokens, §14 update, allowance (AC-2, AC-7).
12. Acceptance: README, retrospective; merge and tag `m5` when the owner asks.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| The small model keeps adding numbers (e.g. its own percentages) | Frequent fallbacks: correct but plain reports | The prompt shows exactly the allowed numbers and says so; one retry names the offenders; the fallback rate is measured in AC-7 and the prompt wording adjusted once if it's high |
| The check is too strict for honest rounding | Good text rejected | D-M5-3's rounding rule; AC-4's accept cases |
| The check is too loose | A made-up number reaches the owner | Units and the one-significant-digit rule; AC-4's reject cases; AC-2's hand trace |
| Prompt size with 15 headlines and a full transcript | `PromptTooLarge` → fallback | AC-10's worst-case estimate; if it's close, the prompt drops the transcript's conceded lines first (a prompt change, not a scope change) |
| SPY or VIX download fails | No market section | "Not available" plus a warning; the request still completes |
