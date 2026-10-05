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
    TradeRecord,
    approval_record,
    trade_record,
)
from bullpit.risk.sizing import round_cent
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
    """Buy now at the price the report was made at, unless `seen_price` is given."""
    order = client.get(f"/requests/{request_id}/report").json().get("order")
    if order is not None:
        body.setdefault("seen_price", order["reference_price"])
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
    _record_approval(env.sessions, other_id, other["order"], approved=shares - 1)

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


def _preview(client: TestClient, request_id: str, **body: Any) -> Any:
    return client.post(f"/requests/{request_id}/order-preview", json=body)


def _distances(order: dict[str, Any]) -> tuple[Decimal, Decimal]:
    """The plan's risk and reward per share, which every repriced order keeps."""
    reference = Decimal(order["reference_price"])
    return reference - Decimal(order["stop_loss"]), Decimal(order["take_profit"]) - reference


def _record_approval(
    sessions: sessionmaker[Session],
    request_id: str,
    order: dict[str, Any],
    *,
    approved: int | None = None,
    limit: Decimal | None = None,
) -> None:
    """The approvals row the API commits before the order step, written by hand to
    stand for a process that died right after it."""
    reference = Decimal(order["reference_price"])
    entry = reference if limit is None else limit
    repriced_stop = entry - (reference - Decimal(order["stop_loss"]))
    repriced_target = entry + (Decimal(order["take_profit"]) - reference)
    decision = ApprovalDecision(
        decision="approved",
        recommended_shares=order["shares"],
        approved_shares=order["shares"] if approved is None else approved,
        decided_by="owner",
        order_type="market" if limit is None else "limit",
        entry_price=entry,
        limit_price=limit,
        stop_loss=repriced_stop,
        take_profit=repriced_target,
        seen_price=None if limit is not None else entry,
    )
    with sessions() as session:
        session.add(approval_record(request_id, decision, decided_at=naive_utc_now()))
        session.commit()


@pytest.mark.parametrize(
    ("order_exists", "is_limit"), [(True, False), (False, False), (True, True)]
)
def test_recorded_approval_past_expiry(env: Env, order_exists: bool, is_limit: bool) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    shares = report["order"]["shares"]
    limit = Decimal(report["order"]["reference_price"]) - 5 if is_limit else None
    _record_approval(env.sessions, request_id, report["order"], limit=limit)
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
        # The lookup carries the approved entry as the trade's reference price (FR-20).
        assert env.broker.lookups == [limit or Decimal(report["order"]["reference_price"])]
    else:
        assert detail["status"] == "expired"
        assert (
            detail["status_reason"]
            == "Approved, but no order was placed before the report expired."
        )


def _limit_body(report: dict[str, Any]) -> dict[str, Any]:
    """A limit well below the report's price, which is also the price now."""
    return {
        "order_type": "limit",
        "limit_price": str(Decimal(report["order"]["reference_price"]) - 5),
    }


