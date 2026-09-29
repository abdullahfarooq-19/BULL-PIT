# M5 — Report generator: tasks

| | |
|---|---|
| **Status** | T-1 to T-11 done and T-12's README and retrospective written (2026-09-29); waiting for the owner's acceptance, then push, CI, merge and tag `m5` |
| **Date** | 2026-09-29 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (reviewed and corrected 2026-09-29, §7.1; necessary testing, D-M5-11) |
| **Branch** | `m5-report`, from `master` **after M4 is merged and tagged `m4`** (M4-T-15) |

Each task is about half a day or less, is one commit when the owner asks for commits (CLAUDE.md), and is ticked only when its check passes. **Code and its tests land in the same task.** After every task, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` ("four checks") are clean, and the diff has been re-read for anything the task doesn't need.

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | M5-T-1 | **Docs and branch.** Check that M4 is merged into `master` and tagged `m4`; if not, stop and ask the owner. Create `m5-report` from `master`. Commit `specs-plan.md`, this file, and dev-plan's status line (M5 in progress) | `docs/milestones/M5-report/*`, `docs/dev-plan.md` | DoR §1.4 | Branch exists; docs committed | f0ce22a |
| [x] | M5-T-2 | **Settings, reply schema, shared SMA.** Add `vix_low_threshold` (15.0) and `vix_high_threshold` (25.0) to `config.py` and `.env.example`, plus their defaults in `test_config.py`. Add `ReportProse` to `llm/schemas.py`. Rename `tools.indicators._sma` to public `sma` (callers updated, no behaviour change) | `bullpit/config.py`, `.env.example`, `tests/test_config.py`, `bullpit/llm/schemas.py`, `bullpit/tools/indicators.py` | FR-13; D-M5-6, D-M5-7; AC-6 (defaults) | Four checks clean; `test_indicators.py` unchanged and passing | e8950f7 |
| [x] | M5-T-3 | **Number check.** Write `report/number_check.py` (§11.1): ID and ISO-date extraction, number tokens with units, the rounding and one-significant-digit rules, `allowed_numbers`, `check_text`, `mask_unknown_numbers`. Plus `test_number_check.py`: every AC-4 accept and reject case, `T99`, masking | `bullpit/report/number_check.py`, `tests/report/__init__.py`, `tests/report/test_number_check.py` | FR-6; D-M5-3; AC-4, AC-3 (check level) | `test_number_check.py` passes; module imports only the stdlib | e8950f7 |
| [x] | M5-T-4 | **Report model.** Write `report/model.py` (`Report`, `DebateSummary`, `AttemptRow`, `MarketContext`, `DataNotes`, `ReportOutcome`, `ProseSource`; §5) and add `RequestState.report` | `bullpit/report/model.py`, `bullpit/state.py` | FR-1, FR-2; D-M5-9; NFR-4 | Four checks clean; `report/model.py` imports only `domain` and `llm/schemas` | e8950f7 |
| [x] | M5-T-5 | **Builder (pure) and Markdown.** In `report/builder.py`: `market_context` with the explanation table (§11.2), `build_report` with the FR-1 section rules, FR-2 reason split and quote masking (§11.5), `fallback_prose` (§11.3), `render_markdown` (§11.4) over `report/templates/report.md`. Plus `test_builder.py`: example card, sections per outcome, traceability, market context | `bullpit/report/builder.py`, `bullpit/report/templates/report.md`, `tests/report/test_builder.py` | FR-1 to FR-4; D-M5-7, D-M5-8, D-M5-12, D-M5-13; AC-1, AC-2 (auto), AC-5, AC-6 | `test_builder.py` passes | e8950f7 |
| [x] | M5-T-6 | **Writing step.** Write `llm/prompts/report.md` (§9.5; first line `You are the report writer`; `rejected` section) and `report_node` in `builder.py` (§9.3 steps 2–6: masked transcript, first call, check, one retry naming the rejected tokens, fallback on a second failure, a flagged reply, `LLMUnavailable` or `PromptTooLarge`). Plus `test_report_node.py` and the `report.md` case in `test_prompts.py` (render and worst-case ceiling) | `bullpit/llm/prompts/report.md`, `bullpit/report/builder.py`, `tests/report/test_report_node.py`, `tests/llm/test_prompts.py` | FR-5, FR-7, FR-9; D-M5-2, D-M5-4, D-M5-5; NFR-2; AC-3, AC-10 (ceiling) | Both test files pass | e8950f7 |
| [x] | M5-T-7 | **Graph.** Add `_report_node` in `graph.py` (market-context fetch through `get_market_context`, the `DataUnavailable` fallback and warning, skipped for rejections; `utc_now()` for the report time). Every router that returned `END` now returns `"report"`; `report → END`. Give `RecordingLLM` in `test_graph.py` a default `report.md` reply (clean, cites `T1`) so the existing graph tests keep passing. **Note:** `test_graph.py`'s `_patch_prices()` fake ignores the requested symbol and always returns the AAPL fixture (85 sessions, April–July 2024), so SPY's mocked history is also under 200 sessions there — `market.spy_above` comes back `None` in every graph test by construction, not by a new fixture. That's expected and needs no new fixture; `report/test_builder.py` (T-5) is where the 200-and-more-session case is actually exercised, with a synthetic close series | `bullpit/graph.py`, `tests/test_graph.py` | FR-4, FR-8, FR-9; D-M5-1; NFR-5 | Four checks clean; every existing graph test passes | 2621d53 |
| [x] | M5-T-8 | **Journal and runner.** Add `ReportRecord` (§10), migration `0004_reports`, and the `reports` row in `_finalize` (same transaction) | `bullpit/journal/models.py`, `bullpit/journal/migrations/versions/0004_reports.py`, `bullpit/runners/request.py` | FR-10, FR-12; D-M5-10; AC-9 | `test_migrations.py` passes with no schema diff after `0001`–`0004` | 2621d53 |
| [x] | M5-T-9 | **CLI.** `bullpit request` prints `=== REPORT ===` and `render_markdown(result.report)` after the M4 output. Add the buy-with-report case to `test_cli.py` | `bullpit/cli.py`, `tests/test_cli.py` | FR-11; AC-10 | `test_cli.py` passes | 2621d53 |
| [x] | M5-T-10 | **Graph tests.** Existing path tests each check `state.report` and one `reports` row. New: a request-check rejection (no LLM call, report `rejected`, no market fetch); `LLMUnavailable` on `report.md` (fallback, `completed`); `QuotaExhausted` on `report.md` (`failed`, lock released) | `tests/test_graph.py` | AC-8 | All graph tests pass; whole suite under a minute | 2621d53 |
| [x] | M5-T-11 | **Real runs, tracing, tokens.** Run `bullpit request` for JPM and AAPL `--mode backtest --as-of 2024-10-18`, XOM `--as-of 2024-07-12`, and SPY. Read each report; trace every number of the JPM report by hand; record each `prose_source`. Measure per-request tokens per model (FR-14); update architecture §14 and add revision v2.3; re-derive `llm_output_allowance_tokens` (and `test_config.py` if it asserts it); re-run one request to confirm nothing is flagged. Paste the evidence below | `docs/architecture.md`, `bullpit/config.py`, `.env.example`, this file | AC-2, AC-7; FR-14; C14 | Evidence pasted; four checks clean | 2bd8b4f |
| [ ] | M5-T-12 | **Acceptance.** Add the report to the README quick start. Write the retrospective (tokens vs §14, `prose_source` rates, test count and suite time, carry-overs). Then, when the owner asks: push, CI green, merge to `master`, tag `m5` | `README.md`, this file | DoD §1.5 | Owner accepts | 2bd8b4f |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-5 |
| AC-2 | T-5, T-11 |
| AC-3 | T-3, T-6 |
| AC-4 | T-3 |
| AC-5 | T-5 |
| AC-6 | T-2, T-5 |
| AC-7 | T-11 |
| AC-8 | T-7, T-8, T-10 |
| AC-9 | T-8 |
| AC-10 | T-6, T-9 |

| Requirement | Task |
|---|---|
| FR-1 to FR-3 | T-4, T-5 |
| FR-4 | T-5, T-7 |
| FR-5 | T-6 |
| FR-6 | T-3 |
| FR-7 | T-6 |
| FR-8 | T-7 |
| FR-9 | T-6, T-7 |
| FR-10, FR-12 | T-8 |
| FR-11 | T-9 |
| FR-13 | T-2 |
| FR-14 | T-11 |

---

## Evidence

**AC-7 and AC-2: real runs on the pinned models (2026-09-29).** `bullpit doctor` first: all services OK. Then `bullpit request --mode backtest`:

| Request | Route | Outcome | `prose_source` |
|---|---|---|---|
| JPM 2024-10-18 | debate | no trade (trader: bull and bear convictions equal) | `llm` |
| AAPL 2024-10-18 | debate | no trade | `retry` (the first draft was rejected, the retry passed) |
| XOM 2024-07-12 | weak signals, no debate | no trade | `llm` |
| SPY 2024-10-18 | request check | rejected (ETF: no SEC filings); report `rejected`, no LLM call | `none` |
| NVDA 2024-10-18 | debate | **buy** 40 shares (Stage A 57, shrunk by the review) | `llm` |
| JPM 2024-10-04 and 2024-09-27, MSFT 2024-10-04, AMZN 2024-10-18 | debate | no trade | `llm` |

Across the 9 LLM-written reports: 8 first-time `llm`, 1 `retry`, 0 `fallback`, and no flagged call in `llm_calls`. JPM 2024-10-18 (M4's buy) and AAPL both came back as no trade this time, so several tickers had to be tried before one bought (NVDA). The trader's prompt differs from M4's first runs (its `decisive_evidence` fix, and the live account's cash and equity are in the prompt), which may explain it; not investigated.

**Reports read by hand.** The JPM, XOM and NVDA reports read clearly: the summary states the reason with valid evidence IDs, the debate points and the trader's quoted reasoning are faithful to the transcript, and the numbers in prose are the code's (`122.4%`, `36.8%`, `$30.04B`). In the trader's quoted reasoning, numbers the report doesn't contain show as `[?]` (JPM: "the board score is low ([?])", "a [?] equity limit"), which reads acceptably. One cosmetic bug found and fixed: the attempts list printed `No_trade` (the template now removes the underscore).

**AC-2 hand trace of the JPM 2024-10-18 report** (`20241018-JPM-dad0de3a`), against the journal and the price source:

| Report value | Source | Match |
|---|---|---|
| Confidence 0.42 | `recommendations.confidence` (attempt 1) | yes |
| Signals: technical neutral 0.55, fundamentals bullish 0.90, sentiment bullish 0.26 | `signals` rows (0.2581...) | yes |
| Convictions bull 0.70, bear 0.70; unsupported points 1 | `debate_turns` (round-2 convictions 0.7 / 0.7; one unsupported point in bull round 1) | yes |
| SPY $584.59 above its 200-day average $529.27 | `get_prices("SPY")` recomputed: last close 584.59, mean of the last 200 closes 529.27 | yes |
| VIX 18.03, normal (between 15 and 25) | `get_prices("^VIX")` last close 18.03 | yes |
| Models, 15 headlines, 10-Q filed 2024-08-02, price source yfinance | `data_notes` vs the sentiment `signals` row (15 evidence items) and the fundamentals evidence F5 | yes |
| T1 to T6, F1 to F5 evidence facts | Copied from the analysts' code-written evidence (`225.37`, RSI `70.1`, `$50.20B`, `+21.5%`...) | yes |

**Token measurement (FR-14), from `llm_calls`, a cached call counted at the tokens of the original call with the same `cache_key`** (input / output / reasoning):

| Request | Calls | Small model | Large model | Total |
|---|---|---|---|---|
| Buy, NVDA | 10 | 3,802 / 503 / 352 = 4,657 | 9,164 / 1,163 / 524 = 10,851 | 15,508 |
| No trade after debate, JPM | 9 | 3,852 / 560 / 115 = 4,527 | 8,394 / 1,270 / 551 = 10,215 | 14,742 |
| No trade after debate, AAPL (with a report retry) | 10 | 6,005 / 711 / 406 = 7,122 | 7,927 / 998 / 444 = 9,369 | 16,491 |
| Weak signals, XOM | 4 | 2,312 / 325 / 149 = 2,786 | none | 2,786 |

By step (NVDA buy): analysts about 2.0K (small); debate about 7.1K, trader 2.4K and review 1.3K (large); report 2.7K (small). The `report.md` call itself, over 9 real calls: 1,197 to 2,538 input, at most 274 output plus reasoning. A debated request costs about 15K in total against §14's earlier 25 to 30K estimate. Architecture §14 is updated with these numbers (revision v2.3).

**Allowance re-derivation (FR-14).** The largest output plus reasoning over every real call of the **current** template versions is 610 (`bull.md`, AMZN: 194 + 416); `report.md` is at most 274. M2's `measurement_probe.md` and superseded template versions are left out, as in M4 (an older `sentiment.md`, `bfbc5755f890`, reached 623 before M3 changed it). `3 x 610 = 1830`, above the 500 floor, so `llm_output_allowance_tokens` moves from M4's 1743 to **1830**. Ceiling check: the largest real prompt is 4,533 tokens (`trader.md`), so 4,533 + 1,830 = 6,363, under the 8,000 limit; `test_prompts.py` still passes with the new value. Re-ran NVDA 2024-10-18: 10 calls, 0 flagged, `prose_source` `llm`.

## Retrospective

**What changed from the plan.** Scope did not change. Four small spec corrections, found while implementing:

- **AC-4's `$226` example was wrong arithmetic.** 225.37 rounds to 225, not 226. D-M5-3's rule (round half up, never more precise) is right and the code follows it; `$225` is now the accept case and `$226` a reject case. Corrected in `specs-plan.md` (AC-4, D-M5-3, §11.1).
- **`fallback_prose(report, debate)` takes the debate turns.** §5's signature had only the report, but §11.3's fallback names the evidence IDs each side cited, and the report doesn't hold them.
- **Fallback "conceded" sentence has no count.** §11.3's "The bull conceded {n} point(s)" would put a number that may not be in the report into a sentence that must pass the check by construction. It now says the bull "made concessions" or "made no concessions".
- **`report_node` takes `generated_at`.** The graph passes `utc_now()` (T-7), so the node stays free of wall-clock reads.

**Measured numbers.** See Evidence. A debated request is about 15K tokens (10 to 11K large), against §14's 25 to 30K. The allowance moved 1743 to 1830 because a bull call on AMZN used 610 output and reasoning tokens. The M5 report call adds about 2.5K small-model tokens and never came close to the ceiling.

**`prose_source` rates.** 8 of 9 LLM-written reports were accepted first time, 1 needed the retry, 0 fell back. Too few runs to say how often the small model adds a number; the retry path worked on its one real occurrence.

**Test count and suite time.** 220 automated tests (up from M4's 168: the number check, builder and report node in `tests/report/`, the report prompt, the graph, CLI, config), full suite in about 13 to 26 s locally. Testing followed dev-plan §7 (D-M5-11): one test per behaviour, plus accept and reject cases for the number check.

**Carry-overs.**

**Fixed in the pre-merge review.** (1) A fallback warning names the rejected tokens, and it was added to the state before the final masking, so a token the writer invented twice would have unmasked the same number in the trader's or reviewer's quoted text; the warning is now added after masking (regression test in `test_report_node.py`). (2) After a review shrink, section 6 said "Size set by the target limit" beside a smaller final order; it now reads "Stage A size set by the target limit; the risk review shrank it to 40 shares." (3) AC-6's `DataUnavailable` path had no automated test; one graph test added.

- `Report.generated_at` is wall-clock time. M6-AC-4 ("exactly the same journal" after a resume) must compare journals without wall-clock fields, like `requests.created_at`.
- The loss warning shows "not available" until M6 and M8 feed it equity history (D-M4-9, C16).
- The number check's allowed set is the report itself, so every number shown there is allowed as a plain number, including small integers ("200-day", `gpt-oss-20b`) and numbers inside code-shown text that isn't code-written: news headlines and data warnings. One M4 warning quotes LLM output verbatim ("trader decisive evidence dropped (not registered): ..."); since M4's `trader.md` fix these are IDs, but if it ever carries a number, that number is shown unmasked and allowed. M4 code, so out of M5's scope; worth masking when M8 touches warnings.
- `bullpit request` prints the report only for requests that passed the request check; a rejected request prints its `REJECTED:` line and exits 1 as before (the rejected report is in the journal).
- Buys were rare in these runs (2 of 9 debated requests, both NVDA), so M7 should not assume they are common; the measured cost per request (about 15K, not 25 to 30K) lets Q11's repeat-run scope be revisited then.
