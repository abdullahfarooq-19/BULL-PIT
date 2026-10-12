# Bull Pit: system walkthrough

Written 2026-09-30 from a review session. This page explains, in plain language,
how a request travels from "you pick a stock" to "a trade is placed and shown on
the dashboard". It also records the project's status, what a review found, and
the answers to the questions asked during the session.

The sources of truth stay [`architecture.md`](architecture.md),
[`dev-plan.md`](dev-plan.md) and [`milestones/`](milestones/). If this page
disagrees with them, they win. Thresholds quoted here are the defaults in
`bullpit/config.py` on the day of writing.

## Contents

1. [What Bull Pit is](#1-what-bull-pit-is)
2. [The technology stack](#2-the-technology-stack)
3. [Project status](#3-project-status)
4. [The flow at a glance](#4-the-flow-at-a-glance)
5. [The shared state](#5-the-shared-state)
6. [The flow, node by node](#6-the-flow-node-by-node)
7. [Parts outside the graph](#7-parts-outside-the-graph)
8. [What you see on the dashboard](#8-what-you-see-on-the-dashboard)
9. [Backtest mode and baselines](#9-backtest-mode-and-baselines)
10. [Where AI judgment ends and code starts](#10-where-ai-judgment-ends-and-code-starts)
11. [Questions and answers](#11-questions-and-answers)
12. [Review findings](#12-review-findings)
13. [Candidate changes](#13-candidate-changes)

---

## 1. What Bull Pit is

Bull Pit works like a small research desk that studies one stock at a time.

1. You pick a stock.
2. Three analysts study it: price trend, company financials, news.
3. A **bull** agent argues for buying and a **bear** agent argues against, for two rounds.
4. A **trader** says "buy" or "no trade". Code works out the share count and the
   exits. A **risk manager** can shrink the order or veto it.
5. You get a **report**. **Nothing trades until you approve.**
6. Approved trades go to an **Alpaca paper account** (fake money, real prices).
   In backtest mode a simulated broker is used instead.

One rule runs through the whole design: **code does the math, and the AI only
does judgment.** An LLM's output is never used as a number unless code
validated and bounded it.

**No real money, ever.** The Alpaca client refuses any URL other than
`paper-api.alpaca.markets`.

## 2. The technology stack

| Layer | Tool | Its job |
|---|---|---|
| Language | Python 3.12 (managed with `uv`) | All the backend |
| Orchestration | LangGraph, with a SQLite checkpointer | Runs the steps, runs the analysts in parallel, pauses for your approval |
| LLM access | LiteLLM, through `bullpit/llm/gateway.py` | One door for every model call |
| LLM models | Groq `openai/gpt-oss-20b` (small) and `openai/gpt-oss-120b` (large) | Judgment and wording only. M7's pilot used `qwen/qwen3.8-27b:free` on OpenRouter (deviation D13) |
| Structured output | Pydantic v2 | Validates every agent reply and every value crossing a node |
| Data processing | pandas, NumPy | Indicators, ATR, ratios, sizing |
| Prices | yfinance, with Alpaca market data as backup | Daily bars, S&P 500 (SPY) and VIX |
| Fundamentals | SEC EDGAR companyfacts | Filing-based ratios with filing dates |
| News | Alpaca news API | Headlines up to `as_of` |
| Cache | Parquet files | Repeatable runs, fewer downloads |
| Journal | SQLite through SQLAlchemy and Alembic | Every request, signal, debate turn, report, approval and trade |
| Broker (live) | Alpaca paper trading, bracket orders | Fake-money orders |
| Broker (backtest) | Simulated broker in Python | Fills from daily bars |
| API | FastAPI, bound to `127.0.0.1` only | Starts requests, serves reports, takes decisions |
| Dashboard | Next.js 16, React, Tailwind, shadcn, TradingView Lightweight Charts | The screens you click |
| Quality | pytest, ruff, mypy, GitHub Actions, gitleaks | Tests, lint, types, CI, secret scan |

## 3. Project status

| Milestone | What it built | State |
|---|---|---|
| M0 | Foundations: scaffold, paper-only guard, `doctor`, CI, spikes | Done, tagged `m0` |
| M1 | Data layer, date guard, cache | Done, tagged `m1` |
| M2 | LLM gateway | Done, tagged `m2` |
| M3 | Request check, three analysts, signals board, brain | Done, tagged `m3` |
| M4 | Debate, trader, risk manager | Done, tagged `m4` |
| M5 | Report generator | Done, tagged `m5` |
| M6 | Simulated broker, journal, backtest runner | Done, tagged `m6` |
| M7 | Evaluation, baselines, pilot results | Done, tagged `m7` |
| M8 | Live mode: API, dashboard, approval, bracket orders, fill check | Done, tagged `m8` (accepted 2026-10-06) |
| M11.1 to M11.4 | Report explanations and order box; dashboard restructure; live P&L and market status; Backtests page removed | Done, tagged `m11.1` to `m11.4` |
| M9 | Dashboard polish, README, results write-up | In progress |

Status refreshed 2026-10-12; the rest of this page is as written on 2026-09-30
unless a note says otherwise. What each milestone built:
[`progress.md`](progress.md).

### The pilot result

The M7 pilot ([`results/results.md`](results/results.md)) used 2 stocks (BRK.B,
MSFT) over 2 weeks, one seed, on the free Qwen model.

| Approach | Total return | Tokens per request |
|---|---|---|
| Bull Pit | +0.30% | 21,361 |
| Single agent | +0.49% | 2,321 |
| Always buy | +0.44% | 0 |
| Moving-average rule | +0.36% | 0 |
| Bull Pit replayed (`bullpit_fixed`) | +0.36% | 0 |
| Buy and hold MSFT | +4.72% | n/a |
| Buy and hold BRK.B | +0.06% | n/a |

The differences between the approaches are noise. The pilot shows that the
pipeline works end to end. It does not show that any approach is better. The
open cost question is real: Bull Pit used about 9 times the tokens of the
single agent, and nothing yet shows the debate pays for itself. A proper test
(26 weeks, several stocks, repeat seeds) needs about 300 or more requests,
which the free tiers can't cover.

## 4. The flow at a glance

```
You pick a stock
  → request_check            (code: tradable? data? account?)
  → technical | fundamentals | sentiment     (in parallel: code maths + small LLM)
  → signals_board            (code: validate, score, conflict)
  → brain                    (code: debate or skip)
  → bull ⇄ bear              (large LLM, 2 rounds, 4 turns)
  → trader                   (large LLM: buy or no trade, weight, exit style)
  → risk_sizing              (code: Stage A, exits, share count, hard rules)
  → risk_review              (large LLM: Stage B, approve / shrink / veto)
  → report                   (code numbers, small LLM wording)
  → approval                 (pauses; YOU approve or reject)
  → execute                  (one idempotent bracket order to Alpaca)
  → fill check               (records fills; never changes a trade)
  → dashboard
```

Shortcuts that skip straight to `report`:

- a failed request check (rejection),
- the brain deciding weak signals aren't worth a debate,
- the trader saying "no trade",
- Stage A blocking the trade,
- Stage B vetoing after the retries are used up.

Only a **live buy** continues past the report to `approval` and `execute`.

Loops: `bull → bear → bull → bear` (two rounds), and `risk_review → trader` on a
veto, at most twice (`risk_max_vetoes = 2`).

## 5. The shared state

The graph is one LangGraph graph. Every node reads from and writes to one typed
object, `RequestState` (`bullpit/state.py`). Each node adds only its own fields,
so the state grows as the request goes on:

| Field | Filled by |
|---|---|
| `request_id`, `mode`, `as_of`, `ticker` | The runner, before the graph starts |
| `rejection` | `request_check` (only if a check fails) |
| `company_name`, `account`, `position`, `prices` | `request_check` |
| `indicators`, `technical_signal` | technical analyst |
| `fundamentals`, `fundamentals_signal` | fundamentals analyst |
| `sentiment_signal` | sentiment analyst |
| `board` | signals board |
| `route`, `warnings` (and `outcome`/`no_trade_reason` on "no trade") | brain |
| `debate` | bull and bear |
| `attempts` | trader, risk sizing, risk review |
| `sized_order`, `outcome`, `no_trade_reason` | risk nodes |
| `loss_warning` | the runner, from equity snapshots |
| `report` | report |
| `approval` | approval |
| `trade` | execute |

Dependencies such as settings, the journal, the broker and the LLM function are
bound when the graph is built and are never stored in the state. That keeps the
state serialisable for the checkpointer.

## 6. The flow, node by node

Legend: `[Code]` plain Python, `[LLM]` an AI does the work, `[Both]` they share it.

### 6.0 Before the graph: the runner opens the request

- **Input:** the ticker you typed.
- **What happens:**
  1. The API trims and upper-cases the ticker and checks its shape.
  2. `as_of` is set by the live clock to the **last NYSE session whose close has
     already happened**.
  3. The duplicate lock is taken (see [question 1](#q1-second-request-for-the-same-ticker-refused-for-how-long)).
  4. Any overdue waiting reports for that ticker expire first.
  5. The graph starts in a background thread, and the API returns a `request_id`
     at once (HTTP 202).
- **Output:** a `running` request row in the journal and a `request_id` such as
  `20260930-MSFT-1a2b3c4d`.

### 6.1 `request_check` `[Code]`

Runs first and costs no tokens, so a bad request is free.

- **Input:** `ticker`, `as_of`, the broker.
- **Computes:**
  1. Alpaca's asset lookup: the stock must exist, be tradable and be active.
  2. SEC filings must exist. ETFs and unknown tickers fail here with "No SEC
     filings found for this ticker. Try a US company stock."
  3. Prices through the date guard: about 300 sessions fetched, at least 60
     required (`min_price_sessions`).
  4. Your account (cash, equity) and any existing position in this stock.
  5. `reference_price` is the last close.
- **Output:** `company_name`, `account`, `position`, `prices`. On any failure it
  outputs `rejection` with a message you can act on, and the graph goes straight
  to `report`.

### 6.2 The date guard and data layer (how data reaches the graph)

Agents never call yfinance, the SEC or Alpaca directly. Every data function takes
`as_of` and is protected twice: the request asks only for data up to `as_of`, and
the response is checked and any row dated later is dropped and logged. Prices are
**point-in-time**: a split is applied to history only once it had happened, so a
stored history never changes after the fact (ADR-0003). Everything is cached as
Parquet.

### 6.3 Technical analyst `[Both]`

- **Input:** `prices` from the state (no new fetch).
- **Code computes:** SMA 20 and SMA 50, RSI 14, ATR 14, 20-day volatility
  (annualised), and 1-week, 1-month and 3-month returns. It writes six evidence
  facts:

  | ID | Fact (example) |
  |---|---|
  | T1 | Close 182.00 is above SMA 20 (178.40) |
  | T2 | Close 182.00 is above SMA 50 (170.10) |
  | T3 | RSI 14 is 68.0 |
  | T4 | ATR 14 is 4.00 (2.2% of the close) |
  | T5 | 20-day volatility is 24.0% a year |
  | T6 | Returns: 1 week +1.2%, 1 month +3.4%, 3 months +8.0% |

- **LLM (small model):** sees only those facts and answers `direction` and
  `confidence`. It writes no reasoning and no summary.
- **Output:** `technical_signal`, plus `indicators` saved in the state. ATR is
  later used to set the stop-loss and take-profit.

### 6.4 Fundamentals analyst `[Both]`

- **Input:** SEC facts filed on or before `as_of`, and the price.
- **Code computes:** revenue growth (this quarter against the same quarter last
  year), net margin (net income ÷ revenue), trailing four-quarter EPS, and the
  **P/E ratio**. The missing Q4 is computed as the annual total minus Q1 to Q3.
  Different XBRL tags for the same number are handled by a mapping list.
- **LLM (small model):** judges direction and confidence from the **filing-based
  ratios only**. P/E moves with the daily price, so code adds it to the evidence
  for the debate and report, but it is kept out of the LLM's prompt. The prompt
  then changes only when a new filing arrives, so the verdict is cached by
  (ticker, latest filing date) and is never reused with a later price (D10).
- **Output:** `fundamentals_signal` (F-IDs) and `fundamentals` metrics.

### 6.5 Sentiment analyst `[Both]`

- **Input:** Alpaca news from the 7 days before `as_of`.
- **Code computes:** removes near-duplicates (similarity 0.8) and keeps up to 15
  headlines. After the LLM scores them, code takes a relevance-weighted average
  (with a neutral band of ±0.15).
- **LLM (small model):** scores each headline from −1 to +1 and marks how
  relevant it is to this company.
- **Output:** `sentiment_signal` (S-IDs). No news gives neutral with confidence 0.

The three analysts run in parallel. The analyst format is shared:

```json
{
  "ticker": "AAPL",
  "analyst": "technical",
  "direction": "bullish",
  "confidence": 0.6,
  "evidence": [
    {"id": "T1", "fact": "Close 182 is above SMA50 of 170"},
    {"id": "T2", "fact": "RSI 68, near the overbought zone"}
  ]
}
```

### 6.6 `signals_board` `[Code]`

- **Input:** the three signals.
- **Computes:**
  - `score` = the sum of (direction × confidence) across the three signals,
    divided by 3. Bullish counts +1, neutral 0, bearish −1.
  - `conflict` = true if one analyst is bullish and another bearish, both with
    confidence of at least 0.4 (`brain_conflict_min_confidence`).
  - An **evidence registry** of every ID the debate may cite. It checks each ID
    has the right prefix (T, F or S) and is unique.
- **Output:** `board`.

### 6.7 `brain` `[Code]`, no LLM

- **Input:** `board`.
- **Computes:**
  - **Route:** if `|score|` is below 0.15 (`brain_min_abs_score`) and there is no
    conflict, the route is `no_trade` and the debate is skipped, saving about 5
    LLM calls. Otherwise the route is `debate`.
  - **Data warnings:** a flagged analyst, no news, fewer than 3 headlines
    (`news_thin_articles`), missing indicators or fundamentals metrics, and prices
    that came from the Alpaca backup.
- **Output:** `route`, `warnings`, and on "no trade" also `outcome` and
  `no_trade_reason`.

### 6.8 Bull and bear debate `[LLM]`, large model

- **Input:** the board score, the conflict flag, every signal's direction,
  confidence and flagged status, every evidence fact, and the transcript so far.
- **Flow:** the bull speaks first each round.
  - Round 1: the bull states its three strongest points; the bear rebuts each
    and adds counter-evidence.
  - Round 2: the bull answers the attacks; the bear gives its final response.
  - That is four turns (`debate_rounds = 2`).
- **Each turn returns the same format:** `points` (a claim plus evidence IDs),
  `concessions`, and `conviction` from 0 to 1. The word limit is 150 per turn
  (`debate_turn_max_words`).
- **Code checks after each turn:**
  - A point that cites no ID, or an ID not in the registry, is marked
    **unsupported**.
  - It counts the words and flags a turn that goes over the limit. The limit is
    soft: code flags it and adds a warning, and it never truncates.
  - An invalid reply after one retry becomes an empty, flagged turn.
- **Output:** a list of `DebateTurn` added to `debate`. Each side's final
  conviction is the conviction of its last turn.

### 6.9 `trader` `[LLM]`, large model

- **Input:** the board score and conflict flag, the signals, the facts, the
  transcript, both final convictions, your cash, equity and existing holding
  (as a percentage of equity), the 10% maximum, the three exit-style
  descriptions, and any earlier vetoes (so it can adjust).
- **LLM returns:** `action` (`buy` or `no_trade`), `target_weight` (0 to 1, as a
  fraction of equity), `exit_style` (tight, normal or wide), `confidence`,
  `decisive_evidence` (fact IDs), and `reasoning`.
- **Code then:** clamps the weight to between 0 and 10% (`max_position_pct`),
  and keeps only registered evidence IDs. An invalid reply after the retry is
  recorded as a flagged "no trade".
- **Output:** a `Recommendation`, stored as a `TradeAttempt`. `no_trade` goes to
  the report. `buy` goes to `risk_sizing`.

### 6.10 `risk_sizing`: Stage A `[Code]`

- **Input:** the last recommendation, the account, `held_value`, the reference
  price, and ATR.
- **Hard blocks, in this order:**
  1. ATR or price missing.
  2. No cash or no equity.
  3. The position you already hold is 10% or more of equity.
  4. Exit prices invalid (stop at or below zero, or at or above the price).
  5. The size rounds to 0 shares.
- **Exits from ATR** (`exit_reward_risk = 1.5`):

  | Style | Stop-loss | Take-profit |
  |---|---|---|
  | Tight | entry − 1.5 × ATR | entry + 2.25 × ATR |
  | Normal | entry − 2 × ATR | entry + 3 × ATR |
  | Wide | entry − 3 × ATR | entry + 4.5 × ATR |

- **Share count = the smallest of four limits:**
  1. the trader's target weight,
  2. **risk per trade**: a stop hit loses at most 1% of equity,
  3. **per-stock cap**: this stock including shares you already hold stays under 10%,
  4. **cash**: never more than available cash (Alpaca `cash`, never `buying_power`).
- **Worked example** (from the architecture). Equity $100,000, cash $96,000,
  AAPL at $182, ATR $4, "normal" at 6%. Stop = 182 − 2×4 = **$174**, target =
  182 + 3×4 = **$194**, risk per share = $8. Limit 1 (target): 32 shares. Limit 2
  (risk): 1% of equity = $1,000 ÷ $8 = 125 shares. Limit 3 (cap): 54 shares.
  Limit 4 (cash): 527 shares. Final: **32 shares** (about $5,824), with a
  maximum loss of about $256 and a possible gain of about $384.
- **Output:** a `SizedOrder` (shares, stop, target, cost, maximum loss, maximum
  gain, which limit set the size), or a block reason and `no_trade`.
- **Loss warning:** separately, if equity fell more than 5% over the last 7 days
  (`loss_warning_pct`, `loss_warning_days`), the report shows a red warning and
  approval needs an extra confirmation. It is unknown (`None`) until the
  equity history reaches back far enough.

### 6.11 `risk_review`: Stage B `[LLM]`, large model

- **Input:** the sized order, the debate, and the signals.
- **LLM returns:** `approve`, `shrink` (with a share count) or `veto`, with a
  reason. It looks for things rules can't see, such as a serious bear point the
  trader ignored or a size that doesn't match weak confidence.
- **Code:** enforces **shrink-only**. A larger share count is clamped back to
  the original. The LLM can never enlarge an order.
- **Output:** a `RiskVerdict`.
  - Approve or shrink: `outcome = buy` and the final `sized_order`.
  - Veto: back to the trader, at most twice. After that the result is "no trade".

### 6.12 `report` `[Both]`

- **Input:** all the state above. It also fetches the S&P 500 and VIX for market
  context (VIX below 15 is low, above 25 is high). A rejected request skips this
  and costs nothing.
- **Code fills every number and section.** The ten sections, in order:
  1. Header (ticker, company, time, date of the price data)
  2. Recommendation (buy or no trade, confidence, one sentence)
  3. Suggested order (buy only): shares, amount, % of equity, stop, target,
     maximum loss, possible gain
  4. What the analysts found (the signals table with evidence)
  5. The debate
  6. Risk manager (which limit set the size, any shrink or veto, warnings)
  7. What would change the view
  8. Market context
  9. Data notes (models, article count, latest filing date, warnings)
  10. Actions (buy only): share count, Approve, Reject
- **The small LLM writes only six short fields:** `summary`, `strongest_bull`,
  `strongest_bear`, `bull_conceded`, `unresolved`, `would_change_view`. The four
  debate fields are empty when there was no debate.
- **The number check** rejects any figure or evidence ID in the LLM's text that
  isn't already in the report. The LLM is asked to rewrite it once.
- **Output:** `report`, saved to the journal. A report is produced for **every**
  request: buy, no trade and rejected.
- **Next:** only a live buy goes on to `approval`.

### 6.13 `approval`: the pause `[Code]`

- **Input:** the sized order.
- **What happens:** the node calls LangGraph's `interrupt()`. The graph's state
  is saved to the SQLite checkpointer (`checkpoints.db`, its own file, with a
  strict list of allowed state types) and the graph waits. It survives an API
  restart. The request's status becomes `awaiting_approval`.
- **You decide on the dashboard.** When you click Approve the API runs the
  decision checks, under a lock, stopping at the first failure:
  1. **Expiry:** the report must be no older than the close of the first session
     after it was made.
  2. **Shares:** between 1 and the recommended count. They can only go down.
  3. **Latest price:** fetched from Alpaca (the latest trade). If unavailable,
     the approval is refused.
  4. **Staleness:** if the price moved more than 2% (`approval_staleness_pct`)
     since the report, you must confirm again or re-run.
  5. **Loss warning:** must be confirmed if active.
  6. **Price against exits:** the latest price can't be at or below the stop or
     at or above the target.
  7. **Cash and cap:** re-checked at the latest price, **net of orders that
     haven't filled yet**.
- **Order of record:** the approval is written to the journal **before** any
  order is placed.
- **Output:** an `ApprovalDecision`. Reject ends the graph.

### 6.14 `execute` `[Code]`

- **Input:** the approval.
- **What happens:**
  1. It confirms the **same approval is recorded** in the journal, otherwise it
     refuses.
  2. It submits **one bracket order** to Alpaca: a market buy with a stop-loss
     and a take-profit, good-till-cancelled, whole shares, with a unique
     `client_order_id` derived from the request ID.
  3. Submitting is idempotent. A retry after a crash or a network error looks up
     the order by `client_order_id` and uses it, so at most one order exists.
  4. It saves the trade and marks the request completed, in one transaction.
- **Output:** a `Trade`. An order placed while the market is closed waits for
  the next open.

## 7. Parts outside the graph

| Part | Input | What it does | Output |
|---|---|---|---|
| **LLM gateway** | A prompt template, variables, a reply schema | Routes to the small or large model, caches responses, paces to the free tier's limits, retries on rate limits with backoff, validates the JSON (one retry with the error, then a safe default and a flag), enforces a daily token budget, logs every call | A validated reply and a row in `llm_calls` |
| **Journal** | Everything the graph produces | Stores requests, signals, debate turns, recommendations, reports, approvals, trades, equity snapshots, LLM calls, backtest runs | The history the dashboard and evaluation read |
| **Fill check** | Live trades that are pending or open | Reads Alpaca order status and equity history. **It only records**: entries, exits (stop, target or manual close), partial-fill warnings, and live equity snapshots | Updated trade rows and snapshots |
| **API** | Your clicks | `POST /requests`, `GET /requests/{id}`, `GET /requests/{id}/report`, `POST /requests/{id}/approval`, `GET /trades`, `GET /equity`, `POST /fill-check`, `GET /history`, `GET /account`, `GET /market`, `GET /portfolio`, `GET /watchlist` | JSON for the dashboard |
| **Clock** | Nothing | The only place that reads the wall clock. `LiveClock` gives the last completed session; `SimClock` gives a fixed date | `as_of` |

The fill check runs each time the dashboard opens (there is no scheduler), or
with `bullpit fill-check`. A trade can also be closed by hand in Alpaca. The fill
check detects it from the orders and records it as a `manual` exit.

## 8. What you see on the dashboard

The design direction is "the pit, at night": a dark, dense trading-desk screen
where bull and bear are the only saturated colours.

| Page | What it shows |
|---|---|
| **Account & Wallet** | The Alpaca paper account (masked number, Demo badge, balance refreshed every 5 seconds, day change, cash); the ticker box and Start; **Liked stocks**; an S&P 100 **watchlist** with a filter and stars. Picking a stock fills the ticker box. Ctrl+K opens a command palette |
| **Trades History** | One row per analysis, from analysing to closed: date, ticker, one status label, shares, entry, TP, SL, P&L, exit, and Cancel for a waiting order. Filter chips; the ticker opens the stored analysis, which has a link back |
| **Portfolio** | The **equity chart** (TradingView Lightweight Charts) with entry and exit markers; realised statistics; a short description of Bull Pit and a disclaimer |
| **Report and decide** (opened from Trades History) | While running: a progress timeline (Check, Analysts, Debate, Trader, Risk, Report), refreshed every 2 seconds. When ready: the recommendation, the **bracket price ladder**, a paragraph and lean bar per analyst, the debate round by round with its full turns, risk notes, an **expiry countdown** and the **order box** (live price, Buy now or Buy at a price, advanced mode, hold-to-approve, Reject, Cancel). Since M11.2 it starts with a link back to Trades History |

Since M11.1 the report carries the debate's turns, so the page shows them; the sections above describe the dashboard as of M11.2 (2026-10-06).

## 9. Backtest mode and baselines

The same graph runs in backtest mode. Only three things are swapped:

| | Live | Backtest |
|---|---|---|
| Clock | Last completed session | A fixed past date |
| Broker | Alpaca paper | Simulated broker |
| Approver | You | A fixed rule: follow every buy as sized |

- **Window:** starts on 2024-07-01 or later, after the models' June 2024
  training cutoff, so the model can't remember the future. The runner refuses an
  earlier start.
- **Simulated broker:** enters at the **next session's open** plus 0.05%
  slippage. Each day it checks the day's low and high against the stop and
  target. If both are reached the same day, **the stop is assumed first**. A gap
  past an exit level exits at the open. Trades still open at the end are valued
  at the last close and reported separately.
- **Resumable:** progress is saved after every simulated week. When the free
  daily quota runs out, the run pauses and resumes the next day.
- **Fair stock selection:** by a rule that uses only information from the start
  date (ADR-0006), never by picking past winners.
- **Baselines** use the same stocks, dates, sizing, exits and slippage, so only
  the buy decision differs:
  1. always buy,
  2. a moving-average rule (buy only when the price is above its 50-day average),
  3. a single agent (one LLM call with all the analysts' data),
  4. Bull Pit itself,
  plus buy and hold as a market reference. A short graph is used for these:
  `request_check → indicators → decide → risk_sizing → accept`.
- **Metrics:** total return, Sharpe, maximum drawdown, win rate, profit factor,
  "no trade" value, Brier score (how honest the confidence numbers are), and
  tokens per request.

**Look-ahead protection** covers two kinds of leak: *leaky data* (the date guard,
SEC filing dates, next-open entries) and *leaky memory* (an LLM recalling the
future, handled by the post-cutoff window). Live requests are free of both.

## 10. Where AI judgment ends and code starts

| The AI decides | Code decides |
|---|---|
| Each analyst's direction and confidence | All indicators, ratios, evidence facts and scores |
| Headline sentiment scores | The sentiment average |
| The bull and bear arguments and convictions | Whether a claim cites valid evidence, word counts |
| Buy or no trade, the target weight, the exit style | The exits, the share count, the hard rules, the routing |
| Approve, shrink or veto in the risk review | That the review can only shrink |
| The wording of six report fields | Every number in the report, and the check that rejects invented ones |

Safety guarantees:

1. Numbers are produced by code. An LLM's output is used as a number only after
   code has validated and bounded it.
2. Paper only, with a guard that can't be switched off.
3. No order without a recorded owner approval.
4. The date guard blocks look-ahead.
5. One order per request, however many retries.

## 11. Questions and answers

### Q1. "Second request for the same ticker refused": for how long?

The lock is about **requests**, not holdings. A request for the same ticker in
the same mode is refused:

- **While it is being processed.** The lock is released when the graph finishes.
- **While its report is waiting for your decision.** If you generate a MSFT
  report and leave it, you can't start another MSFT request until you decide or
  it expires.

The lock does not last forever:

- A request stuck in "running" for more than **30 minutes**
  (`request_lock_timeout_minutes`) is marked failed ("abandoned") and stops
  blocking.
- An unanswered report expires at the close of the first trading session after
  the report.
- Once you approve or reject, the lock is released, even if the order hasn't
  filled. A new request is then allowed, and its sizing counts the unfilled
  order against your cash and the 10% cap.

A refused request is still saved in the journal as "rejected" with the reason.

### Q2. "At least 60 days of trading data": does that mean newer stocks?

Yes, but only **very new** ones. It means 60 **trading sessions** (about 3
months), not calendar days. A company that listed less than about 3 months ago is
refused with "has only N trading days of prices". The system fetches about 300
sessions and needs at least 60, because SMA 50, ATR 14 and the returns need that
history. A separate check needs SEC filings, so ETFs and unknown tickers are
refused too.

### Q3. "No other request for the stock is running": does that mean we can't buy or sell a holding stock?

No. **You can request a stock you already hold.** The request check reads your
position in it. If the position is already **10% or more of equity**, Stage A
blocks the buy ("Per-stock cap reached"). Below that, the 10% cap counts what
you hold, so the new size is smaller.

Bull Pit **never sells anything you hold**. It is long-only and buy-only. A
position only closes through its own stop-loss or take-profit, or when you close
it yourself in Alpaca.

### Q4. What is in the `prices` that the request check outputs?

A `PriceSnapshot`:

- `source`: yfinance, or alpaca if yfinance had no data,
- `bars`: daily open, high, low, close and volume, oldest first, about 300
  sessions, point-in-time,
- `splits`: the split dates and ratios,
- `reference_price`: the latest close.

The request check also outputs `company_name`, `account` (cash, equity) and
`position`.

### Q5. What is the latest date of price data we get?

The live clock sets `as_of` to the **last NYSE session whose close has already
happened**. The data is **daily bars through that close**. There is no intraday
price and no partial bar for today, even while the market is open.

The only real-time price is the latest trade from Alpaca, fetched once when you
click Approve, for the 2% staleness check. It never reaches the agents.

### Q6. Does each agent pass its results, summary or final decision to the LLM?

The agents mostly **are** LLM calls, and each one receives a compact digest, not
the full data:

| Agent | What it receives |
|---|---|
| Analysts | Only code-written evidence facts |
| Bull and bear | Each analyst's direction, confidence and flagged status, the board score, the conflict flag, every evidence fact (ID and text), and the debate so far |
| Trader | All of that, plus the final convictions, your cash, equity and holding, the exit-style descriptions, and any earlier vetoes |
| Report writer | The report text and the debate transcript |

An analyst's LLM returns **only two values**: direction and confidence. It writes
no reasoning and no summary. Downstream agents see those two values plus the
code-written facts.

### Q7. Should the LLM give a short, clear report for each analyst?

It doesn't today. The report shows a signals table with each analyst's
direction, confidence and evidence facts, and the facts are the "what was found".
The report writer's LLM writes a summary of the **recommendation** and the debate
points, but nothing per analyst.

This is a candidate change (see [section 13](#13-candidate-changes)):

- **Option A:** the analyst's LLM also returns a one- or two-sentence finding.
- **Option B:** the report writer writes one sentence per analyst.

Things to weigh: it adds LLM text that the number check must cover; the free tier
has an 8K-token ceiling per call; and it changes behaviour, so it needs a new
deviation in `dev-plan.md` §3 and an `architecture.md` revision before any code.

### Q8. What does "analyst failed" mean, and when does it show neutral?

An analyst is replaced by a **neutral signal with confidence 0 and
`flagged = true`** in these cases:

- **Any error inside the analyst**, such as a data fetch failing, SEC or news
  being unreachable, or unexpected data. The note says "analyst failed: …".
- **The LLM reply is invalid after one retry** (note: "LLM reply invalid after
  retry").
- **Fundamentals only:** revenue or net income isn't available for the latest
  quarter.

Two errors are **not** turned into neutral: a quota failure
(`QuotaExhausted`) and a date-guard violation (`LookaheadViolation`). They fail
the request loudly, because a silently degraded signal would corrupt a backtest.

There are three kinds of "neutral", which are easy to confuse:

| Kind | Direction | Confidence | Flagged? |
|---|---|---|---|
| A real neutral judgment | neutral | above 0 | no |
| No news in the last 7 days | neutral | 0 | no (warning "no news in the lookback window") |
| A failed analyst | neutral | 0 | **yes**, with a note |

A failed analyst adds zero to the board score. Two failures can therefore push
the score under 0.15 and send the request to "no trade". The report shows "X
analyst flagged: …" as a warning.

### Q9. Is 150 words too low for the debate? Who writes a summary?

The limit is per turn, set by `debate_turn_max_words`. The count covers claims
and concessions, not evidence IDs. It is a **soft limit**: code flags
`over_word_limit` and adds a warning, and never truncates.

It is low for a reason. Each debate call carries the signals, the facts and the
growing transcript, and the free tier caps a call at about 8K tokens including
hidden reasoning. The four debate calls measured about 7K tokens in total.
Raising the limit is a config change, and the architecture calls these "starting
values you can tune". It should be tested against the real token cost first.

**Who writes a summary?** Neither side. Bull and bear use the same format, and
each turn returns `points` (claim plus evidence IDs), `concessions` and
`conviction` (0 to 1). The debate summary in the report (strongest bull point,
strongest bear point, what the bull conceded, what is unresolved) is written
afterwards by the **report-writer LLM**.

One gap: the report has a field for what the **bull** conceded, but none for the
bear's concessions. The bear's are stored in the journal but not shown in the
report.

### Q10. What do "direction, confidence 0–1, evidence facts" mean?

- **Direction:** bullish, bearish or neutral. The LLM's judgment.
- **Confidence:** a number from 0 to 1 that the LLM picks for how strongly it
  believes its direction. It is **not** a calibrated probability. The
  evaluation's Brier score is what tests whether confidence is honest.
- **Evidence facts:** sentences written by **code**, each with an ID the debate
  can cite. The technical analyst's six facts (T1 to T6) are in
  [section 6.3](#63-technical-analyst-both).

So the LLM never does arithmetic. It reads these lines and answers, for example,
"bullish, 0.6".

### Q11. How does the trader decide the percentage of equity and the exit style?

**It is pure LLM judgment.** The prompt (`bullpit/llm/prompts/trader.md`) gives
the trader the board score, the signals, the facts, the debate, both
convictions, your cash, equity and holding, the **10% maximum**, and one line per
exit style (tight: stop 1.5 ATR below and target 2.25 above; normal: 2 and 3;
wide: 3 and 4.5).

**There is no rule in the prompt** linking conviction to weight, or volatility to
style. Code only clamps the weight to 0 to 10%.

The trader's weight is **only one of four limits**. The final share count is the
smallest of the trader's target, the 1% risk limit, the 10% cap, and cash. A
rough illustration, with "normal" at a 2 ATR stop:

- If ATR is about 2% of the price, the 1% risk limit alone would allow about
  25% of equity, so the **10% cap** binds first.
- If ATR is about 6% of the price, the risk limit allows about 8%, so the
  **risk limit** binds.

For most ordinary stocks, then, the trader's weight (up to 10%) is the real
size. The exit style is the **least-guided decision in the system**. It changes
how wide the stop is, and so the dollar risk, but nothing in the prompt says when
to use which style.

## 12. Review findings

*Status on 2026-10-12: findings 1 and 2 are closed (M8 was accepted and real orders were placed and approved; M0 was accepted and tagged). Finding 5 is closed by M11.1 (the report carries the debate turns). Findings 3, 4 and 7 stand as written; finding 6 is history.*

1. **M8 is not pushed.** 15 local commits, and the CI web job has never run. A
   disk problem would lose it, and CI could still find something. Pushing is
   cheap.
2. **M8's real proof is missing.** No real order has been placed with a person
   approving it. That needs an open market. The US session opens at 18:30 PKT
   from 2026-09-30 until 2026-11-01, then at 19:30 PKT. It would also let the
   leftover M0 position be closed.
3. **The pilot proves little.** 2 stocks, 2 weeks, one seed, a free model. The
   9× token cost of the debate against the single agent is the real open
   question.
4. **The full evaluation can't be run free.** About 300 or more requests plus
   repeat seeds exceeds the free tiers.
5. **The dashboard can't show the debate turn by turn.** An owner decision is
   open.
6. **The process was bent once.** M1 to M7 were tagged on top of an unclosed M0,
   against the rule that a milestone is accepted before the next depends on it.
7. **The "LLMs never produce numbers" rule is slightly softer than it sounds.**
   The board score is built from LLM-produced confidence values that code only
   bounds (0 to 1). The "no trade" shortcut (`|score|` below 0.15) therefore
   rests on LLM output. That is a fair design choice, but it is worth knowing.

## 13. Candidate changes

*Status on 2026-10-12: candidates 1, 3 and 6 were built in M11.1 (analyst paragraphs, the debate narrative, the debate turns in the report). The others were not built.*

These are ideas only. Nothing here is decided or built. Under the project's own
rules, each one changes system behaviour, so each needs a new deviation in
[`dev-plan.md` §3](dev-plan.md) and an `architecture.md` revision entry, and
probably belongs after M8 acceptance (M9 or later).

| # | Change | Why | Notes |
|---|---|---|---|
| 1 | A short finding per analyst in the report | Q7: you want a clear "what each analyst found" | Option A (analyst LLM writes it) or Option B (report writer writes it). The number check must cover it |
| 2 | Raise the debate word limit | Q9: 150 words may be too tight | A setting change; check the token cost and the 8K per-call ceiling first |
| 3 | Show the bear's concessions in the report | Q9: only the bull's are shown | A small report-model addition |
| 4 | Guidance for the trader's size and exit style | Q11: the exit style is the least-guided decision | For example, tie the style to ATR as a percentage of the price |
| 5 | Clearer dashboard display of failed and no-news analysts | Q8: today it is only a warning line | UI change |
| 6 | Serve the per-turn debate transcript through the API | The dashboard has only the summary | Open owner decision from M8 |
| 7 | Reduce Bull Pit's token cost | Pilot: about 9× the single agent | For example, skip weak debates more aggressively |
| 8 | Order of remaining work | Risk and closure | Push, run the market session, accept M8, then M9 |