@pytest.mark.parametrize("mode", ["market", "limit", "advanced"])
def test_order_equals_recorded_approval(env: Env, mode: str) -> None:
    """The request sent to Alpaca is built from the committed approvals row
    (M11.1-AC-9), and the trades row records its entry as the reference price."""
    client = env.client()
    request_id, report = env.waiting_report(client)
    order = report["order"]
    reference = Decimal(order["reference_price"])
    bodies = {
        "market": {},
        "limit": _limit_body(report),
        "advanced": {
            "advanced": True,
            "shares": order["shares"] + 2,
            "stop_loss": str(reference - 1),
            "take_profit": str(reference + 2),
            "confirm_overrides": True,
        },
    }

    done = _approve(client, request_id, **bodies[mode])

    assert done.status_code == 200, done.text
    (row,) = _rows(env.sessions, ApprovalRecord)
    (placed,) = env.broker.submitted
    assert placed.client_order_id == f"{ORDER_ID_PREFIX}{request_id}"
    assert (placed.shares, placed.reference_price) == (
        row.approved_shares,
        Decimal(row.entry_price),
    )
    assert (placed.stop_loss, placed.take_profit) == (
        Decimal(row.stop_loss),
        Decimal(row.take_profit),
    )
    assert placed.order_type == row.order_type == ("limit" if mode == "limit" else "market")
    assert placed.limit_price == (None if row.limit_price is None else Decimal(row.limit_price))
    (trade_row,) = _rows(env.sessions, TradeRecord)
    assert (trade_row.reference_price, trade_row.order_type) == (row.entry_price, row.order_type)
    if mode == "limit":
        limit = round_cent(reference - 5)
        assert placed.limit_price == limit == placed.reference_price
        assert placed.stop_loss == round_cent(limit - (reference - Decimal(order["stop_loss"])))
    if mode == "advanced":
        assert (placed.shares, placed.stop_loss) == (order["shares"] + 2, round_cent(reference - 1))
        assert row.overrides == ["custom_exits", "size_above_plan"]


def test_a_recorded_limit_approval_is_resent_as_a_limit_order(env: Env) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    limit = Decimal(report["order"]["reference_price"]) - 5
    _record_approval(env.sessions, request_id, report["order"], limit=limit)

    finished = _approve(client, request_id, order_type="market")  # the body is ignored

    assert finished.status_code == 200, finished.text
    (placed,) = env.broker.submitted
    assert (placed.order_type, placed.limit_price, placed.reference_price) == (
        "limit",
        limit,
        limit,
    )


