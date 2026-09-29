"""The API end to end, with recorded fixtures, a scripted LLM, a fake broker, a fixed
clock and a fake price source (M8-AC-1 to AC-5, AC-10, AC-11, AC-15).

Each test starts a real request through `POST /requests`; the background run
finishes before the test client returns, so the report and the pause are in the
journal when the next call is made.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from bullpit.api.app import create_app
from bullpit.approval.gate import ApprovalDecision
from bullpit.broker.alpaca import LiveOrder
from bullpit.config import Settings
from bullpit.domain import Account, Asset, Trade
from bullpit.errors import BrokerRejected, DataUnavailable
from bullpit.graph import ApprovalWiring, Deps, build_graph
from bullpit.journal.models import (
    ApprovalRecord,
    BacktestRun,
    EquitySnapshot,
    Request,
    trade_record,
)
from bullpit.runners.request import make_checkpointer, naive_utc_now, resume_live
from tests.broker.fake_broker import FakeOrderBroker
from tests.test_graph import RecordingLLM, _patch_news, _patch_prices, _patch_sec

NOW = datetime(2024, 7, 5, 22, 0, tzinfo=UTC)  # the close of Friday 5 July has passed
EXPIRED = NOW + timedelta(days=4)  # after Monday's close, the report's last session
ORDER_ID_PREFIX = "bullpit-"


@pytest.fixture
def settings(settings: Settings, tmp_path: Path) -> Settings:
    return settings.model_copy(
        update={
            "llm_tpm_limit": 1_000_000,
            "llm_rpm_limit": 1_000,
            "checkpoint_db_path": tmp_path / "checkpoints.db",
            "results_dir": tmp_path / "results",
        }
    )


class Env:
    """One journal, one broker, one clock and one price: `client()` builds an app
    over them, and building a second one is a restart of the process."""

    def __init__(self, settings: Settings, sessions: sessionmaker[Session]) -> None:
        self.settings = settings
        self.sessions = sessions
        self.broker = FakeOrderBroker(
            account=Account(cash=Decimal("100000"), equity=Decimal("100000")),
            assets={"AAPL": Asset(symbol="AAPL", name="Apple Inc.", tradable=True, active=True)},
        )
        self.now = NOW
        self.price: Decimal | None = None
        self.llm = RecordingLLM()

    def _latest_price(self, symbol: str) -> Decimal:
        if self.price is None:
            raise DataUnavailable("no price")
        return self.price

    def client(self) -> TestClient:
        app = create_app(
            self.settings,
            broker=self.broker,  # type: ignore[arg-type]
            sessions=self.sessions,
            checkpointer=make_checkpointer(self.settings),
            now=lambda: self.now,
            completion_fn=self.llm,
            latest_price=self._latest_price,
        )
        return TestClient(app)

    def start(self, client: TestClient, ticker: str = "AAPL") -> str:
        with _patch_sec(), _patch_prices(), _patch_news():
            response = client.post("/requests", json={"ticker": ticker})
        assert response.status_code == 202, response.text
        return str(response.json()["request_id"])

    def waiting_report(self, client: TestClient) -> tuple[str, dict[str, Any]]:
        """Starts a request and returns its ID and report; the price is left at the
        report's reference price, so nothing is stale."""
        request_id = self.start(client)
        report = client.get(f"/requests/{request_id}/report").json()
        self.price = Decimal(report["order"]["reference_price"])
        return request_id, report


@pytest.fixture
def env(settings: Settings, sessions: sessionmaker[Session]) -> Env:
    return Env(settings, sessions)


def _approve(client: TestClient, request_id: str, **body: Any) -> Any:
    return client.post(f"/requests/{request_id}/approval", json={"decision": "approve", **body})


def _rows(sessions: sessionmaker[Session], model: type[Any]) -> list[Any]:
    with sessions() as session:
        return list(session.query(model).all())


