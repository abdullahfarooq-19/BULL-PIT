# M11.1: Report readability and the order box: specs and plan

| | |
|---|---|
| **Status** | **Revision 2, 2026-10-05.** Revision 1 was approved and `task.md` written. Revision 2: the owner asked for enough testing to be sure everything works, so §13 gains end-to-end flow tests, a data-migration test, a stored-report compatibility test, a gate property test, a scripted browser check and a regression pass (AC-17, D-M11.1-17); `task.md` is updated to match. **Start-rule override (2026-10-05):** the owner gave the green light to implement before M8 is accepted, so Q3 and the "after M8" rule below no longer hold; the work is on a branch cut from `m8-live-mode` (see `task.md`) |
| **Date** | 2026-10-05 |
| **Size** | XL. Written as one `specs-plan.md` on the owner's instruction, as M3, M4, M6 and M8 were (D-M11.1-1). [Dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents) would otherwise ask for separate `specs.md` and `plan.md` |
| **Name** | "M11.1" is the owner's name for this milestone (first called M1.1, renamed on 2026-10-05). It is **not** a patch to any earlier milestone. It sits after M8 and takes the report-page and order-box part of what dev-plan §5 lists under M9; M9's README and results write-up are untouched. There is no M10 or M11 in the dev plan; M11.1 is only a label |
| **Branch** | `m11.1-report-and-order-box`, cut from `m8-live-mode` (owner's override; originally from `master` once M8 is tagged `m8`) |
| **ADRs** | **ADR-0008: limit-entry bracket orders** (new, M11.1-AC-8). It assumes M8's ADR-0007 (exit anchoring) is written first; the numbers follow the order they are written |
| **Depends on** | **M8** (live mode: API, dashboard, approval, bracket orders, fill check): **not yet accepted**. M8 still needs a market session (M8-T-12), a push for CI's web job, and the owner's click-through. M11.1 does not start until M8 is accepted ([dev-plan §1.4](../../dev-plan.md#14-definition-of-ready-a-milestone-may-start-when)). It reuses M5 (report, number check), M4 (`share_limits`, `shrink`, `build_order`) and M6's journal |
| **Sources** | [architecture Part 9](../../architecture.md#part-9--bull-vs-bear-debate-llm), [Part 11](../../architecture.md#part-11--risk-manager-both), [Part 12](../../architecture.md#part-12--report-generator-both), [Part 13](../../architecture.md#part-13--approval-gate-code), [Part 14](../../architecture.md#part-14--execution-broker-adapter-code), [§7](../../architecture.md#7-the-report), [§9](../../architecture.md#9-a-trades-life), [§14](../../architecture.md#14-free-tier-budget); [dev-plan §1.2, §3, §5 M8–M9, §6.1, §6.5, §7, §8](../../dev-plan.md); [M8 specs-plan](../M8-live-mode/specs-plan.md) (FR-6 to FR-10, FR-29, D-M8-4, D-M8-10, D-M8-25, D-M8-28, §9.6); [M5 specs-plan](../M5-report/specs-plan.md) and its retrospective (token measurements); [M3](../M3-analysts/specs-plan.md) and [M4](../M4-debate-trader-risk/specs-plan.md) task.md measurements; [ADR-0002](../../adr/0002-bracket-order-tif-and-legs.md); [M0 findings](../M0-foundations/findings.md) A7–A9; [system walkthrough](../../system-walkthrough.md) |

Part A says **what** M11.1 delivers and how it is accepted. Part B says **how** it gets built. Neither restates the architecture or the dev plan; they link to them.

---

## Contents

**Part A: Specs**: [1 Goal](#1-goal) · [2 Scope](#2-scope) · [3 Functional requirements](#3-functional-requirements) · [4 Non-functional requirements](#4-non-functional-requirements) · [5 Interfaces](#5-interfaces) · [6 Acceptance criteria](#6-acceptance-criteria) · [7 Decisions](#7-decisions-made-in-this-document) · [8 Open questions](#8-open-questions-for-the-owner)

**Part B: Plan**: [9 Module design](#9-module-design) · [10 Data model](#10-data-model) · [11 Key algorithms](#11-key-algorithms) · [12 Error handling](#12-error-handling) · [13 Tests and checks](#13-test-and-verification-plan) · [14 Work order](#14-work-order) · [15 Risks](#15-risks)

---

# Part A: Specs

## 1. Goal

After M8 the owner can run the full loop, but two things on the **Report and decide** page fall short in real use:

1. **The report is hard to understand.** It lists facts in a table and shows a short debate summary. The owner wants each analyst explained in a plain-language paragraph with the confidence and the facts below it, and the debate explained round by round, with how it reached its conclusion. The signal gauges also mislead.
2. **The order box is too rigid.** It shows a plan priced on yesterday's close and sends a market order whatever the price is now. The owner wants a live price, exits that follow the entry price, a choice between buying now and buying at a price they set, a way to cancel a waiting order, and an opt-in mode to change the exits and the size.

The done-when, in the architecture's style: *a live report explains each analyst and the debate in plain language; the owner sees the live price, chooses to buy now or at a set price, approves, and a real pending order is visible on Alpaca paper and can be cancelled from the dashboard.* The **Recommendation section stays as it is.**

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | **Analyst sections** on the report page: per analyst a summary paragraph, the confidence number and a lean bar, then all facts as a list. A failed analyst is shown as "could not run" | Part 12 (the report writer) |
| S2 | **Debate section**: a paragraph per round and a "how it reached its conclusion" paragraph, the conviction bars, and an expandable list of the full turns | Part 9, Part 12 |
| S3 | **`LeanBar`**, replacing `SignalGauges`: bearish fills left, bullish fills right, length = confidence; flagged and neutral states; one overall bar for the board score | M8 §9.6 |
| S4 | Report writing: three analyst summaries as extra fields in the existing report LLM call; the debate narrative as one extra small-model call; both **live mode only**; both under the report's number and ID check; code-written fallbacks | Part 12; M5 |
| S5 | `Report` gains `analyst_summaries`, `board_score`, `debate_turns`, `debate_narrative` (all optional) | Part 15 (reports) |
| S6 | **Order preview** endpoint: the live price and the order computed for the chosen entry mode, exits and size, with warnings. The order box shows it and refreshes it about every 5 seconds | Part 13 |
| S7 | **Entry modes**: *buy now* (a market order, exits priced from the price the owner saw) and *buy at a price I set* (a GTC limit-entry bracket) | Part 14 |
| S8 | `reprice`: stop and target follow the entry, keeping the plan's stop and target distances | Part 11 |
| S9 | **Owner cancel** of a pending live order: `AlpacaBroker.cancel_order`, `POST /trades/{id}/cancel`, a Cancel button | Part 14; §9 |
| S10 | **Advanced mode**: an opt-in toggle to edit stop, target and shares, with a warning and a confirmation; cash is the only hard limit; every override is recorded and badged | Part 11, Part 13 |
| S11 | Approval gate and `execute` extended for S7 and S10; the order placed is built from the **recorded** approval | Part 13; M8-FR-7 |
| S12 | Journal migration `0008`; Alpaca limit-entry probe and ADR-0008; deviations D15 to D18 and architecture revision v2.7 | dev-plan §3, §8 |
| S13 | Manual checks the owner asked for: a real pending limit order on Alpaca paper (no fill needed), and a basic check that the three analysts work | §7.3 |

### 2.2 Out of scope

- **Editing a pending order.** Changing a waiting order's price means cancelling it and starting a new request (about 15K tokens). A replace flow is a later milestone.
- A background job that cancels old pending orders (C9: no scheduler). A pending limit order lives until it fills or the owner cancels it.
- A live price on the Trades page, and a "market open" indicator. The order box labels the price "last trade" with its fetch time.
- Selling or closing a position, or changing a filled trade (architecture §9 stands for every **filled** trade).
- Any change to the analysts' own prompts, the debate prompts, the trader, the risk review, or what the pipeline decides. M11.1 only **explains** their output.
- The other pages (History, Trades, Backtests) apart from an "override" badge and the Cancel button.
- M7's carry-overs and M8's open items.
- A sell stop, trailing stop, scaling in or out, or short selling.

## 3. Functional requirements

**Report readability (architecture Part 12; M5)**

- **M11.1-FR-1 Analyst sections.** The report page shows, for each of technical, fundamentals and sentiment, in that order: the analyst's name, its direction as a badge, its confidence as a number with a lean bar, the **summary paragraph**, then **every fact** as a list item with its ID chip. A sentiment list of more than six headlines collapses after six, with "show all". A caption under the block says: *"Direction and confidence are the model's judgment of these facts, not a calculation."*
- **M11.1-FR-2 Failed analysts.** A flagged signal (it failed, or its reply was invalid) shows "This analyst could not run: <note>" in place of the direction, confidence and paragraph. It is never drawn as a neutral reading, and its facts, if any, are still listed.
- **M11.1-FR-3 Summary paragraphs.** The report writer writes one paragraph per analyst, at most `report_paragraph_max_words` (110) words, in plain language for a non-expert: what the facts say, why they point to the stated direction, and what cuts against it. It may use only numbers and evidence IDs that appear in the report (the M5 rule). It writes nothing for a flagged analyst.
- **M11.1-FR-4 Debate narrative.** After a debate, the report writer writes `debate_rounds` (2) round paragraphs, each at most `report_paragraph_max_words` words, saying what each side argued and answered in that round, and a **conclusion paragraph** saying how the debate led to the trader's decision: the two final convictions, the strongest unresolved point, the trader's decision and reason, and the risk review's outcome. Same number and ID rule as FR-3. A request that skipped the debate has no narrative and no debate section, as today.
- **M11.1-FR-5 Debate section.** The page shows the narrative paragraphs, then the two conviction bars (bull and bear) as today, then an expandable **full turns** list: each turn's claims with evidence chips, unsupported claims struck through with an "unsupported" tag, concessions in italics, and the conviction. The data comes inside the report (FR-8), so no new endpoint is needed.
- **M11.1-FR-6 Live only.** Summaries and the narrative are produced only for live reports. Backtest and baseline reports keep today's prose, so their token cost and M7's tokens-per-request numbers do not change (AC-3). A live report made before M11.1, or any report whose writer fell back, still renders: the page shows the facts and direction, and for a missing paragraph a one-line note, never an empty section.
- **M11.1-FR-7 Fallbacks.** If the writer's reply is invalid after the one retry (the M5 rule), the paragraphs are written by code from the signals: "Technical: bullish with confidence 0.60. See the facts below." and, for the debate, from the existing debate summary fields and the two convictions. The report records which source wrote the prose (`prose_source`, existing).
- **M11.1-FR-8 Report fields.** `Report` gains optional `analyst_summaries` (analyst name to paragraph), `board_score` (the code-computed score, so the page never recomputes it), `debate_turns` (every turn: side, round, claims with evidence IDs and the `unsupported` flag, concessions, conviction) and `debate_narrative` (round paragraphs and conclusion). All default to `None`, so stored reports from before M11.1 still load.
- **M11.1-FR-9 Lean bar.** One component draws every signal: a horizontal track with a fixed centre tick; bearish fills left in the bear colour, bullish fills right in the bull colour, the fill's length is the confidence; neutral shows a grey centre marker; the value is written beside it ("Bullish 0.60"); a flagged analyst shows an amber "could not run" state. A separate overall bar shows `board_score` from `-1` to `+1`. The old gauges are removed. The bar has a text label for screen readers and respects reduced motion.

**Order box (architecture Parts 11, 13, 14)**

- **M11.1-FR-10 Order preview.** `POST /requests/{id}/order-preview` takes the entry mode and, in advanced mode, the owner's edits, and returns the latest price and the order that mode would place (FR-12 to FR-16), without placing anything. It is available while the request is `awaiting_approval`. The order box calls it on open, about every 5 seconds while the tab is visible, and (debounced) whenever the owner changes the mode, price, stop, target or shares. **All order maths is on the server**; the page only displays the numbers. A failed price read returns the last good preview's data unchanged and a `price_unavailable` warning; it never invents a price.
- **M11.1-FR-11 Live price.** The preview's `price` is Alpaca's latest trade on the IEX feed (`data/prices.latest_price`, M8-FR-12), with `fetched_at`. The box shows it as "Last trade, fetched hh:mm:ss". Outside market hours it is the last trade of the session and does not move.
- **M11.1-FR-12 Reprice.** Given the report's order and an entry price `E`, the repriced order has `stop = E - (reference - stop)` and `take_profit = E + (take_profit - reference)`, rounded to the cent, with cost, maximum loss and maximum gain recomputed (M4's `build_order`). This is exactly the architecture's ATR rule for the same ATR and exit style, because the plan's distances are `style x ATR` and `1.5 x style x ATR`. A repriced stop at or below zero is refused.
- **M11.1-FR-13 Entry mode: buy now.** The entry is the **price the owner saw** (`seen_price`, the preview's `price`). Exits are `reprice(order, seen_price)`. The order is a GTC market bracket, as in M8. Before it is placed, the server fetches the latest price and refuses the approval as `stale` if it moved more than `approval_staleness_pct` (2%) from `seen_price`, unless the owner confirms (M8 behaviour, now measured against the price on screen, not yesterday's close).
- **M11.1-FR-14 Entry mode: buy at a price I set.** The owner enters a limit price `L > 0`. Exits are `reprice(order, L)`. The order is a **GTC limit-entry bracket**: a limit buy at `L` with the stop and take-profit legs. It waits on Alpaca until the price reaches `L`. The preview warns when `L` is at or above the latest price ("this fills at once at the market price"); it does not refuse that. The staleness check does not apply (the limit protects the price).
- **M11.1-FR-15 Share count (normal mode).** The maximum is `min(recommended shares, cash_shares, cap_shares)` at the entry price, with cash and position **net of pending orders** (M8-FR-29). Shares can still only go down from the recommended count (M8-FR-6.3). Maximum loss, % of equity and cost are shown for the chosen count.
- **M11.1-FR-16 Advanced mode.** A toggle, off by default, opens editable **stop, take-profit and shares**, under a warning that stays visible while it is on: *"You are overriding Bull Pit's risk rules. Losses can exceed the planned 1% of equity."* Rules:
  1. `0 < stop < entry < take_profit` (the entry is `seen_price` or `L`).
  2. Shares are a whole number of at least 1, and may **exceed the recommended count**.
  3. **Available cash is the only hard limit**: `shares x entry <= cash` net of pending orders. Never buying power (M0 A13).
  4. The 10% per-stock cap and the 1% risk limit become **warnings** in the box, red when exceeded: *"This puts 14% of equity in one stock (plan cap 10%)"* and *"Maximum loss is 2.3% of equity (plan 1%)"*.
  5. Approving with any override opens a confirmation dialog listing each override and warning, with "I understand and approve" (`confirm_overrides`).
  The report is not edited: a note under the box says the report's numbers refer to the original plan.
- **M11.1-FR-17 Decision checks.** `POST /requests/{id}/approval` takes the M8 body plus `order_type`, `limit_price`, `seen_price` and the advanced edits. Code re-computes the order from these (it never trusts exits sent by the page outside advanced mode) and checks, in this order, refusing at the first failure ([§11.3](#113-approval-checks-gatecheck_decision-revised)): not awaiting; expired; shares (normal: `1..max`; advanced: `>= 1`); latest price available; **staleness (buy now only)**; loss warning confirmed; **latest price above the final stop, and for a market order below the final take-profit** (M8 D-M8-28, now for the final exits; a limit order waits, D-M11.1-15); override validity and confirmation; cash (and, in normal mode, the cap).
- **M11.1-FR-18 Record, then order.** A decision that passes is committed to `approvals` **before** the graph resumes, with the order type, the entry price, the limit price, the final stop, take-profit and shares, `seen_price`, and the `overrides` list (M8-FR-7, extended). The `execute` node builds the order **from that recorded row**, not from the graph state, and places it only if the row exists and says `approved`. Placing it is idempotent with the same `client_order_id` (M8-FR-2). One order per request, as before.
- **M11.1-FR-19 Override record.** The server computes the `overrides` list: `custom_exits` (stop or take-profit differ from the repriced values), `size_above_plan` (shares above the recommended count), `above_cap` (position after the trade above the cap), `above_risk_limit` (maximum loss above `risk_per_trade_pct` of equity). History and Trades show an "override" badge for any approval with a non-empty list, and the order type.
- **M11.1-FR-20 Pending reservation.** A trade's `reference_price` is the **entry** it was placed at (the seen price or the limit), so M8-FR-29's `net_of_pending` reserves cash and cap at the right price for limit orders with no further change.
- **M11.1-FR-21 Cancel.** `POST /trades/{id}/cancel` cancels a **pending** live trade: `AlpacaBroker.cancel_order`, then a re-read of the order through `live_order`, and the row is updated to `cancelled` with reason `cancelled by owner`. If the entry has already filled or partly filled, nothing is cancelled and the response is a `not_cancellable` refusal that says to run the fill check. A cancelled entry never becomes a manual close (D-M8-10 reads only `open` trades, and `live_order` already maps a cancelled unfilled entry to `cancelled`). A Cancel button shows on the Trades page and on the report page while the trade is pending.
- **M11.1-FR-22 Limit-order lifetime.** A limit order is GTC and has no automatic expiry (decided by the owner). It stays `pending` until it fills (the fill check records it) or the owner cancels it. The report's own expiry (M8-FR-9) only limits how long the **approval** can be given.

**Settings and journal**

- **M11.1-FR-23 Settings.** One new setting in `config.py` and `.env.example`: `report_paragraph_max_words` = 110 (a soft limit like `debate_turn_max_words`: code flags a paragraph over it and adds a warning, and never truncates). No other new threshold: staleness reuses `approval_staleness_pct`, the warnings reuse `max_position_pct` and `risk_per_trade_pct`.
- **M11.1-FR-24 Migration.** `0008` ([§10](#10-data-model)).

## 4. Non-functional requirements

- **M11.1-NFR-1 (tests)** [Dev-plan §7](../../dev-plan.md#7-testing-strategy)'s categories, with the owner's request for more assurance (D-M11.1-17) spent only where a failure would lose money, lose or corrupt a stored record, or send the owner wrong numbers: `reprice`, the gate (with a property test), the limit-entry request shape and cancel, the order recorded equals the order placed, one end-to-end flow test per entry mode, the `0008` data migration, stored M8 reports still loading, and the number check on the new fields. The dashboard gets a **scripted browser check** run from the session scratchpad (nothing added to the repo), plus the owner's click-through. Prompt quality and the live probe are checked by hand. No network (`pytest-socket`); the suite stays under about a minute.
- **M11.1-NFR-2 (pure core)** `reprice`, the override flags and the gate stay pure: no I/O, no settings reads, no clock reads; prices, `now`, the account and the position are passed in.
- **M11.1-NFR-3 (money)** Prices, costs and limits are `Decimal` rounded to the cent; shares are integers; the page never does money arithmetic that matters (it displays the server's strings).
- **M11.1-NFR-4 (safety)** Paper guard unchanged. No order without a committed owner approval. One order per `client_order_id`. The order placed equals the recorded approval. An override can never spend more cash than available. The cap, the risk limit and the stale-price confirmation are warnings the owner may accept, never silently skipped, and always recorded.
- **M11.1-NFR-5 (tokens)** Live debated requests add about **2.2 to 2.7K small-model tokens** (summaries about 0.65K, narrative about 1.5 to 2.0K; the estimate is in [§11.5](#115-token-budget)), about 16% of the ~15.5K total and about +50% of the small model's share. The large model is untouched, so the live limit of about 18 debated requests a day does not change. Backtest and baseline requests add nothing. The retrospective records the measured numbers ([dev-plan §6.5](../../dev-plan.md#65-performance-and-budget)).
- **M11.1-NFR-6 (Alpaca data)** The preview makes up to three Alpaca calls (latest trade, account, position) about every 5 seconds while the tab is visible, about 36 a minute, far under Alpaca's limit. The poll stops when the tab is hidden or the request is no longer waiting.
- **M11.1-NFR-7 (browser)** As M8: current Chrome or Edge on a laptop screen, one dark theme (C10).

## 5. Interfaces

```python
# bullpit/domain.py (+)
OrderType = Literal["market", "limit"]
class Trade(BaseModel, frozen=True):          # M8 fields, plus:
    order_type: OrderType = "market"
    limit_price: Decimal | None = None

# bullpit/risk/sizing.py (+; pure)
def reprice(order: SizedOrder, entry: Decimal) -> SizedOrder | None: ...   # None: stop <= 0 (FR-12)

# bullpit/approval/gate.py (+; pure)
class OwnerDecision(BaseModel):               # M8 fields, plus:
    order_type: OrderType = "market"
    limit_price: Decimal | None = None
    seen_price: Decimal | None = None         # the preview's price; required for "market"
    stop_loss: Decimal | None = None          # advanced mode only
    take_profit: Decimal | None = None        # advanced mode only
    advanced: bool = False
    confirm_overrides: bool = False
class ApprovalDecision(BaseModel):            # M8 fields, plus:
    order_type: OrderType
    entry_price: Decimal | None               # None for a rejection
    limit_price: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    seen_price: Decimal | None
    overrides: list[str]                      # custom_exits, size_above_plan, above_cap, above_risk_limit
def final_order(order: SizedOrder, decision: OwnerDecision, ...) -> SizedOrder | ApprovalProblem: ...
def override_flags(final: SizedOrder, plan: SizedOrder, equity: Decimal, held_value: Decimal, ...) -> list[str]: ...

# bullpit/broker/alpaca.py (+)
class AlpacaBroker:
    def submit_bracket_order(self, order: SizedOrder, *, client_order_id: str,
                             submitted_on: date, limit_price: Decimal | None = None) -> Trade: ...
        # limit_price None: market bracket as in M8; set: GTC limit-entry bracket
    def cancel_order(self, order_id: str) -> None: ...          # BrokerRejected on any Alpaca error except "already gone"

# bullpit/report/model.py (+; all optional, default None)
class DebateTurnView(BaseModel, frozen=True): ...   # side, round, claims (text, evidence_ids, unsupported), concessions, conviction
class DebateNarrative(BaseModel, frozen=True):
    rounds: list[str]                                # one paragraph per round
    conclusion: str
class Report(BaseModel):                             # + fields
    analyst_summaries: dict[str, str] | None
    board_score: float | None
    debate_turns: list[DebateTurnView] | None
    debate_narrative: DebateNarrative | None

# bullpit/llm/schemas.py (+)
class ReportProse(BaseModel):                        # + three optional strings (live mode)
    technical_summary: str = ""
    fundamentals_summary: str = ""
    sentiment_summary: str = ""
class DebateNarrativeReply(BaseModel):
    rounds: list[str]
    conclusion: str

# bullpit/api/schemas.py (+)
class OrderPreviewBody(BaseModel):      # order_type, limit_price?, advanced, shares?, stop_loss?, take_profit?
class OrderPreview(BaseModel):          # price, fetched_at, entry_price, order_type, stop_loss, take_profit,
                                        # shares, max_shares, cost, max_loss, max_gain, pct_of_equity,
                                        # loss_pct_of_equity, position_pct_after, overrides, warnings[{code, message}]
```

`POST /requests/{id}/order-preview` returns 200 `OrderPreview`; 404 unknown request; 409 `not_awaiting`; 422 invalid body (for example a limit order without a price). `POST /trades/{id}/cancel` returns 200 `TradeOut`; 404; 409 `not_cancellable`; 502 if Alpaca cannot be reached. `POST /requests/{id}/approval` keeps its path and refusal codes and adds `override_not_confirmed`, `price_unavailable` (as before), `limit_invalid` and `exits_invalid`.

## 6. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| **M11.1-AC-1** | A live report's page shows, for each analyst, its direction, confidence and lean bar, a summary paragraph of at most 110 words, and every fact; a flagged analyst shows "could not run" and no reading. A report from before M11.1 still renders with a one-line note | Manual: owner reads 3 real live reports (a buy, a no-trade after a debate, a no-trade without one); **Automated**: the builder fills the fields for live and the page fixtures render |
| **M11.1-AC-2** | The report number and ID check rejects an invented number or an unknown evidence ID in any new field (analyst summary, round paragraph, conclusion), asks once for a rewrite, then falls back to code-written text | **Automated** |
| **M11.1-AC-3** | Backtest and baseline reports have `analyst_summaries`, `debate_turns` and `debate_narrative` unset, and a backtest request makes the same LLM calls as before M11.1 (the fake LLM counts them) | **Automated** |
| **M11.1-AC-4** | A debated live report shows the round paragraphs, the conclusion paragraph, the conviction bars and the full turns (with unsupported claims struck through); a skipped-debate request shows no debate section | Manual: owner reads; **Automated**: `debate_turns` match the debate recorded in the journal |
| **M11.1-AC-5** | The lean bar draws bullish, bearish, neutral and flagged states correctly at confidence 0.1, 0.5 and 1.0, with a text label; the old gauges are gone | Manual: screenshots of a fixture page showing every state |
| **M11.1-AC-6** | `reprice` keeps the plan's stop and target distances for any entry (the architecture's AAPL example: entry 182, stop 174, target 194 repriced to entry 190 gives 182 and 202), rounds to the cent, and refuses a stop at or below zero | **Automated** (worked example + one property test) |
| **M11.1-AC-7** | The gate, with a fake price source: (a) normal mode refuses more shares than `min(recommended, cash, cap)`; (b) buy now refuses a latest price more than 2% from `seen_price` unless confirmed, and exactly 2% passes; (c) a latest price at or below the final stop is refused in both modes, and at or above the final take-profit for a market order (a limit order waits, D-M11.1-15); (d) a limit order skips the staleness check and refuses `L <= 0`; (e) advanced mode accepts shares above the recommended count and above the cap, refuses shares costing more than cash net of pending orders, refuses `stop >= entry` or `entry >= take_profit`, and refuses without `confirm_overrides`; (f) the `overrides` list is exactly the flags that apply | **Automated** |
| **M11.1-AC-8** | **A real limit-entry bracket on Alpaca paper:** a 1-share GTC limit buy far below the market, with its two legs, is **accepted and visible as pending** in Alpaca's orders (no fill is needed: a limit order fills at its price by Alpaca's own design), is read back by `live_order` as `pending`, and is cancelled and read back as `cancelled`. The two invalid shapes (take-profit below the limit, stop above it) are rejected. Findings go in ADR-0008 | Manual: the spike `scripts/spikes/alpaca_limit_entry.py` output, the Alpaca orders view and the ADR, pasted in `task.md` |
| **M11.1-AC-9** | The order placed equals the recorded approval: for market and limit approvals, with and without overrides, the request sent to Alpaca (type, limit, quantity, stop, take-profit, `client_order_id`) is built from the committed `approvals` row; with no committed row nothing is sent; the same approval sent twice gives one order | **Automated** (fake broker and fake `TradingClient`) |
| **M11.1-AC-10** | Cancel: a pending trade is cancelled through the API and recorded `cancelled by owner`; a trade that has filled is refused `not_cancellable` and not changed; after a cancel the fill check leaves the row alone and the request's lock stays released | **Automated** (fake broker, one happy path) + Manual (once for real, in AC-8's order) |
| **M11.1-AC-11** | The order box on a running app: the live price refreshes about every 5 seconds and stops when the tab is hidden; switching buy now and set a price changes the entry, stop, target and shares at once; the advanced toggle shows the warning, unlocks the fields, and approving with an override asks for confirmation; Reject and Approve (hold) still work | Manual: owner click-through against a running API, notes in `task.md` |
| **M11.1-AC-12** | **A limit order approved through the dashboard on real Alpaca paper** (a price well below the market) appears pending in Alpaca with the entry, stop and take-profit the box showed, is shown on the Trades page as pending with a Cancel button, and is then cancelled from the dashboard. A market-mode approval is also placed once, in a market session, and recorded | Manual: dashboard screenshots, Alpaca order view and journal queries pasted in `task.md` |
| **M11.1-AC-13** | **Analyst check:** for two real live requests, no analyst is flagged; the technical and fundamentals facts match numbers recomputed independently (SMA 20 and 50, RSI, ATR from the cached bars; revenue growth, margin and EPS from the SEC data); each direction is consistent with its facts; each summary reads correctly against its facts | Manual: owner reads; the comparison is pasted in `task.md` |
| **M11.1-AC-14** | History and Trades show the order type and an "override" badge for any approval with overrides | Manual (+ **Automated** at the API: the badge's data is the stored `overrides`) |
| **M11.1-AC-15** | `alembic upgrade head` on an empty database matches `models.py` (the migration test covers `0008`); CI regenerates `web/openapi.json` and `web/src/api/schema.d.ts` with no diff, and lints and builds the web app | **Automated** (CI) |
| **M11.1-AC-16** | Tokens are measured on two real debated live requests and recorded against §11.5's estimate; no other call's tokens change | Manual: numbers from `llm_calls` in `task.md` |
| **M11.1-AC-17** | **Nothing that worked before breaks, and each new flow works from end to end.** (a) The whole suite passed before M11.1 started (the baseline count is recorded) and passes after every task. (b) Through the real HTTP layer with the fake LLM and fake broker: a **buy-now** flow (request, preview, approve, one market order with exits repriced from the seen price, a pending trade, the fill check opens it), a **limit** flow (the same to a pending limit trade with its reference price the limit, then cancelled by the owner, then the fill check leaves it alone) and an **advanced** flow (overrides recorded, confirmation required, badge data stored). (c) A `0007` database holding an approval, a trade and a report upgrades to `0008` with every row intact. (d) A report stored by M8 still loads. (e) The **scripted browser check** passes against a scratch server: every page state, the lean bar's states, the mode switch, the price refresh and its stop when the tab is hidden, advanced mode and its confirmation, Cancel, a keyboard-only approval, the API-stopped error state and the empty-journal state | **Automated** (a, b, c, d) + **Scripted** from the scratchpad, screenshots pasted in `task.md` (e) |

## 7. Decisions made in this document

D-M11.1-4 to D-M11.1-7 change what the system does, so they become deviations **D15 to D18** in [dev-plan §3](../../dev-plan.md#3-deviations-from-the-architecture-roadmap) and architecture revision **v2.7**, written in the first task (Part 12 and Part 15; Part 11, Part 13 and §9; Part 14). The other decisions are implementation choices.

| # | Decision | Reason |
|---|---|---|
| D-M11.1-1 | **One `specs-plan.md`** for this XL milestone | The owner asked for it, as for M3, M4, M6 and M8 |
| D-M11.1-2 | **Analyst summaries are written by the report writer, in the existing report call, not by the analysts' own calls** | It keeps every analyst cache valid (the cache key includes the template hash), leaves the fundamentals design (P/E kept out of its prompt, cached per filing; D10) alone, lets the writer see all facts including P/E, and puts the text under the existing number and ID check. Sentiment's direction comes from code, so its LLM has no reasoning to capture anyway. The paragraphs **explain** the code-written facts against the stated verdict; they are not the model's hidden reasoning, and the page says so (FR-1's caption) |
| D-M11.1-3 | **The debate narrative is a separate small-model call, live mode only** | Folding five more paragraphs into the report call would push its output towards the 1830-token cap that output and reasoning share. A separate call keeps each reply short and a retry cheap. Live only keeps M6 and M7 costs and metrics unchanged |
| D-M11.1-4 | **(D15) The report page explains the analysts and the debate in plain language written by the report writer, and the report carries the debate's turns** | Part 12 lets the LLM write "the plain-language parts"; this adds three paragraphs and a narrative under the same rule. Carrying the turns settles M8's open decision on serving them, with no new endpoint |
| D-M11.1-5 | **(D16) The order box prices the order from the live price the owner sees: exits follow the entry by keeping the plan's stop and target distances; "buy now" is a market order whose staleness is measured against that seen price; a limit-entry mode places a GTC limit bracket** | Today's exits hang on the last close, so a gap can leave the stop or target on the wrong side of the real fill. Keeping the distances reproduces the architecture's ATR rule exactly and needs no stored ATR. The pending order exists on Alpaca, so waiting for a price needs no new moving part in Bull Pit |
| D-M11.1-6 | **(D17) The owner can cancel a pending order** | Architecture §9 says the system never touches a trade after approval. A GTC limit that never fills would hold cash for ever, so cancelling an **unfilled** order must be possible. A filled trade is still never touched |
| D-M11.1-7 | **(D18) Advanced mode lets the owner change stop, take-profit and shares; cash is the only hard limit; the 10% cap and the 1% risk limit become recorded warnings** (owner, 2026-10-05) | The owner asked for control with a fair warning. Architecture Parts 11 and 13 state the cap and "shares can only go down" as rules for the **recommendation**; they stay so. The owner's override is explicit, warned, confirmed and recorded, and a trade can never spend cash the account does not have |
| D-M11.1-8 | **The quote is folded into the preview endpoint; there is no separate quote endpoint** | The box needs the price and the order computed from it together. One call is one source of truth and one poll, and keeps order maths on the server (NFR-3) |
| D-M11.1-9 | **In buy-now mode the server prices the exits from `seen_price` and never trusts exits sent by the page outside advanced mode** | What the owner saw is what is placed, and the 2% staleness check bounds how far the market may have moved since. A page sending its own exits would be a way around the gate |
| D-M11.1-10 | **The `execute` node builds the order from the recorded `approvals` row** | M8-FR-7: no order without a recorded approval. Building from the row makes "the order placed equals the order approved" a property of one function, and the crash-recovery path (a resend) uses the same row |
| D-M11.1-11 | **A trade's `reference_price` is its entry** (the seen price or the limit) | FR-29's reservation, `net_of_pending`, then needs no change and reserves cash and cap at the right price for a limit order |
| D-M11.1-12 | **One setting, `report_paragraph_max_words`, for every new paragraph; a soft limit** | One named place for the fact (CLAUDE.md). It matches how the debate's word limit works: a prompt rule, flagged and warned when exceeded, never truncated |
| D-M11.1-13 | **The overall lean bar needs `board_score` in the report** | The page must not recompute the score (code for math). It is one optional field |
| D-M11.1-14 | **A resumed backtest after M11.1 recomputes its cached report prose once** | The report template file changes, so its cache key's `prompt_version` changes (M2). The rendered backtest prompt is unchanged, and the cost is one small call per cached report, so one template with conditionals is simpler than two near-identical templates |
| D-M11.1-15 | **The gate's exits-versus-price check (M8 D-M8-28) applies to the final exits in both modes. For a limit order only the stop side applies** (clarified in T-5, 2026-10-05) | A limit above the market by more than the stop distance would fill below its own stop. Refusing it keeps the dashboard from sending an order Alpaca may reject or fill badly. The take-profit side can't apply to a limit order: a limit well below the market (the whole point of the mode, AC-12) has a latest price above its repriced target, but its exit legs only start once the entry fills |
| D-M11.1-16 | **The analyst check and the limit-order probe are acceptance criteria (AC-13, AC-8, AC-12), not new automated tests** | The owner asked for them. They exercise live services, which dev-plan §7.3 checks by hand; a placed limit order proves the feature without waiting for a fill |
| D-M11.1-17 | **More testing than dev-plan §7's minimum, on the owner's request (2026-10-05), bounded by what a failure would cost.** Added beyond M11.1's first revision: one end-to-end flow test per entry mode through the HTTP layer, a data-preserving `0007` to `0008` migration test, a test that an M8-era stored report still loads, a property test on the gate, limit-order cases in the existing mapping, resend and expiry tests, a cancel-race test, a preview-refusal test, report-mode cases (buy, no-trade after a debate, no debate, a failed analyst, fallback, over-length), a **scripted browser check** from the scratchpad, and a regression pass. **Not** added: tests of prompt wording, of exact UI layout or styling, of live services (checked by hand), a browser-test framework or any new dependency in the repo, or coverage targets | CLAUDE.md says not to add tests beyond dev-plan §7 without asking; the owner asked. Each addition guards money, a stored record or what the owner sees: a bug there is silent. Tests that only pin wording or layout would break on every polish pass and prove nothing about money. The scripted browser check lives in the scratchpad (as M8's did), because CLAUDE.md allows no new dependency the plan doesn't name and forbids scratch files in the repo |

## 8. Open questions for the owner

| # | Question | Answer |
|---|---|---|
| **Q1** | Advanced mode: cash only, or cash and the 10% cap as hard limits? | **Cash only** (owner, 2026-10-05). D-M11.1-7 |
| **Q2** | How long does a limit order wait? | **GTC until filled or cancelled, with a Cancel button** (owner, 2026-10-05). FR-22 |
| **Q3** | When does the work start? | **After M8 is accepted** (owner, 2026-10-05); the owner will give the go-ahead. Not before |
| **Q4** | What is this milestone called? | **M11.1** (owner, 2026-10-05, after first using M1.1). Folder `M11.1-report-and-order-box`, branch `m11.1-report-and-order-box`, tag `m11.1`, IDs `M11.1-FR-x`, `M11.1-T-x` |

Nothing else is open. Every other choice above is a default with its reason; say if you want any changed.

---

# Part B: Plan

## 9. Module design

### 9.1 Files created or changed

```text
bullpit/
  config.py                 + report_paragraph_max_words (110)
  domain.py                 + OrderType; Trade.order_type, Trade.limit_price
  risk/sizing.py            + reprice (pure); reuses build_order, cash_shares, cap_shares, round_cent
  approval/gate.py          OwnerDecision and ApprovalDecision extended; check_decision revised (§11.3);
                            + final_order, override_flags (pure)
  broker/alpaca.py          submit_bracket_order(limit_price=None) builds a market or a limit bracket;
                            + cancel_order
  graph.py                  _execute_node builds the order from the recorded approvals row (§11.4)
  journal/models.py         approvals and trades columns; migrations/versions/0008_order_box.py
  report/model.py           + DebateTurnView, DebateNarrative; Report's four optional fields
  report/builder.py         live mode: analyst summaries (extra fields), debate narrative (second call),
                            fallbacks, number check on the new fields, board_score, debate_turns
  report/number_check.py    unchanged logic; the new fields are passed to it
  llm/schemas.py            ReportProse + three optional strings; DebateNarrativeReply
  llm/prompts/report.md     + analyst paragraphs when requested (live)
  llm/prompts/report_debate.md   NEW: the narrative prompt
  api/app.py, api/schemas.py     order-preview and trade-cancel endpoints; approval body and refusals
  runners/request.py        PendingAwareBroker unchanged; the preview reuses it for cash and position
web/
  openapi.json, src/api/schema.d.ts   regenerated
  src/components/report/lean-bar.tsx          NEW, replaces signal-gauges.tsx (deleted)
  src/components/report/analyst-section.tsx   NEW: summary, confidence, facts
  src/components/report/debate-section.tsx    NEW: narrative, bars, full turns
  src/components/report/order-panel.tsx       rewritten: mode, price, advanced, confirmations, cancel
  src/components/report/bracket-ladder.tsx    draws the preview's numbers
  src/components/report/report-view.tsx       uses the two new sections; the signals table and gauges go
  src/lib/use-order-preview.ts                NEW: the 5-second poll and the debounce
  src/app/trades/page.tsx, requests/page.tsx  order type, override badge, Cancel button
scripts/spikes/alpaca_limit_entry.py          the probe (already written, not yet run); README table row
docs/                       dev-plan §3 D15 to D18; architecture v2.7; ADR-0008; README
tests/                      §13
```

`analyst-section.tsx` and `debate-section.tsx` are new files because `report-view.tsx` already holds all ten sections in one component; the split keeps each readable, and nothing else is split (CLAUDE.md: no extra files).

### 9.2 Dependency direction

Unchanged from M8. `reprice`, the gate and the override flags are pure and import only `domain` and `risk/sizing`. The API calls the broker, the price source and the journal and passes plain values into them. `report/` stays free of I/O except through the passed-in LLM function.

### 9.3 The order box, as the owner sees it

```text
 Order box                                   expires in 5 h 12 m
 ( Buy now )  ( Buy at a price )         Last trade $182.40  (12:04:31)
 Entry          $182.40   (buy now: the price on screen)
 Take-profit    $194.40   +$12.00 per share
 Stop-loss      $174.40   -$8.00 per share
 Shares  [ - ]  32  [ + ]     (max 32: shares can only go down)
 Cost $5,836.80 · 5.8% of equity · max loss $256.00 · max gain $384.00
 [ ] Edit stop, take-profit and size   (advanced: warning shown when on)
 [ hold to approve ]   [ Reject ]
```

The price ladder draws the preview's stop, entry and target. In "price" mode the entry field is editable, and a warning appears when the price is at or above the last trade.

## 10. Data model

Migration `0008_order_box`. Money stays `TEXT` (`Decimal` strings). Existing rows read as market orders with no overrides.

| Table | Change | Notes |
|---|---|---|
| `approvals` | + `order_type TEXT NOT NULL DEFAULT 'market'`, + `entry_price TEXT NULL`, + `limit_price TEXT NULL`, + `stop_loss TEXT NULL`, + `take_profit TEXT NULL`, + `seen_price TEXT NULL`, + `overrides JSON NULL` | What was approved, so the order can be rebuilt from the row (FR-18). A rejection leaves the new columns `NULL` |
| `trades` | + `order_type TEXT NOT NULL DEFAULT 'market'`, + `limit_price TEXT NULL` | `reference_price` already exists and becomes the entry (D-M11.1-11) |
| `reports` | none | The report is JSON; the new fields are optional keys |

## 11. Key algorithms

### 11.1 Reprice (`risk/sizing.py`, pure)

```text
reprice(order, E):
  risk   = order.reference_price - order.stop_loss        # = style x ATR, from the plan
  reward = order.take_profit - order.reference_price      # = 1.5 x risk
  stop   = round_cent(E - risk);  target = round_cent(E + reward)
  if stop <= 0: return None
  return build_order(order.ticker, order.shares, reference=E, stop=stop, take_profit=target,
                     exit_style=order.exit_style, limit=order.limit, limit_shares=order.limit_shares)
```

`limit` and `limit_shares` stay as the plan's record of which limit set the size; the final order's size is the owner's.

### 11.2 Preview (`POST /requests/{id}/order-preview`, under no lock: it places nothing)

```text
load request (must be awaiting_approval) and its report; order = report.order
price = latest_price(ticker)              # failure -> warning price_unavailable, no invented price
account, position = PendingAwareBroker reads (net of pending orders)
entry = body.limit_price if order_type == limit else price
final = reprice(order, entry)             # then, if advanced: stop, take_profit, shares from the body
max_shares = min(order.shares, cash_shares(cash, entry), cap_shares(...)) in normal mode;
             cash_shares(cash, entry) in advanced mode
warnings = [limit_at_or_above_price, exits_invalid, shares_over_cash, above_cap, above_risk_limit, ...]
return the numbers (cost, max loss and gain, % of equity, loss % of equity, position % after)
```

The numbers use the same pure functions the gate uses, so the preview and the approval cannot disagree.

### 11.3 Approval checks (`gate.check_decision`, revised)

```text
if not awaiting:                                   problem not_awaiting      # as M8
if now > expires_at(as_of):                        problem expired
if decision == reject:                             return rejected
if latest is None:                                 problem price_unavailable
entry = limit_price if limit else seen_price       # limit <= 0 or missing seen_price: limit_invalid / 422
final = final_order(order, body, entry)            # reprice; in advanced mode apply the owner's edits
if final is a problem:                             return it                  # exits_invalid
if not advanced and not 1 <= shares <= min(order.shares, cash_shares, cap_shares) at entry:
                                                   problem shares_invalid / rules(max_shares)
if advanced and shares < 1:                        problem shares_invalid
if market and |latest - seen_price| / seen_price > approval_staleness_pct and not confirm_stale:
                                                   problem stale
if loss_warning and not confirm_loss_warning:      problem loss_warning
if latest <= final.stop_loss or latest >= final.take_profit:   problem rules   # both modes (D-M11.1-15)
if shares x entry > cash (net of pending):         problem rules(max_shares)    # advanced: the only hard limit
overrides = override_flags(final, order, equity, held_value)
if overrides and not confirm_overrides:            problem override_not_confirmed
return ApprovalDecision(approved, ..., order_type, entry, limit, final stop/target/shares, seen_price, overrides)
```

The two checks marked as M8's keep their order; the new ones slot in where the old price checks were.

### 11.4 Execute (`graph._execute_node`)

```text
row = the committed approvals row for request_id            # must exist, decision approved
order = build_order(ticker, row.approved_shares, reference=row.entry_price,
                    stop=row.stop_loss, take_profit=row.take_profit, exit_style=..., ...)
trade = broker.submit_bracket_order(order, client_order_id=..., submitted_on=as_of,
                                    limit_price=row.limit_price if row.order_type == "limit" else None)
trade row: reference_price = entry, order_type, limit_price; status pending
```

`submit_bracket_order` builds a `MarketOrderRequest` or a `LimitOrderRequest` (`order_class` bracket, GTC, whole shares, the two legs). The idempotent lookup is unchanged.

### 11.5 Token budget

Measured baseline for a debated request: about 15.5K tokens (small about 4.7K, large about 10.9K; M5 task.md and architecture §14). The report call alone is 1.2 to 2.5K input and at most 274 output plus reasoning. Estimates for the additions (my arithmetic: 120 words about 160 tokens, plus reasoning at "low"):

| Addition | Extra small tokens | Largest call after (limit 8,000 including the 1,830 allowance) |
|---|---|---|
| Three analyst paragraphs as fields in the report call | about 0.65K | about 4.5K |
| Debate narrative call | about 1.5 to 2.0K | about 3.3K |
| **Both** | **about 2.2 to 2.7K** | `trader.md` stays the largest at 6,363 |

The small model's daily capacity drops from about 43 to about 28 debated requests; the large model's limit of about 18 does not change, so it still binds. A report retry (a number slip) doubles that call's cost. AC-16 measures the real numbers.

### 11.6 Prompt rules (what the writer is told)

The analyst paragraphs and the narrative prompts say: write for a person with no finance background; explain what each fact means in plain words before using a term; state which facts support the direction and which cut against it; use only numbers and IDs that appear above, written the same way, and never calculate a new one; cite IDs in brackets. The debate prompt gets the masked transcript (unconfirmed numbers shown as `[?]`, as M5), the two final convictions, the trader's reason and the review verdict, and is told to write exactly `debate_rounds` round paragraphs and one conclusion.

### 11.7 Cancel

```text
trade = live pending trade by id            # else 404; not pending -> 409 not_cancellable
broker.cancel_order(trade.order_id)         # "already filled/canceled" -> re-read, no error
live = broker.get_live_order(trade)         # the same mapper as the fill check
if live.trade.status == cancelled: row.status = cancelled, row.cancel_reason = "cancelled by owner"
else (it filled meanwhile):        update the row from live (the fill check's rule), then 409 not_cancellable
```

## 12. Error handling

| Where | Error | Result |
|---|---|---|
| Preview | Price read fails | The last good numbers are kept on screen; a `price_unavailable` warning shows; no price is invented; the approval is refused until a price is available |
| Preview | Request not waiting | 409 `not_awaiting`; the box stops polling and shows the request's status |
| Approval | Limit missing or `<= 0` | `limit_invalid` |
| Approval | Stop at or above the entry, or entry at or above the take-profit | `exits_invalid` |
| Approval | Overrides present, no confirmation | `override_not_confirmed`; the page opens the confirmation dialog listing each |
| Approval | Alpaca rejects the limit bracket | The request becomes `failed` with Alpaca's message (M8-FR-8); the approval row stays |
| Cancel | Alpaca unreachable | 502; the row is unchanged |
| Cancel | Order already filled | 409 `not_cancellable`; the row is updated from Alpaca and the page says to review the trade |
| Report writing | Invalid reply after the retry | Code-written fallback paragraphs; `prose_source` records it (FR-7) |

## 13. Test and verification plan

Dev-plan §7's categories, widened on the owner's request and bounded as D-M11.1-17 says. No network; fakes are `FakeOrderBroker` (with a price that can be moved and an order that can be filled between two calls), a fake `TradingClient`, a fixed `now`, a fake `latest_price`, and M3 to M5's `RecordingLLM` and recorded price fixtures. **Baseline first:** before the first code task, `uv run pytest` is run on the branch and its test count and time are recorded; every task ends with the four checks green, so a regression shows up in the task that caused it (AC-17a).

| File | Tests | AC | §7 category |
|---|---|---|---|
| `risk/test_sizing.py` (+) | `test_reprice` (the AAPL example 182 to 190; rounding to the cent; stop at or below zero refused) and one property test: the distances are preserved for any entry | AC-6 | 7.1 exits and sizing |
| `approval/test_gate.py` (+) | `test_market_staleness_vs_seen_price` (above 2% refused, confirmed passes, exactly 2% passes); `test_limit_skips_staleness_and_refuses_bad_price`; `test_exits_vs_latest_both_modes`; `test_normal_shares_only_down`; `test_advanced_overrides` (above recommended, above cap, over cash refused, bad exits refused, confirmation needed); `test_override_flags`; `test_gate_property` (for random entries, sizes, cash and equity, in every mode: an accepted decision never costs more than cash net of pending orders and always has `0 < stop < entry < take_profit`, and every refusal carries a code) | AC-7 | 7.1 safety refusals, money |
| `broker/test_alpaca.py` (+) | `test_limit_bracket_request_shape` (limit buy, GTC, bracket, whole shares, cents, `client_order_id`, both legs); `test_cancel_order` (success, already gone, other error); `test_live_order_mapping` extended over the limit shapes (T-3's real pending and cancelled orders, plus a filled one and a stopped-out one derived from them): each maps to `pending`, `cancelled` with reason `entry canceled`, `open` and `closed`, and a cancelled unfilled entry is never read as a manual close | AC-8, AC-9, AC-10 | 7.1 one order per approval; silent corruption |
| `test_graph.py` / `api/test_app.py` (+) | `test_order_equals_recorded_approval` (market, limit, advanced; none sent without a row; sent twice gives one order; **a limit approval recorded and the process "dying" before the order step, then resent, gives one order**); `test_expiry_finds_limit_order` (D-M8-27 for a limit approval: an order Alpaca already holds is recorded, not expired); `test_pending_limit_reserves_cash_at_limit` (a second approval that fits Alpaca's cash but not the cash net of the first limit order, priced at its limit, is refused); `test_preview_happy_path` and `test_preview_refusals` (not waiting, a limit without a price, a failed price read gives a warning and no invented price); `test_cancel_happy_path`, `test_cancel_filled_trade_refused` and `test_cancel_race` (the fake broker fills between the cancel and the re-read: 409, row updated from Alpaca) | AC-9, AC-10 | 7.1 + 7.2 |
| `api/test_app.py` (+), end-to-end flows | `test_flow_buy_now` (request, preview, approve, one market order with exits repriced from the seen price, pending trade with `reference_price` = the seen price, the fill check opens it); `test_flow_limit` (request, preview in limit mode, approve, pending limit trade with `reference_price` = the limit and `order_type` `limit`, cancelled by the owner, the fill check leaves the row alone, the lock is free); `test_flow_advanced` (overrides refused without `confirm_overrides`, accepted with it, `overrides` stored, `TradeOut` carries the badge data). Fake LLM, fake broker, moving fake price, the real HTTP layer | AC-17b | 7.2 happy path, widened (D-M11.1-17) |
| `report/test_builder.py`, `test_number_check.py` (+) | `test_report_modes` (a buy; a no-trade after a debate; a no-trade with no debate; a failed analyst; each checked for the fields it must and must not have); live reports get the three summaries and the narrative; backtest reports leave them unset and make the same LLM calls; an invented number or unknown ID in a new field is rejected, retried once, then falls back; a paragraph over the word limit adds a warning and is not cut; `test_m8_report_json_still_loads` (a report JSON captured from M8's unchanged model, in `tests/fixtures/reports/`, validates with the new fields `None`) | AC-2, AC-3, AC-17d | 7.1 number check; silent corruption of a stored record |
| `journal/test_migrations.py` | covers `0008`; `test_0008_keeps_existing_rows` (a database at `0007` holding an approval, a trade and a report upgrades to `0008` with every row intact, the new columns at their defaults: `market` and `NULL`) | AC-15, AC-17c | existing; silent corruption |
| `test_config.py` (+) | the new default | FR-23 | — |

CI's web job covers AC-15. Nothing automated touches Alpaca, Groq or market data.

**Manual checks** (evidence pasted into `task.md`):

| Check | How |
|---|---|
| AC-8, the limit probe | `uv run python scripts/spikes/alpaca_limit_entry.py` (dry run), then with `--confirm`: a 1-share limit bracket 20% below the last trade, read back, mapped, cancelled; the two invalid shapes rejected. Any time, market open or closed. The Alpaca orders view is screenshotted while it is pending. Write ADR-0008 |
| AC-13, the analyst check | `uv run bullpit request <TICKER>` for two stocks (no order is ever placed by the CLI). For each: no flagged analyst; recompute SMA 20 and 50, RSI and ATR from the cached bars and revenue growth, margin and EPS from the SEC data, and compare with the facts; read each direction against its facts |
| AC-12, the real limit order | `bullpit serve` and `npm run open`; request a ticker until one says buy; "Buy at a price", a price well below the market; approve; see it pending in Alpaca and on the Trades page; cancel it from the dashboard. In a market session, approve one "buy now" order too |
| AC-1, AC-4, AC-5 | The owner reads three real live reports and the lean bar's four states on a fixture page |
| AC-11 | The owner clicks through the order box: the 5-second refresh, the tab-hidden stop, the mode switch, advanced and its confirmation, Cancel |
| AC-16 | Two debated live requests; sum `llm_calls` tokens by call and compare with §11.5 |
| AC-17e, the scripted browser check | A script in the **session scratchpad** (Playwright installed there, not in the repo; nothing committed, CLAUDE.md) drives the built web app against a scratch API with the fake LLM, a fake broker and a price that moves. It checks: the New request, report, History, Trades and Backtests pages in their loading, error (API stopped) and empty (fresh journal) states; the lean bar's bullish, bearish, neutral and flagged states and their labels; the analyst and debate sections for a buy, a no-trade after a debate and a no-debate report; the order box's price updating inside about 6 seconds and stopping when the page is hidden; the mode switch changing entry, stop, target and shares; advanced mode's warning and override confirmation; a keyboard-only hold-to-approve (Space); Cancel on a pending limit trade. It saves a screenshot of each and exits non-zero on any failure. The results and screenshots are pasted in `task.md`; the scratch files are deleted |
| AC-17, regression | The baseline count from before the first code task against the count after the last; the replayed M8 flows (market approval, restart keeps a waiting request, expiry, the fill check) are the M8 tests, unchanged, still passing |

## 14. Work order

[`task.md`](task.md) breaks this into small tasks, in this order. Backend first, so the real Alpaca checks can start early:

1. Docs on the new branch: this file, `task.md`, dev-plan §3 D15 to D18, and architecture v2.7 (Parts 9, 11, 12, 13, 14 and §9, as the Decisions intro lists).
2. Settings (`report_paragraph_max_words`) and `domain.py` (`OrderType`, `Trade` fields).
3. **The Alpaca limit probe** (AC-8) and **ADR-0008** (no market hours needed).
4. `reprice`, then `gate.py`'s revised checks, `final_order` and `override_flags`, with their tests.
5. Journal: models and migration `0008`; `AlpacaBroker.submit_bracket_order(limit_price)` and `cancel_order`, with tests.
6. `_execute_node` from the recorded row; `test_order_equals_recorded_approval`.
7. The API: order-preview, trade-cancel, the extended approval body and refusals; regenerate the OpenAPI schema and web types.
8. Report: the model fields, live-mode analyst summaries in the existing call, the narrative call, fallbacks, number check wiring, `board_score`, `debate_turns`; tests.
9. **Analyst check** (AC-13) on two real requests; read real report prose and adjust the prompts if needed (a prompt-only fix).
10. Web: `LeanBar`; the analyst and debate sections; the report page wired to them; the old gauges removed.
11. Web: the order box (`use-order-preview`, mode, advanced, confirmations, Cancel), the ladder from the preview, the History and Trades badges and Cancel button; **the owner reviews the page** before task 12.
12. **The real limit order through the dashboard and its cancel** (AC-12); the market-mode order in the next market session.
13. **Regression and end-to-end pass** (AC-17): the full suite against the baseline, the scripted browser check (from the scratchpad) over every page and flow, the replayed M8 tests.
14. Token measurement (AC-16); the owner's click-through (AC-11); acceptance: README, retrospective; merge and tag `m11.1` when the owner asks.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Alpaca rejects or mishandles a limit-entry bracket (never tried; ADR-0002 proved only the market bracket) | The limit mode cannot ship as designed | The probe is task 3, before any code depends on it, and needs no market hours. If it fails, the limit mode is redesigned or dropped before the gate and the API are written |
| A limit order that never fills holds cash | Cash is locked | Counted by FR-29 at the limit price, so later sizing stays correct; the owner cancels it (FR-21). No auto-cancel by decision (Q2) |
| A limit price above the market fills at once | The owner expected to wait | A preview warning says so; it is not refused |
| The page and the gate disagree on a number | The owner approves numbers that are not placed | One set of pure functions behind both the preview and the gate; the order placed is built from the recorded row (AC-9) |
| Advanced mode removes the 10% cap and 1% limit | A larger loss than the plan | Explicit toggle, a persistent warning, a confirmation listing each override, the override recorded and badged; cash is still a hard limit (D-M11.1-7) |
| The summary paragraphs sound confident about a judgment the model made without reasoning | The owner over-trusts them | The caption in FR-1; the paragraphs explain the facts against the stated verdict and cut-against points; AC-13 reads them against recomputed facts |
| The writer invents a number or ID in a longer text | A wrong figure reaches the owner | The M5 number and ID check covers every new field; one rewrite, then a code-written fallback (AC-2) |
| A report retry doubles the report call's tokens | Quota use rises | Few new fields, a strict prompt, a separate narrative call so a slip costs one small call; measured in AC-16 |
| Changing `report.md` makes cached report prose miss once | A resumed backtest recomputes some report text | Accepted (D-M11.1-14): one small call per cached report |
| A fill and a cancel cross | The row shows the wrong state | `cancel` re-reads the order after cancelling and updates the row from Alpaca; the refusal tells the owner to review (FR-21) |
| The order box polls Alpaca every 5 seconds | Rate use | About 36 calls a minute while the tab is visible and the request is waiting; the poll stops otherwise (NFR-6) |
| US market hours are Pakistan evenings and nights | Few real sessions | The probe, the limit order and its cancel work with the market closed (an order is accepted and queued); only the market-mode order needs a session |
| M8 is not yet accepted | M11.1 cannot start | Documents only until M8 is accepted (Q3; the owner will approve M8 later); the plan builds on M8's code as it stands |
| The scripted browser check is not in the repo | It can't run in CI and can be lost | Deliberate (D-M11.1-17, CLAUDE.md). Its checks are listed in §13 and its results and screenshots are kept in `task.md`; CI still lints and builds the web app (AC-15) |
| More tests than §7's minimum slow the suite or turn brittle | A suite that is ignored or constantly edited | Only money, stored-record and owner-facing-number cases; no wording or layout tests; the suite stays under about a minute (NFR-1) |
