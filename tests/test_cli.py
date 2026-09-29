"""CLI tests (M4-AC-14, M5-AC-10): `bullpit request` prints the FR-18 debate
turns, attempts and OUTCOME line for a buy and for a no-trade result, and
the Markdown report under `=== REPORT ===`, exiting 0.

`run_request` and everything around it (journal schema upgrade, engine,
sessions, the broker, logging) are patched out: this only checks the CLI's
own formatting of an already-built `RequestState`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import patch

from typer.testing import CliRunner

from bullpit.cli import app
from bullpit.config import Settings
from bullpit.domain import Account, SizedOrder
from bullpit.report.builder import build_report
from bullpit.state import (
    CheckedPoint,
    DebateTurn,
    Recommendation,
    RequestState,
    RiskVerdict,
    TradeAttempt,
)

runner = CliRunner()

_ORDER = SizedOrder(
    ticker="AAPL",
    shares=32,
    reference_price=Decimal("182"),
    stop_loss=Decimal("174.00"),
    take_profit=Decimal("194.00"),
    exit_style="normal",
    cost=Decimal("5824.00"),
    max_loss=Decimal("256.00"),
    max_gain=Decimal("384.00"),
    limit="target",
    limit_shares={"target": 32, "risk": 125, "cap": 54, "cash": 527},
)


def _fake_settings() -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        alpaca_api_key="fake-key",
        alpaca_secret_key="fake-secret",
        groq_api_key="fake-groq-key",
        sec_contact_email="test@example.com",
    )


def _buy_state() -> RequestState:
    recommendation = Recommendation(
        ticker="AAPL",
        action="buy",
        target_weight=Decimal("0.06"),
        exit_style="normal",
        confidence=0.62,
        decisive_evidence=["T1"],
        reasoning="Trend and margins outweigh the news risk.",
        flagged=False,
    )
    verdict = RiskVerdict(
        decision="approve",
        reason="Looks sound.",
        requested_shares=None,
        clamped=False,
        flagged=False,
    )
    turn = DebateTurn(
        side="bull",
        round=1,
        points=[
            CheckedPoint(claim="Momentum favours buying", evidence_ids=["T1"], unsupported=False)
        ],
        concessions=[],
        conviction=0.7,
        word_count=3,
        over_word_limit=False,
        flagged=False,
    )
    return RequestState(
        request_id="20241018-AAPL-cli",
        mode="backtest",
        as_of=date(2024, 10, 18),
        ticker="AAPL",
        company_name="Apple Inc.",
        account=Account(cash=Decimal("96000"), equity=Decimal("100000")),
        route="debate",
        debate=[turn],
        attempts=[TradeAttempt(recommendation=recommendation, sized_order=_ORDER, verdict=verdict)],
        sized_order=_ORDER,
        outcome="buy",
    )


def _no_trade_state() -> RequestState:
    return RequestState(
        request_id="20241018-AAPL-cli2",
        mode="backtest",
        as_of=date(2024, 10, 18),
        ticker="AAPL",
        company_name="Apple Inc.",
        account=Account(cash=Decimal("96000"), equity=Decimal("100000")),
        route="no_trade",
        outcome="no_trade",
        no_trade_reason="Signals too weak for a debate (board score +0.03, no conflict).",
    )


def _invoke(fixed_state: RequestState) -> object:
    with (
        patch("bullpit.cli.get_settings", return_value=_fake_settings()),
        patch("bullpit.cli.configure_logging"),
        patch("bullpit.cli._upgrade_journal_schema"),
        patch("bullpit.cli.make_engine"),
        patch("bullpit.cli.make_sessions"),
        patch("bullpit.cli.make_alpaca_broker"),
        patch("bullpit.cli.run_request", return_value=fixed_state),
    ):
        return runner.invoke(
            app, ["request", "AAPL", "--mode", "backtest", "--as-of", "2024-10-18"]
        )


class TestRequestCommandPrintsM4Output:
    def test_buy_outcome(self) -> None:
        result = _invoke(_buy_state())

        assert result.exit_code == 0, result.output
        assert "bull round 1: conviction 0.70" in result.output
        assert "Momentum favours buying (T1)" in result.output
        assert "attempt 1: buy 6.00% normal (confidence 0.62)" in result.output
        assert (
            "sized: 32 shares @ ref 182.00, stop 174.00, take-profit 194.00 (set by target)"
            in result.output
        )
        assert "review: approve - Looks sound." in result.output
        assert (
            "OUTCOME: BUY 32 AAPL @ ref 182.00, stop 174.00, take-profit 194.00, "
            "max loss 256.00, gain 384.00 (set by target)"
        ) in result.output

    def test_no_trade_outcome(self) -> None:
        result = _invoke(_no_trade_state())

        assert result.exit_code == 0, result.output
        assert (
            "OUTCOME: NO TRADE: Signals too weak for a debate (board score +0.03, no conflict)."
        ) in result.output


class TestRequestCommandPrintsReport:
    def test_buy_prints_the_report(self) -> None:
        state = _buy_state()
        report = build_report(
            state,
            prose=None,
            prose_source="none",
            market=None,
            models=[],
            generated_at=datetime(2024, 10, 18, 21, 0, tzinfo=UTC),
        )

        result = _invoke(state.model_copy(update={"report": report}))

        assert result.exit_code == 0, result.output
        assert "=== REPORT ===" in result.output
        assert "32 shares, about $5,824.00 (5.8% of equity)" in result.output
