"""Typer entry points. `doctor` is the only command from M0; `request` (M3)
runs the graph end to end for one ticker (D-M3-6: a way to run and inspect
the graph long before the dashboard); `backtest` (M6) runs or resumes a
weekly backtest; `eval` (M7) writes the results page from finished runs.
"""

from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Literal, cast, get_args

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

from bullpit.broker.alpaca import make_alpaca_broker
from bullpit.clock import Clock, LiveClock, SimClock
from bullpit.config import Settings, get_settings
from bullpit.doctor import Status, run_all_checks
from bullpit.errors import BullPitError, ConfigError
from bullpit.eval.baselines import Policy
from bullpit.eval.report import evaluate
from bullpit.journal.db import journal_url, make_engine, make_sessions
from bullpit.logging import configure_logging
from bullpit.report.builder import render_markdown
from bullpit.runners.backtest import RunResult, WeekSummary, run_backtest, start_backtest
from bullpit.runners.request import run_request
from bullpit.state import RequestState

# LLM text (M4's debate/report prose) can contain characters outside
# Windows' legacy console codepage (e.g. U+2011 non-breaking hyphen); print
# it rather than crash the CLI on a UnicodeEncodeError (found running M4-T-14).
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

app = typer.Typer(add_completion=False, help="Bull Pit: research, not financial advice.")

_MIGRATIONS_DIR = Path(__file__).parent / "journal" / "migrations"


@app.callback()
def main() -> None:
    """Bull Pit: research, not financial advice. Paper trading only."""


@app.command()
def doctor() -> None:
    """Check settings and every external service Bull Pit depends on."""
    try:
        settings = get_settings()
    except BullPitError as exc:
        typer.echo(f"config          FAIL    {exc}")
        raise typer.Exit(code=1) from None

    configure_logging(settings)

    results = run_all_checks(settings)
    for result in results:
        typer.echo(result.line())

    if all(result.status is Status.OK for result in results):
        typer.echo("All checks passed.")
        raise typer.Exit(code=0)

    typer.echo("Some checks failed. See above.")
    raise typer.Exit(code=1)


def _upgrade_journal_schema(settings: Settings) -> None:
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", str(_MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", journal_url(settings))
    alembic_command.upgrade(cfg, "head")


def _print_debate_and_outcome(result: RequestState) -> None:
    """M4-FR-18: each debate turn, each trader attempt, then the OUTCOME line."""
    for turn in result.debate:
        flag = " [FLAGGED]" if turn.flagged else ""
        typer.echo(f"{turn.side} round {turn.round}: conviction {turn.conviction:.2f}{flag}")
        for point in turn.points:
            ids = ", ".join(point.evidence_ids) if point.evidence_ids else "no IDs"
            suffix = " [unsupported]" if point.unsupported else ""
            typer.echo(f"  {point.claim} ({ids}){suffix}")
        for concession in turn.concessions:
            typer.echo(f"  concedes: {concession}")

    for index, attempt in enumerate(result.attempts, start=1):
        recommendation = attempt.recommendation
        flag = " [FLAGGED]" if recommendation.flagged else ""
        typer.echo(
            f"attempt {index}: {recommendation.action} "
            f"{recommendation.target_weight:.2%} {recommendation.exit_style} "
            f"(confidence {recommendation.confidence:.2f}){flag}"
        )
        if attempt.sized_order is not None:
            order = attempt.sized_order
            typer.echo(
                f"  sized: {order.shares} shares @ ref {order.reference_price:.2f}, "
                f"stop {order.stop_loss:.2f}, take-profit {order.take_profit:.2f} "
                f"(set by {order.limit})"
            )
        elif attempt.blocked_reason is not None:
            typer.echo(f"  blocked: {attempt.blocked_reason}")
        if attempt.verdict is not None:
            typer.echo(f"  review: {attempt.verdict.decision} - {attempt.verdict.reason}")

    if result.outcome == "buy" and result.sized_order is not None:
        order = result.sized_order
        typer.echo(
            f"OUTCOME: BUY {order.shares} {result.ticker} @ ref {order.reference_price:.2f}, "
            f"stop {order.stop_loss:.2f}, take-profit {order.take_profit:.2f}, "
            f"max loss {order.max_loss:.2f}, gain {order.max_gain:.2f} (set by {order.limit})"
        )
    elif result.outcome == "no_trade":
        typer.echo(f"OUTCOME: NO TRADE: {result.no_trade_reason}")


