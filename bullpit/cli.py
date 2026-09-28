"""Typer entry points. `doctor` is the only command in M0; more arrive from M3."""

from __future__ import annotations

import typer

from bullpit.config import get_settings
from bullpit.doctor import Status, run_all_checks
from bullpit.errors import BullPitError
from bullpit.logging import configure_logging

app = typer.Typer(add_completion=False, help="Bull Pit: research, not financial advice.")


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


if __name__ == "__main__":
    app()
