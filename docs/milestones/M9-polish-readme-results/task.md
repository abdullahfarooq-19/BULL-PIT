# M9 — Dashboard polish, README, results write-up: tasks

| | |
|---|---|
| **Status** | **Accepted by the owner 2026-10-14, merged to `master` and tagged `m9`, with the exceptions listed in the Retrospective.** Written 2026-10-12 after the owner approved [`specs-plan.md`](specs-plan.md) revision 1 ("specs plan is approved write the task.md and complete the M9"). Q1 to Q6 take the recommended answers (the owner gave none): Q1 = A, Q2 = A, Q3 = A, Q4 = A, Q5 = A, Q6 = B (crop) or leave out |
| **Date** | 2026-10-12 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (revision 1; necessary testing, dev-plan §7) |
| **Branch** | `m9-polish-readme-results`, from `master` (`d2a382c`) |

Each task is about half a day or less and is one commit when the owner asks for commits (CLAUDE.md). It is ticked only when its check passes. After every task that touches code, the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit`, `uv run pytest`) are clean, and for web changes `npm run lint` and `npm run build` too. The diff is re-read for anything the task doesn't need. M9 changes no behaviour (D-M9-2). **Steps marked ◆ need the owner or a real service.**

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [x] | M9-T-1 | **Documents.** `dev-plan.md`: status line, revision 11 (status only), §4 M11.3 row and M9 state, §5 M11.3 section. Stale state fixed: `M8/task.md` (T-12 and the "not done yet" heading point to the acceptance note), `M11.2/task.md` status, `M11.3/specs-plan.md` built/deferred note, `M11.4/specs-plan.md` merge, tag and retrospective line. The §11.8 table filled in this file | `docs/dev-plan.md`, milestone docs | FR-12; AC-2 | Every row of the Documents check below has its link and no stale status | 5bb1daa, be50a41 |
| [x] | M9-T-2 ◆ | **Hand pass and issue log.** The owner goes through Account & Wallet, Trades History, Portfolio and the report page (normal, API stopped, empty journal, keyboard only, narrow window; a buy, a no-trade, a pending limit order). Issues go in the Issues table below with a severity | this file | FR-1; AC-3 | The owner has confirmed the list | |
| [x] | M9-T-3 | **Fixes.** One issue per commit, P1 and P2 first; a trivial P3 only if it changes no behaviour. A bug in the §7.1 categories gets one regression test | `bullpit/**`, `web/src/**`, `tests/**` | FR-2 to FR-4; AC-8 | Issues table has no open P1 or P2 (or an owner-accepted exception); four checks clean | none needed |
| [x] | M9-T-4 | **Dependency audit and `.env.example`.** Import check of every direct dependency (Python and web), `uvx pip-audit`, `npm audit`, comparison of `.env.example` with the variables `config.py` reads. Output pasted below | `pyproject.toml`, `uv.lock`, `web/package*.json`, `.env.example` (only if needed) | FR-11, FR-15; AC-6, AC-7 | Output pasted; unused dependencies removed; four checks and web build clean | 5bb1daa |
| [x] | M9-T-5 | **Dead code and clutter sweep** ([specs-plan §11.4](specs-plan.md#114-dead-code-and-clutter-sweep)) | `bullpit/**`, `web/src/**`, `tests/**` | FR-10; AC-6 | Output pasted; nothing unused left; four checks and web build clean | 5bb1daa |
| [x] | M9-T-6 | **README rewrite** to [specs-plan §11.2](specs-plan.md#112-readme-outline): diagram, screenshots, quick start, results excerpt, project tree, links. The risk-manager screenshot per Q6 | `README.md`, `docs/images/*` | FR-5 to FR-8; AC-4 | Link check output pasted | be50a41 |
| [ ] | M9-T-7 ◆ | **Market session (optional, Q2 = A).** 1-share AC-13 probe, ADR-0007 addendum, a restart with a real waiting report, a small approved buy closed by hand. Evidence below | `docs/adr/0007-exit-anchoring.md`, `M8/task.md`, this file | M8 carry-overs | Evidence pasted, or recorded as still an accepted exception | |
| [x] | M9-T-8 | **Live track record and final status docs** ([specs-plan §11.6](specs-plan.md#116-live-track-record-snapshot)): the README section, `progress.md`, `system-walkthrough.md` | `README.md`, `docs/progress.md`, `docs/system-walkthrough.md` | FR-9, FR-13, FR-14; AC-5 | Numbers match the screen; owner reads the wording | be50a41 |
| [ ] | M9-T-9 | **History secret scan, then the dry run** ([§11.7](specs-plan.md#117-history-secret-scan), [§11.3](specs-plan.md#113-readme-dry-run)) on the final README | this file | FR-16, FR-18; AC-1, AC-3 | Scan clean; dry run recorded; a second person's run if Q4 = A | |
| [ ] | M9-T-10 ◆ | **Push and CI,** only when the owner asks: `master` and the tags to `origin`; read the CI result; fix forward until `check`, `secrets` and `web` are green | this file | FR-17; AC-3 | Three green jobs | |
| [x] | M9-T-11 ◆ | **Acceptance.** Retrospective below; the owner accepts; when asked, merge to `master` and tag `m9` | this file | DoD §1.5 | Owner accepts | |

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-6, T-9 |
| AC-2 | T-1 |
| AC-3 | T-2, T-3, T-9, T-10 |
| AC-4 | T-6 |
| AC-5 | T-8 |
| AC-6 | T-4, T-5 |
| AC-7 | T-4 |
| AC-8 | T-3 |

---

## Issues

Severity: P1 can lose money, leak the future, bypass an approval or the paper-only guard, or crash the main loop. P2 shows the owner a wrong or misleading number or text, loses a recorded fact, or blocks a page's main job. P3 is cosmetic or wording, with a workaround.

| ID | Page | What was seen | Severity | Decision |
|---|---|---|---|---|
| M9-I-1 | Report page, risk reviewer's reason | `[?]` appears where the reviewer's quoted reason held a number the code didn't write (real report, screenshot 2026-10-06). It is the number check's designed masking (D-M5-2), not a crash | P3 | **Accept (Q3 = A).** The README explains the `[?]`. A different display would change behaviour (a deviation) |
| M9-I-2 | Report page | Most debated reports carry the soft "N debate paragraphs are over 110 words" warning (M11.1 carry-over) | P3 | Listed, not fixed: changing the writer's prompt changes behaviour |
| M9-I-3 | Report page, sentiment facts | Headlines with relevance 0.00 (for example unrelated companies) are still listed as facts S1 to S6 | P3 | Listed, not fixed: M3's sentiment rule (the weight is 0, the list is code-written) |
| M9-I-4 | Backend, warnings | M5 carry-over: one M4 warning quotes LLM text; a number in it would show unmasked | P3 | Listed: per the M5 retrospective it has carried IDs only since M4's `trader.md` fix (not re-checked on a real report in M9) |
| M9-I-5 | Dashboard, owner's pass | The owner's own click-through of the four pages (keyboard only, narrow window, API stopped, empty journal) has **not** been recorded | closed | Closed 2026-10-14: the owner went through the dashboard and reported it clear; no notes or screenshots were pasted |
| M9-I-6 | `web/` dependencies | `npm audit` still reports high findings in the shadcn CLI's and `eslint-config-next`'s dev-time dependencies (`ts-morph`, `fast-glob`, `braces`, `micromatch`, `@next/eslint-plugin-next`); the only offered "fix" is a downgrade to shadcn 1.0.0 and eslint-config-next 14 | P3 | Accepted: nothing in the running dashboard or API uses them; the direct `next` advisories are fixed (16.4.0) |

No P1 or P2 issue was found, by this session's checks or by the owner's hand pass (2026-10-14).

## Evidence

**T-1 documents (2026-10-12).** `dev-plan.md` revision 11 (M11.3 row and section in §4 and §5, M9 pointer, `ValidationFailed` removed from §2.2's list). Stale states fixed: M0 (status and M0-T-25 ticked, accepted 2026-09-30, `953e1cb`), M5 (T-12 ticked, merged and tagged), M8 (T-12 ticked with a pointer to the Acceptance section), M11.2 (status), M11.3 and M11.4 (retrospectives added). Two broken anchors fixed (M8 and M11.1 specs-plans).

**T-4 dependency audit.**

- Python: every one of the 19 runtime and 7 dev dependencies is imported or used (`pytest-socket` through `--allow-hosts` in pytest's options; `pandas-stubs` by mypy). `uvx pip-audit` on the exported lockfile: **No known vulnerabilities found.**
- Web: every runtime dependency is imported in `web/src` (`shadcn` through `@import "shadcn/tailwind.css"`, so it stays). `npm audit` found 10 high findings. Fixed: `next` 16.3.7 to 16.4.0 and `eslint-config-next` to 16.4.0 (exact pins), plus `npm audit fix` for the lockfile; `npm run lint`, `npm run build` and `npm run gen:api` (no content change in `openapi.json` and `schema.d.ts`) all clean. Remaining 9 are dev-time transitive findings (issue M9-I-6).
- `.env.example` against `Settings`: no name missing either way (throwaway comparison script).

**T-5 sweep.** No `TODO`, `FIXME`, `XXX`, `print(` or `breakpoint(` in `bullpit/` or `web/src/`; no tracked `_old`, `_v2`, backup, scratch or demo file; tracked non-source files are the original design HTML, the spike scripts (kept, D-M9-15) and the generated OpenAPI files. A scratch script counted references of every top-level function and class in `bullpit/`: the only definition referenced once was `ValidationFailed` (never raised; **removed**); `eval_command` and `fill_check_command` are Typer commands. Three web components with no importer (`ui/badge.tsx`, `ui/popover.tsx`, `ui/scroll-area.tsx`) **removed**. After the removals: `ruff check`, `ruff format --check`, `mypy` (64 files) clean; **429 tests pass in 55 s**; web lint and build clean.

**T-6 README.** Rewritten to the outline of the specs-plan (§11.2): screenshots, one Mermaid diagram, quick start with prerequisites and where to get the keys, backtest, evaluation, results excerpt, live track record, live mode, safety, structure with links. Every CLI command in it exists (`bullpit --help`). Link check (a scratchpad script over `README.md`, `CLAUDE.md` and `docs/**/*.md`, anchors included): **611 links, 0 problems.** The risk-manager screenshot is left out (Q6; the file is untracked in `docs/images/`).

**T-7 market session, partly (2026-10-12, US market open, paper account).**

- **AC-13 probe, done.** A throwaway script submitted, through `AlpacaBroker.submit_bracket_order`, a 1-share **market** bracket on F (price $12.01) with the stop **above** the price ($12.37) and the take-profit $12.73. Alpaca rejected it at submission: HTTP 422, code 42210000, `stop_loss.stop_price must be <= base_price - 0.01` (`base_price` 12.0101). Nothing filled; a check afterwards found 0 open F orders and the positions CSCO 50 and GOOGL 15 only. Written up as ADR-0007's addendum.
- **AC-7 real half, already done by the owner:** the 1-share MSFT trade (in $517.90 on 2026-09-30) was closed by hand on 2026-10-08 at $529.13, recorded by the fill check as `closed`, exit reason `manual`, **+$11.23** (read from `GET /trades` on 2026-10-12).
- **Not done:** the restart check with a real waiting report (it needs a request that ends in a buy; buys are rare, about 2 in 9 debated requests in M5) and a stop or target firing on a real Bull Pit trade (AC-6 exit half). Both stay accepted exceptions (Q2).

**T-8 live track record.** Numbers read on 2026-10-12 from a temporary second API on port 8001 (stopped afterwards; the same endpoints the dashboard pages use): `GET /portfolio` gave approved 4, rejected 0, ongoing 2, closed 1, total profit $11.23, total loss $0, net $11.23; `GET /history` gave 22 analyses (12 no trade, 3 failed, 2 open, 2 no decision, 1 cancelled, 1 expired, 1 closed); `GET /account` gave equity $99,599.14, day change -$169.47 (-0.17%). They are copied into the README as a dated snapshot. `docs/system-walkthrough.md` status table and notes refreshed. `docs/progress.md` is final at acceptance.

**T-9 history scan and dry run.**

- gitleaks 8.21.2 (the version pinned in `.pre-commit-config.yaml` and CI), `gitleaks git` over the repository history: **151 commits scanned, no leaks found.** Only `.env.example` is tracked among env files, and no `.pem`, `.key` or `.db` was ever added.
- **Dry run in a fresh clone** (scratchpad, a copy of the owner's `.env`, deleted afterwards), the README followed as written: `uv sync` 12 s; `bullpit doctor` all checks passed; `alembic upgrade head` created the journal at `0009`; `bullpit request AAPL --mode backtest --as-of 2024-07-12` exit 0 in 154 s (route debate, outcome no trade, report printed). Dashboard: `npm ci` and `npm run build` in 75 s, `bullpit serve` and `npm run start`: `/`, `/trades` and `/portfolio` answered 200 on `127.0.0.1`, `/api/account` returned the live account, an empty journal showed zeros. **No stumble in the README steps**; the only warning was uv noting the author shell's `VIRTUAL_ENV`, which a stranger won't have. **This is the author's own run on the author's machine with the author's keys, not "someone other than the author"**: a second person's run (Q4 = A) is still to be done.

## Documents check

| Milestone | Where the retrospective is | State |
|---|---|---|
| M0 | [`M0-foundations/task.md`](../M0-foundations/task.md#retrospective) | Accepted 2026-09-30, tagged `m0`; status and T-25 fixed |
| M1 | [`M1-data-layer/task.md`](../M1-data-layer/task.md#retrospective) | Accepted, tagged `m1` |
| M2 | [`M2-llm-gateway/task.md`](../M2-llm-gateway/task.md#retrospective) | Accepted, tagged `m2` |
| M3 | [`M3-analysts/task.md`](../M3-analysts/task.md#retrospective) | Accepted, tagged `m3` |
| M4 | [`M4-debate-trader-risk/task.md`](../M4-debate-trader-risk/task.md#retrospective) | Accepted, tagged `m4` |
| M5 | [`M5-report/task.md`](../M5-report/task.md#retrospective) | Accepted, tagged `m5`; status and T-12 fixed |
| M6 | [`M6-backtest/task.md`](../M6-backtest/task.md#retrospective) | Accepted, tagged `m6` |
| M7 | [`M7-evaluation/task.md`](../M7-evaluation/task.md#retrospective) | Accepted, tagged `m7` |
| M8 | [`M8-live-mode/task.md`](../M8-live-mode/task.md#retrospective) and [Acceptance](../M8-live-mode/task.md#acceptance-2026-10-06) | Accepted, tagged `m8`; T-12 ticked, AC-7 real half and AC-13 now done |
| M11.1 | [`M11.1-report-and-order-box/task.md`](../M11.1-report-and-order-box/task.md#retrospective) | Accepted, tagged `m11.1` |
| M11.2 | [`M11.2-dashboard-restructure/task.md`](../M11.2-dashboard-restructure/task.md#retrospective) | Tagged `m11.2`; status fixed |
| M11.3 | [`M11.3-live-pnl-close-market/specs-plan.md`](../M11.3-live-pnl-close-market/specs-plan.md#retrospective) | Tagged `m11.3`; retrospective added (Close button deferred) |
| M11.4 | [`M11.4-remove-backtests-page/specs-plan.md`](../M11.4-remove-backtests-page/specs-plan.md#retrospective) | Tagged `m11.4`; retrospective added |
| M9 | this file | Retrospective written at acceptance |

## Retrospective

(Written 2026-10-14, at the owner's acceptance.)

**Accepted.** The owner said "dashboard hand pass is clear i have checked it" and asked for the merge and the `m9` tag. M9 changed no behaviour (D-M9-2): no deviation, migration or architecture revision.

**Built.** The README rewritten for a newcomer (diagram, prerequisites and key sources, quick start, results excerpt and limits, a dated live track record, project tree, screenshots); stale status lines and missing retrospectives fixed across M0 to M11.4; ADR-0007's AC-13 probe addendum; the dependency audit (Python clean, `next` 16.4.0); dead code removed; the full history scanned (gitleaks 8.21.2, 151 commits, no leaks); a fresh-clone dry run with no stumble. **Numbers:** 429 tests in about 55 s, unchanged from before M9 (no test added or edited); ruff, mypy, ESLint and the web build clean; 611 doc links, 0 broken.

**What changed from the plan**

- The AC-13 probe and the AC-7 real half were already available: the probe ran in a market session on 2026-10-12, and the owner had closed the MSFT trade by hand on 2026-10-08 (the fill check recorded it `manual`, +$11.23), so the README's track record has one closed trade.
- Q1 to Q5 took the recommended answers (the owner gave none); Q6: the risk-manager screenshot was left out and stays an untracked file in `docs/images/`.
- No P1 or P2 issue was logged. The five P3s (`[?]` masking, long debate paragraphs, relevance-0 headlines, the M5 warning carry-over, dev-time npm findings) are listed in the Issues table and not fixed, because each fix would change behaviour or touch nothing that runs.

**Accepted by the owner as exceptions to the specs-plan** (the way M8 accepted its own):

- **M9-AC-1's second reader.** ~~Not done at acceptance.~~ **Done after acceptance (2026-10-14):** the owner reported the second-reader run of the README "done and working fine". No step-by-step notes or stumbles were pasted, so the run is recorded as reported, without timings. The author's own fresh-clone run (above) had no stumble either.
- **T-7's restart check with a real waiting report**, and a stop or target firing on a real Bull Pit trade (M8-AC-6's exit half). Both need a buy report and market time.
- **T-10, the first push and CI.** Nothing has been pushed since M0 (`master` is 51 commits ahead of `origin`, with all tags local). So **M9-AC-3's "CI green" and M8-AC-8 are not met**: the three CI jobs have never run, and the history scan above is local only. The push is the owner's to ask for; the first thing to do after it is read the CI result and fix forward.

**Carry-overs**

- The full gpt-oss evaluation (26 weeks, three stocks, repeat seeds, debate impact) is documented, not run (Q1 = A): commands in the [M7 retrospective](../M7-evaluation/task.md#retrospective).
- The M11.3 Close button stays deferred.
- The soft "debate paragraphs over 110 words" warning and the `[?]` display remain as designed (M9-I-1, M9-I-2).
