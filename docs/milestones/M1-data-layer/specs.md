# M1 — Data layer, date guard, cache, calendar: specs

| | |
|---|---|
| **Status** | Approved by the owner on 2026-09-28 (D-M1-2 included). Corrected afterwards while writing and reviewing the plan, from checks against the real services and libraries (none changes the approved behaviour): FR-5 yfinance split-list exception; FR-6 log levels; FR-8 mixed-source rule; FR-11/FR-12 ETF path; FR-14 and AC-10 news paging; FR-15/FR-16 cache layout and merge; NFR-3 date storage; NFR-4 Alpaca timeouts |
| **Date** | 2026-09-28 |
| **Size** | L (so `specs.md`, then `plan.md`, then `task.md`, [dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents)) |
| **Branch** | `m1-data-layer` |
| **Depends on** | M0. Its open tasks (T-17 to T-19 bracket spike, T-25 acceptance) only feed M8. M1 implementation starts after M0 is accepted ([dev-plan §1.4](../../dev-plan.md#14-definition-of-ready-a-milestone-may-start-when)) |
| **Sources** | [dev-plan §5 M1](../../dev-plan.md#m1--data-layer-date-guard-cache-calendar), [§7](../../dev-plan.md#7-testing-strategy), [§10.1](../../dev-plan.md#101-scope-review-revision-4) (C12, C13); [architecture Part 2](../../architecture.md#part-2--data-layer-and-date-guard-code), [§11](../../architecture.md#11-look-ahead-protection); M0 [`findings.md`](../M0-foundations/findings.md) |

This says **what** M1 delivers and how it's accepted. `plan.md` (next gate) says how.

---

## 1. Goal

The only door to the outside world, provably leak-free: every piece of market, filing and news data reaches the rest of Bull Pit through a tool that takes `as_of` and returns nothing that wasn't known at `as_of`. The architecture's done-when: *"Tests prove no data after `as_of` leaks."*

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | `bullpit/clock.py`: `Clock` protocol, `LiveClock`, `SimClock` | D5 |
| S2 | `bullpit/data/calendar.py`: NYSE sessions, holidays, early closes (`pandas_market_calendars`, offline) | D2 |
| S3 | `bullpit/data/guard.py`: request filter + response check, shared by every tool | Part 2 |
| S4 | `bullpit/data/prices.py`: daily bars from yfinance, Alpaca backup, point-in-time split handling, SPY and `^VIX` for market context | Part 2; findings C3 |
| S5 | `bullpit/data/sec.py`: ticker to CIK, companyfacts, filing-date filtering, SEC User-Agent and pacing | Part 2, Part 6 |
| S6 | `bullpit/data/news.py`: Alpaca news for the lookback window, with pagination | Part 2, Part 7; findings C2 |
| S7 | `bullpit/data/cache.py`: Parquet cache, re-checked by the guard on every read | Part 2 |
| S8 | Settings for M1's tunables; `.env.example` updated | CLAUDE.md "no magic numbers" |
| S9 | Move `sec_user_agent()` from `doctor.py` into `data/sec.py`, taking the version from `bullpit.__version__` (not a second hard-coded `"0.1.0"`) | M0 specs-plan §9.5 ("M1 reuses it") |
| S10 | Recorded test fixtures under `tests/fixtures/`; the automated tests in [§6](#6-acceptance-criteria) | dev-plan §7 |

### 2.2 Out of scope

- Indicators, fundamentals ratios, XBRL tag mapping, Q4 derivation, headline de-duplication and the 15-headline cap (M3).
- The request check's "about 60 trading days" and "SEC filings exist" rules (M3). M1 only raises `DataUnavailable`, which M3 turns into the user message.
- SPY 200-day average and VIX high/low labels (M5). M1 only returns the bars.
- Calendar helpers that only later milestones use: `next_open`, `last_trading_day_of_week` (M6), trading days between two dates (M3). Each is added by the milestone that first calls it (the same rule as D-M0-12 for settings).
- Dividend adjustment of prices (see D-M1-2), intraday data, and point-in-time ticker changes (see D-M1-7).

## 3. Functional requirements

**Clock and calendar**

- **M1-FR-1** `SimClock(as_of)` always returns that date. It raises `ConfigError` if `as_of` isn't an NYSE session.
- **M1-FR-2** `LiveClock` returns the latest NYSE session whose close has already happened (architecture §2: live "today" is the latest market close). `clock.py` is the only module in `bullpit/` allowed to read the wall clock (M0-FR-3); the ruff exemption covers that one file.
- **M1-FR-3** The calendar answers: is a date a session; the session's close as a UTC datetime (16:00 New York time, 13:00 on early closes); the last completed session at a given moment; and the first session of an N-session lookback ending at `as_of`. It works with no network.

**Date guard**

- **M1-FR-4** Each `as_of` has one **knowledge cutoff**: the close of the `as_of` session. Each kind of data is compared with it:

  | Data | Kept when |
  |---|---|
  | Daily bar | bar's session date ≤ `as_of` |
  | News article | `created_at` ≤ cutoff |
  | SEC fact | `filed` ≤ `as_of` (a date; see D-M1-1) |
  | Split event | ex-date ≤ `as_of` |

- **M1-FR-5 Request filter.** Every source call asks for nothing later than the cutoff (for example, yfinance's exclusive `end` is `as_of` + 1 day; the news `end` is the cutoff). Two calls have no date parameter: SEC companyfacts, whose response check is its guard, and yfinance's split list, which is read in full only to undo Yahoo's own split adjustment and never returned (ADR-0003).
- **M1-FR-6 Response check.** One shared guard function runs on every tool's result, **after every fetch and after every cache read**. It drops each row later than the cutoff and logs it (source, symbol, row date, `as_of`): a **warning** when the row came straight from a source (it ignored the request filter), **debug** when it came from the cache (later rows stored for another request are expected there).
- **M1-FR-7** A row with no usable date can't be proven safe: the guard raises `LookaheadViolation` (stop loudly, dev-plan §2.2).

**Prices and market context**

- **M1-FR-8** `get_prices` returns daily open, high, low, close and volume for the `sessions` sessions ending at `as_of`, indexed by session date. Source order: yfinance, then Alpaca (SIP feed) if yfinance raises or returns no rows. The result records which source was used (`alpaca` if any returned bar came from the backup), and the log says so.
- **M1-FR-9 Point-in-time prices.** Returned prices are as they were quoted at `as_of`: splits with an ex-date on or before `as_of` are applied to earlier bars, splits after `as_of` are not, and dividends are never adjusted. The result is the same whichever source was used (D-M1-2).
- **M1-FR-10** `get_market_context` returns SPY and `^VIX` bars through the same path. Index symbols (leading `^`) have no Alpaca backup, so a yfinance failure for `^VIX` raises `DataUnavailable`.

**SEC EDGAR**

- **M1-FR-11** The ticker is mapped to a CIK with SEC's `company_tickers.json` (cached). An unknown ticker triggers one refetch of the map; if it's still missing, `DataUnavailable` is raised with the architecture's message ("No SEC filings found for this ticker. Try a US company stock."). Share-class tickers are matched in SEC's form (`BRK.B` is `BRK-B`).
- **M1-FR-12** `get_sec_facts` returns the company's companyfacts as a flat table (taxonomy, tag, unit, period start, period end, value, `fy`, `fp`, `form`, `filed`, accession number). It keeps only facts with `filed` ≤ `as_of`, and for each (taxonomy, tag, unit, start, end) keeps only the one filed most recently. So a restated number replaces the original only once the restatement was filed. A company with no companyfacts (SEC answers 404) raises the same `DataUnavailable` as FR-11. ETFs fail at one of these two steps (checked 2026-09-28: QQQ isn't in the map; SPY is, but has no companyfacts), which is how M3 rejects them (findings C1).
- **M1-FR-13** Every SEC request sends `sec_user_agent()` and is paced to at most `sec_max_requests_per_second`. `doctor` imports the helper from `data/sec.py`.

**News**

- **M1-FR-14** `get_news` returns Alpaca articles for the symbol with `created_at` in the `news_lookback_days` before the cutoff, reading every page (findings C2). alpaca-py 0.44 already follows `next_page_token` when no `limit` is set, so Bull Pit doesn't page by hand. Each article keeps its ID, `created_at` (UTC), headline, summary, symbols, source and URL; full content isn't fetched. No articles gives an empty list, not an error (M3 turns it into a neutral signal).

**Cache**

- **M1-FR-15** Fetched data is stored as Parquet under `data_cache_dir`, one file per dataset and symbol, with the window it covers and the last date it's complete through. Each price row records its source, so rows from yfinance and from the backup can share one file. Prices are stored raw with their split events, so stored data never changes after the fact.
- **M1-FR-16** A cache entry answers a request only if it covers the whole requested window and was fetched on a later New York date than `as_of` (so nothing for that window could still arrive). Otherwise the tool fetches only the missing part (never past the cutoff), merges it into the entry, and returns from that. A request entirely before an entry's window replaces the entry instead. Every hit, miss and source used is logged.

**Settings**

- **M1-FR-17** New settings, with the architecture's defaults: `data_cache_dir` (`data_cache`), `news_lookback_days` (7), `sec_max_requests_per_second` (10). `.env.example` lists them.

## 4. Non-functional requirements

- **M1-NFR-1 (no network in tests)** The automated suite uses recorded fixtures and fakes only; `pytest-socket` (M0) blocks anything else. The whole suite still runs in well under a minute.
- **M1-NFR-2 (types)** `bullpit.data` stays under mypy `strict` (already configured in M0); `clock.py` under the standard settings.
- **M1-NFR-3 (time)** Every timestamp (news `created_at`, session closes) is timezone-aware UTC. Session and filing dates are `date`s in Python signatures, and naive midnight `datetime64` columns in tables. Ruff's `DTZ` and wall-clock bans stay on.
- **M1-NFR-4 (network)** yfinance and SEC calls have a timeout (`http_timeout_seconds`). alpaca-py 0.44 offers no request timeout, so Alpaca calls rely on the SDK's own behaviour (patching its private session isn't worth the fragility). Every third-party error is wrapped in `DataUnavailable`, with the original chained.
- **M1-NFR-5 (platform)** Cache paths use `pathlib` and are safe on Windows for symbols such as `^VIX` and `BRK.B`; a cache write is atomic (write, then replace), so a crash can't leave a half-written file.

## 5. Interfaces

```python
# bullpit/clock.py
class Clock(Protocol):
    def as_of(self) -> date: ...
class LiveClock: ...                      # latest completed NYSE session
class SimClock:
    def __init__(self, as_of: date) -> None: ...

# bullpit/data/calendar.py
def is_session(day: date) -> bool: ...
def session_close(day: date) -> datetime: ...                 # UTC; the knowledge cutoff
def last_completed_session(moment: datetime) -> date: ...     # pure; LiveClock passes the wall clock
def lookback_start(as_of: date, sessions: int) -> date: ...

# bullpit/data/prices.py
@dataclass(frozen=True)
class PriceHistory:
    symbol: str
    as_of: date
    source: Literal["yfinance", "alpaca"]
    bars: pd.DataFrame        # index: session date (naive DatetimeIndex); columns open, high, low, close, volume (float)

@dataclass(frozen=True)
class MarketContextData:
    spy: PriceHistory
    vix: PriceHistory

def get_prices(symbol: str, as_of: date, sessions: int, *, settings: Settings) -> PriceHistory: ...
def get_market_context(as_of: date, sessions: int, *, settings: Settings) -> MarketContextData: ...

# bullpit/data/sec.py
@dataclass(frozen=True)
class SecFacts:
    ticker: str
    cik: int
    as_of: date
    facts: pd.DataFrame       # taxonomy, tag, unit, start, end, value, fy, fp, form, filed, accn

def sec_user_agent(settings: Settings) -> str: ...
def get_cik(ticker: str, *, settings: Settings) -> int: ...
def get_sec_facts(ticker: str, as_of: date, *, settings: Settings) -> SecFacts: ...

# bullpit/data/news.py
class NewsArticle(BaseModel, frozen=True):
    id: int
    created_at: datetime      # UTC
    headline: str
    summary: str
    symbols: list[str]
    source: str
    url: str | None

def get_news(symbol: str, as_of: date, *, settings: Settings) -> list[NewsArticle]: ...
```

Bars and facts are plain float tables. Indicator maths may use floats (dev-plan §2.2). Converting to `Decimal` happens at the boundary into sizing (M4). News articles are Pydantic models because they go into prompts and graph state.

Errors: `DataUnavailable` (no data, unknown ticker, source failure after the backup), `LookaheadViolation` (undated row), `ConfigError` (`SimClock` given a non-session). All exist since M0.

## 6. Acceptance criteria

Automated tests only where dev-plan §7 requires them (the date guard, point-in-time correctness, the calendar the guard depends on, plus one happy-path test per data tool). Everything else is checked by hand, with the evidence pasted in `task.md`.

| AC | Criterion | Verified by |
|---|---|---|
| **M1-AC-1** | For every tool, with fake sources returning rows on both sides of the cutoff, no returned row is later than the cutoff, both for `as_of` = 2024-06-07 and for random session dates | **Automated:** unit test + one hypothesis property test |
| **M1-AC-2** | A later-than-cutoff row injected into a source response, or written into a cache file, is dropped and logged, never returned; an undated row raises `LookaheadViolation` | **Automated** |
| **M1-AC-3** | An SEC fact whose period ends before `as_of` but that was filed after it is excluded, and a restated fact returns the latest value filed on or before `as_of` | **Automated** (SEC fixture) |
| **M1-AC-4** | A second identical request makes no network call (a cache hit in the log) | Manual (C12): log excerpt |
| **M1-AC-5** | With yfinance forced to fail, prices come from Alpaca, the result and log say `alpaca`, and the prices match the yfinance ones for the same `as_of` to within rounding | Manual (C12): output pasted |
| **M1-AC-6** | The calendar is right on known dates: weekends; Good Friday 2024-03-29 and Thanksgiving 2024-11-28 closed; early closes on 2024-07-03 and 2024-11-29 at 13:00 New York; normal closes either side of the March 2024 DST change; `last_completed_session` just before and just after a close | **Automated** (small parametrised test) |
| **M1-AC-7** | SEC requests carry the configured User-Agent and never go faster than the configured rate | Manual (C12): log excerpt |
| **M1-AC-8** | The default test suite makes no network call and runs in under about a minute | `uv run pytest` green locally and in CI, with `pytest-socket` active |
| **M1-AC-9** | Point-in-time prices: on an NVDA fixture spanning its 10:1 split (ex-date 2024-06-10), `as_of` = 2024-06-07 returns pre-split prices (close about 1,208.88); `as_of` = 2024-06-11 returns the whole window split-adjusted (2024-06-07 close about 120.89); dividends aren't adjusted; yfinance-shaped and Alpaca-shaped fixtures give the same result | **Automated** |
| **M1-AC-10** | Each tool parses a recorded real response correctly (prices, market context, SEC facts, news) | **Automated:** one happy-path test per tool (dev-plan §7.2) |
| **M1-AC-11** | Against the real services, by hand: each tool returns data for AAPL at a recent session and at 2024-07-12, and an AAPL news window with more than 50 articles comes back complete (paging); SPY and `^VIX` return bars; SPY and an unknown ticker raise `DataUnavailable` from `get_sec_facts` | Manual (C13): output pasted |

AC-1 to AC-8 carry over the dev-plan's draft criteria. AC-9 to AC-11 cover in-scope items the drafts didn't test.

## 7. Decisions made in this document

Low-stakes choices I made so M1 isn't blocked. D-M1-2 decides what "look-ahead-free prices" means; the owner approved it with this document.

| # | Decision | Reason |
|---|---|---|
| D-M1-1 | `as_of` is a session **date**; its knowledge cutoff is that session's close (FR-4). SEC facts use `filed` ≤ `as_of`, as the architecture words it (Part 6) | companyfacts has only a filing date, no time. The small leftover (a filing made between the close and 17:30 on `as_of` counts) isn't look-ahead in practice: a backtest enters at the **next** open, after that filing was public, and a live request run that evening sees the same filing |
| D-M1-2 | **Point-in-time prices**: splits on or before `as_of` applied, splits after it undone, no dividend adjustment. Stored raw, adjusted per request. Recorded as **ADR-0003** in the plan gate (findings C3) | yfinance's default (`auto_adjust=True`) and even its "unadjusted" `Close` bake in splits and dividends from after `as_of` (checked on NVDA on 2026-09-28: close about $120.89 on 2024-06-07, when it actually traded at about $1,208.88). That's future information, and it makes a cached history differ from a fresh one. Raw prices plus split events never change after the fact, and give the same prices the market and the broker actually showed |
| D-M1-3 | Alpaca backup uses the **SIP** feed with `adjustment=raw`, and split events from Alpaca's corporate-actions endpoint | Checked on 2026-09-28: the free plan returns SIP daily bars for 2024 (findings A12 left the feed open). Raw bars plus splits go through the same point-in-time function as yfinance |
| D-M1-4 | Cache hit rule is "covers the window **and** fetched on a later New York date than `as_of`" (FR-16) | One rule that's safe for all three sources: a same-day fetch may still be missing that day's late filings or news, so it isn't trusted for that `as_of` |
| D-M1-5 | Dropped rows are logged and the request continues; only undated rows raise (FR-6, FR-7) | A later row can be proven unsafe and removed, so dropping it is enough; it comes from the cache (expected), from SEC (no request filter), or from a source ignoring the request filter (a warning worth seeing). A row that can't be dated can't be proven either way, so it must stop loudly |
| D-M1-6 | `get_market_context` lives in `data/prices.py`, not a separate `data/market_context.py` | It's two calls to the price path. A one-function module is against CLAUDE.md; this doesn't change behaviour |
| D-M1-7 | Ticker to CIK uses SEC's **current** map; the map is refetched once on a miss | The backtest window starts 2024-07-01, so ticker reuse since then is unlikely; a point-in-time ticker history would be a data project of its own. Noted as a known limitation |
| D-M1-8 | News uses `created_at`, not `updated_at`, and fetches no article content | An article published before `as_of` is known at `as_of`. Later edits to its text are a small leftover risk, accepted and noted. Headline and summary keep prompts inside the 8K-token limit |
| D-M1-9 | New dependencies: `pandas`, `pyarrow`, `pandas-market-calendars` (runtime); `hypothesis` (dev). `plan.md` confirms each against pandas 3 and mypy strict, and names `pandas-stubs` if strict typing needs it | Named here so no dependency arrives unannounced (CLAUDE.md) |

## 8. Open questions for the owner

None.
