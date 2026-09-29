"""`bullpit eval` on fixture runs of every policy (M7-AC-2; dev-plan sec7.2
happy path)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.eval.baselines import Policy
from bullpit.eval.report import evaluate
from bullpit.runners.backtest import run_backtest, start_backtest
from tests.runners.test_backtest import (
    START,
    TICKERS,
    _forbidden,
    _lookup,
    _script,
    _SingleAgentLLM,
)
from tests.test_graph import _patch_news, _patch_prices, _patch_sec


@pytest.fixture
def settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"llm_tpm_limit": 1_000_000, "llm_rpm_limit": 1_000})


@pytest.fixture(autouse=True)
def _recorded_data() -> Iterator[None]:
    with _patch_sec(), _patch_prices(), _patch_news():
        yield


def _run(
    settings: Settings,
    sessions: sessionmaker[Session],
    policy: Policy,
    completion_fn: object,
    source_run: str | None = None,
) -> str:
    run_id = start_backtest(
        TICKERS,
        START,
        weeks=3,
        seed=1,
        starting_cash=Decimal("100000"),
        settings=settings,
        sessions=sessions,
        asset_lookup=_lookup(),
        policy=policy,
        source_run=source_run,
    )
    run_backtest(run_id, settings=settings, sessions=sessions, completion_fn=completion_fn)  # type: ignore[arg-type]
    return run_id


def test_eval_happy_path(
    settings: Settings, sessions: sessionmaker[Session], tmp_path: Path
) -> None:
    source = _run(settings, sessions, "bullpit", _script())
    run_ids = [
        source,
        _run(settings, sessions, "single_agent", _SingleAgentLLM()),
        _run(settings, sessions, "always_buy", _forbidden),
        _run(settings, sessions, "ma_rule", _forbidden),
        _run(settings, sessions, "bullpit_fixed", _forbidden, source),
    ]

    path = evaluate(run_ids, tmp_path / "results", settings=settings, sessions=sessions)

    text = path.read_text(encoding="utf-8")
    for policy in ("bullpit", "single_agent", "always_buy", "ma_rule", "bullpit_fixed"):
        assert f"| {policy} |" in text
    assert all(f"| buy and hold {ticker} |" in text for ticker in TICKERS)
    assert "## Limits" in text
    assert "can't tell skill from luck" in text
    for chart in ("equity.png", "drawdown.png", "calibration.png"):
        assert (path.parent / chart).stat().st_size > 0