def test_endpoints_happy_path(env: Env, tmp_path: Path) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    env.price = Decimal(report["order"]["reference_price"]) * Decimal("1.03")  # stale

    detail = client.get(f"/requests/{request_id}").json()
    assert detail["status"] == "awaiting_approval"
    assert detail["stage"] == "awaiting_approval"
    assert detail["expires_at"] == "2024-07-08T20:00:00Z"
    assert [row["id"] for row in client.get("/requests").json()] == [request_id]

    stale = _approve(client, request_id)
    assert stale.status_code == 409 and stale.json()["code"] == "stale"
    done = _approve(client, request_id, confirm_stale=True)
    assert done.status_code == 200, done.text
    assert done.json()["trade"]["status"] == "pending"
    (approval,) = _rows(env.sessions, ApprovalRecord)
    assert approval.confirmations == ["stale"]
    assert Decimal(approval.latest_price) == env.price
    assert client.get(f"/requests/{request_id}").json()["status"] == "completed"
    assert [t["request_id"] for t in client.get("/trades").json()] == [request_id]

    env.broker.history = [(date(2024, 7, 5), Decimal("100000"))]
    summary = client.post("/fill-check").json()
    assert summary["snapshots"] == 1
    assert client.get("/equity").json() == [{"date": "2024-07-05", "equity": "100000"}]

    assert client.get("/backtests").json() == []
    assert client.get("/backtests/none/results").status_code == 404
    assert client.get("/results").json()["code"] == "not_found"
    _seed_backtest(env.sessions)
    (run,) = client.get("/backtests").json()
    assert Decimal(run["last_equity"]) == Decimal("100000")
    assert client.get(f"/backtests/{run['id']}/results").json()["equity"][0]["equity"] == "100000"
    results = tmp_path / "results"
    results.mkdir()
    (results / "results.md").write_text("# Results", encoding="utf-8")
    (results / "equity.png").write_bytes(b"png")
    assert client.get("/results").json() == {"markdown": "# Results", "images": ["equity.png"]}
    assert client.get("/results/files/equity.png").content == b"png"
    assert client.get("/results/files/results.md").status_code == 404


