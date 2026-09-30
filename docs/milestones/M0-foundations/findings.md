# M0 — External-services verification: findings

| | |
|---|---|
| **Date** | 2026-09-28 |
| **Source** | Runs of `scripts/spikes/*.py`; raw JSON in `scripts/spikes/output/` (git-ignored) |
| **Scope** | Assumptions A1-A16 from [`specs-plan.md` §11.2](specs-plan.md#112-assumptions-to-verify) |

No keys, account IDs or the SEC contact email appear below (M0-FR-21).

---

## Groq

| ID | Assumption | Observed | Verdict | Evidence | Affects |
|---|---|---|---|---|---|
| A1 | Both pinned models served on this key | `openai/gpt-oss-20b` and `openai/gpt-oss-120b` both listed by `GET /openai/v1/models` | **Confirmed** | `groq_models.py`, `a1_models_served` | M2 |
| A2 | Free-tier limits: 30 RPM, 1K RPD, 8K TPM, 200K TPD per model | Response headers (small model): `x-ratelimit-limit-requests: 1000`, `x-ratelimit-limit-tokens: 8000`. RPD and TPM match exactly. RPM and TPD aren't exposed as separate headers (Groq reports daily requests and per-minute tokens only) | **Confirmed** (RPD, TPM); **not directly observable** (RPM, TPD — no header carries them; taken on faith from the architecture's own stated figures) | `groq_models.py`, `a2_rate_limit_headers` (direct httpx call; litellm doesn't surface response headers) | M2, M6, M7 |
| A3 | JSON mode and JSON-schema (strict) both work | Both returned exactly the requested shape (`{"direction":"bullish","confidence":0.5}`) on the small model | **Confirmed** | `a3_json_object_small`, `a3_json_schema_small` | M2 |
| A4 | `reasoning_effort` accepted (low/medium), changes reasoning-token use | `low`: 9 reasoning tokens; `medium`: 41-43 reasoning tokens (small model, same prompt, two runs). Large model at `low`: 13-16 reasoning tokens | **Confirmed** | `a4_low_small`, `a4_medium_small`, `a4_low_large` | M2 |
| A5 | Reasoning tokens reported in usage; a small output cap can starve content | `completion_tokens_details.reasoning_tokens` present on every call. With `max_tokens=5`: `completion_tokens=5`, `reasoning_tokens=3`, **content was empty** — the model spent its whole cap on reasoning tokens and never emitted the answer | **Confirmed, and the risk is real** | `a5_small_max_tokens` | M2 (per-call ceiling and output-token budgeting must leave real headroom past reasoning) |
| A6 | `seed` and `temperature` accepted | Call succeeded with `seed=42, temperature=0.0`, normal reply | **Confirmed** | `a6_seed_temperature` | M2 |

Total tokens spent across all Groq spike calls: **1,143** (well under the 10K budget, NFR-7).

## Alpaca

| ID | Assumption | Observed | Verdict | Evidence | Affects |
|---|---|---|---|---|---|
| A7 | Whole shares required; exits persist with a suitable `time_in_force`; leg prices validated against a reference price | Fractional qty (0.5) rejected: `"fractional orders must be simple orders"`. Inverted exits rejected: `"take_profit.limit_price must be > stop_loss.stop_price"`. A real 1-share GTC bracket on F filled at $12.57; both legs (take-profit `NEW` at $13.19, stop-loss `HELD` at $11.94) came back **identical** on `inspect` the next morning, after a full overnight close — neither leg was dropped, altered, or needed resubmitting | **Confirmed**: whole shares required, leg prices validated against the reference price, and GTC legs persist unchanged across the overnight close | `alpaca_bracket_validate.json`, `alpaca_bracket_place.json`, `alpaca_bracket_inspect.json` | M8 (ADR-0002) |
| A8 | A reused `client_order_id` is rejected | Re-submitting `client_order_id=spike-m0-f-1` immediately after the fill was rejected outright: `{"code":40010001,"message":"client_order_id must be unique"}` | **Confirmed** | `alpaca_bracket_place.json` | M8 |
| A9 | Orders placed while the market is closed wait for the next open | The GTC bracket above was accepted while the market was closed; both legs came back `HELD` (not rejected, not immediately routed) | **Confirmed** | `alpaca_bracket_validate.json` | M8 |
| A10 | News history back to 2015; enough articles per reference ticker per week; free-plan rate limit | Earliest AAPL article: **2015-01-01**. July 2024 week (Jul 8-12) counts: AAPL 50 (page-limit-capped), MSFT 49, JPM 18, XOM 8, JNJ 5. Recent week: AAPL 50, MSFT 50, JPM 13, XOM 10, JNJ 6. `limit` caps a single response at up to 50 — pagination (`page_token`) is needed for tickers with more than 50 articles in a window. No rate-limit error was hit across the ten calls made | **Confirmed reachable and back to 2015; XOM and JNJ are thin (5-10/week) — a real signal for M1's neutral-confidence-0 fallback design; pagination needed for busy tickers/weeks** | `alpaca_readonly.json`, `a10_news` | M1 (pagination), M3 (thin-news tickers) |
| A11 | Asset fields support the request check; ETFs distinguishable from stocks | AAPL and SPY (an ETF) both came back `tradable=True`, `status=ACTIVE`, `fractionable=True`, `asset_class=US_EQUITY`. **`asset_class` does *not* distinguish an ETF from a stock** — both are `US_EQUITY` | **Correction**: the request check cannot use `asset_class` to reject ETFs. This matches, and confirms, the dev plan's own design (M3 scope: "SEC filings exist (so ETFs are rejected)") — SEC EDGAR has no filings for SPY, so that check alone does the job. No new open question; recorded here so M3's spec states the reason explicitly | `alpaca_readonly.json`, `a11_assets` | M3 (specs.md should say explicitly: ETF rejection relies on the SEC-filings check, not `asset_class`) |
| A12 | Daily bars work as a backup price source | 9 daily bars returned for AAPL, 2024-07-01 to 2024-07-12 (matches the 9 trading days in that range) | **Confirmed**. Which feed (IEX vs SIP) wasn't distinguishable from the response object in this call; the plan default was used | `alpaca_readonly.json`, `a12_backup_prices` | M1 |
| A13 | Account cash, equity, buying power; sizing must use cash | `cash = equity = 99435.53`; `buying_power = 397742.12` (4x); the account object's own `multiplier` field reads `"2"`, which doesn't match the 4x buying-power ratio observed — an Alpaca quirk, not investigated further since the decision (use cash, never buying power) already avoids depending on this field | **Confirmed**: cash and equity are equal (no open positions), buying power is inflated by margin as expected. D-M0-9 (use cash) stands | `alpaca_readonly.json`, `a13_account` | M4, M8 |

## SEC EDGAR

| ID | Assumption | Observed | Verdict | Evidence | Affects |
|---|---|---|---|---|---|
| A14 | companyfacts reachable with a proper User-Agent; facts carry `filed`, `fy`, `fp`, `form` | Apple's companyfacts returned 200 with `User-Agent: BullPit/0.1.0 <email>`. The `Revenues` tag's USD facts each carry `accn, end, filed, form, fp, frame, fy, start, val` | **Confirmed** | `sec_edgar.json`, `a14_companyfacts` | M1, M3 |
| A15 | Fair-access limit: 10 requests/second | SEC's published access page (redirected from `/os/accessing-edgar-data` to `/search-filings/edgar-search-assistance/accessing-edgar-data`, both 200) states the 10 req/s guidance; not load-tested (per plan) | **Confirmed** (policy text; not load-tested) | `sec_edgar.json`, `a15_fair_access_policy` | M1 |

## yfinance

| ID | Assumption | Observed | Verdict | Evidence | Affects |
|---|---|---|---|---|---|
| A16 | Daily bars for AAPL, SPY, `^VIX` from 2024-07-01; `auto_adjust` default | yfinance **1.7.0**. All three tickers returned 9 daily bars for 2024-07-01..2024-07-12. `auto_adjust` **defaults to `True`** (adjusted `Close` differs from the unadjusted one) | **Confirmed reachable; default is adjusted prices**, which M1's price-adjustment ADR must account for explicitly | `yfinance_check.json` | M1 |

---

## Corrections raised as open questions

| # | For milestone | Question |
|---|---|---|
| C1 | M3 | The request check can't use Alpaca's `asset_class` field to reject ETFs (A11) — it already plans to rely on "no SEC filings" instead (dev-plan M3 scope), so `specs.md` should state this explicitly as the reason, not as a fallback |
| C2 | M1 | News pagination (`page_token`) is needed for any ticker/week with more than 50 Alpaca news articles (A10); `data/news.py`'s design should page through results rather than assume one page is enough — **Answered:** M1-FR-14; alpaca-py 0.44 already follows `next_page_token` when no `limit` is set, verified live on 2026-09-28 with an AAPL week of 59 articles (M1-T-10, AC-11) |
| C3 | M1 | yfinance's `auto_adjust` defaults to `True` (A16); the adjustment-policy ADR should say explicitly whether Bull Pit keeps that default or requests unadjusted prices, and why — **Answered:** ADR-0003 (point-in-time prices): raw prices stored, split-adjusted only up to `as_of`, dividends never adjusted |
| C4 | M2 | A small `max_tokens` cap can silently starve visible content because reasoning tokens are drawn from the same budget (A5); the gateway's per-call ceiling and per-role `max_tokens` must leave headroom past the *measured* reasoning-token cost, not just the visible-answer length — **Answered:** every call sends `max_tokens = llm_output_allowance_tokens` (2000), and empty content counts as an invalid reply that triggers the validation retry and, on a second failure, the flagged safe default (M2-FR-4a). In JSON mode the starvation shows up as Groq rejecting the generation (`json_validate_failed`, "max completion tokens reached"), which the gateway handles the same way (M2-FR-10, specs-plan §7.2 R11). M2-AC-7's real measurement (`measure_tokens.py`) found 55-59 reasoning tokens per call at `low` effort on a full analyst-shaped prompt, far inside the 2000 allowance |

## Final outcome (M0-T-18)

The spike's test position was closed 2026-09-30, market open: the
take-profit leg was cancelled and the share sold at market, filling
immediately at **$12.17**. Entry was $12.57, so the round trip realised a
loss of $0.40/share ($0.40 total on 1 share) -- closed manually, well
inside the stop ($11.94) and take-profit ($13.19) band, neither of which
triggered. Position confirmed flat and no open orders remain on F
afterwards. This is the spike's only real trade; it exercised the manual
market-sell path, not the stop or target legs.
