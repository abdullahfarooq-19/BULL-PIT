# M3 — Request check, three analysts, signals board, brain: specs and plan

| | |
|---|---|
| **Status** | Part A (specs) approved by the owner on 2026-09-28, with Q1 answered **A** (deviation D10). Part B (plan) awaiting approval. Checks against the real services while writing the plan corrected Part A in the places listed in [§7.1](#71-corrections-found-while-planning); none changes scope or an acceptance criterion |
| **Date** | 2026-09-28 |
| **Size** | XL. Normally `specs.md` + `plan.md` ([dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents)); the owner asked for them combined in one file for M3 |
| **Branch** | `m3-analysts` |
| **Depends on** | M1 (data layer, `Clock`, calendar), M2 (gateway, journal). Both accepted |
| **Sources** | [dev-plan §5 M3](../../dev-plan.md#m3--request-check-three-analysts-signals-board-brain), [§3 D4, D6, D8, D10, D11](../../dev-plan.md#3-deviations-from-the-architecture-roadmap), [§7](../../dev-plan.md#7-testing-strategy), [§8](../../dev-plan.md#8-data-model-evolution), [§10.1](../../dev-plan.md#101-scope-review-revision-4) (C1, C12, C14); [architecture Parts 0, 1, 4–8](../../architecture.md#6-every-part-in-detail), [§5](../../architecture.md#5-one-request-step-by-step), [§14](../../architecture.md#14-free-tier-budget); M0 [findings](../M0-foundations/findings.md) A10, A11, C1; M2 [retrospective carry-overs](../M2-llm-gateway/task.md#retrospective) |

Part A says **what** M3 delivers and how it's accepted. Part B says **how** it gets built. Neither restates the architecture or the dev plan; they link to them.

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

The first half of the graph runs end to end: a request is checked, three analysts produce signals in parallel, the signals board validates them, and the brain picks the route (debate or no trade). The architecture's done-when: *"Valid signals for any stock on any past date."*

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | `state.py`: the typed graph state (M3's fields only, D-M3-4) | Part 0 |
| S2 | `domain.py`: `Account`, `Position`, `Asset` | dev-plan §2.3 |
| S3 | `broker/base.py` (read-only `Broker` protocol) and `broker/alpaca.py` (read-only Alpaca implementation); a fake broker in `tests/` | D4, C1 |
| S4 | `request_check.py`: tradable, SEC filings, price history, account snapshot; duplicate lock in the journal | Part 1 |
| S5 | `tools/indicators.py`, `tools/fundamentals.py`, `tools/sentiment.py`: the pure maths | Parts 5–7 |
| S6 | `agents/technical.py`, `agents/fundamentals.py`, `agents/sentiment.py` and their prompts in `llm/prompts/` | Parts 5–7 |
| S7 | `agents/signals_board.py`, `agents/brain.py` (code only, no LLM) | Parts 4, 8; D8 |
| S8 | `graph.py`: LangGraph graph, analysts in parallel, ends at the route | Part 0, §5 |
| S9 | `runners/request.py` and `bullpit request` CLI command | D6 |
| S10 | Journal: `requests` filled in, request lock, `signals` table (migration `0002`) | dev-plan §8 |
| S11 | Real token measurement of each analyst prompt, and the M2 output-allowance carry-over | C14; M2 retrospective |

### 2.2 Out of scope

- Debate, trader, risk manager, sizing (M4). The debate route ends the graph in M3 (D-M3-5).
- Report and market context (M5), simulated broker and simulated account (M6, C1), order placement (M6, M8), LangGraph checkpointer (M8).
- Graph-state fields that later milestones fill (`debate`, `recommendation`, `sized_order`, `risk_verdict`, `report`, `approval`): each milestone adds its own (D-M3-4).

## 3. Functional requirements

**Request and modes**

- **M3-FR-1** `bullpit request TICKER [--mode live|backtest] [--as-of DATE]`. Live (default) uses `LiveClock`, and `--as-of` is refused. Backtest requires `--as-of` and uses `SimClock(as_of)`; an `as_of` on or before any pinned model's training cutoff (settings `llm_small_model_cutoff`, `llm_large_model_cutoff`) is rejected before any data or LLM call, because the model may remember what happened next (architecture §11, Kind 2). With today's models the earliest allowed date is 2024-07-01.
- **M3-FR-2** Each request gets a `request_id` of the form `YYYYMMDD-TICKER-xxxxxxxx` (`as_of`, ticker, 8 random hex characters) and one `requests` row, whose `status` goes `running` → `completed`, `rejected` or `failed`, with a reason for the last two. The row is written for every request, including rejected ones.
- **M3-FR-3 Duplicate lock.** At most one `running` request per (ticker, mode), enforced atomically by the journal. A duplicate is rejected with the message in FR-5. The lock is released however the request ends (success, rejection, error). A `running` row older than `request_lock_timeout_minutes` is treated as abandoned (a killed process): it's marked `failed` with a warning in the log, and the new request proceeds.

**Request check (Part 1)**: the graph's first node, code only, **before any LLM call**

- **M3-FR-4** Checks, in order: (1) the asset exists on Alpaca and is tradable and active; (2) the ticker has SEC companyfacts filed on or before `as_of` (`get_sec_facts`); (3) at least `min_price_sessions` sessions of prices through `as_of` (it fetches `price_history_sessions`); (4) the account snapshot: cash, equity and any position in this ticker, read only. **ETFs are rejected by check (2), not by Alpaca's `asset_class`**, which is `us_equity` for both stocks and ETFs (findings A11, C1). Buying power is never read: sizing (M4) uses cash, since the architecture allows no borrowing.
- **M3-FR-5** A failed check ends the graph with a rejection and one of these messages:

  | Case | Message |
  |---|---|
  | Unknown or untradable on Alpaca | `{T} isn't a tradable stock on Alpaca.` |
  | No SEC filings (ETF, fund, foreign filer, unknown to SEC) | `No SEC filings found for this ticker. Try a US company stock.` (M1's existing message) |
  | Too little history | `{T} has only {n} trading days of prices up to {as_of}; at least {min} are needed.` |
  | Duplicate | `A {mode} request for {T} is already running.` |
  | Backtest date too early (FR-1) | `Backtest dates must be after the models' training cutoff: use {earliest} or later.` |

- **M3-FR-6** A passed check hands over: the company name (from the Alpaca asset), the account snapshot, and a **price snapshot**: the point-in-time bars, their source, the split events up to `as_of`, and the **reference price** (the latest close up to `as_of`, as `Decimal`). Prices are fetched once per request, here; the analysts read them from state (D-M3-2).

**Broker (D4)**

- **M3-FR-7** A read-only `Broker` protocol: `get_account()`, `get_position(symbol)`, `get_asset(symbol)`. `AlpacaBroker` implements it through `make_trading_client` (so the paper-only guard always runs). No order methods yet (M6, M8). In M3 both modes use `AlpacaBroker`, because no simulated account exists until M6 (C1, D-M3-6).

**Technical analyst (Part 5)**

- **M3-FR-8** Code computes from the snapshot's bars (the latest bar is the `as_of` session, or the last one before it if the stock didn't trade that day):

  | Indicator | Definition |
  |---|---|
  | SMA 20, SMA 50 | Mean of the last 20 / 50 closes; plus whether the close is above each |
  | RSI 14 | Wilder: first average gain and loss = simple mean of the first 14 close-to-close changes, then `avg = (prev × 13 + current) / 14`; `RSI = 100 − 100 / (1 + gain / loss)`, 100 when the average loss is 0 |
  | ATR 14 | Wilder: true range `max(H − L, |H − prev C|, |L − prev C|)`; first ATR = mean of the first 14 true ranges, then the same smoothing |
  | Volatility | Sample standard deviation of the last 20 daily simple returns × √252 |
  | Returns | `close / close k sessions earlier − 1`, for k = 5 (1 week), 21 (1 month), 63 (3 months) |

  An indicator without enough bars is `None` (for example the 3-month return of a stock with 60 sessions of history), shown as "not available" and turned into a data warning (FR-17).
- **M3-FR-9** Code writes the evidence facts `T1…` from those numbers (for example `T2: Close 182.31 is above SMA 50 (170.02)`). The LLM (small model) sees only those facts and replies with a direction and a confidence. The signal is the code-written evidence plus the LLM's verdict (D-M3-1, D11). ATR 14 is kept in state for sizing (M4).

**Fundamentals analyst (Part 6)**

- **M3-FR-10** Code computes from SEC `us-gaap` facts filed on or before `as_of` (M1 already keeps only the latest filed value per period):
  - **Periods:** a fact is a quarter if it spans 80–100 days, a fiscal year if 350–380 days (covers 52/53-week years). 6- and 9-month year-to-date facts are ignored.
  - **Tags:** an ordered candidate list per metric: revenue (`RevenueFromContractWithCustomerExcludingAssessedTax`, `Revenues`, `RevenuesNetOfInterestExpense`, `SalesRevenueNet`), net income (`NetIncomeLoss`), diluted EPS (`EarningsPerShareDiluted`). **One tag per metric per request:** the candidate whose quarterly series (Q4 included) reaches the most recent quarter, ties broken by list order. Every period used (latest quarter, year-ago quarter, Q1–Q3 for Q4, the TTM quarters) comes from that one tag, so two tags with different definitions are never mixed (§7.1 C-1).
  - **Q4 = fiscal year − (Q1 + Q2 + Q3)**, for revenue, net income and EPS, when all three quarters inside that fiscal year exist. Q4 counts as known from the 10-K's filing date.
  - **Revenue growth:** latest quarter against the quarter ending about one year earlier (±10 days). **Net margin:** latest quarter's net income ÷ revenue. **TTM EPS:** sum of the last 4 consecutive quarters' diluted EPS. **P/E:** reference price ÷ TTM EPS; `None` when TTM EPS ≤ 0 ("not meaningful: negative earnings").
  - **Splits:** each quarter's EPS is divided by every split with an ex-date after that fact's filing date and on or before `as_of` (from the price snapshot), so EPS and price are on the same share basis. Without this, NVDA's P/E in July 2024 would be 10× too low (10:1 split on 2024-06-10, EPS filed before it).
- **M3-FR-11** Code writes the evidence facts `F1…` (revenue growth, net margin, TTM EPS, P/E, latest filing: form, period end and filing date). **The fundamentals prompt contains only filing-derived facts: no price, no P/E, no `as_of`** (Q1 = A, D10). So the prompt, and with it the gateway's response cache entry, only changes when a new filing arrives: that *is* the architecture's "cached by (ticker, latest filing date)", with no extra cache and no look-ahead risk. P/E still reaches the debate and the report as a fundamentals evidence fact.
- **M3-FR-12** If revenue or net income can't be computed for the latest quarter, the analyst makes no LLM call and returns a neutral, confidence-0, flagged signal with the reason.

**Sentiment analyst (Part 7)**

- **M3-FR-13** Code takes `get_news` for the `news_lookback_days` before the cutoff, removes near-duplicates (normalised headline word sets with Jaccard similarity ≥ `news_duplicate_similarity`, the most recent copy kept) and keeps the `news_max_headlines` most recent, numbered `S1` (newest) onwards. No news gives a neutral, confidence-0 signal with no LLM call.
- **M3-FR-14** The LLM (small model, one call for all headlines, headlines only) replies with a `score` in [−1, 1] and a `relevance` in [0, 1] for each headline ID. Code ignores unknown IDs and drops headlines the reply left out. **Code** then computes `s = Σ(relevance × score) / Σ relevance` (neutral, confidence 0 if Σ relevance = 0); direction is bullish if `s > sentiment_neutral_band`, bearish if `s < −sentiment_neutral_band`, otherwise neutral; confidence = `|s|`. Each headline's evidence fact includes its date, headline, score and relevance.

**Failure handling (Part 8)**

- **M3-FR-15** An analyst that raises, or whose reply was the gateway's flagged safe default, becomes a neutral, confidence-0, flagged signal with the reason, and the request continues. Two exceptions are **never** swallowed: `QuotaExhausted` (M6 must pause and resume the backtest, not record degraded signals) and `LookaheadViolation` (the date guard always stops loudly, dev-plan §2.2). Either one fails the request.

**Signals board (Part 8) and brain (Part 4, D8)**: code only

- **M3-FR-16 Board.** Holds exactly one signal per analyst. Computes the **score** = mean over the three of `direction × confidence` (bullish +1, neutral 0, bearish −1), in [−1, 1], and **conflict** = at least one bullish and one bearish signal each with confidence ≥ `brain_conflict_min_confidence`. Builds the **evidence registry**: every evidence ID, unique, with the right prefix (`T`, `F`, `S`); a duplicate or wrong prefix is a programming error and raises.
- **M3-FR-17 Brain.** Route = `no_trade` when `|score| < brain_min_abs_score` and there's no conflict; otherwise `debate`. No LLM call on either route. It attaches data warnings: an analyst failed or was flagged (with the reason); no news; fewer than `news_thin_articles` headlines; an indicator or fundamentals metric not available; prices came from the Alpaca backup.

**Graph, runner, CLI, journal**

- **M3-FR-18 Graph.** `request_check` → (rejected: end) → `technical` ∥ `fundamentals` ∥ `sentiment` → `signals_board` → `brain` → end. The analysts write separate state fields, so no reducer is needed. Dependencies (settings, journal sessions, broker, the LLM completion function) are bound when the graph is built and never stored in state, so the state stays serialisable for M8's checkpointer.
- **M3-FR-19 Runner.** Creates the request row (taking the lock), binds `request_id`, `mode` and `as_of` to the log context, runs the graph, then records the final state in one transaction: the `requests` row filled in (FR-21) and one `signals` row per analyst. Graph nodes never write the journal themselves; only the gateway writes `llm_calls` (M2). The lock is released in all cases.
- **M3-FR-20 CLI.** `bullpit request` brings the journal schema up to date (`alembic upgrade head`), runs the request and prints: request ID, mode, `as_of`, company, account snapshot, each signal (direction, confidence, evidence), board score and conflict, route and warnings. A rejection prints its message. Exit code 0 when completed, 1 when rejected or failed.
- **M3-FR-21 Journal (migration `0002`).** `requests` gains `ticker`, `status`, `status_reason`, `route`, `warnings` (JSON), `config` (JSON snapshot of every setting **except secrets and the SEC email**; it includes model IDs and seed), `git_commit`, `price_source`, `finished_at`, and a partial unique index on (`ticker`, `mode`) where `status = 'running'` (the lock). New table `signals`: `request_id` (FK), `analyst`, `direction`, `confidence`, `evidence` (JSON), `flagged`, `note`.

**Settings**

- **M3-FR-22** New settings (in `config.py` and `.env.example`):

  | Setting | Default | Source |
  |---|---|---|
  | `min_price_sessions` | 60 | Part 1 |
  | `price_history_sessions` | 300 | Covers the 3-month return, indicator warm-up and the splits over the TTM EPS year |
  | `news_max_headlines` | 15 | Part 7 |
  | `news_duplicate_similarity` | 0.8 | D-M3-8 |
  | `news_thin_articles` | 3 | D-M3-8 (findings A10: XOM, JNJ get 5–10 a week) |
  | `sentiment_neutral_band` | 0.15 | D-M3-8 |
  | `brain_min_abs_score` | 0.15 | D-M3-7 |
  | `brain_conflict_min_confidence` | 0.4 | D-M3-7 |
  | `request_lock_timeout_minutes` | 30 | FR-3 |
  | `llm_small_model_cutoff`, `llm_large_model_cutoff` | 2024-06-30 | Architecture §10; M6 reuses them for the window check |

**Token measurement (C14) and the M2 carry-over**

- **M3-FR-23** Real tokens (input, output, reasoning) of each analyst prompt are measured from `llm_calls` over the AC-1 runs. M2's pacing counts the whole 2,000-token output allowance per call, which limits each model to 2–3 calls a minute; once measured, `llm_output_allowance_tokens` is lowered to 3× the largest measured reasoning + output of any M3 call (never below 500), and the change is recorded in the retrospective. M4 re-checks it for the large-model prompts.

## 4. Non-functional requirements

- **M3-NFR-1 (tests)** Automated tests only where [dev-plan §7](../../dev-plan.md#7-testing-strategy) requires them; no network (recorded fixtures, scripted fake LLM, fake broker); the whole suite stays under about a minute.
- **M3-NFR-2 (threads)** The three analysts run in parallel threads, so everything they share is safe to use concurrently: the gateway's token buckets (locked), journal writes (`llm_calls`), and the data caches (each analyst owns a different source in the parallel phase: technical none, fundamentals SEC, sentiment news).
- **M3-NFR-3 (pure core)** `tools/` imports nothing from `data/`, `llm/`, `journal/`, `broker/` or the CLI, and stays under mypy `strict` with `broker/`. Money (cash, equity, position value, reference price) is `Decimal`; indicators and ratios are floats (dev-plan §2.2).
- **M3-NFR-4 (tokens)** All three analysts use the small model at `low` reasoning effort, with compact prompts (each well under the 8K per-call ceiling). A request makes at most 3 LLM calls and none on a rejection.
- **M3-NFR-5 (time)** No wall-clock reads outside `clock.py`; every node works from `as_of`.

## 5. Interfaces

```python
# bullpit/domain.py
class Account(BaseModel, frozen=True):
    cash: Decimal
    equity: Decimal
class Position(BaseModel, frozen=True):
    symbol: str
    qty: int
    market_value: Decimal
class Asset(BaseModel, frozen=True):
    symbol: str
    name: str
    tradable: bool
    active: bool

# bullpit/broker/base.py
class Broker(Protocol):
    def get_account(self) -> Account: ...
    def get_position(self, symbol: str) -> Position | None: ...
    def get_asset(self, symbol: str) -> Asset | None: ...     # None: unknown symbol

# bullpit/llm/schemas.py (M2's Evidence and Signal, extended)
class Signal(BaseModel):                  # built by code, not returned by the LLM
    ticker: str
    analyst: Literal["technical", "fundamentals", "sentiment"]
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: list[Evidence]
    flagged: bool = False                 # failed, or safe-default reply
    note: str | None = None               # why it's flagged or thin
class AnalystVerdict(BaseModel):          # technical and fundamentals LLM reply
    direction: Literal["bullish", "bearish", "neutral"]
    confidence: float = Field(ge=0.0, le=1.0)
class HeadlineScore(BaseModel):
    id: str
    score: float = Field(ge=-1.0, le=1.0)
    relevance: float = Field(ge=0.0, le=1.0)
class HeadlineScores(BaseModel):          # sentiment LLM reply
    scores: list[HeadlineScore]

# bullpit/tools/indicators.py, bullpit/tools/fundamentals.py (§7.1 C-4: owned by the maths)
class Indicators(BaseModel, frozen=True): ...           # FR-8 values, each float | None
class FundamentalsMetrics(BaseModel, frozen=True): ...  # FR-10 values + latest filing form/period/date

# bullpit/state.py
class Bar(BaseModel, frozen=True):
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
class PriceSnapshot(BaseModel, frozen=True):
    source: Literal["yfinance", "alpaca"]
    bars: list[Bar]                       # point-in-time, oldest first
    splits: list[tuple[date, float]]      # ex-date <= as_of, ratio new/old
    reference_price: Decimal              # latest close up to as_of
class SignalsBoard(BaseModel, frozen=True):
    signals: dict[str, Signal]            # keyed by analyst
    score: float
    conflict: bool
    evidence: dict[str, Evidence]         # the registry the debate may cite (M4)
class RequestState(BaseModel):
    request_id: str
    mode: Literal["live", "backtest"]
    as_of: date
    ticker: str
    rejection: str | None = None
    company_name: str | None = None
    account: Account | None = None
    position: Position | None = None
    prices: PriceSnapshot | None = None
    indicators: Indicators | None = None
    fundamentals: FundamentalsMetrics | None = None
    technical_signal: Signal | None = None
    fundamentals_signal: Signal | None = None
    sentiment_signal: Signal | None = None
    board: SignalsBoard | None = None
    route: Literal["debate", "no_trade"] | None = None
    warnings: list[str] = []

# bullpit/runners/request.py
def run_request(ticker: str, mode: Literal["live", "backtest"], clock: Clock, *,
                settings: Settings, sessions: sessionmaker[Session], broker: Broker,
                completion_fn: CompletionFn = litellm_completion) -> RequestState: ...

# bullpit/data/prices.py (additive change to M1)
class PriceHistory:  # + splits: list[tuple[date, float]]   (ex-date <= as_of, within the window)
```

## 6. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| **M3-AC-1** | For AAPL, MSFT, JPM, XOM and JNJ, at `as_of` 2024-07-12, 2024-10-18 and 2025-01-17 (backtest), plus one live request, `bullpit request` produces three valid signals and a route, with no uncaught error. The graph also runs end to end on recorded fixtures | Manual: output pasted. **Automated:** graph happy path (fake LLM, fake broker) |
| **M3-AC-2** | Indicator values match hand-computed values on a small bar fixture | **Automated** |
| **M3-AC-3** | Fundamentals maths is right on a small hand-built facts fixture: tag choice, Q4 derivation, YoY growth, margin, TTM EPS across a split, negative EPS (no P/E). Real revenue for each reference ticker's latest quarter at 2024-10-18 matches a hand-checked table from the filings. (Restated values are M1-AC-3's, already tested.) | **Automated** (fixture) + Manual (table) |
| **M3-AC-4** | SPY (ETF), an unknown ticker, a ticker with too little history before `as_of`, a duplicate running request, and a backtest date before 2024-07-01 are each refused with the FR-5 message and **no** `llm_calls` row | Manual (C12): output and `llm_calls` query pasted |
| **M3-AC-5** | An analyst that raises gives a neutral, confidence-0, flagged signal and a warning, and the request completes; `QuotaExhausted` from an analyst fails the request instead | **Automated** (graph) |
| **M3-AC-6** | Every evidence ID is unique, has its analyst's prefix, and is in the board's registry | **Automated** (in the happy-path test) |
| **M3-AC-7** | Weak neutral signals route to `no_trade`, and the whole request makes only the analysts' LLM calls (the brain makes none on either route) | **Automated** (graph, counted from `llm_calls`) |
| **M3-AC-8** | The three analysts run in parallel | Manual: overlapping start times in the log |
| **M3-AC-9** | No data dated after `as_of` reaches any prompt: the recorded fixtures hold real prices, news and SEC facts after `as_of`, and none of them appears in any prompt the fake LLM receives or in the state's numbers | **Automated** (graph) |
| **M3-AC-10** | Real tokens of each analyst prompt are measured from `llm_calls` and recorded in the retrospective; `llm_output_allowance_tokens` is revised per FR-23 | Manual: query output pasted |
| **M3-AC-11** | After a run, the `requests` row has every FR-21 field with no secret in `config`, the `signals` rows exist, and a stale `running` row is cleared by the next request; `alembic upgrade head` gives a schema matching the models | Manual: query output pasted |

AC-1 to AC-10 are the dev-plan's drafts (AC-3 and AC-4 made concrete). AC-11 covers the journal work in scope.

## 7. Decisions made in this document

Approved by the owner with Part A.

| # | Decision | Reason |
|---|---|---|
| D-M3-1 | **Code writes every evidence fact; the LLM only judges** (deviation D11). Technical and fundamentals reply with direction and confidence; sentiment replies with per-headline scores. The signal keeps the architecture's format (`id`, `fact`, direction, confidence) | "Code for math, LLMs for judgment": no LLM-written number can reach the debate or the report, and the evidence registry is exact. It also keeps replies tiny (M2 measured this exact reply shape at ~320 tokens) |
| D-M3-2 | Prices are fetched once, by the request check, and the bars live in state | One fetch per request, the analysts can't race on the same cache file, and M4 (ATR, reference price) and M5 (report numbers) use exactly the bars the analysts saw. ~300 bars is small enough for M8's checkpoints |
| D-M3-3 | The analysts write separate state fields; only the brain writes `warnings` | No LangGraph reducers needed, so the dev-plan's merge-semantics risk goes away by design |
| D-M3-4 | `RequestState` holds only M3's fields; M4–M8 add theirs | The dev-plan asked for later fields "defined now, as optional", but their types don't exist yet; CLAUDE.md forbids placeholder code. Same rule as settings (D-M0-12) |
| D-M3-5 | No debate stub node: the `debate` route ends the graph in M3, and M4 attaches the debate there | A stub would be written only to be deleted |
| D-M3-6 | Both modes read the Alpaca paper account in M3. A backtest request's account and asset status are today's, not `as_of`'s, until M6 plugs in the simulated account | C1 put the simulated broker in M6. M3 only records the account; nothing sizes from it until M4 |
| D-M3-7 | Brain rule: debate unless `|score| < 0.15` and no conflict (both settings) | The architecture gives no numbers. Checked against its own example (technical bullish 0.6, fundamentals neutral 0.4, sentiment bearish 0.5): conflict, so debate. All neutral: skip. One analyst bullish at 0.45 or more: debate. The route split over the AC-1 runs goes in the retrospective, and the thresholds can be tuned there |
| D-M3-8 | Sentiment: relevance is a 0–1 weight, not a yes/no mark; headlines only (no summaries); confidence = `|weighted score|`; neutral band 0.15; duplicate threshold 0.8; "thin news" under 3 headlines | A weight covers "is it about this company" and lets code do the averaging the architecture asks for. Headlines keep the prompt small (8K ceiling) |
| D-M3-9 | Every analyst failure becomes a neutral signal **except** `QuotaExhausted` and `LookaheadViolation`, which fail the request | Swallowing a quota error would silently record degraded signals in a backtest instead of pausing it (M6); the date guard must stop loudly |
| D-M3-10 | Indicator periods (20, 50, 14, 5/21/63, √252) and the fundamentals period lengths are named constants in `tools/`, not settings | They define what "SMA 50" or "a quarter" means; changing one changes the indicator, not a tunable limit |
| D-M3-11 | Net margin and revenue growth use the latest quarter; EPS is split-adjusted to the `as_of` share basis; `PriceHistory` gains a `splits` field | Matches the architecture's growth definition; the split adjustment fixes a real P/E error (FR-10); M1's cache already stores the split events |
| D-M3-12 | Model training cutoffs become settings now (FR-1) | A single backtest-mode request on a pre-cutoff date is already a Kind-2 leak; M6's window check reuses the same settings |
| D-M3-13 | `bullpit request` runs `alembic upgrade head` itself | Single-user local tool; the upgrade is idempotent, and M3 adds a migration the owner would otherwise hit as an error |
| D-M3-14 | New dependency: `langgraph` (the core package only; no checkpointer package until M8) | Named in architecture §13 for the graph and parallel analysts |
| D-M3-15 | Live mode downloads SEC companyfacts twice per request (request check, then fundamentals) | M1's cache rightly distrusts same-day fetches (D-M1-4). A few MB, 5–8 live requests a day; backtests read from the cache |
| D-M3-16 | `data/sec.py` gets a small CIK override table, starting with `XOM → 34088` (§7.1 C-2) | SEC's current ticker map now sends XOM to a holding company created in July 2026, with no history. Exxon's original CIK holds every filing and still files 10-Qs, so it's right for every `as_of`. A point-in-time ticker history stays out of scope (D-M1-7) |

**Noted, not changed:** the system is long-only, so debating a clearly bearish board almost always ends in "no trade" and costs about 6 large-model calls. The architecture says to debate anything that isn't weak, so M3 does. M7's "debate impact" metric will show whether skipping strongly bearish boards is worth an architecture change.

### 7.1 Corrections found while planning

Checked against the real services on 2026-09-28 (SEC companyfacts for the five reference tickers, the Alpaca asset endpoint, LangGraph 1.2.12). All corrected above.

| # | Problem | Correction |
|---|---|---|
| C-1 | "First tag per period" mixes definitions. XOM reports `RevenueFromContractWithCustomerExcludingAssessedTax` (a sub-total) up to Q2 2023 and `Revenues` (total) up to Q2 2024, so Q2 2024 vs Q2 2023 would compare two different numbers. JPM needs `RevenuesNetOfInterestExpense` | One tag per metric per request, the one reaching the latest quarter (FR-10); `RevenuesNetOfInterestExpense` added. AAPL, MSFT and JNJ resolve to `RevenueFromContract…`, XOM to `Revenues`, JPM to `RevenuesNetOfInterestExpense`; all five have `NetIncomeLoss` and `EarningsPerShareDiluted` through Q2 2024 |
| C-2 | XOM maps to CIK 2115436 (ExxonMobil Holdings Corp, first filing 2026-07-01) with no facts before 2026, so every XOM backtest would be rejected as "no SEC filings" | D-M3-16 |
| C-3 | AC-3 listed "restated value", which is M1's filtering, already tested by M1-AC-3 | Dropped from M3's fixture test |
| C-4 | `Indicators` and `FundamentalsMetrics` were placed in `state.py`, which would make `tools/` import the state (and through it `llm/`) | Defined in the `tools/` module that computes them; `state.py` imports them (NFR-3) |
| C-5 | LangGraph's `invoke` returns a plain dict even with a Pydantic state | The runner validates it back into `RequestState` |

## 8. Open questions for the owner

None. Q1 was answered **A** on 2026-09-28: the fundamentals LLM judges filing-based numbers only, P/E goes to the debate and report as evidence (deviation D10, architecture v2.2).

---

# Part B: Plan

## 9. Module design

### 9.1 Files created or changed

```text
pyproject.toml, uv.lock        + langgraph (D-M3-14)
.env.example                   + the FR-22 settings
bullpit/
  config.py                    + FR-22 settings
  domain.py                    new: Account, Position, Asset
  state.py                     new: Bar, PriceSnapshot, SignalsBoard, RequestState
  request_check.py             new: the request_check node
  graph.py                     new: Deps, build_graph, the analyst failure wrapper
  broker/base.py               new: Broker protocol
  broker/alpaca.py             new: AlpacaBroker (read-only)
  data/prices.py               PriceHistory.splits (D-M3-11)
  data/sec.py                  CIK override table (D-M3-16)
  tools/indicators.py          new: Indicators, compute_indicators
  tools/fundamentals.py        new: FundamentalsMetrics, compute_fundamentals
  tools/sentiment.py           new: select_headlines, weighted_sentiment
  agents/technical.py          new
  agents/fundamentals.py       new
  agents/sentiment.py          new
  agents/signals_board.py      new
  agents/brain.py              new
  llm/schemas.py               Signal extended; AnalystVerdict, HeadlineScore(s)
  llm/gateway.py               thread-safe token buckets and Langfuse latch (NFR-2)
  llm/prompts/technical.md     new
  llm/prompts/fundamentals.md  new
  llm/prompts/sentiment.md     new
  journal/models.py            Request columns, SignalRecord
  journal/migrations/versions/0002_request_lock_signals.py   new
  runners/request.py           new: run_request, the lock, recording
  cli.py                       + request command
tests/
  conftest.py                  journal fixture moves to a temp file (threads, §13)
  broker/fake_broker.py        new
  tools/__init__.py            new
  tools/test_indicators.py     new
  tools/test_fundamentals.py   new
  test_graph.py                new
  fixtures/sec/aapl_companyfacts.json   + NetIncomeLoss, EarningsPerShareDiluted (recorded)
docs/dev-plan.md               §3 D10, D11
docs/architecture.md           v2.2: Part 5, Part 6 wording
README.md                      quick start: first `bullpit request`
```

`bullpit/agents/`, `tools/`, `runners/` already exist as empty packages from M0.

### 9.2 Dependency direction

```text
cli ──► runners/request ──► graph ──► request_check, agents/* ──► tools/* (pure)
                    │                        │           └──► llm/gateway, data/*
                    └──► journal             └──► broker/base (protocol)
state ──► domain, llm/schemas, tools (models only)
```

`tools/` imports only pandas, NumPy and Pydantic. Agents do the I/O (data layer, gateway) and turn tool results into evidence. Nodes take `(state, deps)` and return a dict of the fields they set.

### 9.3 Nodes

| Node | Reads | Writes | Calls |
|---|---|---|---|
| `request_check` | `ticker`, `as_of` | `rejection`, or `company_name`, `account`, `position`, `prices` | `broker.get_asset`, `get_sec_facts`, `get_prices`, `broker.get_account`, `broker.get_position` |
| `technical` | `prices` | `indicators`, `technical_signal` | `compute_indicators`, `call_llm(SMALL, "technical.md")` |
| `fundamentals` | `prices` | `fundamentals`, `fundamentals_signal` | `get_sec_facts`, `compute_fundamentals`, `call_llm(SMALL, "fundamentals.md")` |
| `sentiment` | `ticker`, `as_of`, `company_name` | `sentiment_signal` | `get_news`, `select_headlines`, `call_llm(SMALL, "sentiment.md")`, `weighted_sentiment` |
| `signals_board` | the three signals | `board` | `build_board` |
| `brain` | whole state | `route`, `warnings` | `choose_route`, `data_warnings` |

The analyst nodes are wrapped once, in `graph.py`, by `_analyst_node(field, fn)`: it catches every exception except `QuotaExhausted` and `LookaheadViolation`, logs it with its traceback, and writes a neutral, confidence-0, flagged `Signal` with the reason (FR-15). A flagged gateway result is turned into the same kind of signal inside each agent.

### 9.4 Graph wiring

```python
@dataclass(frozen=True)
class Deps:
    settings: Settings
    sessions: sessionmaker[Session]
    broker: Broker
    completion_fn: CompletionFn

def build_graph(deps: Deps) -> CompiledStateGraph: ...
```

`StateGraph(RequestState)`; `START → request_check`; a conditional edge from `request_check` returns `END` when `rejection` is set, otherwise the list `["technical", "fundamentals", "sentiment"]` (the fan-out, checked with LangGraph 1.2.12: the three run in a thread pool); each analyst → `signals_board` (LangGraph waits for all three) → `brain` → `END`. Each node is bound with `functools.partial(node, deps=deps)`.

### 9.5 Evidence facts

Written by the agents, from tool results only. Formatting: prices and EPS to 2 decimals, percentages to 1 decimal with a sign, RSI to 1 decimal, dollar totals in billions or millions with 2 decimals; a `None` value becomes "not available". No zone labels such as "overbought": the number is enough, and a label would need its own thresholds.

| ID | Fact (example) |
|---|---|
| T1 | `Close 182.31 is above SMA 20 (179.40)` |
| T2 | `Close 182.31 is above SMA 50 (170.02)` |
| T3 | `RSI 14 is 68.2` |
| T4 | `ATR 14 is 4.02 (2.2% of the close)` |
| T5 | `20-day volatility is 24.1% a year` |
| T6 | `Returns: 1 week +1.2%, 1 month +5.4%, 3 months not available` |
| F1 | `Revenue for the quarter ended 2024-06-29 was $85.78B, +4.9% on a year earlier` |
| F2 | `Net margin for that quarter was 25.0%` |
| F3 | `Diluted EPS over the last 4 quarters was 6.57` |
| F4 | `P/E is 34.8 at the reference price` (evidence only, not in the prompt, D10) |
| F5 | `Latest filing: 10-Q for the period ended 2024-06-29, filed 2024-08-02` |
| S1… | `2024-07-10: "Apple unveils …" (score +0.60, relevance 0.90)` |

### 9.6 Prompts

Three compact Markdown templates (Jinja2, M2's loader), each: one-line role, the ticker and company name, the facts with their IDs, the reply format and "JSON only". Technical and fundamentals ask for `{"direction", "confidence"}`, with confidence described as "0 = no view, 1 = very strong". Sentiment lists `ID: date: headline` and asks for `{"scores": [{"id", "score", "relevance"}]}`, with relevance described as "how much the headline is about {company} itself". The fundamentals template receives no price, P/E or date (FR-11).

### 9.7 Runner and CLI

`run_request` in order:

1. `request_id` from `as_of`, ticker and `secrets.token_hex(4)`.
2. Backtest and `as_of` on or before the latest model cutoff: write a `rejected` row with the FR-5 message and return.
3. **Lock** (one transaction): mark `running` rows for (ticker, mode) older than the timeout as `failed` ("abandoned", logged as a warning); insert the `running` row; an `IntegrityError` from the partial unique index means a duplicate: roll back and write a `rejected` row instead.
4. Bind `request_id`, `mode` and `as_of` with `structlog.contextvars`; `build_graph(deps).invoke(RequestState(...))`; `RequestState.model_validate(result)` (§7.1 C-5).
5. `finally`, in one transaction: set status (`rejected` if `rejection`, `completed`, or `failed` with the exception text), `route`, `warnings`, `config`, `git_commit`, `price_source`, `finished_at`, and add the `signals` rows. A failure re-raises after recording.

`config` is `settings.model_dump(mode="json")` minus every `SecretStr` field and `sec_contact_email`. `git_commit` is `git rev-parse HEAD` through `subprocess.run` with the path from `shutil.which("git")`, or `"unknown"`.

The `request` command parses `--mode` and `--as-of`, refuses `--as-of` in live mode and requires it in backtest (typer errors, exit 2), runs `alembic.command.upgrade(cfg, "head")` with `script_location` set to `bullpit/journal/migrations` (so it works from any working directory), builds the clock, `AlpacaBroker`, journal sessions and `Deps`, calls `run_request`, and prints the result as plain text.

### 9.8 Thread safety (NFR-2)

- `gateway._TokenBucket.acquire` and `_bucket_for` take a `threading.Lock`; the sleep happens outside the lock, then the bucket is rechecked. `_maybe_register_langfuse` takes the same kind of lock.
- The journal file engine gives each thread its own connection (SQLAlchemy's pool for file SQLite); WAL plus SQLite's default busy timeout covers three short `llm_calls` inserts.
- Data caches: in the parallel phase, fundamentals only touches `sec_facts/`, sentiment only `news/`, and technical touches no cache (D-M3-2). SEC pacing's module-level timestamp is only used by one thread at a time.

## 10. Data model

Migration `0002_request_lock_signals`, written with `op.batch_alter_table("requests")` (SQLite can't add `NOT NULL` columns in place; `requests` is still empty on every existing journal, since only the M2 measurement spike ever wrote to one, in a temp DB).

| Table | Column | Type | Notes |
|---|---|---|---|
| `requests` | `ticker` | `TEXT NOT NULL` | Upper-case |
| | `status` | `TEXT NOT NULL` | `running` \| `completed` \| `rejected` \| `failed` |
| | `status_reason` | `TEXT` | Rejection message or error text |
| | `route` | `TEXT` | `debate` \| `no_trade` |
| | `warnings` | `JSON` | List of strings |
| | `config` | `JSON` | Settings snapshot without secrets |
| | `git_commit` | `TEXT` | |
| | `price_source` | `TEXT` | `yfinance` \| `alpaca` |
| | `finished_at` | `DATETIME` | UTC |
| | index `uq_requests_running` | unique (`ticker`, `mode`) `WHERE status = 'running'` | The lock (FR-3); `sqlite_where` |
| `signals` | `id` | `INTEGER PRIMARY KEY` | |
| | `request_id` | `TEXT NOT NULL`, FK → `requests.id`, indexed | |
| | `analyst` | `TEXT` | |
| | `direction` | `TEXT` | |
| | `confidence` | `FLOAT` | |
| | `evidence` | `JSON` | List of `{id, fact}` |
| | `flagged` | `BOOLEAN` | |
| | `note` | `TEXT` | |

The ORM class for `signals` is `SignalRecord`, so it doesn't clash with the `Signal` schema. `llm_calls.request_id` stays a plain indexed column (M2-FR-13).

## 11. Key algorithms

### 11.1 Indicators

As defined in FR-8, over the bars as a DataFrame (floats). Wilder smoothing is a plain loop over NumPy arrays (clear, and fast enough for 300 bars). Returns and volatility use `pct_change`. Each value needs a minimum number of bars (SMA 20: 20; SMA 50: 50; RSI and ATR: 15; volatility: 21; returns: k + 1) and is `None` below it.

### 11.2 Fundamentals

```text
facts = us-gaap facts, unit USD (revenue, net income) or USD/shares (EPS)
days  = end − start;  quarter if 80..100, year if 350..380
for each candidate tag of a metric:
    quarters = discrete quarters
    for each year fact (S, E) with no discrete quarter ending at E:
        q = discrete quarters with start ≥ S and end < E
        if len(q) == 3: add Q4 = year − Σq, period (end of the third quarter, E], filed = year's filed
    series[tag] = quarters by end date
tag = the candidate whose series has the latest end (ties: list order)   # §7.1 C-1
latest       = series[tag] last quarter
year_ago     = quarter with end in [latest.end − 375 d, latest.end − 355 d]
growth       = latest / year_ago − 1               (None if no year_ago)
margin       = net_income(latest.end) / revenue(latest.end)
ttm quarters = the last 4 EPS quarters, each end 80..100 days after the one before
eps_adj(q)   = q.eps / Π(ratio for (ex_date, ratio) in splits if q.filed < ex_date)
ttm_eps      = Σ eps_adj over the 4 quarters    (None if fewer than 4)
pe           = float(reference_price) / ttm_eps  if ttm_eps > 0 else None
```

Net income is matched to revenue by period end date. The latest filing is the `form`, `end` and `filed` of the latest revenue quarter's fact.

### 11.3 Sentiment

```text
words(h)  = set of lower-case [a-z0-9]+ tokens in the headline
articles newest first; keep one if Jaccard(words, each kept) < news_duplicate_similarity
stop at news_max_headlines; number S1 (newest) …
s = Σ r·score / Σ r over the IDs the reply scored (unknown IDs ignored)
```

### 11.4 Board and brain

```text
value(direction) = +1 bullish, 0 neutral, −1 bearish
score    = Σ value × confidence / 3
conflict = any(bullish, conf ≥ c) and any(bearish, conf ≥ c),  c = brain_conflict_min_confidence
route    = "no_trade" if |score| < brain_min_abs_score and not conflict else "debate"
```

## 12. Error handling

| Where | Error | Result |
|---|---|---|
| Runner, before the graph | `as_of` too early, duplicate | `rejected` row, message, no LLM call |
| `request_check` | `get_asset` returns `None` (Alpaca 404, checked 2026-09-28) or not tradable/active | Rejection |
| `request_check` | `DataUnavailable` from `get_sec_facts` | Rejection with M1's message |
| `request_check` | `DataUnavailable` from `get_prices`, or fewer than `min_price_sessions` bars | Rejection "too little history" (n = 0 when nothing came back) |
| `request_check` | Broker error reading the account | Raises: request `failed` (it's an outage, not a bad ticker) |
| Analyst | Any exception except the two below; flagged gateway reply | Neutral, confidence-0, flagged signal, warning (FR-15) |
| Anywhere | `QuotaExhausted`, `LookaheadViolation` | Request `failed`, lock released, re-raised; the CLI prints it and exits 1 |
| Board | Duplicate or wrongly prefixed evidence ID | `ValueError` (a bug in our code, never data) |

`AlpacaBroker` wraps alpaca-py errors: a 404 on `get_asset` or `get_position` becomes `None`; anything else becomes `BrokerRejected` (M0's hierarchy), so no SDK exception leaves `broker/`.

## 13. Test and verification plan

Automated tests only where [dev-plan §7](../../dev-plan.md#7-testing-strategy) requires them. All run offline in a few seconds.

**`tests/tools/test_indicators.py`** (AC-2): two bar fixtures built in the test: a linear ramp, where SMA, returns and RSI (100) have closed forms, and a 20-bar hand-worked series with gaps, whose RSI 14, ATR 14 and volatility are written as literals worked out by hand (the working is in the test's docstring). Plus: a 3-month return with 60 bars is `None`.

**`tests/tools/test_fundamentals.py`** (AC-3, fixture part), on small hand-built fact tables:

| Test | Checks |
|---|---|
| `test_quarterly_metrics` | Growth, margin, TTM EPS and P/E on four clean quarters and the year-ago quarter |
| `test_q4_derived_from_annual` | A latest quarter that exists only as FY − Q1..Q3 (the MSFT case at 2024-10-18), with the 10-K's filing date |
| `test_tag_choice_does_not_mix_definitions` | Two revenue tags (the XOM case): the one reaching the latest quarter is used for every period |
| `test_eps_split_adjusted_and_negative_pe` | EPS filed before a 10:1 split is divided by 10; negative TTM EPS gives `pe = None` |

**`tests/test_graph.py`**: the graph through `run_request`, with the fake broker, a temp-file journal, recorded AAPL fixtures (prices, news, companyfacts; downloads patched as in M1's tests) at `as_of` = 2024-07-05, and a fake completion function defined in the test that answers **by template** (parallel calls arrive in any order, so M2's queue fake can't be used) and records every prompt.

| Test | AC |
|---|---|
| `test_debate_route` | AC-1 (automated), AC-6: status `completed`, three unflagged signals, every evidence ID unique, prefixed and in the registry, 3 `llm_calls` rows and 3 `signals` rows; the sentiment direction and confidence equal the weighted average of the scripted scores (covers FR-14) |
| `test_weak_signals_route_to_no_trade` | AC-7: all-neutral replies → `no_trade`, exactly 3 `llm_calls` rows |
| `test_failed_analyst` (parametrised) | AC-5: fundamentals raising `LLMUnavailable` → neutral flagged signal, warning, `completed`; raising `QuotaExhausted` → `run_request` raises, row `failed`, a new request for the ticker isn't refused (lock released) |
| `test_no_future_data_reaches_a_prompt` | AC-9: no prompt contains any headline created after the 2024-07-05 close; the technical close equals the recorded 2024-07-05 close; the fundamentals latest filing date is on or before 2024-07-05 |

The fixture companyfacts gains AAPL's `NetIncomeLoss` and `EarningsPerShareDiluted` facts, recorded from SEC the same way M1 recorded revenue.

`tests/conftest.py`'s `sessions` fixture moves from `sqlite://` (one database per connection, so a worker thread would see an empty journal) to a file in `tmp_path`.

Not tested automatically (dev-plan §7.3, C12): the request check's rejections, the CLI, logging, `AlpacaBroker`, the Alembic migration, the prompts' quality, the token buckets' locking.

**Manual checks**, evidence pasted into `task.md`:

| Check | How |
|---|---|
| AC-1 | `bullpit request` for the 5 tickers × 3 dates (backtest) and one live request; outputs pasted, one line each |
| AC-3 table | Latest-quarter revenue at 2024-10-18 per ticker, compared with the 10-Q/10-K figure |
| AC-4 | SPY, an unknown ticker, a recent listing before 60 sessions, a duplicate (a second terminal during a run), `--as-of 2024-06-28`; messages and the `llm_calls` count per `request_id` pasted |
| AC-8 | `llm_call` start lines of one request show the three analysts starting together |
| AC-10 | `llm_calls` per template over the AC-1 runs (max and mean input, output, reasoning); the new allowance |
| AC-11 | One `requests` row and its `signals` rows; a hand-inserted stale `running` row cleared by the next request; `alembic upgrade head` on a temp DB compared with `models.py` |
| AlpacaBroker | Account, AAPL position (or none) and an unknown asset against the real paper account |

## 14. Work order

`task.md` breaks this into tasks:

1. Docs on the new branch; D10, D11 and architecture v2.2.
2. Dependency and settings.
3. Data-layer additions (`splits`, CIK override).
4. Domain types and the broker (plus the fake).
5. Indicators and their test.
6. Fundamentals maths and its test.
7. Sentiment tools.
8. Schemas, state, prompts.
9. Gateway thread safety; journal fixture on a temp file.
10. The three analyst agents.
11. Signals board and brain.
12. Request check.
13. Journal models and migration `0002`.
14. Graph, runner, CLI.
15. Graph tests and the fixture companyfacts.
16. Real runs: AC-1, AC-3 table, AC-4, AC-8, AC-11.
17. Token measurement and the allowance (AC-10).
18. Acceptance.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| LangGraph changes its API or threading | Graph breaks on upgrade | Pinned in `uv.lock`; the graph tests are the gate |
| Log context (`request_id`) not carried into LangGraph's worker threads | Analyst log lines lack `request_id` | Checked in AC-8's log excerpt; if missing, the nodes bind it from `state.request_id` |
| Another ticker's SEC data has a tag or reorganisation the list doesn't cover | Fundamentals neutral and flagged, or the request rejected | The flag and warning make it visible; AC-1 covers the reference tickers; the tag list and override table grow as needed |
| Pacing: three small calls at once with the 2,000-token allowance | The third analyst waits up to a minute | Expected; FR-23 lowers the allowance after measuring |
| A lower allowance starves the sentiment reply (15 scored headlines) | Flagged neutral sentiment | 3× the largest measured call, never below 500; flagged rates checked over the AC-1 runs |
| SQLite write contention between analyst threads | "database is locked" | Three tiny inserts; WAL and the default busy timeout; seen in AC-1 if it happens |

## 16. ADRs

None. Every M3 choice is recorded in §7; the two that change the architecture are deviations D10 and D11 in [dev-plan §3](../../dev-plan.md#3-deviations-from-the-architecture-roadmap).
