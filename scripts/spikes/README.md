# M0 spikes

Throwaway scripts (dev-plan.md sec1.1 glossary: "Spike"). They exist to answer
questions before M1+ code depends on the answers. Nothing in `bullpit/`
imports anything from here.

Each script loads `Settings` the normal way (from `.env`) and, where it talks
to Alpaca, goes through `bullpit.broker.clients` so the paper-only guard is
exercised too. Raw JSON responses are written to `scripts/spikes/output/`
(git-ignored — may contain account identifiers), and their findings are
summarised by hand into `docs/milestones/M0-foundations/findings.md`, with
account IDs, keys and the SEC contact email left out.

Run each with `uv run python scripts/spikes/<name>.py`.

| Script | Checks | Needs market hours? |
|---|---|---|
| `groq_models.py` | Models served, rate-limit headers, JSON mode, JSON schema, `reasoning_effort`, reasoning-token usage, `seed`/`temperature` (A1-A6) | No |
| `sec_edgar.py` | Companyfacts reachable, `filed` date present, SEC's fair-access policy (A14, A15) | No |
| `yfinance_check.py` | Daily bars for AAPL, SPY, `^VIX` from 2024-07-01; version and `auto_adjust` default (A16) | No |
| `alpaca_readonly.py` | News depth and rate limits, asset fields, backup price bars, account cash/equity (A10-A13) | No |
| `alpaca_bracket.py` | Bracket order rules: rejections, whole-market fill, overnight leg persistence, idempotent `client_order_id` (A7-A9) | `place`/`inspect`/`close` steps: yes |

`alpaca_bracket.py` only acts on `--confirm`; without it, it prints its plan
and touches nothing.
