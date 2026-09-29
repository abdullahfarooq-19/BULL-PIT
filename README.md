# Bull Pit

A multi-agent AI stock research and paper-trading system. You pick a stock;
three analyst agents (technical, fundamentals, news sentiment) study it; a
bull and a bear agent debate the evidence; a trader recommends buy or no
trade; a risk manager sizes and checks it; a report is produced; **you
approve every trade**.

> **Paper trading only. Not financial advice.** Every trade goes to an
> Alpaca **paper** account (fake money, real prices) or a simulated broker
> in backtests. The code refuses to start against anything but Alpaca's
> paper endpoint. Reports are a research tool, not investment advice.

Full design and build process: [`docs/architecture.md`](docs/architecture.md)
(what it does) and [`docs/dev-plan.md`](docs/dev-plan.md) (how it's built,
milestone by milestone). Current status lives in
[`docs/milestones/`](docs/milestones/).

## Quick start

Requires Python 3.12 and [`uv`](https://docs.astral.sh/uv/).

```bash
# 1. Install dependencies into a local virtual environment.
uv sync

# 2. Copy the environment template and fill in your own keys.
cp .env.example .env
# then edit .env: Alpaca paper keys, a Groq API key, and an email for the
# SEC User-Agent header. See .env.example for what each variable is.

# 3. Check everything is configured and every external service is reachable.
uv run bullpit doctor

# 4. Create the journal database (LLM call log, requests, and later tables).
uv run alembic upgrade head

# 5. Run your first research request (technical, fundamentals and news
#    sentiment analysts, then a debate-or-no-trade route). `bullpit request`
#    also applies any pending journal migration itself, so step 4 is
#    optional once you've run it once.
uv run bullpit request AAPL --mode backtest --as-of 2024-07-12
# Live mode (today's data, no --as-of): uv run bullpit request AAPL
```

`doctor` prints one line per check (config, the paper-only guard, Alpaca
trading and data, Groq, SEC EDGAR, yfinance) and exits non-zero if anything
needs fixing, without ever printing a secret.

`bullpit request` prints the account snapshot, each analyst's signal with
its evidence, the signals board's score and conflict, and the route
(`debate` or `no_trade`). When the route is `debate`, it goes on to print
each bull/bear turn (points with their evidence IDs, `[unsupported]` if a
citation doesn't check out, concessions, conviction), each trader attempt
(the recommendation, the sized order or the block reason, the risk
manager's decision and reason), and a final line:

```text
OUTCOME: BUY 30 JPM @ ref 225.37, stop 216.94, take-profit 238.01, max loss 252.90, gain 379.20 (set by target)
```

or, when the recommendation is to stand aside:

```text
OUTCOME: NO TRADE: Trader recommended no trade: ...
```

The report generator (M5) turns this into the readable report you decide
from; the approval gate, order placement and journal read-back arrive in
M6 and M8.

## Development commands

```bash
uv sync                          # install / update the environment
uv run pytest                    # run the test suite (no network calls; fast)
uv run ruff check . && uv run ruff format .   # lint and format
uv run mypy bullpit              # type check
uv run pre-commit run --all-files  # everything pre-commit checks, on demand
```

Pre-commit hooks (ruff, mypy, gitleaks secret scanning, and basic hygiene
checks) run automatically on `git commit` once installed with
`uv run pre-commit install`.

## Safety

- **Paper only, always.** `bullpit/broker/safety.py` refuses to build a
  trading client for any URL other than Alpaca's paper endpoint
  (`https://paper-api.alpaca.markets`), before any network call. There is
  no setting to turn this off.
- **A person approves every trade.** No live code path places an order
  without a recorded approval.
- **Secrets stay local.** `.env` is git-ignored; `.env.example` lists the
  variable names with no values; gitleaks scans every commit and every CI
  run for accidentally-committed secrets.
- **No borrowing.** Position sizing always reads account **cash**, never
  buying power (a paper account's reported buying power includes margin
  Bull Pit never uses).

## Project structure

```text
bull-pit/
├── bullpit/            the package: config, errors, logging, cli, broker/, ...
├── tests/              automated tests (mirrors bullpit/); no network calls
├── scripts/spikes/     throwaway scripts that verify external-service assumptions
├── docs/
│   ├── architecture.md what the system does
│   ├── dev-plan.md     how it's built: process, milestones, testing policy
│   ├── adr/            decisions not already fixed by the architecture
│   └── milestones/     per-milestone specs, plans, task checklists, findings
└── .github/workflows/  CI: lint, type check, tests, secret scan
```

See [`docs/dev-plan.md` §2.3](docs/dev-plan.md#23-repository-layout) for the
full, target layout as later milestones fill it in.

## How it's built

Bull Pit is built milestone by milestone (M0-M9), each gated on the
project owner's written approval of that milestone's specs before any code
is written. See [`docs/dev-plan.md` §1](docs/dev-plan.md#1-how-we-work) for
the process, and [`docs/milestones/`](docs/milestones/) for what's done and
what's next.

## Testing philosophy

Automated tests exist where a bug would lose money, leak the future, or
silently corrupt results (the date guard, sizing and exits, the simulated
broker's fill rules, report numbers, and so on). Everything else — prompt
quality, the dashboard, live services — is checked by hand at milestone
acceptance. See [`docs/dev-plan.md` §7](docs/dev-plan.md#7-testing-strategy)
for the full policy and its reasoning.
