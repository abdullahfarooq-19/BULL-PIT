# M9 — Dashboard polish, README, results write-up: specs and plan

| | |
|---|---|
| **Status** | **Revision 1, 2026-10-06. Written, waiting for the owner's approval.** No `task.md` and no code until it is approved. Six open questions for the owner in [§8](#8-open-questions-for-the-owner), each with a recommended answer |
| **Date** | 2026-10-06 |
| **Size** | M: one `specs-plan.md` + `task.md` ([dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents)) |
| **Branch** | `m9-polish-readme-results`, from `master` (at `d2a382c`, M8 accepted and tagged `m8`; M11.1 to M11.4 tagged) |
| **Depends on** | M7 (accepted, tagged `m7`) and M8 (accepted 2026-10-06, tagged `m8`), per [dev-plan §4](../../dev-plan.md#4-milestone-overview-and-dependencies). M11.1 to M11.4 are built on M8 and do not block M9, but they changed the dashboard M9 polishes, so their notes are read too. M8's accepted exceptions are listed in [§2.3](#23-carried-in-from-earlier-milestones) |
| **Sources** | [dev-plan §5 M9](../../dev-plan.md#m9--dashboard-polish-readme-results-write-up) (scope and draft ACs), [§1.2](../../dev-plan.md#12-per-milestone-documents), [§1.5](../../dev-plan.md#15-definition-of-done-a-milestone-is-accepted-when) (Definition of Done), [§2.2](../../dev-plan.md#22-code-conventions), [§3](../../dev-plan.md#3-deviations-from-the-architecture-roadmap) (D13 to D21: none is touched), [§6.1](../../dev-plan.md#61-safety), [§6.5](../../dev-plan.md#65-performance-and-budget), [§7](../../dev-plan.md#7-testing-strategy) (necessary testing only), [§8](../../dev-plan.md#8-data-model-evolution) (no M9 row), [§9](../../dev-plan.md#9-plan-level-risks), [§10](../../dev-plan.md#10-decisions-log) (Q6 hosting, Q11), [§10.1](../../dev-plan.md#101-scope-review-revision-4) (C6, C10, C11); [architecture §16](../../architecture.md#16-build-roadmap) (M9 done-when), [§12](../../architecture.md#12-evaluation), [§14](../../architecture.md#14-free-tier-budget), [§17](../../architecture.md#17-risks-and-fixes), [Part 12](../../architecture.md#part-12--report-generator-both) and [Part 16](../../architecture.md#part-16--evaluation-code); [M7 task.md](../M7-evaluation/task.md#retrospective) (carry-over commands), [M8 task.md](../M8-live-mode/task.md#acceptance-2026-10-06) (acceptance and carry-overs), [M5 task.md](../M5-report/task.md#retrospective) (masking carry-over), [M11.1 task.md](../M11.1-report-and-order-box/task.md#retrospective), [M11.2 task.md](../M11.2-dashboard-restructure/task.md#retrospective), [M11.3](../M11.3-live-pnl-close-market/specs-plan.md) and [M11.4](../M11.4-remove-backtests-page/specs-plan.md) specs-plans; [`results/results.md`](../../results/results.md); the state of the repo, CI and journal read on 2026-10-06 ([§7.1](#71-facts-that-shape-this-revision)) |

Part A says **what** M9 delivers and how it's accepted. Part B says **how** it gets done. Neither restates the architecture or the dev plan; they link to them.

---

## Contents

**Part A: Specs**: [1 Goal](#1-goal) · [2 Scope](#2-scope) · [3 Functional requirements](#3-functional-requirements) · [4 Non-functional requirements](#4-non-functional-requirements) · [5 Interfaces](#5-interfaces) · [6 Acceptance criteria](#6-acceptance-criteria) · [7 Decisions](#7-decisions-made-in-this-document) · [8 Open questions](#8-open-questions-for-the-owner)

**Part B: Plan**: [9 Module design](#9-module-design) · [10 Data model](#10-data-model) · [11 Key procedures](#11-key-procedures) · [12 Error handling](#12-error-handling) · [13 Tests and checks](#13-test-and-verification-plan) · [14 Work order](#14-work-order) · [15 Risks](#15-risks)

---

# Part A: Specs

## 1. Goal

The architecture's done-when for M9: *"A stranger can understand the system and its results from the repo."* ([§16](../../architecture.md#16-build-roadmap)). Everything else is built; M9 makes it **finishable and trustworthy**:

1. The README takes a newcomer from "what is this" to a first request and a first backtest without help, and says honestly what the results do and don't show.
2. The dashboard issues found in real use are fixed, with no new pages (C10).
3. The repo is clean: no dead code, no stale docs, no unused dependency, no secret in the history, CI green on a first push.

M9 builds **no new feature and changes no system behaviour**. It writes no deviation, no migration and no architecture revision. If a fix turns out to change behaviour, work stops and the owner is asked (CLAUDE.md, "any change to system behaviour needs a new deviation").

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | **Dashboard fixes** for issues found by the owner's hand pass over Account & Wallet, Trades History, Portfolio and the report page ([§11.1](#111-issue-triage)). No new pages, themes or mobile layout | dev-plan M9; C10 |
| S2 | **README rewrite** for a stranger: what it is, safety statement, screenshots, how it works (one diagram), quick start, backtest and evaluation, results and limits, live track record, structure, links to ADRs and milestone docs | dev-plan M9 |
| S3 | **Results write-up:** the README results section (an excerpt of `results/results.md` and its limits) and the owner's **live track record** as a dated snapshot ([§11.6](#116-live-track-record-snapshot)) | dev-plan M9 |
| S4 | **Clean-up:** dead code, TODOs without a task ID, stray files ([§11.4](#114-dead-code-and-clutter-sweep)) | dev-plan M9; CLAUDE.md |
| S5 | **Dependency audit:** every direct Python and web dependency is used, and known vulnerabilities are checked ([§11.5](#115-dependency-audit)) | dev-plan M9 |
| S6 | **Secret scan across the whole git history**, run before the first push ([§11.7](#117-history-secret-scan)) | dev-plan M9; [§6.1](../../dev-plan.md#61-safety) |
| S7 | **Documents complete:** every milestone folder has its retrospective or acceptance note; stale status lines, `progress.md` and `system-walkthrough.md` brought up to date ([§3](#3-functional-requirements), FR-12 to FR-14) | M9-AC-2 |
| S8 | **First push and CI green** (the owner asks for the push; M8-AC-8 closes with it) | M9-AC-3; [M8 acceptance](../M8-live-mode/task.md#acceptance-2026-10-06) |
| S9 | **The recorded dry run** of the README from a fresh clone ([§11.3](#113-readme-dry-run)) | M9-AC-1 |

### 2.2 Out of scope

- **New features, pages, endpoints, settings or agents.** Anything not in this document becomes a note or a question (CLAUDE.md).
- **The full gpt-oss evaluation** (26 weeks × 3 stocks, 3 seeds × 13 weeks, debate impact) unless the owner chooses it in Q1. It needs about 300 requests; the free Groq quota covers roughly 18 debated requests a day ([architecture §14](../../architecture.md#14-free-tier-budget)).
- **The Close button** deferred by M11.3, and every other "candidate change" in `system-walkthrough.md` §13 not already built.
- **Hosting, auth, a licence decision beyond Q5, mobile or themes** ([dev-plan §10](../../dev-plan.md#10-decisions-log) Q6; C10).
- **New automated tests** beyond one regression test per fixed bug that falls under [§7.1](../../dev-plan.md#71-must-have-automated-tests).

### 2.3 Carried in from earlier milestones

These are the items earlier milestones accepted as open. M9 handles them as follows (the owner's choice for the first is Q2):

| From | Item | M9 treatment |
|---|---|---|
| M8 | **AC-13 probe** (a 1-share bracket whose stop is above the price, in market hours; ADR-0007 is written and says it's outstanding) | Optional task, one market session (Q2) |
| M8 | **AC-1 real half** (restart the API with a real waiting report) and README screenshots | Restart check: optional task with the probe. Screenshots: done 2026-10-06 except the risk-manager image (Q6) |
| M8 | **AC-6 exit half** (a stop or target fires on a real Bull Pit trade) and **AC-7 real half** (a Bull Pit trade closed by hand shows as `manual`) | Need market time the open trades may not give by acceptance. M9 records them in the track record **if they happen**; acceptance does not wait for them (Q2) |
| M8 | **AC-8** (CI web job green) | Closes with the first push (S8) |
| M5 | The warning that quotes LLM text ("trader decisive evidence dropped…") may show a number unmasked | Checked in the hand pass ([§11.1](#111-issue-triage)); fixed only if it shows a wrong number |
| M7 | The full evaluation, repeat seeds, debate impact | Documented, not run (Q1) |
| M11.1 | Debate paragraphs often carry the soft "over 110 words" warning | Triaged as P3 ([§7](#7-decisions-made-in-this-document) D-M9-3) |
| M11.2 | The owner's own click-through of the four pages, keyboard-only and narrow window, was not recorded | Part of the hand pass |
| M11.3 | The Close button (FR-6 to FR-11) is deferred; no `task.md`, no retrospective | A short built/deferred note is written (FR-12); the button stays deferred |

## 3. Functional requirements

**Dashboard (S1; C10, C11)**

- **M9-FR-1 Issue log.** Every issue found in the owner's hand pass, and any found by the dry run, is logged in `task.md` with an ID, page, what was seen, and a severity ([D-M9-3](#7-decisions-made-in-this-document)). Nothing is fixed without an entry.
- **M9-FR-2 Fix rule.** Every P1 and P2 issue is fixed or explicitly accepted by the owner as an exception (the way M8 did). A P3 is fixed only if the fix is a few lines in one module and changes no behaviour; otherwise it is listed in the retrospective.
- **M9-FR-3 No new surface.** No new page, endpoint, setting, migration, theme or mobile layout. A fix that needs one is stopped and asked about.
- **M9-FR-4 Safety rules untouched.** No fix weakens the paper-only guard, the approval gate, the number check or the date guard. The existing safety tests pass unchanged.

**README (S2, S3)**

- **M9-FR-5 Structure.** The README has, in this order: the one-paragraph description and the safety statement; screenshots; how it works (one diagram and a few lines, linking the architecture); quick start; running a backtest and the evaluation; results and their limits; the live track record; live mode (the dashboard); safety; development commands; project structure; links to the ADRs and milestone docs. Content that is correct today is kept, not rewritten for its own sake.
- **M9-FR-6 Quick start is complete.** It names every prerequisite (Python 3.12, `uv`, Node 22 for the dashboard, the three API keys and where to get them, the SEC email), every command in order, and what a successful result looks like. Commands that need a market session or paid quota say so.
- **M9-FR-7 Accuracy.** Every command, path, setting name, port and link in the README exists and works as written (checked by the dry run, AC-1, and a link check, AC-4). The project-structure tree matches the repo.
- **M9-FR-8 Results section.** It shows an excerpt of `results/results.md` (the five approaches and buy and hold: total return and tokens per request), the run IDs and window, and the page's own limits in plain words. The numbers are copied from that file, with its date, and the section links to it for the rest ([D-M9-6](#7-decisions-made-in-this-document)). It makes no claim the data doesn't support (M7-AC-5's rule).
- **M9-FR-9 Live track record.** A dated snapshot of what the owner's real paper trades show: number of requests, buys approved, trades open and closed, realised P&L and the account's equity change, each number read from the Portfolio and Trades History pages (code-computed) and copied by hand ([§11.6](#116-live-track-record-snapshot)). It states plainly that open trades are unrealised, that the sample is tiny, and that it is not evidence of skill. Closed-trade results (a stop, a target, a manual close) are added only if they exist at the snapshot date.

**Clean-up and audits (S4 to S6)**

- **M9-FR-10 Dead code and clutter.** No commented-out code, unused import, `pass` stub, debug print, or TODO without a task ID in `bullpit/`, `web/src/` or `tests/`; no scratch, demo, backup or `_old` file tracked; no unreferenced module or function (CLAUDE.md, "no dead code", "no clutter").
- **M9-FR-11 Dependencies.** Each direct dependency in `pyproject.toml` and `web/package.json` is imported or used by a script; unused ones are removed. `pip-audit` and `npm audit` results are recorded. A fix for a known high or critical vulnerability is applied one package at a time with the suite as the gate ([dev-plan §2.1](../../dev-plan.md#21-toolchain)). No new dependency is added.
- **M9-FR-12 Documents complete.** Every milestone folder (M0 to M8, M11.1 to M11.4) has a retrospective or acceptance note, no stale status line ("uncommitted", "waiting for review", an unticked task whose work was done), and the dev plan's §4 and §5 list M11.3 and M9's status. `dev-plan.md` gets a revision entry for these status changes only.
- **M9-FR-13 `progress.md`** is final at M9 acceptance and still links to, not restates, the milestone docs.
- **M9-FR-14 `system-walkthrough.md`** is dated, and its project-status table (§3), review findings (§12) and candidate changes (§13) are updated so nothing in them contradicts the repo (D-M9-8).
- **M9-FR-15 `.env.example`** lists every environment variable that `config.py` reads (names only, no values).

**Release (S6, S8, S9)**

- **M9-FR-16 History scan before the first push.** The full history is scanned with the pinned gitleaks version; a finding stops the push (§12).
- **M9-FR-17 First push, when the owner asks.** `master` and the tags `m0` to `m8`, `m11.1` to `m11.4` (and `m9` after acceptance) go to `origin`; the CI `check`, `secrets` and `web` jobs run and are green, or the failures are fixed with new commits and the run is green.
- **M9-FR-18 Dry run.** The README is followed literally from a fresh clone to a first backtest request, and the result is recorded in `task.md` ([§11.3](#113-readme-dry-run)).

## 4. Non-functional requirements

- **M9-NFR-1 No behaviour change.** The diff of `bullpit/` contains only fixes listed in the issue log; nothing alters a number, a limit, a prompt or an order rule unless the owner approved it as an exception.
- **M9-NFR-2 Paper only, no secrets.** No key in any committed file, screenshot or log excerpt; `.env` stays git-ignored; the scratch clone's `.env` is deleted after the dry run.
- **M9-NFR-3 Testing bar unchanged** ([§13](#13-test-and-verification-plan)): dev-plan §7, no looser, no stricter.
- **M9-NFR-4 Four checks clean** after every task that touches code: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit`, `uv run pytest` (429 tests today, about 72 s on this laptop), and for web changes `npm run lint` and `npm run build`.
- **M9-NFR-5 One place for each fact.** The README links to the architecture, dev plan, ADRs and `results.md` instead of copying them, except the short results excerpt the dev plan requires (D-M9-6).
- **M9-NFR-6 Written for a stranger.** Plain language, no jargon without a link, short sentences; the README says what the system is not (not advice, not live money).

## 5. Interfaces

M9 adds **no API endpoint, CLI command, setting, table or file format**. What it changes:

| Artifact | Change |
|---|---|
| `README.md` | Rewritten to the outline in [§11.2](#112-readme-outline) |
| `docs/images/` | Eight screenshots renamed and linked (done 2026-10-06); the risk-manager image per Q6 |
| `docs/progress.md`, `docs/system-walkthrough.md`, `docs/dev-plan.md` (status and §4/§5 rows only), milestone `task.md` and `specs-plan.md` status lines | Status and retrospective fixes (FR-12 to FR-14) |
| `docs/milestones/M9-polish-readme-results/task.md` | Created after this file is approved; holds the issue log, evidence and retrospective |
| `docs/milestones/M11.3-…` | A short built/deferred note |
| `bullpit/`, `web/src/` | Only fixes from the issue log (FR-2) |
| `pyproject.toml`, `uv.lock`, `web/package.json`, `web/package-lock.json` | Only unused-dependency removals or audit fixes (FR-11) |
| `.env.example` | Only if a variable is missing (FR-15) |

## 6. Acceptance criteria

The first three are the dev plan's ([§5 M9](../../dev-plan.md#m9--dashboard-polish-readme-results-write-up)).

- **M9-AC-1** Someone other than the author can follow the README from a fresh clone to a first backtest request without help. *Verified by a recorded dry run (Q4): the steps, the time taken, every stumble, and the fix for each.* (FR-6, FR-7, FR-18)
- **M9-AC-2** Every milestone's documents are complete, with retrospectives. *Checked by hand against the table in [§11.8](#118-documents-check): one row per milestone, each with its retrospective link and no stale status.* (FR-12 to FR-14)
- **M9-AC-3** No open P1 or P2 issues; CI green; history secret scan clean. *The issue log has no open P1 or P2 (or an owner-accepted exception); the `check`, `secrets` and `web` jobs are green on the pushed `master`; the local history scan reports no finding.* (FR-1, FR-2, FR-16, FR-17)
- **M9-AC-4** The README has every section of FR-5, and every link in it and in the docs it links to resolves. *A link check over `README.md` and `docs/**/*.md` (a throwaway script in the scratchpad, not committed); its output is pasted in `task.md`.* (FR-5, FR-7)
- **M9-AC-5** The results and track-record sections match their sources. *Every number is compared by hand with `results/results.md` and with the Portfolio and Trades History pages at the snapshot date, and the owner reads both sections and approves the wording (M7-AC-5's rule).* (FR-8, FR-9)
- **M9-AC-6** No dead code, TODO or clutter remains, and every dependency is used. *The sweep's commands and output, and the audit results, are pasted in `task.md`; the four checks, `npm run lint` and `npm run build` are clean and the suite still passes.* (FR-10, FR-11, NFR-4)
- **M9-AC-7** `.env.example` covers every variable `config.py` reads. *A throwaway comparison script (scratchpad) lists any difference; the output is pasted.* (FR-15)
- **M9-AC-8** M9 changed no behaviour. *Every changed line in `bullpit/` traces to an issue-log entry; no deviation, migration or architecture revision was needed (or the owner approved the exception).* (NFR-1, FR-3, FR-4)

## 7. Decisions made in this document

| # | Decision | Reason |
|---|---|---|
| D-M9-1 | **Size M, one `specs-plan.md` + `task.md`; folder `M9-polish-readme-results`, branch `m9-polish-readme-results`.** | [dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents) and §4 |
| D-M9-2 | **M9 changes no behaviour, so it writes no deviation, migration or architecture revision.** The dev plan gets a status-only revision entry. A fix that would change behaviour is stopped and asked (Q3 is the one known case). | CLAUDE.md: any change to system behaviour needs a deviation; M9's dev-plan scope is polish, README and write-up |
| D-M9-3 | **Severity.** **P1:** can lose money, leak the future, bypass an approval or the paper-only guard, or crash the main loop (request, approve, fill check). **P2:** shows the owner a wrong or misleading number or text, loses a recorded fact, or blocks a page's main job. **P3:** cosmetic or wording, with a workaround. | The dev plan says "no open P1 or P2" without defining them; these follow the project's own rules (money, future, silent corruption: [§7](../../dev-plan.md#7-testing-strategy)) |
| D-M9-4 | **The issue log lives in M9's `task.md`**, not a separate file. | CLAUDE.md: no notes files; the log is evidence for AC-3 |
| D-M9-5 | **P1 and P2 are fixed (or owner-accepted as exceptions); P3 only when trivial** (FR-2). | Keeps M9 small and stops it turning into a feature milestone (CLAUDE.md, "don't expand scope") |
| D-M9-6 | **The README repeats a short excerpt of the pilot table** (return and tokens per request), dated and linked, and nothing else from `results.md`. The dev plan requires "the results table and its limits" in the README; `results.md` is regenerated by `bullpit eval`, so a longer copy would go stale. | One place for each fact vs. the dev plan's M9 scope; an excerpt with its source and date is the smallest thing that satisfies both |
| D-M9-7 | **The live track record is a dated, hand-copied snapshot in the README, not part of `results.md` and not new code.** The numbers come from the Portfolio and Trades History pages, which code computes. | `bullpit eval` rewrites `results.md`, so a hand-written section there would be lost; a new report generator would be a feature. A one-time snapshot needs neither |
| D-M9-8 | **`system-walkthrough.md` is updated in place** (status table, findings, candidate changes) and keeps its date line; it is not rewritten. | It is a dated review; the sources of truth win where they disagree (it says so itself), but its status table currently contradicts the repo |
| D-M9-9 | **Audits use throwaway commands, not new dependencies:** `uvx pip-audit` and `npm audit`, plus a one-off import check. Their output is pasted in `task.md`. | CLAUDE.md: no new dependency unless the plan names it; an audit tool is not a runtime need |
| D-M9-10 | **The history scan uses gitleaks pinned to the version in `.pre-commit-config.yaml` and `ci.yml` (8.21.2)**, run once before the first push, in addition to CI's own `secrets` job. | The pre-commit hook scans staged changes only, and CI never ran; the repo is public, so a push publishes whatever the history holds |
| D-M9-11 | **The dry run happens in a fresh clone under the session scratchpad** with a copy of the owner's `.env`, and the clone is deleted afterwards. | Tests the README, not the working tree's hidden state (journal, cache, `.venv`) |
| D-M9-12 | **No push, tag or merge happens unless the owner asks** (CLAUDE.md "commit only when the owner asks"; pushing sends the history to a public remote). The push is a gated step with its own confirmation. | Outward-facing and hard to undo |
| D-M9-13 | **The Close button stays deferred**; M11.3 gets a short built/deferred note, not a new `task.md`. | Out of M9's scope; M11.3's own spec records it as deferred |
| D-M9-14 | **One diagram in the README**, Mermaid (GitHub renders it), of the request flow, taken from [architecture §4/§5](../../architecture.md#4-system-overview), not a new design. | Dev-plan M9 asks for "an architecture summary with diagrams"; one is enough and avoids a second source for the flow |
| D-M9-15 | **`tests/` and `scripts/spikes/` stay as they are**; spikes keep their README and are linked as evidence for M0's findings. | CLAUDE.md allows spikes only in `scripts/spikes/`; they back ADR-0001, ADR-0002 and ADR-0008 |

### 7.1 Facts that shape this revision

Read on 2026-10-06:

- `master` is clean at `d2a382c` and **45 commits ahead of `origin`**; nothing has been pushed since M0, so CI has not run on M1 to M8 or M11.x. Tags `m0` to `m8` and `m11.1` to `m11.4` exist locally. 159 commits, 290 tracked files, `.git` 7.1 MB.
- **429 tests pass in about 72 s** (dev-plan §7.4 says "about a minute"; noted, not changed).
- No `TODO` or `FIXME` appears in `bullpit/` or `web/src/`; `ruff` already enforces unused imports. The sweep therefore looks for what ruff can't see: unreferenced functions and files, stale docs and tracked clutter.
- Dependencies: 19 Python runtime, 7 dev; 15 web runtime, 9 web dev. `shadcn` (a CLI) sits in the web runtime list. `pyproject.toml` says `license = "Proprietary"` and there is no `LICENSE` file in the public repo (Q5).
- The README's quick start is the M3-era flow (`bullpit request AAPL --mode backtest …`); backtest, evaluation and live mode were appended per milestone. It has no diagram and, until today, no screenshots.
- Documents with stale state: `M11.2/task.md` ("built, uncommitted, waiting for review"), `M8/task.md` (T-12 unticked, evidence heading "not done yet"), M11.3 (no retrospective), M11.4 (no retrospective section), dev-plan §4/§5 (no M11.3), `system-walkthrough.md` §3 and §12 (written 2026-09-30: "M8 not pushed", "M0 not tagged"). `docs/progress.md` was refreshed today.
- The report page shows `[?]` in the risk reviewer's quoted reason (screenshot of a real report). That is the number check's **designed** masking of a number the code didn't write (D-M5-2), not a crash; it reads badly (Q3).
- Real usage so far: orders placed for MSFT, two GOOGL (one a cancelled limit order) and CSCO; Portfolio shows 4 approved, 3 ongoing, 0 closed, $0.00 realised, equity $99,434.74 against $100,000 (screenshot, 2026-10-06). No stop or target has fired.

## 8. Open questions for the owner

Each has a recommended answer; if you approve this file without answering, the recommendation is used.

| # | Question | Options | Recommendation |
|---|---|---|---|
| **Q1** | **What is the project's final results story?** | **A.** Keep the M7 pilot as the stated result, add the live track record, and document the full evaluation as future work. **B.** Run the full gpt-oss evaluation inside M9: the headline run alone is 78 requests, about 5 days of Groq quota in the architecture's estimate (the dev plan's risk table says 8 to 16 days), and the repeat seeds add weeks. **C.** A middle run (for example 13 weeks × 1 stock on gpt-oss, one seed): about 13 requests, a day or two of quota, still too small to separate skill from luck. | **A.** The pilot already says plainly that it proves the pipeline, not superiority; B delays acceptance by weeks for a result the free tier can barely support; C costs quota without changing what can be claimed |
| **Q2** | **Do the M8 real-world leftovers become M9 tasks?** (the AC-13 probe, the real restart check, a Bull Pit trade closed by hand) | **A.** One market session: the 1-share probe for ADR-0007's addendum, a restart with a real waiting report, and a small approved buy closed by hand to see `manual`; about 15K Groq tokens per request. The exit-fill half of AC-6 is recorded only if it happens. **B.** Leave all of them as accepted exceptions. | **A**, in one session (18:30 to 01:00 PKT until 2026-11-01). They are cheap, they turn "proven only by fixtures" into evidence, and the paper account makes them safe. Acceptance does not wait for a stop or target to fire |
| **Q3** | **The `[?]` in the risk reviewer's reason on the report page.** Leave it as designed (the number check masks any number the code didn't write), or change how a masked number is shown? | **A.** Leave it; log it as P3 and say in the README that `[?]` means "a number the model wrote that the code could not confirm". **B.** Change the display (for example drop the clause). That changes behaviour: it needs a deviation and an architecture revision. | **A.** The masking protects the "no invented number" rule; hiding it is a design change that belongs outside a polish milestone |
| **Q4** | **Who does the AC-1 dry run?** The AC says "someone other than the author". | **A.** I follow the README literally in a fresh clone (catches missing steps and wrong commands), and you also hand it to one other person if you know one, and paste what they hit. **B.** Only the fresh-clone run. | **A.** Only a second human fully meets the AC's wording; B meets its intent but not its letter, so the retrospective would say so |
| **Q5** | **Licence.** `pyproject.toml` says "Proprietary", the repo is public and has no `LICENSE`. | **A.** Leave it, and add one README line: personal portfolio project, all rights reserved, paper trading only. **B.** Add an open licence (for example MIT). | **A.** It is a legal choice that is yours to make; M9 shouldn't make it by default. Say B if you want it done |
| **Q6** | **The risk-manager screenshot** (shows the `[?]` text). | **A.** Leave it out. **B.** Replace it with one cropped to the four limit boxes (Target, Risk, Cap, Cash). **C.** Use it, since Q3 explains it. | **B**, if you have time; otherwise A. The four-limits view is the part that shows "code sizes, AI only shrinks" |

---

# Part B: Plan

## 9. Module design

M9 creates **no module**. It edits documents and, only for logged issues, existing code.

**Files created or changed**

| Path | Change | Task |
|---|---|---|
| `README.md` | Rewritten to [§11.2](#112-readme-outline) | W6 |
| `docs/images/*.jpg` | Already renamed and linked; risk image per Q6 | W6 |
| `docs/milestones/M9-polish-readme-results/task.md` | New, after approval | W0 |
| `docs/progress.md`, `docs/system-walkthrough.md` | Status updates | W1, W8 |
| `docs/dev-plan.md` | Status line, revision 11, §4 and §5 (M11.3 row, M9 state) | W1 |
| `docs/milestones/M8-live-mode/task.md`, `M11.2/task.md`, `M11.3/specs-plan.md`, `M11.4/specs-plan.md` | Stale status, evidence headings, short built/deferred notes | W1 |
| `bullpit/**`, `web/src/**`, `tests/**` | Only issue-log fixes, and one regression test per fixed bug in the §7.1 categories | W3 |
| `pyproject.toml`, `uv.lock`, `web/package*.json` | Only unused-dependency removals or audit fixes | W4 |
| `.env.example` | Only missing names | W4 |

**Dependency direction.** Unchanged ([CLAUDE.md](../../../CLAUDE.md)): any fix stays in the module that owns the job; pure core (`tools/`, `risk/`, `eval/` math) gains no I/O import. No nodes, no graph change.

**Throwaway scripts** (link check, `.env.example` comparison, import check) live in the session scratchpad and are deleted; none enters the repo.

## 10. Data model

No table, column or migration. [dev-plan §8](../../dev-plan.md#8-data-model-evolution) gets no M9 row; the journal stays at migration `0009` (the `0010` of M11.3's deferred Close button is not built).

## 11. Key procedures

### 11.1 Issue triage

1. The owner runs `bullpit serve` and `npm run start` (a fresh build of `web/`), and goes through each page as in M8-AC-12 and M11.2: normal use, API stopped (error state), empty journal (empty state), keyboard only, a narrow window, and the report page for a buy, a no-trade and a pending limit order.
2. Each problem goes in the issue log: `ID · page · what was seen · severity · decision (fix / accept / list)`.
3. The M5 masking carry-over is checked on one real report with a dropped-evidence warning; the M11.1 word-count warning and the sentiment facts with relevance 0.00 are triaged with the rest.
4. Severity follows D-M9-3. Q3's `[?]` is entered as P3 under option A.
5. Fixes are made one issue at a time, each with its four checks (NFR-4); a bug in the [§7.1](../../dev-plan.md#71-must-have-automated-tests) categories gets one regression test.

### 11.2 README outline

| # | Section | Content |
|---|---|---|
| 1 | Title, description, safety statement | Existing text; the disclaimer stays at the top |
| 2 | Screenshots | The eight images added on 2026-10-06, in their README order; the risk image per Q6 |
| 3 | How it works | One Mermaid diagram of the request flow and a short list of "code does the math, AI judges, you approve"; links to architecture §4, §5, §9 |
| 4 | Quick start | Prerequisites (Python 3.12, `uv`, Node 22, keys and where to get them, the SEC email); `uv sync` → `.env` → `doctor` → first request → what to expect; backtest; dashboard |
| 5 | Backtest and evaluation | Existing sections, trimmed; the quota note and pause/resume |
| 6 | Results and limits | The dated excerpt (D-M9-6), the limits in plain words, the carry-over commands linked to M7's retrospective |
| 7 | Live track record | The dated snapshot ([§11.6](#116-live-track-record-snapshot)) |
| 8 | Live mode | Existing section, kept, with `[?]` explained if Q3 is A |
| 9 | Safety | Existing section |
| 10 | Development commands, testing philosophy | Existing, shortened; link to dev-plan §7 |
| 11 | Project structure | A tree that matches the repo, and links to `docs/`, the ADRs and each milestone folder |

### 11.3 README dry run

1. `git clone` the repo into the scratchpad; copy the owner's `.env` in.
2. Follow the README top to bottom, typing each command exactly as written, in a fresh shell, with no help from memory of the project.
3. Record, for each step: the command, whether it worked, the time, and any stumble (a missing prerequisite, a wrong path or flag, an unclear result).
4. Fix the README for each stumble and repeat the failing step until it works; the final pass is clean from step 1.
5. Run the dashboard steps (`npm ci`, `npm run build`, `npm run start`) in the clone and open the three pages once.
6. If a second person follows it (Q4), their stumbles go in the same table.
7. Delete the clone and its `.env`.

The first backtest request is `uv run bullpit request AAPL --mode backtest --as-of 2024-07-12` (about 15K Groq tokens when debated); the two-week MSFT backtest is not part of AC-1.

### 11.4 Dead code and clutter sweep

1. `git ls-files` listed and each non-source file justified (CLAUDE.md "no clutter"); the tracked design HTML at the root and the spike scripts are kept (D-M9-15).
2. Search for `TODO`, `FIXME`, `XXX`, `print(` in `bullpit/` and `web/src/`; for commented-out code blocks; for `_old`, `_v2`, `backup`, `scratch`, `demo` file names.
3. A throwaway scratchpad script lists every top-level function, class and module in `bullpit/` and counts its references across `bullpit/`, `tests/` and `scripts/`; zero-reference names are reviewed by hand (a name used only by a Typer command or an API route is still used).
4. The same for `web/src/components` and the helpers they import.
5. Remove what is unused; run the four checks and the web checks after each removal.

### 11.5 Dependency audit

1. For each of the 19 runtime and 7 dev Python dependencies, confirm an import in `bullpit/`, `tests/` or `scripts/` (or a reason: `hatchling` build, `pytest-socket` plugin). Same for the web list; `shadcn` is checked first (used by the CLI at set-up time, not at run time).
2. Remove what is unused (NFR-4 after each).
3. Run `uvx pip-audit` against the lockfile and `npm audit` in `web/`; paste the summaries.
4. For a high or critical finding with a fix, upgrade that one package, run the suite and the web build, and keep the change only if both pass. LangGraph, LiteLLM and alpaca-py are upgraded only for a vulnerability, one at a time ([dev-plan §2.1](../../dev-plan.md#21-toolchain)).
5. Unfixable findings are listed with the reason; the owner decides whether they block.

### 11.6 Live track record snapshot

1. On the snapshot date, with the API and dashboard running and the fill check just run, read: Portfolio (approved, rejected, ongoing, closed, total profit, total loss, net P&L; the equity chart's start and end), Trades History (counts by state; each open trade's entry, stop, target, shares and live P&L), and Account & Wallet's balance.
2. Write the section with the date and time (and "market open/closed"), the counts, the realised P&L, and the unrealised P&L of open trades as a separate line.
3. State: "paper money", "open trades are unrealised", "no stop or target has fired" (if true), and that a handful of trades cannot show skill.
4. If a stop, target or manual close has happened since 2026-10-06, add each as one line with its exit reason, and mark M8-AC-6 and AC-7's real halves done in M8's acceptance note.
5. The numbers are copied, never recomputed or rounded differently; the owner checks them against the screen (AC-5).

### 11.7 History secret scan

1. Download gitleaks 8.21.2 into the scratchpad (a read-only network call; it needs the owner's approval for the download).
2. Run `gitleaks git` over the full history with redaction on, from the repo root; save the report outside the repo.
3. A finding is judged by hand: a real key stops the push (§12); a false positive (a documentation example, a fixture) is added to a gitleaks allow-list only if one is needed, and the reason is recorded.
4. Also check by hand that `docs/images/` shows no key, full account number or email, and that no `.env*` (other than `.env.example`) is tracked.
5. After the push, CI's `secrets` job (full-history fetch) must be green too.

### 11.8 Documents check

One row per milestone in `task.md`'s evidence, each with the link to its retrospective or acceptance note:

| Milestone | Where the retrospective is | Known gap to fix |
|---|---|---|
| M0 | `M0-foundations/task.md` | None known; confirm |
| M1 to M7 | each `task.md` | Confirm a retrospective and no stale status |
| M8 | `M8-live-mode/task.md` (Retrospective + Acceptance) | T-12 unticked, "T-12: not done yet" heading: add a pointer to the acceptance note |
| M11.1 | `M11.1-…/task.md` | None known; confirm |
| M11.2 | `M11.2-…/task.md` | Status says "built, uncommitted, waiting for review" |
| M11.3 | `M11.3-…/specs-plan.md` | No retrospective: short built/deferred note |
| M11.4 | `M11.4-…/specs-plan.md` | Status says "Built"; add the merge and tag and a retrospective line |
| M9 | this folder's `task.md` | Written at the end |

## 12. Error handling

| Situation | Handling |
|---|---|
| CI fails on the first push (Linux, the web job, a locked-file difference) | Fix forward with new commits (never amend or force-push); each fix is a logged issue; M9 is not accepted until all three jobs are green |
| The history scan finds a real secret | Stop. Tell the owner. The key is **rotated first**; rewriting history is destructive and happens only if the owner asks and agrees to it |
| `pip-audit` or `npm audit` reports a high finding with no safe upgrade | List it with the reason; the owner decides |
| A fix needs a behaviour change | Stop; ask; if approved it becomes a deviation and an architecture revision, as the rules require (D-M9-2) |
| The dry run fails at a step | Fix the README, restart that step; the final pass is a clean run from step 1 |
| A real service is down during the dry run, the probe or the session (Groq quota, Alpaca) | Record it and retry on the next day or session; the free quota may force a pause (`bullpit request` stops with a message; backtests pause and resume) |
| A market session isn't available before acceptance | The Q2 tasks stay accepted exceptions, as M8 recorded them |
| The 8K token ceiling or quota blocks a request in the dry run | Use the cached request already made on that ticker and date, or choose a no-trade case; record it |

## 13. Test and verification plan

**The bar is [dev-plan §7](../../dev-plan.md#7-testing-strategy), unchanged: necessary testing only.**

- **Automated.** No new test is planned. The existing 429 pass unchanged, with no assertion edited. If a P1 or P2 fix is in the [§7.1](../../dev-plan.md#71-must-have-automated-tests) categories (money, the future, silently wrong results), it gets one regression test that fails without the fix. UI wording, README text and docs get none (§7.3).
- **No network** in automated tests; the suite stays at about a minute or its present 72 s.
- **By hand, recorded in `task.md`:** the hand pass, the dry run, the link check output, the audit output, the sweep output, the history scan, the track-record comparison.

| AC | How it is verified |
|---|---|
| M9-AC-1 | Recorded dry run ([§11.3](#113-readme-dry-run)); a second person if Q4 = A |
| M9-AC-2 | The [§11.8](#118-documents-check) table, read by the owner |
| M9-AC-3 | Issue log; CI run URLs or their status read from the public API; local gitleaks output |
| M9-AC-4 | Scratchpad link check, output pasted |
| M9-AC-5 | Side-by-side comparison with `results.md` and the three dashboard pages; owner reads the wording |
| M9-AC-6 | Sweep and audit output; four checks; `npm run lint`, `npm run build`; `uv run pytest` |
| M9-AC-7 | Scratchpad comparison of `.env.example` with `config.py` |
| M9-AC-8 | `git diff master -- bullpit web/src` read against the issue log |

## 14. Work order

Each step becomes one or more tasks in `task.md` (each about half a day or less; one commit when the owner asks). **Steps marked ◆ need the owner or a real service.**

| Step | Work | Gate / check |
|---|---|---|
| **W0** | Owner approves this file → write `task.md` → owner gives the green light → create the branch | CLAUDE.md gates 2 and 3 |
| **W1** | Documents: dev-plan status line and revision 11 (§4 M11.3 row, M9 state), the M8, M11.2, M11.3, M11.4 stale-state fixes, [§11.8](#118-documents-check) table started | FR-12; links resolve |
| **W2** ◆ | Owner's hand pass ([§11.1](#111-issue-triage)); issue log filled and severities agreed | FR-1; owner confirms the list |
| **W3** | Fix P1/P2 issues (and trivial P3s), one per commit, each with its checks and, where §7.1 applies, a regression test | FR-2 to FR-4; AC-8 |
| **W4** | Dependency audit and `.env.example` comparison ([§11.5](#115-dependency-audit)) | FR-11, FR-15; AC-6, AC-7 |
| **W5** | Dead code and clutter sweep ([§11.4](#114-dead-code-and-clutter-sweep)) | FR-10; AC-6 |
| **W6** | README rewrite to [§11.2](#112-readme-outline) with the diagram, screenshots, results excerpt and project tree | FR-5 to FR-8; AC-4 |
| **W7** ◆ | Optional market session (Q2 = A): probe, restart check, hand close; ADR-0007 addendum; M8 notes | Evidence in `task.md`; the paper account's own guard stays on |
| **W8** | Live track-record snapshot ([§11.6](#116-live-track-record-snapshot)); `progress.md` and `system-walkthrough.md` final | FR-9, FR-13, FR-14; AC-5 (owner reads) |
| **W9** | Local history scan ([§11.7](#117-history-secret-scan)); then the dry run ([§11.3](#113-readme-dry-run)) on the final README | FR-16, FR-18; AC-1, AC-3 |
| **W10** ◆ | When the owner asks: push `master` and tags; read the CI result; fix forward until green | FR-17; AC-3 |
| **W11** ◆ | Retrospective in `task.md`; owner accepts; merge and tag `m9` on the owner's ask | [DoD §1.5](../../dev-plan.md#15-definition-of-done-a-milestone-is-accepted-when) |

W4 and W5 come before W6 so the README describes the final tree and dependency set. W9's scan runs before W10 because a push publishes the history.

## 15. Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| **CI fails on its first run** (never run on M1 to M8, M11.x; Linux vs Windows; the web job's `git diff --exit-code` on generated files) | Delay; fix-forward commits | Medium | The same steps pass locally; W10 is its own step with time for fixes; each failure is a logged issue |
| **A secret is in the 159-commit history** | Public leak when pushed | Low (gitleaks ran on every commit through pre-commit) | W9 scans the whole history before any push; a finding means rotating the key first (§12) |
| **The hand pass finds many issues** | M9 grows into a feature milestone | Medium | D-M9-3 and D-M9-5: only P1/P2 are fixed; P3s are listed; behaviour changes are stopped and asked |
| **A "polish" fix quietly changes behaviour** (a prompt, a threshold, the masking) | An unrecorded deviation | Low–Medium | D-M9-2, FR-3, AC-8: every `bullpit/` line traces to an issue; the safety tests run unchanged |
| **The README is accurate for the author's machine only** | A stranger gets stuck (fails AC-1) | Medium | The dry run uses a fresh clone (D-M9-11); a second person if possible (Q4); Windows-specific lines (the `npm run open` script) are labelled |
| **The audit forces an upgrade of LangGraph, LiteLLM or alpaca-py** | Breakage in the graph, gateway or broker | Low | One package at a time with the suite as the gate ([dev-plan §9](../../dev-plan.md#9-plan-level-risks)); keep the change only if everything passes |
| **The results section is read as a claim** | Overstated results | Medium | It repeats the page's own limits, labels the live record "paper, unrealised, tiny sample", and the owner reads it (AC-5) |
| **No real stop or target fires before acceptance** | Track record has no closed trades | High | Said plainly in the section; acceptance does not wait for it (Q2) |
| **Free-quota limits block the dry run or the Q2 session** | Delay | Medium | One debated request is about 15K tokens against a 200K daily allowance ([architecture §14](../../architecture.md#14-free-tier-budget)); retry next day |
| **A screenshot or log excerpt exposes something private** | Leak on a public repo | Low | The images were read in full on 2026-10-06 (masked account suffix, paper money, no keys); re-checked in W9 |