@app.command()
def request(
    ticker: str,
    mode: Annotated[str, typer.Option("--mode")] = "live",
    as_of: Annotated[str | None, typer.Option("--as-of")] = None,
) -> None:
    """Run one research request end to end: check, analysts, route."""
    try:
        settings = get_settings()
    except BullPitError as exc:
        typer.echo(f"config          FAIL    {exc}")
        raise typer.Exit(code=1) from None

    configure_logging(settings)

    if mode not in ("live", "backtest"):
        typer.echo(f"--mode must be 'live' or 'backtest', got {mode!r}")
        raise typer.Exit(code=2)
    if mode == "live" and as_of is not None:
        typer.echo("--as-of is not allowed in live mode")
        raise typer.Exit(code=2)
    if mode == "backtest" and as_of is None:
        typer.echo("--as-of is required in backtest mode")
        raise typer.Exit(code=2)

    clock: Clock
    if mode == "live":
        clock = LiveClock()
    else:
        try:
            parsed_as_of = date.fromisoformat(as_of) if as_of else None
        except ValueError:
            typer.echo(f"--as-of must be an ISO date (YYYY-MM-DD), got {as_of!r}")
            raise typer.Exit(code=2) from None
        if parsed_as_of is None:  # pragma: no cover - guarded above
            raise typer.Exit(code=2)
        try:
            clock = SimClock(parsed_as_of)
        except ConfigError as exc:
            typer.echo(str(exc))
            raise typer.Exit(code=2) from None

    _upgrade_journal_schema(settings)

    engine = make_engine(journal_url(settings))
    sessions = make_sessions(engine)
    broker = make_alpaca_broker(settings)

    validated_mode = cast(Literal["live", "backtest"], mode)
    result = run_request(
        ticker, validated_mode, clock, settings=settings, sessions=sessions, broker=broker
    )

    typer.echo(f"request_id: {result.request_id}")
    typer.echo(f"mode: {result.mode}  as_of: {result.as_of}")
    if result.rejection is not None:
        typer.echo(f"REJECTED: {result.rejection}")
        raise typer.Exit(code=1)

    typer.echo(f"company: {result.company_name}")
    if result.account is not None:
        typer.echo(f"account: cash={result.account.cash}  equity={result.account.equity}")

    for signal in (result.technical_signal, result.fundamentals_signal, result.sentiment_signal):
        if signal is None:
            continue
        flag = " [FLAGGED]" if signal.flagged else ""
        typer.echo(
            f"{signal.analyst}: {signal.direction} (confidence {signal.confidence:.2f}){flag}"
        )
        for item in signal.evidence:
            typer.echo(f"  {item.id}: {item.fact}")
        if signal.note:
            typer.echo(f"  note: {signal.note}")

    if result.board is not None:
        typer.echo(f"board score: {result.board.score:.3f}  conflict: {result.board.conflict}")
    typer.echo(f"route: {result.route}")
    for warning in result.warnings:
        typer.echo(f"warning: {warning}")

    _print_debate_and_outcome(result)

    if result.report is not None:
        typer.echo("=== REPORT ===")
        typer.echo(render_markdown(result.report))


def _print_week(summary: WeekSummary) -> None:
    outcomes = ", ".join(f"{ticker} {label}" for ticker, label in summary.outcomes.items())
    typer.echo(f"{summary.decision_day}: {outcomes} | equity {summary.equity:,.2f}")


def _print_run_summary(result: RunResult) -> None:
    """M6-FR-14: end equity, closed trades, open-at-end trades listed apart, cancelled orders."""
    closed = [trade for trade in result.trades if trade.status == "closed"]
    wins = sum(1 for trade in closed if trade.pnl is not None and trade.pnl > 0)
    total = sum((trade.pnl or Decimal(0) for trade in closed), Decimal(0))
    typer.echo(f"run {result.run_id} completed: end equity {result.end_equity:,.2f}")
    typer.echo(f"closed trades: {len(closed)} ({wins} wins), P&L {total:,.2f}")
    still_open = [trade for trade in result.trades if trade.status == "open_at_end"]
    typer.echo(f"open at window end: {len(still_open)}")
    for trade in still_open:
        typer.echo(
            f"  {trade.ticker} {trade.shares} @ {trade.entry_price} "
            f"marked {trade.exit_price}, P&L {trade.pnl}"
        )
    cancelled = sum(1 for trade in result.trades if trade.status == "cancelled")
    typer.echo(f"cancelled orders: {cancelled}")