def test_pending_limit_reserves_cash_at_limit(env: Env) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    limit = Decimal(report["order"]["reference_price"]) - 5
    # A waiting limit order in another ticker holds all but $1,000 of Alpaca's cash.
    _seed_pending(env.sessions, "MSFT", shares=990, reference=Decimal(99000) / 990, limit=True)

    refused = _approve(client, request_id, **_limit_body(report))

    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "rules"
    assert refused.json()["max_shares"] == int(Decimal("1000") // limit)  # priced at the limit
    assert env.broker.submitted == []


def test_preview_happy_path(env: Env) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    order = report["order"]
    risk, reward = _distances(order)
    env.price = Decimal("230.00")  # the live price is not the report's close

    market = _preview(client, request_id)

    assert market.status_code == 200, market.text
    body = market.json()
    assert Decimal(body["price"]) == Decimal(body["entry_price"]) == Decimal("230.00")
    assert Decimal(body["stop_loss"]) == round_cent(Decimal("230") - risk)
    assert Decimal(body["take_profit"]) == round_cent(Decimal("230") + reward)
    assert body["shares"] == order["shares"]
    assert 0 < body["max_shares"] <= order["shares"]
    assert Decimal(body["cost"]) == Decimal("230.00") * order["shares"]
    assert (body["overrides"], body["warnings"]) == ([], [])

    limit = _preview(client, request_id, order_type="limit", limit_price="200").json()
    assert Decimal(limit["entry_price"]) == Decimal("200.00")
    assert Decimal(limit["stop_loss"]) == round_cent(Decimal("200") - risk)
    assert Decimal(limit["price"]) == Decimal("230.00")  # the live price still shows
    assert limit["warnings"] == []

    at_market = _preview(client, request_id, order_type="limit", limit_price="231").json()
    assert [w["code"] for w in at_market["warnings"]] == ["limit_at_or_above_price"]
    assert env.broker.submitted == [] and _rows(env.sessions, ApprovalRecord) == []


def test_preview_refusals(env: Env) -> None:
    client = env.client()
    assert _preview(client, "no-such-request").status_code == 404
    request_id, report = env.waiting_report(client)

    missing = _preview(client, request_id, order_type="limit")
    assert missing.status_code == 422 and missing.json()["code"] == "invalid_request"

    env.price = None  # the price read fails: nothing is invented
    market = _preview(client, request_id).json()
    assert market["price"] is None and market["entry_price"] is None
    assert market["stop_loss"] is None and market["cost"] is None
    assert [w["code"] for w in market["warnings"]] == ["price_unavailable"]
    limit = _preview(client, request_id, order_type="limit", limit_price="200").json()
    assert limit["price"] is None and Decimal(limit["entry_price"]) == Decimal("200.00")
    assert [w["code"] for w in limit["warnings"]] == ["price_unavailable"]

    env.price = Decimal(report["order"]["reference_price"])
    assert _approve(client, request_id).status_code == 200
    done = _preview(client, request_id)
    assert done.status_code == 409 and done.json()["code"] == "not_awaiting"


def test_flow_buy_now(env: Env) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    order = report["order"]
    risk, reward = _distances(order)
    env.price = Decimal(order["reference_price"]) + 3  # the market moved since the report

    preview = _preview(client, request_id).json()
    seen = Decimal(preview["entry_price"])
    done = _approve(client, request_id, seen_price=str(seen))

    assert done.status_code == 200, done.text
    (placed,) = env.broker.submitted
    assert placed.order_type == "market" and placed.limit_price is None
    assert (placed.reference_price, placed.shares) == (seen, order["shares"])
    assert (placed.stop_loss, placed.take_profit) == (
        round_cent(seen - risk),
        round_cent(seen + reward),
    )
    assert (placed.stop_loss, placed.take_profit) == (
        Decimal(preview["stop_loss"]),
        Decimal(preview["take_profit"]),
    )
    (trade,) = client.get("/trades").json()
    assert (trade["status"], Decimal(trade["reference_price"])) == ("pending", seen)

    _filled(env, placed)
    assert client.post("/fill-check").status_code == 200
    (trade,) = client.get("/trades").json()
    assert (trade["status"], trade["entry_date"]) == ("open", "2024-07-08")


def test_flow_advanced(env: Env) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    order = report["order"]
    reference = Decimal(order["reference_price"])
    edits = {
        "advanced": True,
        "shares": order["shares"] + 2,
        "stop_loss": str(round_cent(reference - 2)),
        "take_profit": str(round_cent(reference + 3)),
    }

    preview = _preview(client, request_id, **edits).json()
    assert preview["overrides"] == ["custom_exits", "size_above_plan"]
    assert preview["max_shares"] >= order["shares"] + 2

    refused = _approve(client, request_id, **edits)
    assert refused.status_code == 409
    assert refused.json()["code"] == "override_not_confirmed"
    assert refused.json()["overrides"] == ["custom_exits", "size_above_plan"]
    assert env.broker.submitted == [] and _rows(env.sessions, ApprovalRecord) == []

    done = _approve(client, request_id, confirm_overrides=True, **edits)

    assert done.status_code == 200, done.text
    (row,) = _rows(env.sessions, ApprovalRecord)
    assert row.overrides == ["custom_exits", "size_above_plan"]
    (placed,) = env.broker.submitted
    assert (placed.shares, placed.stop_loss) == (order["shares"] + 2, round_cent(reference - 2))
    assert done.json()["approval"]["overrides"] == ["custom_exits", "size_above_plan"]
    assert done.json()["trade"]["overrides"] == ["custom_exits", "size_above_plan"]
    (trade,) = client.get("/trades").json()
    assert trade["overrides"] == ["custom_exits", "size_above_plan"]
    (summary,) = client.get("/requests").json()
    assert summary["overrides"] == ["custom_exits", "size_above_plan"]


def _filled(env: Env, placed: Trade) -> None:
    """Alpaca now reports the entry filled."""
    env.broker.live_orders[placed.client_order_id] = LiveOrder(
        trade=placed.model_copy(
            update={
                "status": "open",
                "entry_date": date(2024, 7, 8),
                "entry_price": placed.reference_price,
            }
        ),
        exits_active=True,
        exits_cancelled_at=None,
        partial=False,
    )


def test_cancel_happy_path(env: Env) -> None:
    client = env.client()
    request_id, _ = env.waiting_report(client)
    assert _approve(client, request_id).status_code == 200
    (placed,) = env.broker.submitted

    cancelled = client.post(f"/trades/{request_id}/cancel")

    assert cancelled.status_code == 200, cancelled.text
    assert (cancelled.json()["status"], cancelled.json()["cancel_reason"]) == (
        "cancelled",
        "cancelled by owner",
    )
    assert env.broker.cancelled == [placed.order_id]
    again = client.post(f"/trades/{request_id}/cancel")
    assert again.status_code == 409 and again.json()["code"] == "not_cancellable"
    assert client.post("/trades/no-such-request/cancel").status_code == 404


def test_cancel_filled_trade_refused(env: Env) -> None:
    client = env.client()
    request_id, _ = env.waiting_report(client)
    assert _approve(client, request_id).status_code == 200
    _filled(env, env.broker.submitted[0])
    assert client.post("/fill-check").status_code == 200  # the journal now says open

    refused = client.post(f"/trades/{request_id}/cancel")

    assert refused.status_code == 409 and refused.json()["code"] == "not_cancellable"
    assert env.broker.cancelled == []  # nothing was asked of Alpaca
    assert client.get("/trades").json()[0]["status"] == "open"


def test_cancel_race(env: Env) -> None:
    """The entry fills as the cancel crosses: Alpaca ignores the cancel, the re-read
    shows the fill, and the row is updated as the fill check would."""
    client = env.client()
    request_id, _ = env.waiting_report(client)
    assert _approve(client, request_id).status_code == 200
    (placed,) = env.broker.submitted
    _filled(env, placed)  # the journal still says pending

    refused = client.post(f"/trades/{request_id}/cancel")

    assert refused.status_code == 409 and refused.json()["code"] == "not_cancellable"
    assert env.broker.cancelled == [placed.order_id]
    (trade,) = client.get("/trades").json()
    assert (trade["status"], trade["entry_date"]) == ("open", "2024-07-08")


def test_flow_limit(env: Env) -> None:
    client = env.client()
    request_id, report = env.waiting_report(client)
    order = report["order"]
    risk, reward = _distances(order)
    limit = round_cent(Decimal(order["reference_price"]) - 5)

    preview = _preview(client, request_id, order_type="limit", limit_price=str(limit)).json()
    assert Decimal(preview["entry_price"]) == limit
    done = _approve(client, request_id, **_limit_body(report))

    assert done.status_code == 200, done.text
    (placed,) = env.broker.submitted
    assert (placed.order_type, placed.limit_price, placed.reference_price) == (
        "limit",
        limit,
        limit,
    )
    assert (placed.stop_loss, placed.take_profit) == (
        round_cent(limit - risk),
        round_cent(limit + reward),
    )
    (trade,) = client.get("/trades").json()
    assert (trade["status"], trade["order_type"], Decimal(trade["limit_price"])) == (
        "pending",
        "limit",
        limit,
    )
    assert trade["overrides"] == []
    (summary,) = client.get("/requests").json()
    assert (summary["order_type"], summary["overrides"]) == ("limit", [])

    cancelled = client.post(f"/trades/{request_id}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    result = client.post("/fill-check").json()  # the fill check leaves the row alone
    assert result["changed"] == []
    (trade,) = client.get("/trades").json()
    assert (trade["status"], trade["cancel_reason"]) == ("cancelled", "cancelled by owner")
    with _patch_sec(), _patch_prices(), _patch_news():  # the lock is free again
        assert client.post("/requests", json={"ticker": "AAPL"}).status_code == 202


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
    sessions: sessionmaker[Session],
    ticker: str,
    *,
    shares: int,
    reference: Decimal,
    tag: str = "",
    limit: bool = False,
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
        order_type="limit" if limit else "market",
        limit_price=reference if limit else None,
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