def _seed_backtest(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        session.add(
            BacktestRun(
                id="run00001",
                created_at=naive_utc_now(),
                tickers=["AAPL"],
                start_date=date(2024, 7, 1),
                end_date=date(2024, 7, 5),
                weeks=1,
                seed=1,
                starting_cash="100000",
                models={"small": "s", "large": "l"},
                assets=[],
                git_commit="abc",
                status="completed",
            )
        )
        session.flush()
        session.add(
            EquitySnapshot(
                run_id="run00001",
                day=date(2024, 7, 5),
                cash="100000",
                positions_value="0",
                equity="100000",
            )
        )
        session.commit()


def test_restart_keeps_waiting_request(env: Env) -> None:
    request_id, _ = env.waiting_report(env.client())

    restarted = env.client()  # a new app over the same journal and checkpoint files

    assert restarted.get(f"/requests/{request_id}").json()["status"] == "awaiting_approval"
    done = _approve(restarted, request_id)
    assert done.status_code == 200, done.text
    assert len(env.broker.submitted) == 1
    assert restarted.get(f"/requests/{request_id}").json()["status"] == "completed"


def test_more_shares_refused_by_api(env: Env) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    recommended = report["order"]["shares"]

    for shares in (recommended + 1, 0, -3):
        refused = _approve(client, request_id, shares=shares)
        assert refused.status_code == 409
        assert refused.json()["code"] == "shares_invalid"
    assert _approve(client, request_id, shares="lots").status_code == 422
    assert _rows(env.sessions, ApprovalRecord) == []
    assert env.broker.submitted == []

    fewer = _approve(client, request_id, shares=recommended - 1)
    assert fewer.status_code == 200, fewer.text
    (trade,) = env.broker.submitted
    assert trade.shares == recommended - 1
    assert (trade.stop_loss, trade.take_profit) == (
        Decimal(report["order"]["stop_loss"]),
        Decimal(report["order"]["take_profit"]),
    )


def test_one_order_per_approval(env: Env, settings: Settings) -> None:
    client = env.client()
    request_id, _ = env.waiting_report(client)

    first = _approve(client, request_id)
    second = _approve(client, request_id)  # the same approval sent twice

    assert first.status_code == 200
    assert second.status_code == 409 and second.json()["code"] == "not_awaiting"
    assert len(env.broker.submitted) == 1
    assert len(_rows(env.sessions, ApprovalRecord)) == 1

    # The process died after the decision was recorded and before the order step:
    # sending the approval again finishes it with the recorded decision, whatever the body says.
    env.broker.orders.clear()
    other_id, other = env.waiting_report(client)
    shares = other["order"]["shares"]
    _record_approval(env.sessions, other_id, shares - 1, shares)

    finished = _approve(client, other_id, shares=shares)

    assert finished.status_code == 200, finished.text
    assert [trade.shares for trade in env.broker.submitted] == [shares - 1]

    # Resuming with an approval payload but no committed approvals row places no order.
    env.broker.orders.clear()
    third_id = env.start(client)
    graph = build_graph(
        Deps(settings=settings, sessions=env.sessions, broker=env.broker, completion_fn=env.llm),
        approval=ApprovalWiring(make_checkpointer(settings), env.broker),  # type: ignore[arg-type]
    )
    decision = ApprovalDecision(
        decision="approved", recommended_shares=5, approved_shares=5, decided_by="owner"
    )
    with pytest.raises(BrokerRejected, match="no recorded owner approval"):
        resume_live(third_id, decision, graph, sessions=env.sessions)
    assert env.broker.submitted == []
    assert client.get(f"/requests/{third_id}").json()["status"] == "failed"


def _record_approval(
    sessions: sessionmaker[Session], request_id: str, approved: int, recommended: int
) -> None:
    with sessions() as session:
        session.add(
            ApprovalRecord(
                request_id=request_id,
                decision="approved",
                recommended_shares=recommended,
                approved_shares=approved,
                decided_by="owner",
                decided_at=naive_utc_now(),
                confirmations=[],
            )
        )
        session.commit()


@pytest.mark.parametrize("order_exists", [True, False])
def test_recorded_approval_past_expiry(env: Env, order_exists: bool) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    shares = report["order"]["shares"]
    _record_approval(env.sessions, request_id, shares, shares)
    if order_exists:  # the order reached Alpaca before the process died
        trade = Trade(
            client_order_id=f"{ORDER_ID_PREFIX}{request_id}",
            ticker="AAPL",
            submitted_on=date(2024, 7, 5),
            shares=shares,
            reference_price=Decimal(report["order"]["reference_price"]),
            stop_loss=Decimal(report["order"]["stop_loss"]),
            take_profit=Decimal(report["order"]["take_profit"]),
            status="pending",
        )
        env.broker.live_orders[trade.client_order_id] = LiveOrder(
            trade=trade, exits_active=True, exits_cancelled_at=None, partial=False
        )
    env.now = EXPIRED

    detail = client.get(f"/requests/{request_id}").json()

    assert env.broker.submitted == []  # nothing new is ever placed on an old report
    if order_exists:
        assert detail["status"] == "completed"
        assert detail["trade"]["client_order_id"] == f"{ORDER_ID_PREFIX}{request_id}"
    else:
        assert detail["status"] == "expired"
        assert (
            detail["status_reason"]
            == "Approved, but no order was placed before the report expired."
        )


def test_loss_warning_from_live_snapshots(env: Env) -> None:
    with env.sessions() as session:
        for day, equity in ((date(2024, 6, 28), "100000"), (date(2024, 7, 5), "90000")):
            session.add(EquitySnapshot(run_id=None, day=day, equity=equity))
        session.commit()
    client = env.client()
    request_id, report = env.waiting_report(client)

    assert report["loss_warning"] is True
    refused = _approve(client, request_id)
    assert refused.status_code == 409 and refused.json()["code"] == "loss_warning"
    assert env.broker.submitted == []
    confirmed = _approve(client, request_id, confirm_loss_warning=True)
    assert confirmed.status_code == 200
    (approval,) = _rows(env.sessions, ApprovalRecord)
    assert approval.confirmations == ["loss_warning"]


def test_expired_frees_lock(env: Env) -> None:
    client = env.client()
    request_id, _ = env.waiting_report(client)

    duplicate = client.post("/requests", json={"ticker": "AAPL"})
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "duplicate"
    assert "waiting for your decision" in duplicate.json()["message"]

    env.now = EXPIRED
    assert _approve(client, request_id).json()["code"] == "expired"
    assert client.get(f"/requests/{request_id}").json()["status"] == "expired"
    with _patch_sec(), _patch_prices(), _patch_news():
        assert client.post("/requests", json={"ticker": "aapl "}).status_code == 202


def test_pending_order_counts(env: Env) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    reference = Decimal(report["order"]["reference_price"])
    # Another ticker's approved order that hasn't filled: Alpaca's cash doesn't show it.
    cost = Decimal("99000")
    _seed_pending(env.sessions, "MSFT", shares=990, reference=cost / 990)

    refused = _approve(client, request_id)

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "rules"
    assert refused.json()["max_shares"] == int(Decimal("1000") // reference)
    assert env.broker.submitted == []

    # An unfilled order in the same ticker counts against the per-stock cap.
    assert (
        client.post(f"/requests/{request_id}/approval", json={"decision": "reject"}).status_code
        == 200
    )
    _seed_pending(env.sessions, "AAPL", shares=100, reference=Decimal("100"), tag="cap")
    request_id = env.start(client)
    detail = client.get(f"/requests/{request_id}").json()
    assert detail["status"] == "completed" and detail["outcome"] == "no_trade"


def _seed_pending(
    sessions: sessionmaker[Session], ticker: str, *, shares: int, reference: Decimal, tag: str = ""
) -> None:
    trade = Trade(
        client_order_id=f"bullpit-seed-{ticker}{tag}",
        ticker=ticker,
        submitted_on=date(2024, 7, 5),
        shares=shares,
        reference_price=reference,
        stop_loss=reference - 10,
        take_profit=reference + 15,
        status="pending",
    )
    with sessions() as session:
        session.add(
            Request(
                id=f"seed-{ticker}{tag}",
                mode="live",
                as_of=date(2024, 7, 5),
                created_at=naive_utc_now(),
                ticker=ticker,
                status="completed",
            )
        )
        session.flush()
        session.add(trade_record(f"seed-{ticker}{tag}", trade))
        session.commit()
