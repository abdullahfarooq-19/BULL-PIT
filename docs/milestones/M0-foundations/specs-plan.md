# M0 — Foundations + Alpaca paper: specs and plan

| | |
|---|---|
| **Status** | Approved by the owner on 2026-09-28, with the answers in [§8](#8-open-questions-for-the-owner) |
| **Date** | 2026-09-28 |
| **Size** | M (so specs and plan share this file, [dev-plan §1.2](../../dev-plan.md#12-per-milestone-documents)) |
| **Branch** | `m0-foundations` |
| **Depends on** | Nothing |
| **Sources** | [dev-plan §5 M0](../../dev-plan.md#m0--foundations--alpaca-paper), [§2](../../dev-plan.md#2-engineering-standards), [§7](../../dev-plan.md#7-testing-strategy), [§10](../../dev-plan.md#10-decisions-log); [architecture Part 14](../../architecture.md#part-14--execution-broker-adapter-code), [§13](../../architecture.md#13-tech-stack), [§14](../../architecture.md#14-free-tier-budget) |

Part A says **what** M0 delivers and how it's accepted. Part B says **how** it gets built. Neither restates the architecture or the dev plan; they link to them.

---

## Contents

**Part A: Specs**

1. [Goal](#1-goal)
2. [Scope](#2-scope)
3. [Functional requirements](#3-functional-requirements)
4. [Non-functional requirements](#4-non-functional-requirements)
5. [Interfaces](#5-interfaces)
6. [Acceptance criteria](#6-acceptance-criteria)
7. [Decisions made in this document](#7-decisions-made-in-this-document)
8. [Open questions for the owner](#8-open-questions-for-the-owner)

**Part B: Plan**

9. [Module design](#9-module-design)
10. [Toolchain and CI design](#10-toolchain-and-ci-design)
11. [Spike design](#11-spike-design)
12. [Error handling](#12-error-handling)
13. [Test and verification plan](#13-test-and-verification-plan)
14. [Work order](#14-work-order)
15. [Risks](#15-risks)
16. [ADRs](#16-adrs)

---

# Part A: Specs

## 1. Goal

A reproducible project skeleton that every later milestone builds on, plus written proof that the external services behave the way the architecture assumes.

The architecture's M0 done-when is: *"A test order placed from code fills and can be read back."* Deviation D1 widened M0 to cover the toolchain, CI, config, secrets, logging and a verification spike.

## 2. Scope

### 2.1 In scope

| # | Item | Source |
|---|---|---|
| S1 | Repo scaffold: `pyproject.toml`, `uv.lock`, `.python-version`, the `bullpit/` package with empty sub-packages from [dev-plan §2.3](../../dev-plan.md#23-repository-layout), `tests/`, `scripts/spikes/`, `docs/adr/` | dev-plan M0 |
| S2 | Toolchain: ruff (lint + format), mypy, pytest, pre-commit, secret scanning (gitleaks) | dev-plan §2.1 |
| S3 | GitHub Actions CI on `ubuntu-latest`: `uv sync` → ruff → mypy → pytest, plus a secret scan | dev-plan M0, §6.6 |
| S4 | `bullpit/config.py` (pydantic-settings), `.env.example`, `.gitignore` fixes | dev-plan M0 |
| S5 | `bullpit/logging.py` (structlog, with key redaction) and `bullpit/errors.py` (base exception hierarchy) | dev-plan M0, §2.2, §6.1 |
| S6 | **Paper-only guard** for the Alpaca trading client, with its unit test | architecture Part 14, dev-plan §6.1 |
| S7 | `bullpit doctor` CLI command | dev-plan M0 |
| S8 | Alpaca paper bracket-order spike (`scripts/spikes/`) | architecture M0 done-when |
| S9 | External-services verification spike: Groq, Alpaca (orders, news, assets, market data), SEC EDGAR, yfinance | dev-plan M0 |
| S10 | `findings.md`, ADR-0001 (uv), ADR-0002 (bracket order time-in-force and legs), a short `README.md` with the quick start | dev-plan M0 deliverables, DoD §1.5 |

### 2.2 Out of scope

- Any data layer, `Clock`, calendar, agent, gateway, journal, sizing or trading logic (M1 onward). The spikes are throwaway scripts; nothing in `bullpit/` depends on them.
- The broker protocol and `broker/alpaca.py` (read side in M3, write side in M8). M0 only adds the guarded client factory those will use.
- `api/` and `web/` folders (M8). Empty folders aren't tracked by git, so they're created when they get content.
- Settings for thresholds that later milestones use (1% risk, 10% cap, and so on). Each milestone adds the settings it uses, with the architecture's defaults. M0 adds only what M0 code reads.
- Pushing to or configuring anything on GitHub other than the repo and its Actions (no branch protection, releases or Pages).

## 3. Functional requirements

**Scaffold and toolchain**

- **M0-FR-1** `uv sync` on a fresh clone installs a locked, reproducible environment (Python 3.12) with every runtime and dev dependency M0 needs.
- **M0-FR-2** `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy bullpit` and `uv run pytest` all run from the repo root and pass on the M0 code.
- **M0-FR-3** Ruff bans the wall-clock calls the project forbids outside the `Clock` (`datetime.now`, `datetime.utcnow`, `datetime.today`, `date.today`, `pd.Timestamp.now`, `pd.Timestamp.today`) anywhere in `bullpit/`. `bullpit/clock.py` (M1) is the only file allowed to use them.
- **M0-FR-4** pytest refuses outbound network connections by default (only localhost is allowed), and registers a `live` marker that's deselected by default.
- **M0-FR-5** pre-commit runs on every commit: ruff lint and format, mypy, gitleaks on staged changes, end-of-file and trailing-whitespace fixers, YAML and TOML syntax checks, and a large-file check.
- **M0-FR-6** CI runs on every push and on pull requests to `master`: lint, format check, type check, tests, and a gitleaks scan of the pushed commits. Any failure fails the run.

**Config, secrets, logging, errors**

- **M0-FR-7** `bullpit/config.py` exposes one typed `Settings` object loaded from `.env` and the environment (the environment wins). Secrets are `SecretStr` and never appear in `repr`, logs or CLI output.
- **M0-FR-8** A missing or empty secret doesn't stop the settings from loading. The code that needs it raises `ConfigError` naming the variable (never its value). This lets `doctor` report every problem at once.
- **M0-FR-9** `.env.example` is tracked and lists every variable `Settings` reads, with comments and no values. `.gitignore` keeps `.env` and other `.env.*` files out, but lets `.env.example` in, and also ignores `data_cache/`, `logs/`, `*.db`, `*.sqlite*`, `.venv/` and tool caches.
- **M0-FR-10** `bullpit/logging.py` configures structlog once: readable output on the console, JSON lines in a rotating file under `logs/`. Context variables `request_id`, `mode` and `as_of` are included on every line once bound. A redaction step replaces the configured secret values, and values under key names that look secret (`key`, `secret`, `token`, `password`, `authorization`), with `***`.
- **M0-FR-11** `bullpit/errors.py` defines `BullPitError` and the subclasses listed in [§5.3](#53-exception-hierarchy).

**Paper-only guard**

- **M0-FR-12** The only way `bullpit/` code gets an Alpaca trading client is `make_trading_client(settings)`. Before constructing anything it checks the base URL, and raises `LiveTradingRefused` unless the URL is exactly `https://paper-api.alpaca.markets` (an optional trailing `/` is allowed; nothing else is: no other scheme, host, port, path, query, fragment or user info).
- **M0-FR-13** The same check runs when `Settings` loads, so a bad URL fails at startup too. There is no setting, flag or environment variable that turns the guard off.
- **M0-FR-14** Alpaca market data and news clients (read-only, and unable to place orders) come from `make_data_clients(settings)`, which uses the SDK's fixed data host. They never get the trading base URL.

**Doctor**

- **M0-FR-15** `uv run bullpit doctor` runs the checks in [§5.4](#54-bullpit-doctor) in order, prints one line per check (`OK`, `FAIL` or `SKIP`, with a short plain-ASCII detail), and exits 0 only if every check is `OK`.
- **M0-FR-16** `doctor` never prints a secret, a stack trace or an HTTP response body. A check that fails prints a one-line reason (for example `ALPACA_API_KEY is not set` or `Groq: HTTP 401, key rejected`). Every network call has a timeout.
- **M0-FR-17** `doctor` spends no LLM tokens and places no orders.

**Spikes and findings**

- **M0-FR-18** The bracket spike places a small whole-share bracket order on Alpaca paper through `make_trading_client`, reads it back with its legs, observes the entry fill, observes leg behaviour overnight, and closes the position. It runs only with an explicit `--confirm` flag and prints what it will do first. Details in [§11.1](#111-alpaca-bracket-order-spike).
- **M0-FR-19** The verification spikes check every assumption in [§11.2](#112-assumptions-to-verify) and write their raw output to a git-ignored folder.
- **M0-FR-20** `findings.md` records, for each assumption: what was assumed, what was observed, the verdict (confirmed or corrected), the evidence (script and date), and which milestone it affects. Every correction becomes an open question in that milestone's docs (added to its `specs.md` or `specs-plan.md` when that document is written, and listed in `findings.md` until then).
- **M0-FR-21** `findings.md` contains no keys, no account ID or number, and no SEC contact email.

## 4. Non-functional requirements

- **M0-NFR-1 (secrets)** No secret is ever committed, logged or printed. Enforced by `.gitignore`, `SecretStr`, log redaction, and gitleaks in pre-commit and CI.
- **M0-NFR-2 (speed)** The automated suite runs in well under a minute; CI finishes in about 5 minutes or less.
- **M0-NFR-3 (platform)** Everything works on Windows 11 (PowerShell and Git Bash) and on `ubuntu-latest`. Paths use `pathlib`; helper scripts are Python. Console output is plain ASCII, so it doesn't break on a cp1252 console.
- **M0-NFR-4 (reproducibility)** CI installs with `uv sync --locked`, so a lockfile out of step with `pyproject.toml` fails the build.
- **M0-NFR-5 (types)** mypy is `strict` for `bullpit.risk`, `bullpit.data`, `bullpit.broker`, `bullpit.tools` and `bullpit.eval`, and standard elsewhere, with the pydantic plugin on.
- **M0-NFR-6 (doctor time)** `doctor` finishes in under about 30 seconds when every service is reachable.
- **M0-NFR-7 (quota)** The Groq spike uses under 10K tokens in total across both models.

## 5. Interfaces

### 5.1 Settings (M0 fields only)

| Field | Env variable | Type | Default | Notes |
|---|---|---|---|---|
| `alpaca_base_url` | `ALPACA_BASE_URL` | `str` | `https://paper-api.alpaca.markets` | Checked by the paper guard. No `/v2` (the SDK adds it) |
| `alpaca_api_key` | `ALPACA_API_KEY` | `SecretStr \| None` | `None` | |
| `alpaca_secret_key` | `ALPACA_SECRET_KEY` | `SecretStr \| None` | `None` | |
| `groq_api_key` | `GROQ_API_KEY` | `SecretStr \| None` | `None` | Passed to calls explicitly; not read from the process environment by LiteLLM |
| `sec_contact_email` | `SEC_CONTACT_EMAIL` | `str \| None` | `None` | Goes into the SEC User-Agent. Checked for a basic `x@y.z` shape |
| `llm_small_model` | `LLM_SMALL_MODEL` | `str` | `openai/gpt-oss-20b` | Pinned (D9). M2 adds routing on top |
| `llm_large_model` | `LLM_LARGE_MODEL` | `str` | `openai/gpt-oss-120b` | Pinned (D9) |
| `log_level` | `LOG_LEVEL` | `str` | `INFO` | |
| `log_dir` | `LOG_DIR` | `Path` | `logs` | Relative to the working directory |
| `http_timeout_seconds` | `HTTP_TIMEOUT_SECONDS` | `float` | `10.0` | Used by `doctor` and the spikes |

Empty strings count as unset. `Settings.missing_secrets()` returns the names of unset required variables; `Settings.require(name)` returns the value or raises `ConfigError`.

### 5.2 Safety functions (`bullpit/broker/safety.py`, `bullpit/broker/clients.py`)

```python
PAPER_TRADING_URL: Final = "https://paper-api.alpaca.markets"

def assert_paper_url(url: str) -> str:
    """Return the normalised URL, or raise LiveTradingRefused. Pure; no I/O."""

def make_trading_client(settings: Settings) -> TradingClient:
    """assert_paper_url first, then TradingClient(key, secret, paper=True, url_override=url)."""

def make_data_clients(settings: Settings) -> DataClients:
    """News and stock-history clients on the SDK's fixed data host. Read-only."""
```

### 5.3 Exception hierarchy

```text
BullPitError
├── ConfigError           missing or invalid setting (names the variable, never the value)
├── LiveTradingRefused    paper-only guard tripped
├── DataUnavailable       (used from M1)
├── LookaheadViolation    (used from M1)
├── QuotaExhausted        (used from M2)
├── ValidationFailed      (used from M2)
└── BrokerRejected        (used from M3/M8)
```

The later ones are declared now so the hierarchy is fixed in one place; they get behaviour in their milestones.

### 5.4 `bullpit doctor`

| # | Check | Passes when | Needs |
|---|---|---|---|
| 1 | `config` | Every required variable is set | — |
| 2 | `paper-guard` | `ALPACA_BASE_URL` passes `assert_paper_url` | — |
| 3 | `alpaca-trading` | `get_account()` works, status `ACTIVE`, trading not blocked. Detail shows cash and equity (not buying power, see [§7](#7-decisions-made-in-this-document) D-M0-9) | 1, 2 |
| 4 | `alpaca-data` | The news endpoint returns at least one article for AAPL | 1 |
| 5 | `groq` | `GET /openai/v1/models` lists both pinned models (no tokens spent) | 1 |
| 6 | `sec` | Apple's submissions JSON on `data.sec.gov` returns 200 with the configured User-Agent | 1 |
| 7 | `yfinance` | The last 5 daily bars of SPY are not empty | — |

A check whose dependency failed prints `SKIP` and counts as not OK. Example:

```text
config          OK
paper-guard     OK    https://paper-api.alpaca.markets
alpaca-trading  OK    status ACTIVE, cash 99435.53, equity 99435.53
alpaca-data     OK    news reachable
groq            OK    openai/gpt-oss-20b, openai/gpt-oss-120b served
sec             OK    data.sec.gov reachable
yfinance        OK    SPY bars reachable
All checks passed.
```

### 5.5 `findings.md` layout

One table per service with the columns: **ID** (`F-<n>`) · **Assumption** (with its source) · **Observed** · **Verdict** · **Evidence** (script, date, raw output file) · **Affects**. Then a list of **corrections raised as open questions**, each naming the milestone that must answer it.

## 6. Acceptance criteria

| AC | Criterion | Verified by |
|---|---|---|
| **M0-AC-1** | A fresh clone runs `uv sync` then `uv run pytest` green on Windows (local) and in CI | Manual: clone into a temp folder on Windows; CI run link |
| **M0-AC-2** | CI runs lint, format check, type check, tests and the secret scan on push, and fails when any of them fails | Manual: one throwaway branch with a deliberate lint error goes red, then is deleted; CI link recorded |
| **M0-AC-3** | Building an Alpaca trading client with any non-paper URL raises `LiveTradingRefused` before any network call, and no setting disables the check | **Automated:** `tests/broker/test_paper_guard.py` |
| **M0-AC-4** | `bullpit doctor` prints `OK` for every check with valid keys, and with a key missing prints a one-line reason, no stack trace, no secret, and exits non-zero | Manual: normal run, plus one run with `ALPACA_API_KEY` blanked in the environment; output pasted in `task.md` |
| **M0-AC-5** | A bracket order placed from code is accepted by Alpaca paper, its legs are read back, its entry fill is observed, and the legs' overnight behaviour and final outcome are recorded in `findings.md` | Manual: spike output + `findings.md` |
| **M0-AC-6** | `findings.md` confirms or corrects every assumption in [§11.2](#112-assumptions-to-verify), and each correction is raised as an open question for the milestone it affects | Owner review of `findings.md` |
| **M0-AC-7** | Secret scanning runs in pre-commit and CI and catches a fake key | Manual, once: a fake-key file is blocked by pre-commit locally, and a CI run is shown red on a throwaway branch pushed with `--no-verify`, which is then deleted |
| **M0-AC-8** | `.env.example` is tracked and lists every variable `Settings` reads, without values; `.env`, `data_cache/`, `logs/` and `*.db` are ignored | Manual: `git ls-files` and `git check-ignore -v` output in `task.md` |
| **M0-AC-9** | Using any banned wall-clock call in `bullpit/` fails `ruff check` | Manual, once: a scratch file triggers the rule, then is deleted |
| **M0-AC-10** | ADR-0001 and ADR-0002 exist with status `Accepted`, and `README.md` has a quick start (`uv sync`, `.env`, `bullpit doctor`) that works | Owner review |

Coverage of the dev plan's draft M0 criteria: AC-1 to AC-7 carry them over (AC-7's CI half is made concrete). AC-8 to AC-10 cover in-scope items the drafts didn't test.

## 7. Decisions made in this document

These are low-stakes choices I made so M0 isn't blocked; each can be changed at review.

| # | Decision | Reason |
|---|---|---|
| D-M0-1 | Secret scanner is **gitleaks** (not detect-secrets): the pre-commit hook scans staged changes, and `gitleaks/gitleaks-action` in CI scans pushed commits | Provider-specific rules plus a generic key rule, and it can scan git history, which M9 needs. The action is free for personal-account repos |
| D-M0-2 | Ruff and mypy run in pre-commit as **local hooks through `uv run`**, not from the hook mirrors | Same tool versions as the lockfile, so pre-commit, CI and the command line can't disagree |
| D-M0-3 | Build backend is **hatchling**, flat layout (`bullpit/` at the repo root, as the architecture shows) | Common, simple, no `src/` move needed |
| D-M0-4 | `requires-python = ">=3.12,<3.13"`, with `.python-version` = 3.12 | CLAUDE.md fixes 3.12; one version means one set of behaviour |
| D-M0-5 | Runtime dependencies added in M0: `pydantic`, `pydantic-settings`, `structlog`, `typer`, `httpx`, `alpaca-py`, `litellm`, `yfinance`. Dev group: `ruff`, `mypy`, `pytest`, `pytest-socket`, `pre-commit`. `hypothesis`, `pandas-market-calendars` and the rest arrive with the milestones that use them | `litellm` and `yfinance` are needed now so the spike verifies behaviour on the exact versions later milestones will use |
| D-M0-6 | pytest blocks outbound connections with **`pytest-socket --allow-hosts=127.0.0.1,::1`** (not `--disable-socket`) | Enforces "no network in tests" cheaply. Blocking socket creation outright breaks the asyncio event loop on Windows, which later milestones need |
| D-M0-7 | The paper guard covers the **trading** client. Data and news clients use Alpaca's fixed data host, which serves paper and live accounts alike and can't place orders | Alpaca has no paper data host, so a paper-only check on data clients would reject every valid setup. The rule's purpose (no real orders) is fully kept. This clarifies Part 14; it doesn't change behaviour, so no deviation is needed |
| D-M0-8 | The guard runs at settings load **and** in `make_trading_client`, and it's the only way to build a trading client in `bullpit/` | A misconfigured `.env` fails at startup, and code that builds settings some other way still can't get past the factory |
| D-M0-9 | `doctor` and `findings.md` show **cash**, not buying power | The paper account reports 4x margin as buying power, and the architecture forbids borrowing. Recorded now so M4's sizing spec uses `cash` |
| D-M0-10 | `doctor` checks Groq with the free models endpoint, not a completion | Proves the key and the pinned models without spending quota |
| D-M0-11 | Groq's rate limits are recorded from the response headers of the spike's real calls. A screenshot of the account's limits page is welcome but not required | The headers come from the owner's own account and are recorded automatically |
| D-M0-12 | Settings for thresholds are added by the milestone that first uses them | Avoids unused settings with untested defaults; every setting still lives in `config.py` |
| D-M0-13 | Spikes may use fixed literal dates (for example `2024-07-01`). The wall-clock ban applies to `bullpit/`, not to `scripts/spikes/` | Spikes are throwaway and read live services; they don't feed backtests |

## 8. Open questions for the owner

| # | Question | Why it's yours | Proposed default |
|---|---|---|---|
| **Q-M0-1** | **GitHub remote.** Could you create the public repo on GitHub (the `gh` CLI isn't installed here) and tell me its URL? | It's your account, and the repo is public | Repo name `bull-pit`, created empty (no README or licence, so the first push is clean) |
| **Q-M0-2** | **Commits and pushes during M0.** CI (AC-1, AC-2, AC-7) can only be checked after pushing. May I commit each finished task on `m0-foundations` and push that branch, including the two short-lived throwaway branches for AC-2 and AC-7? | CLAUDE.md says to commit only when you ask | Yes: commit per task, push `m0-foundations`, and delete the throwaway branches right after their CI run |
| **Q-M0-3** | **Real paper orders.** Approving this document approves the bracket spike in [§11.1](#111-alpaca-bracket-order-spike): at most 3 orders of 1 share each in a stock priced about $5–$30, with one position held over one night and then closed. It changes the paper balance by a few dollars at most. OK? | Orders touch your account, even if it's paper money | Yes, as described |
| **Q-M0-4** | **Market-hours timing.** The fill and overnight parts of the spike need two US sessions (6:30 pm – 1:00 am PKT). Will you be around to run them, or should I run them in a session you start during those hours? | Needs your time | I run the script in a session you start during market hours; you just confirm |

**Owner answers (2026-09-28)**

| # | Answer | Effect on M0 |
|---|---|---|
| Q-M0-1, Q-M0-2 | **Not now.** No commits and no pushes for the moment; git and GitHub come later | Everything is built and checked locally first. The CI run (AC-1's CI half, AC-2), the secret-scan checks that need a commit or push (AC-7), and the fresh-clone check (AC-1) move to a later git phase in `task.md`. Tasks are checked off without hashes until then |
| Q-M0-3 | **Approved** as described in §11.1 | The bracket spike may place its orders |
| Q-M0-4 | **Later.** The market-hours steps are run in a later session during US hours | The `place`, `inspect` and `close` steps, ADR-0002 and AC-5 move to a later market-hours phase in `task.md` |

M0 can't be accepted until both later phases are done; everything else goes ahead now.

---

# Part B: Plan

## 9. Module design

### 9.1 Files created in M0

```text
.github/workflows/ci.yml
.pre-commit-config.yaml
.gitleaks.toml               only if an allowlist is needed (for example for test fixture URLs)
.python-version
.env.example
.gitignore                   updated
pyproject.toml               project, deps, ruff, mypy, pytest config
uv.lock
README.md
bullpit/
  __init__.py                package version
  config.py
  errors.py
  logging.py
  cli.py                     typer app; `doctor` only in M0
  doctor.py                  the checks, kept out of cli.py so cli stays thin
  broker/
    __init__.py
    safety.py                assert_paper_url (pure)
    clients.py               make_trading_client, make_data_clients
  agents/ tools/ data/ llm/ risk/ report/ approval/ journal/ eval/ runners/
                             each with an empty __init__.py
tests/
  conftest.py                empty for now
  broker/test_paper_guard.py
scripts/spikes/
  README.md                  what each spike does, how to run it, "throwaway"
  _common.py                 loads Settings, writes raw output to scripts/spikes/output/ (git-ignored)
  alpaca_bracket.py
  alpaca_readonly.py         assets, news depth, market data, rate-limit headers
  groq_models.py
  sec_edgar.py
  yfinance_check.py
docs/adr/0001-package-manager-uv.md
docs/adr/0002-bracket-order-tif-and-legs.md
docs/milestones/M0-foundations/findings.md
docs/milestones/M0-foundations/task.md
```

### 9.2 `config.py`

- `class Settings(BaseSettings)` with `model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")`.
- A `field_validator` turns empty strings into `None` for the optional secrets.
- A `field_validator` on `alpaca_base_url` calls `assert_paper_url` (D-M0-8). A failure there is re-raised as `LiveTradingRefused`, not buried inside pydantic's `ValidationError`, so the message is the guard's own.
- `get_settings()` is a cached accessor for normal use; tests build `Settings(...)` directly with explicit values and `_env_file=None`, so a developer's `.env` never leaks into a test.

### 9.3 Paper guard

`assert_paper_url(url)`:

1. Parse with `urllib.parse.urlsplit`. Reject if parsing fails.
2. Require `scheme == "https"`, `hostname == "paper-api.alpaca.markets"` (compared lower-case), `port is None`, empty `username` and `password`, path `""` or `"/"`, empty query and fragment.
3. Return `PAPER_TRADING_URL`.

It compares the parsed parts, never substrings, so `https://paper-api.alpaca.markets.evil.com` and `https://evil.com/?x=paper-api.alpaca.markets` fail. `make_trading_client` always passes `paper=True` as well as the checked URL, so the SDK's own default is also paper.

### 9.4 `logging.py`

- `configure_logging(settings)` is called once by the CLI entry point.
- Processor chain: `merge_contextvars` → add log level → ISO timestamp (from structlog's own `TimeStamper`, which is logging metadata, not business time, so it's outside the `Clock` rule) → `redact_secrets` → renderer.
- Two outputs through the stdlib `logging` bridge: a console handler with `ConsoleRenderer(colors=False)` (plain ASCII, NFR-3), and a `RotatingFileHandler` at `logs/bullpit.log` (5 MB × 3 files) with `JSONRenderer`.
- `redact_secrets` masks, anywhere in the event dict: the exact values of every `SecretStr` in `Settings`, and the value of any key whose name contains `key`, `secret`, `token`, `password` or `authorization`.

### 9.5 `doctor.py` and `cli.py`

- Each check is a small function returning `CheckResult(name, status, detail)`. It catches every exception and turns it into a one-line `detail` built from the exception type and a short message (never the response body).
- HTTP checks use `httpx` with `settings.http_timeout_seconds`. The Alpaca checks use the SDK clients from `clients.py`. The yfinance check calls `yf.Ticker("SPY").history(period="5d")`, which needs no date from our side.
- The SEC User-Agent is `BullPit/<version> <sec_contact_email>`, the format SEC asks for (name plus contact email). It lives in one helper so M1 reuses it.
- `cli.py` defines `app = typer.Typer()` with a `doctor` command that exits with `typer.Exit(code=0 or 1)`. `[project.scripts] bullpit = "bullpit.cli:app"`.

## 10. Toolchain and CI design

### 10.1 `pyproject.toml` settings

- **ruff:** `target-version = "py312"`, line length 100. Rule sets: `E`, `F`, `W`, `I` (imports), `B` (bugbear), `UP` (pyupgrade), `SIM`, `DTZ` (naive datetimes), `TID251` (banned APIs), `S` (bandit subset, mainly hard-coded passwords), `RUF`. `S101` (assert) is allowed in `tests/`. Banned APIs (M0-FR-3): `datetime.datetime.now`, `datetime.datetime.utcnow`, `datetime.datetime.today`, `datetime.date.today`, `pandas.Timestamp.now`, `pandas.Timestamp.today`, each with the message "Use the injected Clock (bullpit/clock.py)". `scripts/spikes/**` is exempt from the ban (D-M0-13).
- **mypy:** `python_version = "3.12"`, `plugins = ["pydantic.mypy"]`, `warn_unused_ignores`, `warn_redundant_casts`; `[[tool.mypy.overrides]]` with `strict = true` for the five strict packages; `ignore_missing_imports` only for named untyped libraries (for example `yfinance`), never globally.
- **pytest:** `testpaths = ["tests"]`, `addopts = "-ra --strict-markers -m 'not live' --allow-hosts=127.0.0.1,::1"`, marker `live: talks to real services; opt-in only`.

### 10.2 `.pre-commit-config.yaml`

1. `pre-commit/pre-commit-hooks`: `end-of-file-fixer`, `trailing-whitespace`, `check-yaml`, `check-toml`, `check-added-large-files` (500 KB; the architecture HTML already in the repo is about 68 KB).
2. `gitleaks/gitleaks` hook (staged changes only). pre-commit bootstraps Go on first run if Go isn't installed.
3. Local hooks: `uv run ruff check --fix`, `uv run ruff format`, `uv run mypy bullpit` (whole package, which is fast while small; narrowed to changed packages later only if it gets slow).

### 10.3 `.github/workflows/ci.yml`

```text
on: push (all branches), pull_request (to master)
jobs:
  check (ubuntu-latest):
    checkout → astral-sh/setup-uv (with cache) → uv sync --locked
    → uv run ruff check . → uv run ruff format --check . → uv run mypy bullpit → uv run pytest
  secrets (ubuntu-latest):
    checkout (fetch-depth: 0) → gitleaks/gitleaks-action
```

Actions are pinned to major versions. CI needs no secrets: the tests don't touch the network or read `.env`.

## 11. Spike design

All spikes live in `scripts/spikes/`, load `Settings` the normal way, and go through `make_trading_client` / `make_data_clients` so the guard is exercised too. Raw output (JSON) goes to `scripts/spikes/output/` (git-ignored, since it may include account IDs); I summarise it into `findings.md` by hand, leaving out the fields banned by M0-FR-21.

### 11.1 Alpaca bracket-order spike

`uv run python scripts/spikes/alpaca_bracket.py <step> --confirm`. Without `--confirm` it only prints the plan. The symbol is a liquid stock priced about $5–$30 (chosen at run time, recorded in the findings), quantity 1.

| Step | When | What it does | Records |
|---|---|---|---|
| `validate` | Any time | Submits brackets that should be rejected: fractional quantity (0.5); take-profit below the reference price; stop above it. Then submits a valid GTC bracket while the market is closed, reads it back, and cancels it | Each rejection's exact message and code; whether a closed-market bracket is accepted and its status; the leg price rules |
| `place` | Market open | Submits a 1-share market bracket, `time_in_force = gtc`, with stop and take-profit about 5% either side of the latest trade price, and `client_order_id = "spike-m0-<symbol>-1"`. Polls `get_order(nested=True)` until the entry fills (5-minute timeout). Then re-submits the **same** `client_order_id` | Parent and leg IDs, types and statuses before and after the fill; the fill price and time; whether the duplicate ID is rejected (evidence for M8's idempotency) |
| `inspect` | Next session | Reads the parent and legs again | Whether the GTC legs survived the overnight close and are still active |
| `close` | Market open | Cancels the open legs, closes the position with a market sell, and reads the final state | That the position is flat; final statuses; the realised P/L |

If `place` shows that `day` is the only accepted time-in-force for brackets, the spike stops there and I bring it to you before trying anything else, since that would change the design of M8.

### 11.2 Assumptions to verify

| ID | Assumption (source) | How it's checked | Affects |
|---|---|---|---|
| A1 | Groq serves `openai/gpt-oss-20b` and `openai/gpt-oss-120b` on this key (D9) | Models endpoint | M2 |
| A2 | Free-tier limits are 30 RPM, 1K RPD, 8K TPM, 200K TPD per model (arch §14) | `x-ratelimit-*` response headers of one real call per model (D-M0-11) | M2, M6, M7 |
| A3 | LiteLLM supports structured output for both models: JSON mode, and JSON schema with strict mode | One tiny call per mode per model | M2 |
| A4 | `reasoning_effort` is accepted (low, medium, high) and changes reasoning-token use | One tiny call per model at `low` and at `medium` | M2 |
| A5 | Reasoning tokens are reported in usage (for example `completion_tokens_details.reasoning_tokens`), and a small output cap can cut off the reply (empty content) because reasoning counts towards it | Usage fields of the calls above; one call with a deliberately small output cap | M2 |
| A6 | `seed` and `temperature` are accepted | Passed on the calls above | M2 |
| A7 | Brackets need whole shares; exits persist with a suitable `time_in_force`; leg prices are validated against a reference price (Part 14) | Bracket spike, all steps | M8 (ADR-0002) |
| A8 | A reused `client_order_id` is rejected (Part 14 idempotency) | Bracket spike, `place` | M8 |
| A9 | Orders placed while the market is closed wait for the next open (arch §8) | Bracket spike, `validate` | M8 |
| A10 | Alpaca news history goes back to 2015, with enough articles per week for the reference tickers (AAPL, MSFT, JPM, XOM, JNJ) from 2024-07 on; the free plan's rate limit (Part 2) | Earliest article for AAPL; article counts for one week in July 2024 and one recent week; rate-limit headers; page size limit | M1, M3 |
| A11 | Alpaca asset fields support the request check: `tradable`, `status`, `fractionable`, asset class, and whether ETFs can be told apart (Part 1) | `get_asset` for AAPL and SPY | M3 |
| A12 | Alpaca historical daily bars work on the free plan as a backup price source, and which feed they use (IEX or SIP) (Part 2) | Daily bars for AAPL from 2024-07-01 | M1 |
| A13 | Paper account: cash, equity and buying power; sizing must use cash (D-M0-9) | `get_account` | M4, M8 |
| A14 | SEC companyfacts is reachable with a proper User-Agent, and each fact carries a `filed` date (Part 2, Part 6) | Apple's companyfacts: presence of `filed`, `fy`, `fp`, `form` on revenue facts | M1, M3 |
| A15 | SEC's fair-access limit is 10 requests per second (Part 2) | SEC's current published policy page, with its link and date; no load test | M1 |
| A16 | yfinance still returns daily bars for AAPL, SPY and `^VIX` from 2024-07-01, and its current default for `auto_adjust` (Part 2) | `yfinance_check.py`, recording the version and the default | M1 (adjustment ADR) |

Token use for A2–A6 is about 12 short calls; with `low` effort and tiny prompts that's well under NFR-7's 10K.

## 12. Error handling

- `bullpit/` raises only `BullPitError` subclasses across module boundaries. Third-party exceptions are caught at the edge (`clients.py`, `doctor.py`) and wrapped, with the original chained (`raise ... from exc`).
- The paper guard and `ConfigError` always stop loudly. `doctor` is the one place that turns them into a line of output instead of stopping, because reporting them is its job.
- The spikes let exceptions show in full (they're throwaway and run by hand), but secrets still can't appear: keys are only ever in headers, and the SDK's error messages don't include headers.

## 13. Test and verification plan

Per [dev-plan §7](../../dev-plan.md#7-testing-strategy), M0 has **one** automated test file; everything else is a recorded manual check.

**`tests/broker/test_paper_guard.py`** (M0-AC-3), one parametrised test plus one accepting case:

- Rejected URLs: `https://api.alpaca.markets` (live), `http://paper-api.alpaca.markets`, `https://paper-api.alpaca.markets:8443`, `https://paper-api.alpaca.markets/v2`, `https://paper-api.alpaca.markets.evil.com`, `https://user@paper-api.alpaca.markets`, `https://evil.com/?h=paper-api.alpaca.markets`, and an empty string.
- For each: `make_trading_client(Settings(alpaca_base_url=..., ...))` raises `LiveTradingRefused` (from the settings validator or the factory), and a patched `TradingClient` constructor is never called, so no network call is possible. `pytest-socket` backs this up.
- Accepted: the paper URL, with and without the trailing `/`, returns a client built with `paper=True` (checked through the patched constructor's arguments).
- "No setting disables it" is covered by construction: `Settings` has no such field, and the test passes every other field at a non-default value.

**Manual checks**, each with its evidence pasted into `task.md`:

| AC | Check |
|---|---|
| AC-1 | Fresh clone into a temp folder on Windows → `uv sync` → `uv run pytest`; CI run link |
| AC-2 | Throwaway branch with an unused import → CI red → branch deleted |
| AC-4 | `uv run bullpit doctor` normal run; then `$env:ALPACA_API_KEY=""` and run again: `FAIL` line, dependent checks `SKIP`, exit code 1, no traceback |
| AC-5, AC-6 | Spike outputs summarised in `findings.md`; owner review |
| AC-7 | A made-up key in a format gitleaks detects (not AWS's documented example key, which gitleaks deliberately ignores) in a scratch file → `git commit` blocked by gitleaks; the same pushed on a throwaway branch with `--no-verify` → CI `secrets` job red → branch deleted, scratch file removed. If GitHub's own push protection blocks the push first, that's recorded as well, and the CI half is re-run with a generic high-entropy token that push protection doesn't know |
| AC-8 | `git ls-files .env.example`; `git check-ignore -v .env data_cache/x logs/x journal.db` |
| AC-9 | Scratch `bullpit/_scratch.py` calling `date.today()` → `ruff check` fails with the Clock message → file deleted |
| AC-10 | Owner reads the ADRs and follows the README quick start |

Log redaction is checked by hand once (logging is manual under §7.3): a debug line that includes the settings object shows `***` for every secret, on the console and in the log file.

## 14. Work order

`task.md` will break these into half-day tasks. The order:

1. **Scaffold:** `pyproject.toml`, `.python-version`, packages, `uv.lock`, `.gitignore` fix, `.env.example`.
2. **Toolchain config:** ruff, mypy, pytest (with `pytest-socket`), pre-commit.
3. **Core modules:** `errors.py`, `config.py`, `logging.py`.
4. **Paper guard** (`broker/safety.py`, `broker/clients.py`) and its test.
5. **`doctor`** and the CLI entry point.
6. **CI** workflow; first push once Q-M0-1 and Q-M0-2 are answered; AC-1, AC-2 and AC-7 checks.
7. **Read-only spikes** (Groq, SEC, yfinance, Alpaca read-only, bracket `validate`): any time of day.
8. **Bracket spike** `place` → `inspect` → `close`: two US market sessions.
9. **`findings.md`**, ADR-0001, ADR-0002, README, retrospective; owner acceptance.

Steps 7 and 8 can start as soon as step 4 is done, so the market-hours wait overlaps steps 5–6.

## 15. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| pre-commit's Go bootstrap for gitleaks fails on Windows | No local secret scan | Install the gitleaks binary with `winget` and switch to a `language: system` hook; CI scanning is unaffected |
| Alpaca rejects GTC brackets, or legs don't persist overnight | Trades could be left without exits (M8) | Found in the spike before any M8 code; the spike stops and asks (§11.1); ADR-0002 records the outcome |
| Groq's limits or models differ from the architecture | M2 budgets and the backtest window assumption | Recorded as corrections with open questions for M2; a model change goes back through D9 |
| Market hours (evening PKT) delay AC-5 by a day or two | M0 acceptance waits | Read-only spikes and CI work proceed meanwhile (§14) |
| `alpaca-py` changes how `url_override` and `paper` interact | Guard assumptions break | Versions pinned in `uv.lock`; the guard test checks the constructor's arguments |
| yfinance is flaky on the day | `doctor` or the spike fails for reasons outside our code | Re-run later; the flakiness is itself recorded in `findings.md` for M1 |
| SEC blocks requests without a proper User-Agent | Spike and M1 fail | The User-Agent helper is shared, and the spike makes only a handful of requests |

## 16. ADRs

- **ADR-0001 — Package manager: uv.** Context: reproducible installs on Windows and in CI. Decision: uv with a committed `uv.lock`; CI uses `--locked`. Status `Accepted` (already decided in Q5; written down in M0).
- **ADR-0002 — Bracket order time-in-force and leg behaviour.** Written after the spike, from the findings. It fixes the time-in-force, whether legs persist overnight, the leg price validation rule and its reference price, and what the fill check must watch for. It gives M8's exit-anchoring ADR its inputs.

ADRs use the headings Context, Decision, Consequences, Status, as in [dev-plan §1.3](../../dev-plan.md#13-architecture-decision-records-adrs).
