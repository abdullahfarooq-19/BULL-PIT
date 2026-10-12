# M9 — Dashboard polish, README, results write-up: tasks

| | |
|---|---|
| **Status** | Written 2026-10-12 after the owner approved [`specs-plan.md`](specs-plan.md) revision 1 ("specs plan is approved write the task.md and complete the M9"). Q1 to Q6 take the recommended answers (the owner gave none): Q1 = A, Q2 = A, Q3 = A, Q4 = A, Q5 = A, Q6 = B (crop) or leave out |
| **Date** | 2026-10-12 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (revision 1; necessary testing, dev-plan §7) |
| **Branch** | `m9-polish-readme-results`, from `master` (`d2a382c`) |

Each task is about half a day or less and is one commit when the owner asks for commits (CLAUDE.md). It is ticked only when its check passes. After every task that touches code, the four checks (`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit`, `uv run pytest`) are clean, and for web changes `npm run lint` and `npm run build` too. The diff is re-read for anything the task doesn't need. M9 changes no behaviour (D-M9-2). **Steps marked ◆ need the owner or a real service.**

---

| ✓ | ID | Task | Files | Serves | Done when | Commit |
|---|---|---|---|---|---|---|
| [ ] | M9-T-1 | **Documents.** `dev-plan.md`: status line, revision 11 (status only), §4 M11.3 row and M9 state, §5 M11.3 section. Stale state fixed: `M8/task.md` (T-12 and the "not done yet" heading point to the acceptance note), `M11.2/task.md` status, `M11.3/specs-plan.md` built/deferred note, `M11.4/specs-plan.md` merge, tag and retrospective line. The §11.8 table filled in this file | `docs/dev-plan.md`, milestone docs | FR-12; AC-2 | Every row of the Documents check below has its link and no stale status | |
| [ ] | M9-T-2 ◆ | **Hand pass and issue log.** The owner goes through Account & Wallet, Trades History, Portfolio and the report page (normal, API stopped, empty journal, keyboard only, narrow window; a buy, a no-trade, a pending limit order). Issues go in the Issues table below with a severity | this file | FR-1; AC-3 | The owner has confirmed the list | |
| [ ] | M9-T-3 | **Fixes.** One issue per commit, P1 and P2 first; a trivial P3 only if it changes no behaviour. A bug in the §7.1 categories gets one regression test | `bullpit/**`, `web/src/**`, `tests/**` | FR-2 to FR-4; AC-8 | Issues table has no open P1 or P2 (or an owner-accepted exception); four checks clean | |
| [ ] | M9-T-4 | **Dependency audit and `.env.example`.** Import check of every direct dependency (Python and web), `uvx pip-audit`, `npm audit`, comparison of `.env.example` with the variables `config.py` reads. Output pasted below | `pyproject.toml`, `uv.lock`, `web/package*.json`, `.env.example` (only if needed) | FR-11, FR-15; AC-6, AC-7 | Output pasted; unused dependencies removed; four checks and web build clean | |
| [ ] | M9-T-5 | **Dead code and clutter sweep** ([specs-plan §11.4](specs-plan.md#114-dead-code-and-clutter-sweep)) | `bullpit/**`, `web/src/**`, `tests/**` | FR-10; AC-6 | Output pasted; nothing unused left; four checks and web build clean | |
| [ ] | M9-T-6 | **README rewrite** to [specs-plan §11.2](specs-plan.md#112-readme-outline): diagram, screenshots, quick start, results excerpt, project tree, links. The risk-manager screenshot per Q6 | `README.md`, `docs/images/*` | FR-5 to FR-8; AC-4 | Link check output pasted | |
| [ ] | M9-T-7 ◆ | **Market session (optional, Q2 = A).** 1-share AC-13 probe, ADR-0007 addendum, a restart with a real waiting report, a small approved buy closed by hand. Evidence below | `docs/adr/0007-exit-anchoring.md`, `M8/task.md`, this file | M8 carry-overs | Evidence pasted, or recorded as still an accepted exception | |
| [ ] | M9-T-8 | **Live track record and final status docs** ([specs-plan §11.6](specs-plan.md#116-live-track-record-snapshot)): the README section, `progress.md`, `system-walkthrough.md` | `README.md`, `docs/progress.md`, `docs/system-walkthrough.md` | FR-9, FR-13, FR-14; AC-5 | Numbers match the screen; owner reads the wording | |
| [ ] | M9-T-9 | **History secret scan, then the dry run** ([§11.7](specs-plan.md#117-history-secret-scan), [§11.3](specs-plan.md#113-readme-dry-run)) on the final README | this file | FR-16, FR-18; AC-1, AC-3 | Scan clean; dry run recorded; a second person's run if Q4 = A | |
| [ ] | M9-T-10 ◆ | **Push and CI,** only when the owner asks: `master` and the tags to `origin`; read the CI result; fix forward until `check`, `secrets` and `web` are green | this file | FR-17; AC-3 | Three green jobs | |
| [ ] | M9-T-11 ◆ | **Acceptance.** Retrospective below; the owner accepts; when asked, merge to `master` and tag `m9` | this file | DoD §1.5 | Owner accepts | |

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

## Evidence

## Documents check

| Milestone | Where the retrospective is | State |
|---|---|---|

## Retrospective
