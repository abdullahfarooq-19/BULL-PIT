# ADR-0006: Backtest stock selection

| | |
|---|---|
| **Status** | Accepted (owner reads it at M6 acceptance, M6-AC-10) |
| **Date** | 2026-09-29 |
| **Milestone** | M6 ([specs-plan FR-17, Q2](../milestones/M6-backtest/specs-plan.md#8-open-questions-for-the-owner); dev-plan C5, Q10a) |

## Context

Architecture §10 asks for backtest stocks chosen by "a rule that uses only information from the start date", because picking stocks we know did well is survivorship bias. Dev-plan C5 says the rule and its result go in an ADR, with no selection code. Q10a excludes tickers priced above the per-stock cap (10% of $100,000, so one share must cost under $10,000).

## Decision

**Rule.** Take the three largest S&P 500 sectors by index weight. In each, take the largest company by market capitalisation at the close of **2024-06-28**, the last session before the start (2024-07-01). It must pass the request check on 2024-07-01 (tradable on Alpaca, SEC filings, at least 60 sessions of prices), cost under $10,000 a share, and have no stock split in 2024-07-01 to 2024-12-31 (ADR-0005 stops a run at a split). If it fails, the next largest is taken.

**Chosen stocks**, in the order of their sectors' size. The first is M6's real run (M6-AC-6) and M7's run uses all three, with seed 1:

| # | Sector | Stock | Ticker to type |
|---|---|---|---|
| 1 | Information Technology | Microsoft | `MSFT` |
| 2 | Financials | Berkshire Hathaway, class B | `BRK.B` |
| 3 | Health Care | Eli Lilly | `LLY` |

**Sectors.** Information Technology, Financials, Health Care were about 30%, 13% and 12.5% of the index in March 2024 ([SoFi's guide to S&P 500 sector weights](https://www.sofi.com/learn/content/sp-500-sectors/), the closest dated figures found). **The exact weights at 2024-06-28 could not be retrieved** (S&P's factsheet isn't public for that date, and the searches returned nothing for it). The rule only needs which three sectors lead, and the first (Information Technology) leads by a wide margin. The fourth sector's weight wasn't retrieved either; from general knowledge it was about 10% at mid-2024, a couple of points behind, but that is **not verified here**. Accepted as a limit of this ADR, for the owner to check when reading it.

**Market caps at 2024-06-28.** Closing price (raw, from the project's price layer at `as_of` 2024-06-28) times the shares outstanding on the latest SEC cover page filed on or before that date (`dei:EntityCommonStockSharesOutstanding`):

| Sector | Company | Close | Shares | Market cap |
|---|---|---|---|---|
| IT | **Microsoft** | 446.95 | 7.432B (10-Q, filed 2024-04-25) | **$3.32T** |
| IT | Apple | 210.62 | 15.334B (2024-05-03) | $3.23T |
| IT | Nvidia | 123.54 | 24.6B (2.46B in the filing of 2024-05-29, before the 10-for-1 split of 2024-06-10) | $3.04T |
| IT | Broadcom | 1,605.53 | 0.465B (2024-06-13) | $0.75T |
| Financials | **Berkshire Hathaway** | 406.80 (B) | class A and B counts aren't in the flat SEC facts; about 0.87T from the class A price near $610,000 and about 1.43M A-equivalent shares | **about $0.87T (estimate)** |
| Financials | JPMorgan | 202.26 | 2.872B (2024-05-01) | $0.58T |
| Health Care | **Eli Lilly** | 905.38 | 0.950B (2024-04-30) | **$0.86T** |
| Health Care | UnitedHealth | 509.26 | 0.920B (2024-05-09) | $0.47T |

Visa and Mastercard (Financials) and Johnson & Johnson, AbbVie (Health Care) were also checked and are smaller than the winners. Berkshire's figure is an estimate, but the margin over JPMorgan (about 50%) is far beyond its error.

**Checks on the chosen stocks** (run 2026-09-29 through the project's data layer and Alpaca):

- No split in 2024-07-01 to 2024-12-31 for `MSFT`, `BRK.B` or `LLY`. Broadcom (not chosen) has a 10-for-1 split on 2024-07-15.
- Every price is far under $10,000 (`BRK.B` about $405).
- Alpaca returns each as tradable and active; SEC filings and 300 sessions of prices load for each (checked for `BRK.B` on 2024-07-01).

## Consequences

- **Type `BRK.B`, not `BRK-B`.** Alpaca knows the class B share only as `BRK.B` (`BRK-B` is "not found" there, so `bullpit backtest` would refuse it). SEC and yfinance accept the dotted form through their own normalisation. It has to be spelled that way in every command.
- The three stocks are large, long-listed companies, so today's asset lookup (D-M6-14) is valid across the window.
- The stocks are chosen once and reused (M7's repeat runs, headline run), so results across runs are comparable. Surviving large caps are still a survivorship-friendly universe by nature; the report should say so.
- Sector weights and Berkshire's market cap are not exact for the date. Nothing depends on them beyond the ranking and the 50% margin.
