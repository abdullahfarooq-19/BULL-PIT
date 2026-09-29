"""The backtest runner on recorded fixtures and the scripted fake LLM
(M6-AC-3, AC-4, AC-5, AC-7, AC-8; dev-plan.md sec7.1 and sec7.2).

Every symbol gets the AAPL fixture's bars (as in test_graph.py). RecordingLLM's
trader answers "no trade" unless a test queues a buy for it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session, sessionmaker

from bullpit.config import Settings
from bullpit.domain import Account, Asset
from bullpit.errors import ConfigError, QuotaExhausted
from bullpit.journal.models import (
    ApprovalRecord,
    BacktestRun,
    DebateTurnRecord,
    EquitySnapshot,
    RecommendationRecord,
    ReportRecord,
    Request,
    SignalRecord,
    TradeRecord,
)
from bullpit.llm.gateway import CompletionFn, CompletionReply, CompletionRequest
from bullpit.runners.backtest import RunResult, run_backtest, start_backtest
from tests.agents.conftest import FIRST_LINE_TRADER
from tests.broker.fake_broker import FakeBroker
from tests.conftest import fixture_path
from tests.test_graph import RecordingLLM, _patch_news, _patch_prices, _patch_sec

START = date(2024, 7, 1)
DECISION_DAYS = [date(2024, 7, 5), date(2024, 7, 12), date(2024, 7, 19)]
TICKERS = ["AAPL", "BRK-B"]


def _trader_reply(action: str, weight: float) -> str:
    return json.dumps(
        {
            "action": action,
            "target_weight": weight,
            "exit_style": "normal",
            "confidence": 0.6,
            "decisive_evidence": ["T1"],
            "reasoning": "Scripted for the test.",
        }
    )


NO_TRADE = _trader_reply("no_trade", 0.0)
BUY = _trader_reply("buy", 0.06)


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """Raise the per-minute pacing so the real token bucket never sleeps."""
    return settings.model_copy(update={"llm_tpm_limit": 1_000_000, "llm_rpm_limit": 1_000})


@pytest.fixture(autouse=True)
def _recorded_data() -> Iterator[None]:
    with _patch_sec(), _patch_prices(), _patch_news():
        yield


def _lookup() -> FakeBroker:
    return FakeBroker(
        account=Account(cash=Decimal(0), equity=Decimal(0)),
        assets={
            symbol: Asset(symbol=symbol, name=symbol, tradable=True, active=True)
            for symbol in TICKERS
        },
    )


def _start(
    settings: Settings,
    sessions: sessionmaker[Session],
    *,
    weeks: int = 3,
    start: date = START,
    cash: Decimal = Decimal("100000"),
) -> str:
    return start_backtest(
        TICKERS,
        start,
        weeks=weeks,
        seed=1,
        starting_cash=cash,
        settings=settings,
        sessions=sessions,
        asset_lookup=_lookup(),
    )


def _rows[T](sessions: sessionmaker[Session], model: type[T]) -> list[T]:
    with sessions() as session:
        return list(session.scalars(select(model)))


class TestHappyPath:
    def test_three_weeks_two_tickers_one_buy(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        llm = RecordingLLM(trader_reply=NO_TRADE)
        llm.queue(FIRST_LINE_TRADER, BUY)  # the first trader call: AAPL in week 1
        run_id = _start(settings, sessions)

        weeks = []
        result = run_backtest(
            run_id, settings=settings, sessions=sessions, completion_fn=llm, on_week=weeks.append
        )

        assert result.status == "completed"
        assert [week.decision_day for week in weeks] == DECISION_DAYS
        requests = _rows(sessions, Request)
        assert len(requests) == 6  # 3 weeks x 2 tickers
        assert {request.run_id for request in requests} == {run_id}
        assert len(_rows(sessions, ReportRecord)) == 6
        assert len(_rows(sessions, EquitySnapshot)) == 14  # every session, 2024-07-01 to 07-19

        with sessions() as session:
            run = session.get(BacktestRun, run_id)
            assert run is not None
            assert (run.status, run.checkpoint) == ("completed", DECISION_DAYS[-1])

        (approval,) = _rows(sessions, ApprovalRecord)
        assert approval.request_id == f"20240705-AAPL-{run_id}"
        assert (approval.decision, approval.decided_by) == ("approved", "backtest_policy")
        assert approval.recommended_shares == approval.approved_shares

        (trade,) = _rows(sessions, TradeRecord)
        assert trade.request_id == approval.request_id
        assert trade.entry_date == date(2024, 7, 8)  # the next session's open
        bars = pd.read_parquet(fixture_path("prices", "aapl_yf.parquet")).set_index("Date")
        july_8_open = Decimal(
            str(float(bars.loc[bars.index.date == trade.entry_date, "Open"].iloc[0]))
        )
        assert Decimal(trade.entry_price or "0") == (july_8_open * Decimal("1.0005")).quantize(
            Decimal("0.01")
        )
        assert trade.status in ("closed", "open_at_end")

        loss_warnings = {
            request.as_of: _report_of(sessions, request.id)["loss_warning"] for request in requests
        }
        assert loss_warnings[DECISION_DAYS[0]] is None  # no history 7 days back yet
        assert loss_warnings[DECISION_DAYS[1]] is False
        assert loss_warnings[DECISION_DAYS[2]] is False


def _report_of(sessions: sessionmaker[Session], request_id: str) -> dict[str, object]:
    with sessions() as session:
        row = session.scalars(
            select(ReportRecord).where(ReportRecord.request_id == request_id)
        ).one()
        return row.report


class TestSameDayBuysShareCash:
    def test_second_buy_is_sized_on_the_reduced_cash(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        # Raise the caps so cash, not the 10% cap or 1% risk, is the binding limit.
        settings = settings.model_copy(
            update={"max_position_pct": Decimal("0.6"), "risk_per_trade_pct": Decimal("0.5")}
        )
        llm = RecordingLLM(trader_reply=_trader_reply("buy", 0.6))
        run_id = _start(settings, sessions, weeks=2)

        run_backtest(run_id, settings=settings, sessions=sessions, completion_fn=llm)

        first, second = (
            _final_order(sessions, f"20240705-{ticker}-{run_id}") for ticker in TICKERS
        )
        assert first["limit"] != "cash"
        assert second["limit"] == "cash"
        assert int(second["shares"]) < int(first["shares"])  # type: ignore[call-overload]
        cash_after_first = Decimal("100000") - Decimal(str(first["cost"]))
        assert Decimal(str(second["cost"])) <= cash_after_first
        assert all(Decimal(row.cash) >= 0 for row in _rows(sessions, EquitySnapshot))


def _final_order(sessions: sessionmaker[Session], request_id: str) -> dict[str, object]:
    with sessions() as session:
        row = session.scalars(
            select(RecommendationRecord).where(RecommendationRecord.request_id == request_id)
        ).one()
        assert row.final_order is not None
        return row.final_order


_VOLATILE = {"created_at", "finished_at", "generated_at"}


def _journal(sessions: sessionmaker[Session], run_id: str) -> list[str]:
    """Every table but `llm_calls`, as text with row IDs, wall-clock fields and
    the run ID removed, sorted (specs-plan sec11.5; D-M6-17)."""
    with sessions() as session:
        request_ids = list(session.scalars(select(Request.id).where(Request.run_id == run_id)))
        by_request = [SignalRecord, DebateTurnRecord, RecommendationRecord, ReportRecord]
        rows: list[object] = [
            *session.scalars(select(BacktestRun).where(BacktestRun.id == run_id)),
            *session.scalars(select(Request).where(Request.run_id == run_id)),
            *session.scalars(select(TradeRecord).where(TradeRecord.run_id == run_id)),
            *session.scalars(select(EquitySnapshot).where(EquitySnapshot.run_id == run_id)),
            *session.scalars(
                select(ApprovalRecord).where(ApprovalRecord.request_id.in_(request_ids))
            ),
        ]
        for model in by_request:
            rows.extend(session.scalars(select(model).where(model.request_id.in_(request_ids))))
        lines = []
        for row in rows:
            data = {
                attr.key: getattr(row, attr.key)
                for attr in inspect(row).mapper.column_attrs
                if attr.key not in _VOLATILE and not (attr.key == "id" and isinstance(row.id, int))
            }
            if isinstance(row, ReportRecord):
                data["report"] = {k: v for k, v in data["report"].items() if k not in _VOLATILE}
            text = json.dumps({"table": type(row).__name__, **data}, default=str, sort_keys=True)
            lines.append(text.replace(run_id, "RUN"))
    return sorted(lines)


class FailsMidWeekTwo:
    """Wraps a completion function; once week 1 is done (`arm()`), the fifth call
    raises `error`: inside the first request of week 2, after real calls."""

    def __init__(self, inner: CompletionFn, error: Exception) -> None:
        self._inner = inner
        self._error = error
        self._calls_since_armed: int | None = None

    def arm(self) -> None:
        self._calls_since_armed = 0

    def __call__(self, request: CompletionRequest) -> CompletionReply:
        if self._calls_since_armed is not None:
            self._calls_since_armed += 1
            if self._calls_since_armed == 5:
                raise self._error
        return self._inner(request)


def _script() -> RecordingLLM:
    llm = RecordingLLM(trader_reply=NO_TRADE)
    llm.queue(FIRST_LINE_TRADER, BUY)
    return llm


class TestResume:
    @pytest.mark.parametrize(
        "error",
        [
            pytest.param(QuotaExhausted("daily budget"), id="quota"),
            pytest.param(RuntimeError("boom"), id="crash"),
        ],
    )
    def test_resume_matches_uninterrupted(
        self, settings: Settings, sessions: sessionmaker[Session], error: Exception
    ) -> None:
        interrupted_id = _start(settings, sessions)
        llm = _script()
        failing = FailsMidWeekTwo(llm, error)
        result: RunResult | None = None
        if isinstance(error, QuotaExhausted):
            result = run_backtest(
                interrupted_id,
                settings=settings,
                sessions=sessions,
                completion_fn=failing,
                on_week=lambda week: failing.arm(),
            )
            assert result.status == "paused"
        else:
            with pytest.raises(RuntimeError, match="boom"):
                run_backtest(
                    interrupted_id,
                    settings=settings,
                    sessions=sessions,
                    completion_fn=failing,
                    on_week=lambda week: failing.arm(),
                )

        # The failed week left nothing behind: only week 1 is in the journal.
        with sessions() as session:
            run = session.get(BacktestRun, interrupted_id)
            assert run is not None
            assert run.checkpoint == DECISION_DAYS[0]
            assert run.status == ("paused" if result else "stopped")
            request_count = len(
                list(session.scalars(select(Request).where(Request.run_id == interrupted_id)))
            )
            assert request_count == 2
            snapshots = session.scalars(
                select(EquitySnapshot).where(EquitySnapshot.run_id == interrupted_id)
            )
            assert len(list(snapshots)) == 4  # 2024-07-01, 02, 03 and 05

        # Same fake as before the failure: its one queued buy is already used.
        resumed = run_backtest(
            interrupted_id, settings=settings, sessions=sessions, completion_fn=llm
        )
        assert resumed.status == "completed"

        # The uninterrupted run replays the cached replies, so it costs nothing.
        clean_id = _start(settings, sessions)
        run_backtest(clean_id, settings=settings, sessions=sessions, completion_fn=_script())

        journal = _journal(sessions, clean_id)
        assert any('"table": "TradeRecord"' in line for line in journal)  # the buy is compared
        assert _journal(sessions, interrupted_id) == journal


class TestRefusals:
    def test_start_before_cutoff_refused(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        with pytest.raises(ConfigError, match="2024-07-01"):
            _start(settings, sessions, start=date(2024, 6, 28))

        assert _rows(sessions, BacktestRun) == []

    def test_resume_after_model_change_refused(
        self, settings: Settings, sessions: sessionmaker[Session]
    ) -> None:
        run_id = _start(settings, sessions)
        changed = settings.model_copy(update={"llm_large_model": "openai/another-model"})

        with pytest.raises(ConfigError, match=r"openai/gpt-oss-120b.*openai/another-model"):
            run_backtest(run_id, settings=changed, sessions=sessions, completion_fn=RecordingLLM())

        assert _rows(sessions, Request) == []
        with sessions() as session:
            run = session.get(BacktestRun, run_id)
            assert run is not None
            assert (run.status, run.checkpoint) == ("running", None)
