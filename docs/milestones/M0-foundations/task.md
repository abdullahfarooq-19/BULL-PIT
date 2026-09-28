# M0 — Foundations + Alpaca paper: tasks

| | |
|---|---|
| **Status** | Phase 1 (T-1 to T-15) complete, 2026-09-28. Phase 2 (market hours) and Phase 3 (git/CI) still pending |
| **Date** | 2026-09-28 |
| **Specs and plan** | [`specs-plan.md`](specs-plan.md) (approved 2026-09-28) |
| **Branch** | `m0-foundations` (created in the git phase; work is local on the working tree until then) |

Each task is about half a day or less, lists the files it touches, the requirement or acceptance criterion it serves, and how it's verified. A task is ticked when its verification passes. The **Commit** column stays `—` until the git phase (the owner has put commits and pushes on hold, [specs-plan §8](specs-plan.md#8-open-questions-for-the-owner)); hashes are filled in then.

Phases:

- **Phase 1 — Build (now).** Everything that runs locally, any time of day.
- **Phase 2 — Market hours (later).** The bracket spike steps that need the US market open.
- **Phase 3 — Git and CI (later).** Commits, the GitHub remote, CI runs, and the checks that need them.
- **Phase 4 — Acceptance.**

---

## Phase 1 — Build (now)