@app.command()
def backtest(
    tickers: Annotated[str | None, typer.Option("--tickers", help="Comma-separated")] = None,
    start: Annotated[str | None, typer.Option("--start", help="YYYY-MM-DD")] = None,
    weeks: Annotated[int | None, typer.Option("--weeks")] = None,
    seed: Annotated[int | None, typer.Option("--seed")] = None,
    cash: Annotated[str | None, typer.Option("--cash")] = None,
    resume: Annotated[str | None, typer.Option("--resume", help="Run ID to resume")] = None,
    policy: Annotated[
        str | None, typer.Option("--policy", help="bullpit (default), single_agent, ...")
    ] = None,
    source_run: Annotated[
        str | None, typer.Option("--source-run", help="bullpit_fixed: the Bull Pit run to replay")
    ] = None,
) -> None:
    """Start a weekly backtest, or continue one with --resume RUN_ID."""
    try:
        settings = get_settings()
    except BullPitError as exc:
        typer.echo(f"config          FAIL    {exc}")
        raise typer.Exit(code=1) from None

    configure_logging(settings)
    _upgrade_journal_schema(settings)
    sessions = make_sessions(make_engine(journal_url(settings)))

    try:
        if resume is not None:
            given = (tickers, start, weeks, seed, cash, policy, source_run)
            if any(option is not None for option in given):
                typer.echo("--resume takes no other options: the run keeps its own inputs")
                raise typer.Exit(code=2)
            run_id = resume
        else:
            if tickers is None or start is None:
                typer.echo("--tickers and --start are required unless --resume is given")
                raise typer.Exit(code=2)
            if policy is not None and policy not in get_args(Policy):
                typer.echo(f"--policy must be one of: {', '.join(get_args(Policy))}")
                raise typer.Exit(code=2)
            run_id = start_backtest(
                tickers.split(","),
                date.fromisoformat(start),
                weeks=settings.backtest_weeks if weeks is None else weeks,
                seed=settings.llm_seed if seed is None else seed,
                starting_cash=settings.backtest_starting_cash if cash is None else Decimal(cash),
                settings=settings,
                sessions=sessions,
                asset_lookup=make_alpaca_broker(settings),
                policy=cast(Policy, policy or "bullpit"),
                source_run=source_run,
            )
    except (ValueError, InvalidOperation):
        typer.echo("--start must be YYYY-MM-DD and --cash a number")
        raise typer.Exit(code=2) from None
    except ConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2) from None

    try:
        result = run_backtest(run_id, settings=settings, sessions=sessions, on_week=_print_week)
    except ConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2) from None
    except Exception as exc:
        typer.echo(f"Stopped: {exc}. Resume with: bullpit backtest --resume {run_id}")
        raise typer.Exit(code=1) from None

    if result.status == "paused":
        typer.echo(f"Paused: {result.reason}. Resume with: bullpit backtest --resume {run_id}")
        raise typer.Exit(code=3)
    _print_run_summary(result)


@app.command(name="eval")
def eval_command(
    runs: Annotated[str, typer.Option("--runs", help="Comma-separated completed run IDs")],
    out: Annotated[Path, typer.Option("--out", help="Output directory")] = Path("docs/results"),
) -> None:
    """Write results.md and the charts for finished backtest runs."""
    try:
        settings = get_settings()
    except BullPitError as exc:
        typer.echo(f"config          FAIL    {exc}")
        raise typer.Exit(code=1) from None

    configure_logging(settings)
    _upgrade_journal_schema(settings)
    sessions = make_sessions(make_engine(journal_url(settings)))
    try:
        path = evaluate(runs.split(","), out, settings=settings, sessions=sessions)
    except ConfigError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=2) from None
    except BullPitError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1) from None
    typer.echo(f"wrote {path}")


if __name__ == "__main__":
    app()
