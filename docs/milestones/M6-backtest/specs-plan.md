# M6 — Simulated broker, journal, backtest runner: specs and plan

| | |
|---|---|
| **Status** | Approved by the owner on 2026-09-29 ("make sure everything is good to go and then create tasks.md"), after a revision for "complete it today" (D-M6-22) and a check against the code (§7.1). [`task.md`](task.md) is written. Implementation waits for the owner's green light |
| **Date** | 2026-09-29 |
| **Size** | L. Written as one `specs-plan.md` on the owner's instruction, as M3 and M4 were (D-M6-1); [dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents) would otherwise ask for separate `specs.md` and `plan.md` |
| **Branch** | `m6-backtest`, from `master` (M5 is merged and tagged `m5`, merge `37db70b`) |
| **ADRs** | [ADR-0005: sim fill rules](../../adr/0005-sim-fill-rules.md), [ADR-0006: backtest stock selection](../../adr/0006-backtest-stock-selection.md) (M6-AC-10) |
| **Depends on** | M5 (report generator): accepted, tagged `m5`. M6 also calls M1–M4 code directly (calendar, prices, gateway, graph, sizing, loss warning). M0's close-out (M0-T-18, M0-T-25) is still open and blocked on market hours; M6 doesn't touch it |
| **Sources** | [dev-plan §5 M6](../../dev-plan.md#m6--simulated-broker-journal-backtest-runner), [§2.2](../../dev-plan.md#22-code-conventions), [§3](../../dev-plan.md#3-deviations-from-the-architecture-roadmap) (D2, D9), [§6.2](../../dev-plan.md#62-reproducibility), [§7](../../dev-plan.md#7-testing-strategy), [§8](../../dev-plan.md#8-data-model-evolution), [§9](../../dev-plan.md#9-plan-level-risks), [§10](../../dev-plan.md#10-decisions-log) (Q10, Q10a, Q11), [§10.1](../../dev-plan.md#101-scope-review-revision-4) (C1, C4, C5, C15, C16); [architecture Part 13](../../architecture.md#part-13--approval-gate-code), [Part 14 (sim)](../../architecture.md#simulated-broker-backtest), [Part 15](../../architecture.md#part-15--trade-journal-code), [§10](../../architecture.md#10-backtest-mode), [§11](../../architecture.md#11-look-ahead-protection), [§14](../../architecture.md#14-free-tier-budget); [ADR-0002](../../adr/0002-bracket-order-tif-and-legs.md), [ADR-0003](../../adr/0003-point-in-time-prices.md) (split consequence for M6); M2 D-M2-3, M2-FR-11a; M3 D-M3-6, D-M3-9, D-M3-12; M4 D-M4-9, D-M4-12 and [retrospective](../M4-debate-trader-risk/task.md#retrospective); M5 §7.1 and [retrospective](../M5-report/task.md#retrospective) |

Part A says **what** M6 delivers and how it's accepted. Part B says **how** it gets built. Neither restates the architecture or the dev plan; they link to them.

---

## Contents

**Part A: Specs**: [1 Goal](#1-goal) · [2 Scope](#2-scope) · [3 Functional requirements](#3-functional-requirements) · [4 Non-functional requirements](#4-non-functional-requirements) · [5 Interfaces](#5-interfaces) · [6 Acceptance criteria](#6-acceptance-criteria) · [7 Decisions](#7-decisions-made-in-this-document) · [8 Open questions](#8-open-questions-for-the-owner)

**Part B: Plan**: [9 Module design](#9-module-design) · [10 Data model](#10-data-model) · [11 Key algorithms](#11-key-algorithms) · [12 Error handling](#12-error-handling) · [13 Tests and checks](#13-test-and-verification-plan) · [14 Work order](#14-work-order) · [15 Risks](#15-risks)

---

# Part A: Specs

## 1. Goal

Replay the past faithfully and survive the free tier. A backtest runs the **same graph** as live mode, once per chosen stock on the last trading day of every week in a window after the models' training cutoff. It follows every buy as sized through a simulated broker with bracket exits, records everything in the journal, and pauses and resumes cleanly when the daily token quota runs out. The architecture's done-when: *"A resumable 26-week backtest completes on the pinned models."*

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | `broker/sim.py`: the simulated broker. One shared account, cash reserved at submission, entry at the next session's open plus slippage, bracket exits from daily bars, window-end marking | Part 14 (sim); dev-plan M6 |
| S2 | Broker protocol grows the order side (`submit_bracket_order`, `get_order`) as a separate `OrderBroker` protocol; the Alpaca write side stays in M8 | Part 14; D4 |
| S3 | `approval/gate.py`: the backtest policy (approve every buy as sized) | Part 13 |
| S4 | `runners/backtest.py`: weekly loop, deterministic order, week-atomic checkpoint, pause on quota, `--resume`, training-cutoff check, pinned-model guard | §10; C4, C15 |
| S5 | Journal: `backtest_runs`, `approvals`, `trades`, `equity_snapshots` tables; `requests.run_id` (migration `0005`) | Part 15; dev-plan §8 |
| S6 | The loss warning reads the run's `equity_snapshots` and appears in the report | C16; D-M4-9 |
| S7 | `bullpit backtest` CLI command (start and `--resume`) | dev-plan §2.1 |
| S8 | Calendar helpers: sessions in a range, last session of each week (M1's planned `next_open` isn't needed: the sim fills a pending order on the next session the runner hands it) | D2; M1 specs §2.2 |
| S9 | ADR-0005 (sim fill rules, including the gap-past-target reading) and ADR-0006 (backtest stock selection, C5) | dev-plan M6 |
| S10 | One real 2-week, 1-stock run on the pinned models, with a real quota pause and resume (M6-AC-6; D-M6-22) | §10 |

### 2.2 Out of scope

- Evaluation metrics, baselines, the debate-impact counterfactual, the "no trade" value, repeat seeds, charts (M7). M6 only produces the journal they read.
- Live order placement, the approval interrupt, staleness, expiry, fill check, live equity snapshots (M8).
- A LangGraph checkpointer (C4: not needed in backtests).
- Stock-selection code (C5: the rule and its result go in ADR-0006).
- Simulating stock splits during an open trade (D-M6-11: the run stops instead).
- The full 26-week, 3-stock run (moved to M7 as its headline run, D-M6-22).
- Changing single `bullpit request --mode backtest` runs: they still read the Alpaca paper account and place no order (D-M6-19).

## 3. Functional requirements

**Simulated broker (architecture Part 14, sim)**

- **M6-FR-1 Account.** One simulated account per run, starting with `backtest_starting_cash` ($100,000, Q10). `get_account()` returns `cash` = cash minus the reservations of pending orders, and `equity` = all cash (reserved included) plus every open position at its latest close. `get_position(symbol)` returns the open shares and their value at the latest close, or `None`. `get_asset(symbol)` returns the asset the runner looked up when the run was created (D-M6-14).
- **M6-FR-2 Submission.** `submit_bracket_order(order, client_order_id, submitted_on)` records a **pending** trade and reserves `shares × reference_price` of cash. A reused `client_order_id` raises `BrokerRejected` (the same rule as Alpaca, ADR-0002).
- **M6-FR-3 Sessions.** For each session the runner hands the broker that day's bar for every ticker with a pending or open trade. In this order (D-M6-8):
  1. **Entries.** Each pending order fills at `open × (1 + sim_slippage_pct)`, rounded to the cent. If its cost is more than the cash left after the other pending reservations, the order is **downsized** to the whole shares that cash buys; 0 shares cancels it (`not enough cash at the open`). Cash never goes negative.
  2. **Exits**, for every open trade, **including one that entered today** (D-M6-3, Q1):
     - open ≤ stop: exit at the open (gap past the stop, worse);
     - open ≥ take-profit: exit at the open (gap past the target, ADR-0005);
     - otherwise low ≤ stop: exit at the stop; otherwise high ≥ take-profit: exit at the take-profit. **Both on the same day: the stop wins.**
  3. **Equity snapshot** at that session's close.

  Exits fill at their exact price, with no slippage (the architecture gives slippage for the entry only, D-M6-9).
- **M6-FR-4 Window end.** After the last decision day's requests, pending orders are cancelled (`window ended before entry`) and open trades are marked at the last session's close with status `open_at_end` and exit reason `window_end`, **reported separately** from closed trades.
- **M6-FR-5 Data the broker can't use.** A missing bar, or a split ex-date, for a ticker with a pending or open trade stops the run with `DataUnavailable` naming the ticker and day (D-M6-11, D-M6-12).

**Approval (architecture Part 13)**

- **M6-FR-6** In backtest mode every `buy` is approved as sized: one `approvals` row (`decided_by = backtest_policy`, recommended and approved shares equal, decided at the simulated `as_of` close), then the order is submitted with `client_order_id` derived from `request_id`.

**Backtest runner (architecture §10)**

- **M6-FR-7 Start.** `bullpit backtest --tickers AAPL,JPM,LLY --start 2024-07-01 [--weeks 26] [--seed 1] [--cash 100000]`. Defaults come from settings (`backtest_weeks` 26, `llm_seed`, `backtest_starting_cash`). Before anything is written:
  - **Training cutoff:** `start` must be after the latest of `llm_small_model_cutoff` and `llm_large_model_cutoff` (M3 settings), or the run is refused with the earliest allowed date (M6-AC-5).
  - **Assets:** each ticker is looked up once through the Alpaca read-only broker; an unknown or untradable ticker refuses the run.
  - A `backtest_runs` row records the run's inputs, the model IDs, the looked-up assets and the git commit.
- **M6-FR-8 Decision days.** The last NYSE session of each calendar week, for `weeks` weeks starting with the week that contains `start` (only days on or after `start`). Good Friday or another Friday holiday moves the decision day to Thursday.
- **M6-FR-9 One week.** For each decision day D, in **one** journal transaction:
  1. Run every session after the last processed one, through D, through the broker (FR-3), writing trade changes and one `equity_snapshots` row per session.
  2. For each ticker in **alphabetical order**: set `as_of = D`, compute the loss warning (FR-12), run the graph with the sim broker, write the request's rows (the same rows as a single request, plus `run_id`), and, if the outcome is `buy`, approve and submit (FR-6).
  3. On the last decision day, close the window (FR-4).
  4. Record D as the run's checkpoint and commit.
- **M6-FR-10 Deterministic.** Request IDs are `{as_of:%Y%m%d}-{ticker}-{run_id}`, so a re-run week recreates the same IDs; the seed goes into every LLM call; tickers run in a fixed order. With the response cache, a re-run of a week makes the same LLM calls and gets the same replies at no token cost.
- **M6-FR-11 Stop and resume.** Any exception inside a week rolls the week back, so no partial rows remain (spent `llm_calls` rows stay, by design, M2-FR-11a):
  - `QuotaExhausted` or `LLMUnavailable`: the run is marked `paused`, and the CLI prints `Paused: <reason>. Resume with: bullpit backtest --resume <run_id>` and exits 3.
  - Anything else: the run is marked `stopped` with the error, and the CLI exits 1.
  - A killed process leaves the run `running` at its last checkpoint.

  `bullpit backtest --resume RUN_ID` accepts a `running`, `paused` or `stopped` run and continues from the week after its checkpoint, with the run's own inputs (tickers, window, seed, cash, assets). It rebuilds the simulated account from the run's `trades` rows (§11.4).
- **M6-FR-12 Loss warning (C16).** Before each request the runner calls `risk.rules.loss_warning` on the run's `equity_snapshots` up to `as_of`, and puts the result into `RequestState.loss_warning`. The report shows it in section 6 in place of M5's "not available". Early in a run, when the history doesn't reach back `loss_warning_days`, it stays `None`. Live requests keep `None` until M8.
- **M6-FR-13 Pinned-model guard (C15).** `--resume` refuses to continue if the configured small or large model differs from the run's recorded models, naming both. Other settings are not compared (D-M6-15).
- **M6-FR-14 Progress and result.** The CLI prints one line per finished week (each ticker's outcome, buys with shares, equity at D) and, at the end, the end equity, closed trades (count, wins, P&L), `open_at_end` trades listed separately, and cancelled orders. Evaluation metrics are M7's.

**Journal (architecture Part 15, dev-plan §8)**

- **M6-FR-15 Migration `0005`.** New tables `backtest_runs`, `approvals`, `trades`, `equity_snapshots`, and a nullable `requests.run_id` ([§10](#10-data-model)). Every new row carries `request_id` and/or `run_id` (request lineage, dev-plan M6).

**Settings**

- **M6-FR-16** New settings in `config.py` and `.env.example`: `sim_slippage_pct` = 0.0005, `backtest_starting_cash` = 100000, `backtest_weeks` = 26.

**Stock selection (C5)**

- **M6-FR-17** Before the AC-6 run, the stocks are chosen with the rule in ADR-0006, using only information from before the start date (Q2), with tickers priced above the per-stock cap excluded (Q10a). The ADR records the rule, the data it used and the chosen tickers. No selection code. M7's 26-week run uses the same stocks.

## 4. Non-functional requirements

- **M6-NFR-1 (tests)** Dev-plan §7 exactly. The sim fill rules get one small hand-built bar fixture each (§7.1); the refusals and the resume that can silently corrupt results get one test each; the runner gets one end-to-end happy path (§7.2). No network (`pytest-socket`); the suite stays under about a minute.
- **M6-NFR-2 (pure core)** `broker/sim.py` does no I/O and reads no settings: it gets its bars, slippage and starting cash from the runner. `approval/gate.py` is pure. Only `runners/backtest.py` calls the data layer and the journal.
- **M6-NFR-3 (money)** Every price, cost, cash and P&L in the broker, runner and journal is a `Decimal`, rounded to the cent at the broker boundary; bars convert from float with `Decimal(str(x))`, as in M4. Share counts are integers.
- **M6-NFR-4 (time)** No wall-clock read in the sim or the decision logic. Simulated times (`decided_at`, trade dates) are session dates or `session_close(as_of)`. Wall-clock fields exist only as record-keeping (`created_at`, `finished_at`, `Report.generated_at`).
- **M6-NFR-5 (no leak)** The graph sees nothing new: it runs at `as_of = D` through the same data layer and date guard. The broker reads day s's bar only when simulating day s, through `get_prices(ticker, s, 1)`, so the date guard applies to it too.
- **M6-NFR-6 (quota)** A backtest makes the same LLM calls as single requests, and nothing else. A resumed week costs 0 tokens for calls it already made.
- **M6-NFR-7 (memory)** A 26-week, 3-stock run fits the 8 GB laptop: one graph build per run, bars read one session at a time.

## 5. Interfaces

```python
# bullpit/domain.py (+): Bar moves here from state.py (a non-LLM domain type; state imports it)
TradeStatus = Literal["pending", "open", "closed", "cancelled", "open_at_end"]
ExitReason = Literal["stop", "target", "window_end"]      # M8 adds "manual"

class Trade(BaseModel, frozen=True):
    client_order_id: str
    ticker: str
    submitted_on: date
    shares: int                          # after any downsizing at the open
    reference_price: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    status: TradeStatus
    entry_date: date | None = None
    entry_price: Decimal | None = None   # open x (1 + slippage), to the cent
    exit_date: date | None = None
    exit_price: Decimal | None = None    # the last close for open_at_end
    exit_reason: ExitReason | None = None
    cancel_reason: str | None = None

# bullpit/broker/base.py (+)
class OrderBroker(Broker, Protocol):
    def submit_bracket_order(self, order: SizedOrder, *, client_order_id: str,
                             submitted_on: date) -> Trade: ...
    def get_order(self, client_order_id: str) -> Trade: ...

def client_order_id(request_id: str) -> str: ...          # deterministic; M8 reuses it

# bullpit/broker/sim.py (pure)
class SimBroker:                                           # implements OrderBroker
    def __init__(self, *, starting_cash: Decimal, slippage_pct: Decimal,
                 assets: Mapping[str, Asset], trades: Sequence[Trade] = ()) -> None: ...
    def tickers_needing_bars(self) -> list[str]: ...       # pending or open
    def on_session(self, day: date, bars: Mapping[str, Bar],
                   splits: Mapping[str, float]) -> list[Trade]: ...   # changed trades
    def valuation(self) -> tuple[Decimal, Decimal]: ...    # (cash incl. reservations, positions at last close)
    def end_window(self, day: date) -> list[Trade]: ...
    # + get_account, get_position, get_asset, submit_bracket_order, get_order

# bullpit/approval/gate.py (pure)
class ApprovalDecision(BaseModel, frozen=True):
    decision: Literal["approved", "rejected"]
    recommended_shares: int
    approved_shares: int
    decided_by: Literal["backtest_policy"]                # M8 adds "owner"

def backtest_policy(order: SizedOrder) -> ApprovalDecision: ...

# bullpit/state.py (+)
class RequestState(BaseModel):     # existing fields, plus:
    loss_warning: bool | None = None                       # set by the backtest runner (FR-12)

# bullpit/data/calendar.py (+)
def sessions_between(after: date, through: date) -> list[date]: ...   # sessions in (after, through]
def decision_days(start: date, weeks: int) -> list[date]: ...   # last session of each week

# bullpit/runners/request.py: _finalize's row-writing is split out, unchanged in behaviour
def add_request_rows(session: Session, row: Request, *, result: RequestState | None,
                     error: BaseException | None, settings: Settings) -> None: ...  # no commit

# bullpit/runners/backtest.py
def start_backtest(tickers: Sequence[str], start: date, *, weeks: int, seed: int,
                   starting_cash: Decimal, settings: Settings, sessions: sessionmaker[Session],
                   asset_lookup: Broker) -> str: ...        # returns run_id; FR-7 refusals raise ConfigError
def run_backtest(run_id: str, *, settings: Settings, sessions: sessionmaker[Session],
                 completion_fn: CompletionFn = litellm_completion,
                 on_week: Callable[[WeekSummary], None] = ...) -> RunResult: ...
                                                            # also the resume path; FR-13 guard first
```

`WeekSummary` and `RunResult` are small frozen models for the CLI's output (FR-14). `report/builder.py` reads `state.loss_warning` instead of the constant `None`.

## 6. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| **M6-AC-1** | Each sim fill rule, on a small hand-built bar fixture: normal stop; normal target; both on the same day (stop wins); gap down past the stop (fills at the open); gap up past the target (fills at the open); a stop hit on the entry day itself (Q1); still open at window end (marked at the last close, `open_at_end`); a pending order at window end (cancelled) | **Automated** |
| **M6-AC-2** | Entry = the next session's open × 1.0005, to the cent, and skips holidays (an order submitted 2024-07-03 fills on 2024-07-05). Decision days: the last session of each week, Thursday in a Good Friday week (2025-04-17) | **Automated** |
| **M6-AC-3** | Two buys on the same decision day whose total cost is more than the cash: the second request sees the reduced cash and is downsized by Stage A, or ends "no trade". A gap up at the open that would overdraw cash downsizes the fill. Cash is never negative | **Automated** |
| **M6-AC-4** | A backtest stopped partway through a week, once by `QuotaExhausted` and once by an unexpected exception, then resumed, produces **exactly the same journal** as an uninterrupted run with the same seed. Compared: every table except `llm_calls`, without row IDs, wall-clock fields (`created_at`, `finished_at`, `Report.generated_at`) or the run ID (M5 carry-over, D-M6-17). The stopped week leaves no rows behind | **Automated** |
| **M6-AC-5** | A run starting on or before a pinned model's training cutoff (2024-06-28 with the default 2024-06-30 cutoffs) is refused, naming 2024-07-01 as the earliest start, and writes nothing | **Automated** |
| **M6-AC-6** | A **2-week, 1-stock** run on the pinned models, starting 2024-07-01 with the first ADR-0006 stock (the largest company in the largest sector), seed 1, completes the same day (D-M6-22). It is **paused once for real**: started with `LLM_DAILY_TOKEN_BUDGET` lowered so the gateway raises `QuotaExhausted` partway through week 1, then resumed with the default budget; the resumed week's earlier calls are cache hits. Every table is filled in (`trades` and `approvals` only if a buy happened; see §15); tokens used are recorded | Manual: CLI output and journal queries pasted in `task.md` |
| **M6-AC-7** | Resuming a run after `LLM_LARGE_MODEL` (or the small one) changed is refused with both model IDs named, and nothing is written | **Automated** |
| **M6-AC-8** | The end-to-end runner happy path, on recorded fixtures with the scripted fake LLM (3 weeks, 2 tickers, one scripted buy): every week has its requests, reports, snapshots and checkpoint; the buy has an `approvals` row and a `trades` row with its entry; the report's loss warning is `False` (not "not available") once the history reaches back 7 days | **Automated** |
| **M6-AC-9** | `alembic upgrade head` on an empty DB matches `models.py` (the existing migration test, now covering `0005`) | **Automated** |
| **M6-AC-10** | ADR-0005 (fill rules) and ADR-0006 (stock rule, data used, chosen tickers, no split in the window for any of them) are written and linked from this file | Manual: owner reads them |

AC-1 to AC-7 are the dev-plan's drafts, made concrete; AC-8 is §7.2's happy path plus the loss-warning wiring; AC-9 and AC-10 cover the journal and the ADRs.

## 7. Decisions made in this document

None of these changes the system's behaviour, except **D-M6-3** (Q1, decided yes): it becomes deviation D12 in dev-plan §3 and architecture revision v2.4 (Part 14's "each later day" becomes "the entry day and each later day"). **D-M6-22** changes M6's acceptance, not behaviour: it is recorded in dev-plan §10 and the architecture's roadmap row for M6.

| # | Decision | Reason |
|---|---|---|
| D-M6-1 | **One `specs-plan.md`** for this L milestone | The owner asked for it, as for M3 and M4. The content is the same as `specs.md` + `plan.md` |
| D-M6-2 | **The broker protocol splits in two:** `Broker` (read, as today) and `OrderBroker(Broker)` adding `submit_bracket_order` and `get_order`. `AlpacaBroker` stays read-only until M8. `client_order_id(request_id)` lives in `broker/base.py` | The architecture's single interface (Part 14) is kept for the order side. `AlpacaBroker` can't claim methods it won't have until M8 (no stubs, CLAUDE.md), and the graph only needs the read side |
| D-M6-3 | **Exits are checked on the entry day too**, using that day's low and high with the stop first (**Q1**, dev-plan "decision to be approved") | A daily bar's low and high are the regular session's, which starts at the open, so the entry day's whole range happens while the bracket is live. Skipping it would miss stops hit on day one: an optimistic bias. Checking it is the cautious choice the architecture asks for elsewhere |
| D-M6-4 | **The backtest approval runs in the runner, after the graph**, through `approval/gate.py`'s `backtest_policy`; no approval or execution node in the graph yet | Live mode can't execute until M8, so a graph node now would need a live branch that does nothing. M8 adds the `interrupt()` node and reuses `approval/gate.py`. The architecture's "fixed rule: every buy approved as sized" is unchanged |
| D-M6-5 | **Backtest requests don't use `run_request`'s lock and commits.** Their rows go into the week's transaction with the checkpoint; the run is the lock (one process per run). `_finalize`'s row-writing becomes `add_request_rows`, shared by both runners | C4's rule ("a week's journal rows are committed together with its checkpoint") can't hold if each request commits on its own. The per-ticker lock guards concurrent live requests, which a sequential run can't have. One row-writer keeps one definition of each row |
| D-M6-6 | **Request IDs are deterministic in backtests** (`{as_of}-{ticker}-{run_id}`) and `client_order_id` derives from them | A re-run week must recreate the same rows (AC-4). CLAUDE.md requires `client_order_id` from `request_id` in every mode |
| D-M6-7 | **Cash is reserved at `shares × reference_price`**; `get_account().cash` excludes reservations; equity includes them. At the fill, an order that would overdraw the cash left is downsized, never enlarged | Stage A already sizes against the cash it's shown, so the next same-day request sees less cash (AC-3). Only a gap up at the open can make the real cost bigger; downsizing there only lowers risk and keeps every M4 limit true |
| D-M6-8 | **Session order: entries at the open, then exits, then the snapshot.** Entries use the cash as it stood before that day's exits | A market entry fills at the open, before any intraday exit could free cash. Deterministic and cautious |
| D-M6-9 | **Exits fill at their exact price, with no slippage; a gap fills at the open; prices round to the cent** | The architecture gives slippage for the entry only and exits "at the stop price". Adding exit slippage would be a behaviour change |
| D-M6-10 | **Window end:** pending orders are cancelled; open trades are `open_at_end`, marked at the last close with exit reason `window_end` | Architecture Part 14: "valued at the last close and reported separately". The last decision day's buys can't enter inside the window; their recommendations stay in the journal for M7 |
| D-M6-11 | **A split on a bar for a ticker with a pending or open trade stops the run** (`DataUnavailable`); it isn't simulated. ADR-0006 confirms the chosen stocks have no split in the window | ADR-0003 asks M6 to say how splits are handled. Simulating one (share count, exit prices, cash in lieu) is money code that the chosen stocks would never exercise. A loud stop can't bias a result; a rarely used adjustment could |
| D-M6-12 | **A missing bar for a ticker with a pending or open trade stops the run** (`DataUnavailable`) | Guessing a fill (skip the day, carry the last close) is a silent bias. Large-cap daily data has no gaps in practice |
| D-M6-13 | **Every exception rolls the week back.** `QuotaExhausted` and `LLMUnavailable` → `paused`; anything else → `stopped`; `--resume` accepts `running`, `paused` and `stopped` | Either kind of stop is resumable at no token cost. A failed request is never recorded mid-run, so a finished run has no holes. `LLMUnavailable` is a provider outage, which waiting fixes, like quota |
| D-M6-14 | **Assets are looked up once when a run is created** (today's Alpaca status) and stored on the run; `SimBroker.get_asset` serves them | No network inside the weekly loop, and a resume sees the same names. Point-in-time asset status isn't available on the free plan; the stocks are chosen to be tradable throughout (ADR-0006) |
| D-M6-15 | **The pinned-model guard compares model IDs only**; the seed, tickers, window and cash come from the run row on resume | C15 names models, which decide the look-ahead window (D9). Every request already records its full config snapshot (§6.2), so any other change is visible afterwards |
| D-M6-16 | **The loss warning goes through `RequestState.loss_warning`**, set by the runner from `equity_snapshots` (the week's own rows are flushed in the open transaction) | C16. The risk function stays pure (M4); the report reads state as it does for everything else. Live stays `None` until M8 feeds live snapshots |
| D-M6-17 | **AC-4 compares journals without `llm_calls`, row IDs, wall-clock fields and the run ID** | `llm_calls` records spending, and a resumed week adds cache-hit rows by design (M2-FR-11a). `Report.generated_at` and `created_at` are wall-clock (M5 carry-over). Two runs compared have different run IDs |
| D-M6-18 | **The AC-6 run uses seed 1, start 2024-07-01 and the ADR-0006 stocks**, the same as M7's headline run | M7 extends it to 26 weeks with `--weeks 26` on a new run; its first two weeks come back from the response cache at no cost. 2024-07-01 is the earliest start the models allow (D9) |
| D-M6-19 | **`bullpit request --mode backtest` is unchanged**: it still reads the Alpaca paper account and places no order | It's the one-off debugging tool (D6). The simulated account only means something inside a run. D-M3-6 and D-M4-12 end for runs, which is where results come from |
| D-M6-20 | **Testing follows dev-plan §7** (M5's D-M5-11 carries on) | Owner instruction for M5 onward; M4's full coverage was M4 only |
| D-M6-21 | **`Bar` moves to `domain.py`; `risk/sizing.py`'s cent rounding and share flooring become public** | The sim needs both. One place for each fact (CLAUDE.md), the same move M5 made with `sma` |
| D-M6-22 | **M6 is completed today (2026-09-29): the real run is 2 weeks × 1 stock (owner: "check it for 1 stock"), and the 26-week, 3-stock run moves to M7** (owner: "I need it completed today") | Groq's free tier gives the large model 200K tokens per rolling 24 hours. On 2026-09-29 at 03:40 UTC, M5's runs had already used 120,191, which only start freeing after about 19 hours, so about 80K is left today. A debated request costs about 11K large-model tokens (M5), so 2 requests (at most ~22K, with room for a veto loop) fit easily; 78 don't (~860K, about 5 days). The runner, its pause and its resume are the same code at any length, so a short real run plus AC-4's automated resume test proves what the 26-week run would. M7 needs that run anyway as its headline run (Q11) |

### 7.1 Corrections found in the final check

Checked line by line against the M1–M5 code before writing `task.md`. None changes scope:

| What | Change |
|---|---|
| The forced pause for AC-6 | The daily budget is a rolling 24-hour sum per model, and the large model already had ~120K on it. A budget lowered only for week 2 would miss the pause if week 2 skipped the debate. The run now **starts** with the lowered budget and pauses in week 1; cache hits are served before the budget check (`gateway.py`), so the resume replays them for free (AC-6, §13) |
| `next_session` | Nothing would call it (the sim fills on the next bar it's handed), so it's dropped; the holiday skip is tested through `sessions_between` (§5, §13) |
| `SimBroker.equity()` | Replaced by `valuation()`, which gives the snapshot's cash and positions value in one call (§5, §11.1) |
| AC-3's same-day test | Needs a starting cash small enough that the cash limit binds; with $100,000 and a 10% cap, two buys never run out of cash (§13) |
| Analyst and report `LLMUnavailable` | Already handled inside the graph (M3-FR-15, D-M5-5), so it doesn't pause a run; only the debate, trader and review steps do (§12) |

## 8. Open questions for the owner

None open. The two questions that change results were decided on the owner's instruction ("do whatever", 2026-09-29); say if you want either changed.

| # | Question | Decision |
|---|---|---|
| **Q1** | Check exits on the **entry day** too (D-M6-3)? The dev plan left this "to be approved" | **Yes**, because the entry day's low and high all happen after the open, so ignoring them is optimistic. Adds deviation D12 and architecture v2.4 (task 1) |
| **Q2** | **Stock-selection rule** for ADR-0006 (C5, architecture §10: "a rule that uses only information from the start date") | The **largest company by market capitalisation in each of the three largest S&P 500 sectors by index weight**, measured at the close of 2024-06-28 (the last session before the start), limited to ordinary US company stock that passes the request check on 2024-07-01 and is priced under $10,000 (Q10a). Next in size is taken if one fails. The ADR records the data sources and the result |

---

# Part B: Plan

## 9. Module design

### 9.1 Files created or changed

```text
.env.example                          + sim_slippage_pct, backtest_starting_cash, backtest_weeks
bullpit/
  config.py                           + the three settings
  domain.py                           + Bar (moved from state.py), Trade, TradeStatus, ExitReason
  state.py                            Bar imported from domain; + RequestState.loss_warning
  data/calendar.py                    + sessions_between, decision_days
  risk/sizing.py                      _round_cent, _floor_shares → public (D-M6-21)
  broker/base.py                      + OrderBroker, client_order_id
  broker/sim.py                       new: SimBroker (pure)
  approval/gate.py                    new: ApprovalDecision, backtest_policy (pure)
  report/builder.py                   loss_warning from state
  runners/request.py                  _finalize's row-writing → add_request_rows (shared)
  runners/backtest.py                 new: start_backtest, run_backtest, journal sync
  journal/models.py                   + BacktestRun, ApprovalRecord, TradeRecord, EquitySnapshot; Request.run_id
  journal/migrations/versions/0005_backtest.py   new
  cli.py                              + backtest command
tests/
  broker/test_sim.py                  new: AC-1, AC-2 (entry), AC-3 (fill-time downsize)
  data/test_calendar.py               + decision days, next session (AC-2)
  runners/__init__.py                 new
  runners/test_backtest.py            new: AC-3 (same-day), AC-4, AC-5, AC-7, AC-8
  test_config.py                      + the three defaults
docs/adr/0005-sim-fill-rules.md       new
docs/adr/0006-backtest-stock-selection.md   new
docs/dev-plan.md                      status line; D12 (§3); D-M6-22 (§10; M6 draft ACs)
docs/architecture.md                  v2.4: Part 14 entry-day exits (D12); §16 M6 done-when (D-M6-22)
README.md                             running a backtest
```

`bullpit/approval/` exists as an empty package from M0. `tests/broker/fake_broker.py` stays for the graph tests. The migration test covers `0005` without changes.

### 9.2 Dependency direction

```text
cli ──► runners/backtest ──► graph (unchanged)            ──► agents, report, data, llm
              │         ├──► broker/sim (pure) ──► domain, risk/sizing (rounding)
              │         ├──► approval/gate (pure) ──► domain
              │         ├──► risk/rules.loss_warning (pure)
              │         ├──► data/prices.get_prices, data/calendar
              │         └──► journal/models, runners/request.add_request_rows
              └──► broker/alpaca (asset lookup at start only)
```

`broker/sim.py` imports only `domain`, `broker/base`, `errors` and `risk/sizing`; `approval/gate.py` only `domain`. The graph and every agent are unchanged: the sim broker is injected through `Deps.broker` exactly where `AlpacaBroker` is today (architecture §4, "one graph, two modes").

### 9.3 The runner

| Step | Code |
|---|---|
| Start | `start_backtest`: cutoff check → asset lookup → insert `backtest_runs` (status `running`, checkpoint `None`) → return `run_id` |
| Load | `run_backtest`: load the run; pinned-model guard (FR-13); `settings.model_copy(update={"llm_seed": run.seed})`; `SimBroker(starting_cash, slippage, assets, trades=<run's trades rows>)`; `build_graph(Deps(broker=sim, …))` once |
| Weeks | For each decision day after the checkpoint: one session, one transaction ([§11.1](#111-weekly-loop)) |
| Stop | `except QuotaExhausted, LLMUnavailable` → rollback, mark `paused`; `except Exception` → rollback, mark `stopped`, re-raise; both in a new short transaction |
| End | After the last week: status `completed`, `finished_at`; return `RunResult` |

`bullpit backtest` wires it: `_upgrade_journal_schema`, `make_alpaca_broker` (asset lookup only), `start_backtest` unless `--resume`, then `run_backtest` with an `on_week` printer. Exit codes: 0 completed, 1 stopped, 2 usage error, 3 paused.

## 10. Data model

Migration `0005_backtest`. Money is stored as `TEXT` (`Decimal` strings), as in `recommendations.target_weight`.

**`backtest_runs`**

| Column | Type | Notes |
|---|---|---|
| `id` | `TEXT PK` | 8 hex characters |
| `created_at`, `finished_at` | `DATETIME` | Wall clock, record only |
| `tickers` | `JSON` | Sorted |
| `start_date`, `end_date` | `DATE` | First session used; last decision day |
| `weeks`, `seed` | `INTEGER` | |
| `starting_cash` | `TEXT` | |
| `models` | `JSON` | `{"small": …, "large": …}` (FR-13) |
| `assets` | `JSON` | The looked-up assets (D-M6-14) |
| `git_commit` | `TEXT` | At creation |
| `status` | `TEXT` | `running`, `paused`, `stopped`, `completed` |
| `status_reason` | `TEXT NULL` | |
| `checkpoint` | `DATE NULL` | Last completed decision day |

**`requests`** gains `run_id TEXT NULL`, FK → `backtest_runs.id`, indexed. `NULL` for single requests.

**`approvals`**

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER PK` | |
| `request_id` | `TEXT` FK → `requests.id`, **unique** | One decision per request |
| `decision` | `TEXT` | `approved` / `rejected` |
| `recommended_shares`, `approved_shares` | `INTEGER` | |
| `decided_by` | `TEXT` | `backtest_policy` (M8: `owner`) |
| `decided_at` | `DATETIME` | Simulated: `session_close(as_of)` |

**`trades`**

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER PK` | |
| `request_id` | `TEXT` FK → `requests.id`, **unique** | |
| `run_id` | `TEXT NULL` FK → `backtest_runs.id`, indexed | `NULL` for live (M8) |
| `client_order_id` | `TEXT` **unique** | |
| `ticker` | `TEXT` | |
| `submitted_on` | `DATE` | |
| `shares` | `INTEGER` | After any downsizing |
| `reference_price`, `stop_loss`, `take_profit` | `TEXT` | |
| `status` | `TEXT` | `TradeStatus` |
| `entry_date`, `entry_price` | `DATE NULL`, `TEXT NULL` | |
| `exit_date`, `exit_price`, `exit_reason` | `DATE NULL`, `TEXT NULL`, `TEXT NULL` | |
| `cancel_reason` | `TEXT NULL` | |
| `pnl` | `TEXT NULL` | `(exit − entry) × shares`, set when closed or marked |

The row mirrors `Trade`; the runner upserts it from `broker.get_order` whenever the broker reports a change. M8 adds the Alpaca order and leg IDs (dev-plan §8).

**`equity_snapshots`**

| Column | Type | Notes |
|---|---|---|
| `id` | `INTEGER PK` | |
| `run_id` | `TEXT NULL` FK → `backtest_runs.id` | `NULL` for live (M8) |
| `date` | `DATE` | Session |
| `cash`, `positions_value`, `equity` | `TEXT` | Cash includes reservations |

Unique on (`run_id`, `date`).

## 11. Key algorithms

### 11.1 Weekly loop

```text
days = decision_days(run.start_date, run.weeks); todo = [d for d in days if d > run.checkpoint]
last = run.checkpoint or run.start_date − 1 day                  # sessions_between takes plain dates
for D in todo:
    with sessions() as s:                                        # one transaction
        for day in sessions_between(last, D):
            bars, splits = {}, {}
            for t in broker.tickers_needing_bars():
                h = get_prices(t, day, 1)                        # date guard at as_of = day
                missing bar → DataUnavailable;  bars[t] = h.bars row; splits[t] from h.splits
            for trade in broker.on_session(day, bars, splits): upsert TradeRecord
            cash, positions = broker.valuation(); add EquitySnapshot(day, cash, positions, cash + positions)
        s.flush()
        history = [(date, equity) of run's EquitySnapshot rows, date ≤ D]
        for ticker in sorted(run.tickers):
            rid = f"{D:%Y%m%d}-{ticker}-{run.id}"
            lw  = loss_warning(history, D, drop_pct=…, days=…)
            state = RequestState(request_id=rid, mode="backtest", as_of=D, ticker=ticker, loss_warning=lw)
            result = RequestState.model_validate(graph.invoke(state))  # exceptions propagate
            add_request_rows(s, Request(id=rid, …, run_id=run.id), result=result, error=None, …)
            if result.outcome == "buy":
                decision = backtest_policy(result.sized_order); add ApprovalRecord
                trade = broker.submit_bracket_order(result.sized_order,
                            client_order_id=client_order_id(rid), submitted_on=D); add TradeRecord
        if D == days[-1]: for trade in broker.end_window(D): upsert TradeRecord
        run.checkpoint = D; s.commit()
    last = D; on_week(summary)
```

A rejected request (for example too little history) is recorded with its report and the loop goes on, as for a single request.

### 11.2 One session in the broker (`SimBroker.on_session`)

```text
for t in pending, in submission order (alphabetical within a day):
    if splits.get(t.ticker, 1.0) != 1.0 → DataUnavailable(split)
    price     = round_cent(open × (1 + slippage))
    available = cash − Σ reservations of the other pending orders
    shares    = min(t.shares, floor_shares(available / price)); release t's reservation
    shares == 0 → cancelled ("not enough cash at the open")
    else        → open, entry_date = day, entry_price = price, cash −= shares × price
for t in open (including those entered above):
    o, h, l = bar;  split on this bar → DataUnavailable
    if   o ≤ stop:  exit at o,    reason stop       # gap past the stop
    elif o ≥ tp:    exit at o,    reason target     # gap past the target (ADR-0005)
    elif l ≤ stop:  exit at stop, reason stop       # checked before the target: stop wins
    elif h ≥ tp:    exit at tp,   reason target
    on exit: cash += shares × exit price; pnl = (exit − entry) × shares; status closed
mark[t] = close for every bar seen
```

`end_window(day)`: pending → `cancelled` ("window ended before entry"), releasing reservations; open → `open_at_end`, `exit_price = mark`, `exit_reason = window_end`, `pnl` marked.

### 11.3 Decision days (`calendar.decision_days`)

```text
weeks from the Monday of start's week; for each week w in 0..weeks-1:
    sessions in [monday_w, monday_w + 6 days] that are ≥ start → the last one, if any
```

2024-07-01 + 26 weeks gives 2024-07-05 … 2024-12-27; in 2025, the week of Good Friday gives 2025-04-17.

### 11.4 Resume

The account is rebuilt from the run's `trades` rows, so the journal is the only record of broker state:

```text
cash     = starting_cash − Σ entry_price × shares (every trade that entered)
                         + Σ exit_price  × shares (closed trades)
pending  = trades with status pending (their reservations follow from shares × reference_price)
open     = trades with status open (marks come from the next session's bars before any snapshot)
```

The week after the checkpoint then runs from its first session. Its earlier LLM calls come back from the response cache, so the replay is free and identical (FR-10).

### 11.5 Journal comparison (AC-4 test helper)

Every table except `llm_calls`, rows sorted by natural key (`requests` by `as_of`, `ticker`; child rows by `request_id` and their own order), with `id`, `created_at`, `finished_at` and `generated_at` removed and the run ID replaced by a placeholder in `run_id` and every request ID. Lives in `tests/runners/test_backtest.py` only.

## 12. Error handling

| Where | Error | Result |
|---|---|---|
| Start | Start on or before the latest cutoff | `ConfigError` with the earliest allowed date; nothing written (AC-5) |
| Start | Unknown or untradable ticker | `ConfigError` naming it; nothing written |
| Resume | Unknown run, or a `completed` one | `ConfigError`; nothing written |
| Resume | Models changed | `ConfigError` naming both sets; nothing written (AC-7) |
| Week | `QuotaExhausted`, `LLMUnavailable` | Week rolled back; run `paused`; CLI resume message, exit 3 |
| Week | Missing bar or a split for a trade's ticker | `DataUnavailable`; week rolled back; run `stopped`, exit 1 |
| Week | `LookaheadViolation`, `BrokerRejected`, any other exception | Week rolled back; run `stopped` with the error; re-raised, exit 1 |
| Week | A request rejected by the request check | Recorded with its report; the week goes on |
| Week | `LLMUnavailable` in an analyst, or in the report step | Unchanged from single requests: a neutral flagged signal (M3-FR-15) or fallback prose (D-M5-5), recorded; only from the debate on does it pause the run |
| Process killed | — | No commit; run stays `running` at its checkpoint; `--resume` continues |

## 13. Test and verification plan

Dev-plan §7, exactly (D-M6-20). No network; the new tests add seconds.

| File | Tests | AC | §7 category |
|---|---|---|---|
| `broker/test_sim.py` | `test_exit_rules` (parametrised, one hand-built bar fixture each: stop, target, both same day, gap down, gap up, entry-day stop); `test_entry_next_open_with_slippage` (submitted 2024-07-03, filled on the 2024-07-05 bar at open × 1.0005 to the cent); `test_fill_downsized_when_cash_short`; `test_window_end` (open → `open_at_end` at the last close, pending → cancelled); `test_split_or_missing_bar_stops` | AC-1, AC-2, AC-3 | 7.1 sim fill rules |
| `data/test_calendar.py` (+) | `test_decision_days` (2024-07-01 × 26 → 2024-07-05 … 2024-12-27; the Good Friday week → 2025-04-17); `test_sessions_between` (2024-07-03 → 2024-07-05 is `[2024-07-05]`: the holiday is skipped, so the entry lands on the right day) | AC-2 | 7.1 (entry and decision dates decide every fill) |
| `runners/test_backtest.py` | `test_happy_path` (AC-8); `test_same_day_buys_share_cash` (starting cash small enough that the cash limit binds; two scripted buys on one day, the second sized on the reduced cash); `test_resume_matches_uninterrupted` (parametrised: `QuotaExhausted` from a low `llm_daily_token_budget`, and a `RuntimeError` from the fake LLM, both mid-week 2; resumed with normal settings; compared with §11.5); `test_start_before_cutoff_refused`; `test_resume_after_model_change_refused` | AC-3, AC-4, AC-5, AC-7, AC-8 | 7.1 (money, leaks, silent corruption) + 7.2 happy path |
| `test_config.py` (+) | The three new defaults | FR-16 | — |

The runner tests reuse `test_graph.py`'s recorded fixtures (AAPL prices 2024-04-01 to 2024-07-31, SEC, news; every symbol gets the AAPL bars) and its `RecordingLLM`, scripted by ticker. A 3-week window from 2024-07-01 fits inside the fixture, including the entries after the last decision day. The migration test covers `0005` unchanged (AC-9).

**Manual checks** (evidence pasted into `task.md`):

| Check | How |
|---|---|
| Quota first | Before the run, sum the last 24 hours of `llm_calls` per model and confirm the large model has at least 30K left |
| AC-6 | `bullpit backtest --tickers <first ADR-0006 stock> --start 2024-07-01 --weeks 2 --seed 1` (about 5–10 minutes: the gateway's per-minute pacing spaces the ~10 calls of a debated request), started with `LLM_DAILY_TOKEN_BUDGET` = the small model's tokens used in the last 24 hours + 4,000. The budget check is `used + estimate > budget` per model, and cache hits are served before it (`gateway.py`). So the week-1 analyst calls go through, and the next small call, or any large call (the large model is already far above that budget), raises `QuotaExhausted` partway through week 1 whichever route the brain takes. Then `--resume` with the default budget: the week's earlier calls must show `cache_hit = 1`. Record the pause message, tokens used, end equity, trades, and one row count per table |
| Reports and a trade | Read one buy report (if any) and one no-trade report; check any trade's entry against the next session's real open × 1.0005, and any exit against that day's bar |
| AC-10 | ADR-0005 and ADR-0006 read by the owner |

Nothing in the automated suite uses quota: every test runs on recorded fixtures and the scripted fake LLM, in seconds.

## 14. Work order

`task.md` breaks this into tasks, in this order:

1. Docs on the new branch (this file, `task.md`, dev-plan status line and §10 entry for D-M6-22, deviation D12, architecture v2.4).
2. Settings; `Bar` and `Trade` in `domain.py`; public rounding helpers.
3. Calendar helpers and their tests.
4. `broker/base.py` (`OrderBroker`, `client_order_id`) and `broker/sim.py` with `test_sim.py`; ADR-0005.
5. `approval/gate.py`.
6. Journal: models, migration `0005`, `Request.run_id`.
7. `add_request_rows` split out of `_finalize` (existing tests unchanged and passing).
8. `RequestState.loss_warning` and the report reading it.
9. `runners/backtest.py`: start, weekly loop, stop and resume, model guard.
10. `bullpit backtest` CLI.
11. Runner tests.
12. ADR-0006: apply the rule, choose the stocks, check they have no split in the window (can be done alongside tasks 2–11; it uses no LLM quota).
13. Real 2-week run with the forced pause and resume (AC-6), report and trade checks.
14. Acceptance: README, retrospective; merge and tag `m6` when the owner asks.

Everything runs today: tasks 1–12 use no LLM quota, and task 13's run takes about 5–10 minutes (per-minute pacing makes a debated request take a few minutes). The automated suite takes seconds.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Today's quota runs out before the 2-week run ends | The run pauses and can't finish today | About 80K large-model tokens left against at most ~22K for 2 debated requests; the quota check first |
| Buys are rare (2 of 9 debated requests in M5); a 2-week, 1-stock run has only 2 requests | Likely no real trade, leaving `trades` and `approvals` empty in the real run | Reported honestly, not engineered around. The trade path is proven by the automated tests (AC-1 to AC-4, AC-8); M7's 26-week run exercises it on real data |
| The 26-week real run hasn't happened when M6 is accepted (D-M6-22) | A problem that only shows over many weeks is found in M7, not M6 | The runner is the same code at any length; AC-4 proves resume; M7 starts with that run |
| A subtle sim bias (a fill rule read wrongly) | Every backtest result is wrong without showing it | One fixture per rule (AC-1), ADR-0005 reviewed against architecture Part 14 line by line, a hand check of one real trade |
| Non-deterministic ordering inside the graph (parallel analysts' warnings) | AC-4 fails or flakes | AC-4's test shows it at once; if LangGraph's merge order isn't stable, warnings are sorted where they're merged (a one-line fix, noted in `task.md`) |
| A week's transaction holds many rows | Memory or lock time | At most 3 requests' rows plus 5 sessions per week; SQLite handles it easily |
| Groq changes the free limits or a pinned model mid-run | The run can't resume | FR-13 refuses a model change; any model change is a new decision (D9) |
| Asset status is today's, not the window's (D-M6-14) | A stock delisted since would be refused | ADR-0006 picks large caps that traded throughout |