| ✓ | ID | Task | Files | Serves | Verified by | Commit |
|---|---|---|---|---|---|---|
| [x] | M0-T-1 | **Project scaffold.** `pyproject.toml` (hatchling, `requires-python >=3.12,<3.13`, runtime and dev dependencies from D-M0-5, `[project.scripts] bullpit`), `.python-version`, `bullpit/__init__.py` with the version, the empty sub-packages, `tests/conftest.py`; run `uv lock` and `uv sync` | `pyproject.toml`, `.python-version`, `uv.lock`, `bullpit/**/__init__.py`, `tests/conftest.py` | FR-1, S1 | `uv sync --locked` succeeds; `uv run python -c "import bullpit"` works | 7f274f0 |
| [x] | M0-T-2 | **Repo hygiene.** Update `.gitignore` (`!.env.example`, `data_cache/`, `logs/`, `*.db`, `*.sqlite*`, `.venv/`, tool caches, `scripts/spikes/output/`); write `.env.example` with every variable from specs-plan §5.1, comments, no values | `.gitignore`, `.env.example` | FR-9, AC-8 | `git check-ignore -v` on `.env`, `data_cache/x`, `logs/x`, `journal.db`, `scripts/spikes/output/x` (all ignored) and on `.env.example` (not ignored); output pasted below | 3ad64ff |
| [x] | M0-T-3 | **Tool config.** ruff (rule sets, the banned wall-clock APIs with the Clock message, per-file exemptions for `tests/` and `scripts/spikes/`), mypy (strict packages, pydantic plugin, named `ignore_missing_imports`), pytest (`--strict-markers`, `-m 'not live'`, `--allow-hosts=127.0.0.1,::1`, `live` marker) | `pyproject.toml` | FR-2, FR-3, FR-4, NFR-5, AC-9 | `ruff check`, `ruff format --check`, `mypy bullpit` clean; scratch `bullpit/_scratch.py` with `date.today()` fails `ruff check` with the Clock message, then is deleted (AC-9, output pasted below) | 7f274f0 |
| [x] | M0-T-4 | **Errors and settings.** `errors.py` (hierarchy in specs-plan §5.3); `config.py` (`Settings`, empty-string-to-`None`, `missing_secrets()`, `require()`, cached `get_settings()`, paper-guard validator hooked to T-5's `assert_paper_url`) | `bullpit/errors.py`, `bullpit/config.py` | FR-7, FR-8, FR-11, FR-13 | mypy clean; by hand: `Settings()` loads from `.env`, its `repr` shows no secret values, `missing_secrets()` is empty | ce1347c |
| [x] | M0-T-5 | **Paper guard and client factories, with the test.** `broker/safety.py` (`PAPER_TRADING_URL`, `assert_paper_url`), `broker/clients.py` (`make_trading_client`, `make_data_clients`); `tests/broker/test_paper_guard.py` as in specs-plan §13 | `bullpit/broker/safety.py`, `bullpit/broker/clients.py`, `tests/broker/test_paper_guard.py` | FR-12, FR-13, FR-14, AC-3 | `uv run pytest` green, in well under a minute (NFR-2) | 1481784 |
| [x] | M0-T-6 | **Logging.** `configure_logging(settings)`: console (plain ASCII) and rotating JSON file under `logs/`, contextvars, `redact_secrets` | `bullpit/logging.py` | FR-10, NFR-1, NFR-3 | By hand: a debug line carrying the settings object and a `api_key=...` field shows `***` on the console and in `logs/bullpit.log` (output pasted below) | 066897f |
| [x] | M0-T-7 | **`bullpit doctor`.** `doctor.py` (the seven checks in specs-plan §5.4, `CheckResult`, SKIP on failed dependencies, timeouts, one-line reasons, shared SEC User-Agent helper); `cli.py` (typer app, `doctor` command, exit codes, calls `configure_logging`) | `bullpit/doctor.py`, `bullpit/cli.py` | FR-15, FR-16, FR-17, NFR-6, AC-4 | `uv run bullpit doctor` all OK, exit 0; again with `$env:ALPACA_API_KEY=""`: `config` FAIL naming the variable, dependent checks SKIP, no traceback, no secret, exit 1 (both outputs pasted below) | 58a28d3 |
| [x] | M0-T-8 | **pre-commit config.** `.pre-commit-config.yaml` (standard hooks, gitleaks, local `uv run` hooks for ruff and mypy); `uv run pre-commit install` (local git hook only, no commit) | `.pre-commit-config.yaml` | FR-5, S2 | `uv run pre-commit run --files <every M0 file>` passes; the gitleaks hook installs on Windows (fallback per specs-plan §15 if it doesn't) | ddaef4c |
| [x] | M0-T-9 | **CI workflow file.** `.github/workflows/ci.yml` (`check` and `secrets` jobs, specs-plan §10.3). Written and linted now; first run in Phase 3 | `.github/workflows/ci.yml` | FR-6, NFR-4 | `check-yaml` passes; each command in the `check` job run locally in the same order passes | 5625794 |
| [x] | M0-T-10 | **Spike common code and Groq spike.** `scripts/spikes/README.md`, `_common.py` (settings, raw JSON output to `scripts/spikes/output/`), `groq_models.py` (A1–A6: models list, rate-limit headers, JSON mode, JSON schema strict, `reasoning_effort` low and medium, reasoning-token usage, small output cap, `seed`, `temperature`) | `scripts/spikes/README.md`, `scripts/spikes/_common.py`, `scripts/spikes/groq_models.py` | FR-19, NFR-7, AC-6 | Script runs; raw output saved; total tokens under 10K (from the recorded usage) | 5328ea2 |
| [x] | M0-T-11 | **SEC and yfinance spikes.** `sec_edgar.py` (A14: Apple companyfacts, `filed`/`fy`/`fp`/`form` on revenue facts; A15: SEC's published fair-access policy with link and date); `yfinance_check.py` (A16: AAPL, SPY, `^VIX` daily bars from 2024-07-01, yfinance version, `auto_adjust` default) | `scripts/spikes/sec_edgar.py`, `scripts/spikes/yfinance_check.py` | FR-19, AC-6 | Both scripts run; raw output saved | 5328ea2 |
| [x] | M0-T-12 | **Alpaca read-only spike.** `alpaca_readonly.py` (A10: earliest AAPL article, weekly article counts for the five reference tickers in one July 2024 week and one recent week, rate-limit headers, page size; A11: `get_asset` for AAPL and SPY; A12: daily bars for AAPL from 2024-07-01 and the feed used; A13: cash, equity, buying power) | `scripts/spikes/alpaca_readonly.py` | FR-19, AC-6 | Script runs through the client factories; raw output saved | 5328ea2 |
| [x] | M0-T-13 | **Bracket spike script and its `validate` step.** `alpaca_bracket.py` with all four steps (`validate`, `place`, `inspect`, `close`), dry-run without `--confirm`; run `validate` now (A7 rejection rules, A9 closed-market bracket accepted and then cancelled) | `scripts/spikes/alpaca_bracket.py` | FR-18, AC-5 (part) | Dry run prints the plan and places nothing; `validate --confirm` records each rejection message and the closed-market order's status, and leaves no open order (checked with a read-back) | 5328ea2 |
| [x] | M0-T-14 | **Findings, first pass.** `findings.md` in the layout of specs-plan §5.5, filled from T-10 to T-13, with A7 and A8 marked "pending market hours"; corrections listed as open questions per milestone; no keys, account IDs or email | `docs/milestones/M0-foundations/findings.md` | FR-20, FR-21, AC-6 (part) | Every assumption A1–A16 has a row; a search of the file for the key prefixes, the account ID and the email finds nothing | 13c5e0b |
| [x] | M0-T-15 | **ADR-0001 and README.** `docs/adr/0001-package-manager-uv.md` (Accepted); `README.md` with what it is, the paper-only and not-financial-advice statement, and the quick start (`uv sync`, copy `.env.example` to `.env`, `uv run bullpit doctor`, the dev commands) | `docs/adr/0001-package-manager-uv.md`, `README.md` | S10, AC-10 (part) | Quick start followed in a copy of the working tree in a temp folder: `uv sync --locked`, `uv run pytest`, `uv run bullpit doctor` all pass (interim evidence for AC-1 until the fresh clone in Phase 3) | 7b1550a |

## Phase 2 — Market hours (later, 6:30 pm – 1:00 am PKT)

| ✓ | ID | Task | Files | Serves | Verified by | Commit |
|---|---|---|---|---|---|---|
| [ ] | M0-T-16 | **Bracket `place`.** Run `alpaca_bracket.py place --confirm`: 1-share GTC market bracket, poll until filled, re-submit the same `client_order_id`. If GTC brackets are refused, stop and bring it to the owner (specs-plan §11.1) | `scripts/spikes/output/` (raw only) | FR-18, AC-5, A7, A8 | Raw output shows the fill, both legs and their statuses, and the duplicate-ID result | — |
| [ ] | M0-T-17 | **Bracket `inspect`** in the next session: are both legs still active after the overnight close? | `scripts/spikes/output/` | AC-5, A7 | Raw output shows leg statuses after the close | — |
| [ ] | M0-T-18 | **Bracket `close`.** Cancel the legs, market-sell the share, read the final state | `scripts/spikes/output/` | AC-5 | Position flat; no open orders left (read-back) | — |
| [ ] | M0-T-19 | **Findings final pass and ADR-0002.** Fill A7 and A8 in `findings.md`; write `docs/adr/0002-bracket-order-tif-and-legs.md` (Accepted) from them | `findings.md`, `docs/adr/0002-bracket-order-tif-and-legs.md` | AC-5, AC-6, AC-10 | Every row in `findings.md` has a verdict; owner review | — |

## Phase 3 — Git and CI (later, when the owner says so)

| ✓ | ID | Task | Files | Serves | Verified by | Commit |
|---|---|---|---|---|---|---|
| [x] | M0-T-20 | **Branch and commits.** Create `m0-foundations`; commit the Phase 1–2 work as one commit per task where the files allow it (pre-commit hooks run on each); back-fill the hashes in this file | All M0 files | DoD §1.5 | `git log` shows the task commits; pre-commit passed on each | 62e0c6e |
| [x] | M0-T-21 | **Local secret-scan check.** A made-up key in a scratch file is blocked by the gitleaks hook on `git commit`; scratch file removed | none kept | AC-7 (local half) | Blocked-commit output pasted below | — |
| [x] | M0-T-22 | **Remote and first CI run.** Owner creates the public repo; add the remote; push `m0-foundations`; CI green | — | AC-1 (CI half), FR-6 | CI run link | — |
| [x] | M0-T-23 | **CI failure checks.** Throwaway branch with a lint error → CI red; throwaway branch with a fake key pushed with `--no-verify` → `secrets` job red (or GitHub push protection blocks it, recorded, then re-run with a generic token, specs-plan §13); both branches deleted | none kept | AC-2, AC-7 (CI half) | CI run links; real bug found and fixed (evidence below) | 5a16bb0 |
| [x] | M0-T-24 | **Fresh clone on Windows.** Clone from GitHub into a temp folder, `uv sync`, `uv run pytest` | — | AC-1 | Output pasted below | — |

## Phase 4 — Acceptance

| ✓ | ID | Task | Files | Serves | Verified by | Commit |
|---|---|---|---|---|---|---|
| [ ] | M0-T-25 | **Acceptance and retrospective.** Walk through AC-1 to AC-10 with the evidence below; write the retrospective; after owner acceptance, merge to `master` and tag `m0` | `task.md` | DoD §1.5 | Owner accepts | — |

---

## Traceability

| AC | Tasks |
|---|---|
| AC-1 | T-1, T-3, T-15 (interim), T-22, T-24 |
| AC-2 | T-9, T-23 |
| AC-3 | T-5 |
| AC-4 | T-7 |
| AC-5 | T-13, T-16, T-17, T-18, T-19 |
| AC-6 | T-10, T-11, T-12, T-14, T-19 |
| AC-7 | T-8, T-21, T-23 |
| AC-8 | T-2 |
| AC-9 | T-3 |
| AC-10 | T-15, T-19 |

T-4 and T-6 serve requirements (FR-7, FR-8, FR-10, FR-11) that the ACs above depend on rather than an AC of their own.

---

## Evidence

### M0-T-2: `.gitignore` (AC-8)

```
$ git check-ignore -v .env data_cache/x logs/x journal.db scripts/spikes/output/x
.gitignore:4:.env      .env
.gitignore:20:data_cache/      data_cache/x
.gitignore:21:logs/    logs/x
.gitignore:22:*.db     journal.db
.gitignore:25:scripts/spikes/output/ scripts/spikes/output/x

$ git check-ignore .env.example ; echo "exit=$?"
exit=1        # not ignored, as required
```

### M0-T-3: banned wall-clock API (AC-9)

A scratch file using `datetime.date.today()` (then deleted):

```
TID251 `datetime.date.today` is banned: Use the injected Clock (bullpit/clock.py), not date.today().
DTZ011 `datetime.date.today()` used
Found 2 errors.
```

### M0-T-7: `bullpit doctor` (AC-4)

Normal run, all keys present:

```
config          OK
paper-guard     OK       https://paper-api.alpaca.markets
alpaca-trading  OK       status AccountStatus.ACTIVE, cash 99435.53, equity 99435.53
alpaca-data     OK       news reachable
groq            OK       openai/gpt-oss-120b, openai/gpt-oss-20b served
sec             OK       data.sec.gov reachable
yfinance        OK       SPY bars reachable
All checks passed.
```

With `ALPACA_API_KEY` blanked:

```
config          FAIL     missing: ALPACA_API_KEY
paper-guard     SKIP     config failed
alpaca-trading  SKIP     config or paper-guard failed
alpaca-data     SKIP     config failed
groq            SKIP     config failed
sec             SKIP     config failed
yfinance        OK       SPY bars reachable
Some checks failed. See above.
exit=1
```

No secret, no traceback in either run.

### M0-T-6: log redaction (checked by hand, dev-plan.md §7.3)

A debug line carrying a raw secret value both under a secret-looking key
name and embedded in an ordinary string, on console and in the JSON log
file:

```
console: 2026-09-28T13:22:15Z [info] debug_dump  api_key=*** groq_api_key=*** note='hello world'
file:    {"api_key": "***", "groq_api_key": "***", "note": "hello world", "event": "debug_dump", ...}

console: 2026-09-28T13:22:22Z [info] leak_test  message='Authorization: Bearer ***'
```

Both the key-name-based and literal-value-based redaction paths confirmed.

### M0-T-8: pre-commit (AC-7, local half)

All 9 hooks pass, including gitleaks (which bootstrapped cleanly on Windows
with no Go toolchain installed — the D-M0 risk in specs-plan §15 didn't
materialise, so no chocolatey/winget fallback was needed):

```
fix end of files.........................................................Passed
trim trailing whitespace.................................................Passed
check yaml................................................................Passed
check toml.................................................................Passed
check for added large files...............................................Passed
Detect hardcoded secrets...................................................Passed
ruff check..................................................................Passed
ruff format..................................................................Passed
mypy.........................................................................Passed
```

Files were staged (`git add -A`) to make `--all-files` see them, then
unstaged (`git reset`) immediately after — no commit was made, per the
owner's instruction to hold off on git for now.

### M0-T-10 to M0-T-13: spikes (AC-5 partial, AC-6)

Full findings: [`findings.md`](findings.md). Highlights:

- Groq: both pinned models served; rate limits match the architecture
  exactly (1000 req/day, 8000 tokens/min); JSON mode, JSON schema (strict),
  `reasoning_effort`, `seed` and `temperature` all work; reasoning tokens
  are reported and **can silently starve visible output** under a small
  `max_tokens` cap (correction C4 for M2). Total spend: 1,143 tokens.
- SEC EDGAR: companyfacts reachable with the configured User-Agent; every
  fact carries `filed`, `fy`, `fp`, `form`.
- yfinance 1.7.0: AAPL, SPY, `^VIX` all return 9 daily bars for
  2024-07-01..07-12; `auto_adjust` defaults to `True` (correction C3).
- Alpaca read-only: news back to 2015-01-01; XOM/JNJ are thin
  (5-10 articles/week); `asset_class` does **not** distinguish an ETF from
  a stock (correction C1 — M3 already relies on the SEC-filings check
  instead); account cash and equity both $99,435.53, buying power
  $397,742.12 (4x margin, unused per D-M0-9).
- Alpaca bracket `validate --confirm` (real paper orders, per Q-M0-3):
  fractional quantity rejected, inverted exits rejected, a valid 1-share
  GTC bracket accepted while the market was closed (legs `HELD` — confirms
  A9), then cleanly cancelled. No open orders left afterwards.

`place`, `inspect`, `close` (A7's overnight half, A8) are deferred to
Phase 2, market hours.

### M0-T-15: fresh-copy quick start (interim AC-1 evidence)

The full working tree was copied to a temp folder (robocopy, excluding
`.venv`/`.git`/caches) to simulate a fresh clone, since no git remote
exists yet:

```
$ uv sync --locked            # succeeded, all 104 packages installed
$ uv run pytest -q            # 28 passed in 15.02s
$ uv run bullpit doctor       # All checks passed.
```

The temp copy was deleted afterwards. The real fresh-clone check
(M0-T-24) still needs a GitHub remote (Phase 3).

### Full local quality gate (after every Phase 1 task)

```
$ uv run ruff check .          All checks passed!
$ uv run ruff format --check . 32 files already formatted
$ uv run mypy bullpit          Success: no issues found in 19 source files
$ uv run pytest -q             28 passed in 0.8s
```

### M0-T-20 to M0-T-22: git phase, remote, first CI run

`master` (the pre-existing docs commits) and `m0-foundations` (13 commits,
one per Phase 1 task plus the specs-plan and the final task.md update)
were both pushed to `https://github.com/abdullahfarooq-19/BULL-PIT`. The
remote already had one placeholder commit on `main`; `master` and
`m0-foundations` were pushed as new branches alongside it (no conflict).
The first CI run on `m0-foundations`
([run 36431032434](https://github.com/abdullahfarooq-19/BULL-PIT/actions/runs/36431032434))
passed both jobs cleanly on the first try:

```
check    -> success  (Lint, Format check, Type check, Test all passed)
secrets  -> success
```

### M0-T-21: local secret-scan block

A GitHub-PAT-shaped fake key (`ghp_...`) in a scratch file, committed on a
branch off `m0-foundations` (so `.pre-commit-config.yaml` was present):

```
Finding:     GENERIC_TOKEN = "REDACTEDAB01"
RuleID:      generic-api-key
Finding:     GENERIC_TOKEN = "REDACTEDAB01"
RuleID:      github-pat
leaks found: 2

ruff check...............................................................Failed
S105  Possible hardcoded password assigned to: "GENERIC_TOKEN"
```

Both the gitleaks hook and ruff's `S105` (bandit) rule blocked the commit
independently. Scratch file removed; no commit was made this way (see
M0-T-23 for the `--no-verify` variant that exercised CI).

### M0-T-23: CI failure checks, and a real bug found and fixed

**Lint failure** (throwaway branch `ci-check-lint-failure`, an unused
import): CI's `check` job failed at the `Lint` step as expected
([run 36431170358](https://github.com/abdullahfarooq-19/BULL-PIT/actions/runs/36431170358)).
Branch deleted locally and on GitHub afterwards.

**Secret leak** (throwaway branch `ci-check-secret-leak`, the same
GitHub-PAT-shaped fake key, committed with `--no-verify` to bypass the
local hook and reach CI): GitHub's push protection did **not** block the
push (not enabled on this repo). CI's overall `check` job failed (again
via ruff's `S105`), but the **`secrets` job itself reported "no leaks
found"**
([run 36431253053](https://github.com/abdullahfarooq-19/BULL-PIT/actions/runs/36431253053)).
Its logs showed it scanned only the new commit (~63 bytes) and used
whatever gitleaks version `gitleaks-action@v2` currently bundles by
default -- different from the `v8.21.2` pinned for the local pre-commit
hook. That version mismatch is the most likely explanation for the
missed detection.

**Fix:** pinned `GITLEAKS_VERSION: "8.21.2"` in `ci.yml`'s `secrets` job
(commit `5a16bb0`) so CI uses the exact same gitleaks version as
pre-commit. Re-tested on a second throwaway branch
(`ci-check-secret-leak-2`) with the identical fake key: the `secrets` job
now fails correctly
([run 36431648055](https://github.com/abdullahfarooq-19/BULL-PIT/actions/runs/36431648055)):

```
secrets -> failure   (Scan for secrets: failure)
check   -> failure   (Lint: failure)
```

Both branches deleted locally and on GitHub afterwards. This is exactly
the kind of gap M0-AC-7's CI-failure check exists to catch -- found and
fixed before acceptance, not after.

### M0-T-24: fresh clone on Windows (AC-1)

```
$ git clone -b m0-foundations https://github.com/abdullahfarooq-19/BULL-PIT.git <temp dir>
$ uv sync --locked             # succeeded
$ uv run pytest -q             # 28 passed in 4.56s
$ uv run bullpit doctor        # All checks passed.
```

Temp clone deleted afterwards.

---

## Retrospective

Written at acceptance.

*(empty)*
