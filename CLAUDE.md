# Bull Pit — project instructions

Bull Pit is a multi-agent AI stock research system. The user picks a stock; three analysts (technical, fundamentals, news sentiment) produce signals; a bull and a bear agent debate them; a trader recommends buy or no trade; a risk manager sizes and checks it; a report is produced; **the user approves every trade**. Trades go to an **Alpaca paper account** (live mode) or a simulated broker (backtest mode). No real money, ever.

## Sources of truth

Read these before any milestone work. Don't restate them here or in code comments; link to them.

- `docs/architecture.md`: what the system does (v2.1; changes tracked in its revision history).
- `docs/dev-plan.md`: how it's built: process, standards, milestones M0–M9, testing policy (§7), decisions log (§10).
- `docs/milestones/M<n>-<slug>/`: per-milestone specs, plans and task checklists. Current status lives here.
- `docs/adr/`: decisions not fixed by the architecture.

If code and docs disagree, the docs win until the owner approves a change. Any change to system behaviour needs a new deviation in `dev-plan.md` §3 and an `architecture.md` revision entry.

## Workflow (gated — never skip a gate)

1. Each milestone's documents are written first:
   - Size S/M (M0, M2, M5, M7, M9): `specs-plan.md` + `task.md`.
   - Size L/XL (M1, M3, M4, M6, M8): `specs.md` + `plan.md` + `task.md`.
2. **Stop after each document and wait for the owner's explicit approval.** Don't write the next document, or any code, without it.
3. Implement only after the owner gives the green light, task by task from `task.md`, checking each task off with its commit hash.
4. A milestone is done only when the owner accepts it against its acceptance criteria (Definition of Done: `dev-plan.md` §1.5).
5. Don't expand scope. Anything not in the approved docs becomes a note or a question, not code.

## Engineering rules

- **Code for math, LLMs for judgment.** Indicators, ratios, sizing, exits, rules, routing, report numbers and metrics are plain Python. LLM output is never used as a number unless code validated and bounded it.
- **Paper only.** The Alpaca client must refuse any base URL other than `paper-api.alpaca.markets`. Never weaken or bypass this guard.
- **No order without a recorded owner approval** in live mode. Every order has a deterministic `client_order_id` derived from `request_id`.
- **Everything time-aware takes `as_of`.** Never call `datetime.now()` / `date.today()` outside the injected `Clock`. Agents never call data sources directly; only through the data layer and its date guard.
- **Money:** `Decimal` for prices and dollar amounts in sizing, exits, broker and journal code; whole-share integers.
- **No magic numbers.** Every threshold (1% risk, 10% cap, 2% staleness, ATR multipliers, etc.) is a named setting in `bullpit/config.py`, defaulting to the architecture's value.
- **Typed state.** Everything crossing a graph node is a Pydantic model.
- **LLM calls go through `bullpit/llm/gateway.py` only.** Models are pinned: `openai/gpt-oss-20b` (small) and `openai/gpt-oss-120b` (large) on Groq. The free tier caps each call at about 8K tokens including reasoning, so keep prompts compact.
- **Backtest window starts 2024-07-01 or later** (models' June 2024 training cutoff).

## Code quality: write it like a professional

Write the least code that meets the approved spec. The goal is a small, clean codebase, not a big one.

- **No speculative code.** No features, options, parameters, abstractions or "for later" hooks that the current task doesn't need. Three similar lines are better than a helper written too early.
- **No extra files.** Create a file only when the approved layout (`dev-plan.md` §2.3 or the milestone plan) calls for it. Put code in the module that owns that job. No `utils.py`, `helpers.py`, `common.py`, one-function modules, or empty placeholder files.
- **No clutter in the repo.** No scratch, demo, example, backup, `_old` or `_v2` files, and no summary or notes Markdown unless asked. Throwaway work goes in the session scratchpad and is deleted. Spikes live only in `scripts/spikes/`.
- **No dead code.** No commented-out code, unused imports, `pass` stubs, debug prints, or TODOs without a task ID.
- **One place for each fact.** Don't copy a constant, mapping or piece of logic; import it from the module that owns it.
- **Dependencies point inward.** Pure core (`tools/`, `risk/`, `eval/` math) never imports I/O, the CLI, the API or `doctor`. I/O stays in `data/`, `llm/`, `broker/`, `journal/`, `api/`.
- **Short comments and docstrings.** Explain *why* or a contract that isn't obvious. Don't narrate the code or restate the docs; link to them.
- **No new dependency** unless the approved plan names it and says why.
- **Before marking a task done,** re-read the diff and delete anything the task doesn't need.

## Testing policy: necessary testing only

Full policy: `dev-plan.md` §7. In short:

- Automated tests **only** where a bug would lose money, leak the future, or silently corrupt results: date guard, sizing/exits/rules, sim broker fill rules, report number check, indicator and fundamentals math, eval metrics, LLM gateway behaviour, safety refusals.
- One happy-path test for data tools, the graph, and API endpoints. Nothing more.
- Prompt quality, UI, live services, logging and config are checked by hand.
- No coverage targets. No network in automated tests (recorded fixtures, scripted fake LLM). Suite should run in about a minute.
- Don't add tests beyond this without asking.

## Commands (available from M0 onward)

```bash
uv sync                      # install
uv run pytest                # tests
uv run ruff check . && uv run ruff format .
uv run mypy bullpit
uv run bullpit doctor        # check config and external services
```

## Git

- Default branch `master`; one branch per milestone, `m<n>-<slug>`; tag `m<n>` on acceptance.
- Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`), with the task ID in the body (`Task: M1-T-4`).
- Commit only when the owner asks. Remote is a public GitHub repo, so **never commit secrets**: keys live in `.env` only; `.env.example` lists variable names without values.

## Environment

- Windows 11. Use `pathlib` for paths; helper scripts are Python, not shell.
- Python 3.12 via `uv`. Node (for `web/`) only from M8.
- 8 GB RAM laptop, no GPU.
- US market hours are 6:30 pm – 1:00 am Pakistan time (7:30 pm – 2:00 am during US winter time).
