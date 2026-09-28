"""Typer entry points. `doctor` is the only command from M0; `request` (M3)
runs the graph end to end for one ticker (D-M3-6: a way to run and inspect
the graph long before the dashboard).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated, Literal, cast

import typer
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

from bullpit.broker.alpaca import make_alpaca_broker
from bullpit.clock import Clock, LiveClock, SimClock
from bullpit.config import Settings, get_settings
from bullpit.doctor import Status, run_all_checks
from bullpit.errors import BullPitError, ConfigError
from bullpit.journal.db import journal_url, make_engine, make_sessions
from bullpit.logging import configure_logging
from bullpit.runners.request import run_request
from bullpit.state import RequestState

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


if __name__ == "__main__":
    app()
