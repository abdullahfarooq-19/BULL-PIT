"""The Alpaca write side: the request it builds, idempotent submits, and the
order-to-trade mapping (M8-FR-1, FR-2, FR-3; M8-AC-5c, AC-7).

Order shapes are recorded Alpaca responses in tests/fixtures/alpaca/ (M8-T-3);
the filled, cancelled and partial ones are derived from them (see task.md). The
limit-entry shapes are M11.1-T-3's real orders (ADR-0008), plus two derived below.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from alpaca.common.exceptions import APIError
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.models import Order
from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
from requests import ConnectionError as RequestsConnectionError
from requests import Timeout

from bullpit.broker.alpaca import AlpacaBroker, live_order
from bullpit.domain import SizedOrder
from bullpit.errors import BrokerRejected

FIXTURES = Path(__file__).parent.parent / "fixtures" / "alpaca"
SUBMITTED_ON = date(2026, 9, 25)
REFERENCE = Decimal("12.50")
CLIENT_ORDER_ID = "bullpit-20260925-F-abcd1234"


def _load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def _limit_filled() -> dict[str, Any]:
    """`order_limit_pending` with the entry filled at 9.65 (derived: `status`,
    `filled_qty`, `filled_avg_price`, `filled_at`; the legs arm: take-profit `new`,
    stop `held`)."""
    order: dict[str, Any] = _load("order_limit_pending")
    order.update(
        status="filled", filled_qty="1", filled_avg_price="9.65", filled_at="2026-10-06T14:31:00Z"
    )
    order["legs"][0]["status"] = "new"
    return order


def _limit_stopped() -> dict[str, Any]:
    """`_limit_filled` with the stop leg filled at 9.30 on 2026-10-07 (derived: stop
    leg `status`, `filled_qty`, `filled_avg_price`, `filled_at`; take-profit
    `canceled` with `canceled_at`)."""
    order = _limit_filled()
    take_profit, stop = order["legs"]
    take_profit.update(status="canceled", canceled_at="2026-10-07T15:00:00Z")
    stop.update(
        status="filled", filled_qty="1", filled_avg_price="9.30", filled_at="2026-10-07T15:00:00Z"
    )
    return order


_DERIVED = {"order_limit_filled": _limit_filled, "order_limit_stopped": _limit_stopped}


def _order(name: str) -> Order:
    return Order.model_validate(_DERIVED[name]() if name in _DERIVED else _load(name))


def _api_error(message: str, status_code: int) -> APIError:
    """The APIError Alpaca's SDK raises: it reads the status from the HTTP error."""
    http_error = SimpleNamespace(response=SimpleNamespace(status_code=status_code))
    return APIError(message, http_error)


def _recorded_error(name: str) -> APIError:
    recorded = _load(name)
    return _api_error(recorded["message"], recorded["status_code"])


def _sized_order() -> SizedOrder:
    return SizedOrder(
        ticker="F",
        shares=1,
        reference_price=REFERENCE,
        stop_loss=Decimal("11.94"),
        take_profit=Decimal("13.19"),
        exit_style="normal",
        cost=REFERENCE,
        max_loss=Decimal("0.56"),
        max_gain=Decimal("0.69"),
        limit="target",
        limit_shares={"target": 1, "risk": 1, "cap": 1, "cash": 1},
    )


class FakeTradingClient:
    """Answers `submit_order` with a recorded order or a raised error, and
    `get_order_by_client_id` with a recorded order or a recorded 404."""

    def __init__(
        self,
        *,
        submit: Order | Exception,
        lookup: Order | Exception | None = None,
    ) -> None:
        self._submit = submit
        self._lookup = lookup
        self.requests: list[MarketOrderRequest | LimitOrderRequest] = []

    def submit_order(self, request: MarketOrderRequest | LimitOrderRequest) -> Order:
        self.requests.append(request)
        if isinstance(self._submit, Exception):
            raise self._submit
        return self._submit

    def get_order_by_client_id(self, client_id: str) -> Order:
        assert self._lookup is not None, "no lookup expected"
        if isinstance(self._lookup, Exception):
            raise self._lookup
        return self._lookup


def _broker(client: FakeTradingClient) -> AlpacaBroker:
    return AlpacaBroker(client=client)  # type: ignore[arg-type]


def _submit(broker: AlpacaBroker) -> Any:
    return broker.submit_bracket_order(
        _sized_order(), client_order_id=CLIENT_ORDER_ID, submitted_on=SUBMITTED_ON
    )


def test_bracket_request_shape() -> None:
    client = FakeTradingClient(submit=_order("order_pending"))

    trade = _submit(_broker(client))

    (request,) = client.requests
    assert request.symbol == "F"
    assert request.qty == 1
    assert request.side == OrderSide.BUY
    assert request.time_in_force == TimeInForce.GTC
    assert request.order_class == OrderClass.BRACKET
    assert request.client_order_id == CLIENT_ORDER_ID
    assert request.take_profit is not None and request.take_profit.limit_price == 13.19
    assert request.stop_loss is not None and request.stop_loss.stop_price == 11.94
    assert trade.status == "pending"
    assert trade.reference_price == REFERENCE
    assert trade.order_id and trade.stop_order_id and trade.take_profit_order_id


def test_limit_bracket_request_shape() -> None:
    client = FakeTradingClient(submit=_order("order_limit_pending"))
    plan = _sized_order().model_copy(
        update={"stop_loss": Decimal("9.30"), "take_profit": Decimal("10.27")}
    )

    trade = _broker(client).submit_bracket_order(
        plan,
        client_order_id=CLIENT_ORDER_ID,
        submitted_on=SUBMITTED_ON,
        limit_price=Decimal("9.69"),
    )

    (request,) = client.requests
    assert isinstance(request, LimitOrderRequest)
    assert request.limit_price == 9.69
    assert (request.symbol, request.qty, request.side) == ("F", 1, OrderSide.BUY)
    assert request.time_in_force == TimeInForce.GTC
    assert request.order_class == OrderClass.BRACKET
    assert request.client_order_id == CLIENT_ORDER_ID
    assert request.take_profit is not None and request.take_profit.limit_price == 10.27
    assert request.stop_loss is not None and request.stop_loss.stop_price == 9.30
    assert (trade.status, trade.order_type, trade.limit_price) == (
        "pending",
        "limit",
        Decimal("9.69"),
    )


def test_a_market_bracket_is_a_market_trade() -> None:
    trade = _submit(_broker(FakeTradingClient(submit=_order("order_pending"))))

    assert (trade.order_type, trade.limit_price) == ("market", None)


class FakeCancelClient:
    def __init__(self, failure: Exception | None = None) -> None:
        self._failure = failure
        self.cancelled: list[str] = []

    def cancel_order_by_id(self, order_id: str) -> None:
        if self._failure is not None:
            raise self._failure
        self.cancelled.append(order_id)


class TestCancelOrder:
    def test_asks_alpaca_to_cancel_the_order(self) -> None:
        client = FakeCancelClient()

        _broker(client).cancel_order("order-1")  # type: ignore[arg-type]

        assert client.cancelled == ["order-1"]

    @pytest.mark.parametrize(
        "failure",
        [
            pytest.param(_recorded_error("error_order_not_found"), id="not-found"),
            pytest.param(Timeout("timed out"), id="timeout"),
        ],
    )
    def test_any_error_is_a_rejection(self, failure: Exception) -> None:
        with pytest.raises(BrokerRejected, match="cancel_order"):
            _broker(FakeCancelClient(failure)).cancel_order("order-1")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(_recorded_error("error_duplicate_client_order_id"), id="duplicate-id"),
        pytest.param(Timeout("timed out"), id="timeout"),
        pytest.param(RequestsConnectionError("reset"), id="connection-error"),
    ],
)
def test_submit_is_idempotent(failure: Exception) -> None:
    existing = _order("order_open")
    client = FakeTradingClient(submit=failure, lookup=existing)

    trade = _submit(_broker(client))

    assert trade.order_id == str(existing.id)
    assert trade.status == "open"


def test_submit_raises_when_the_unknown_order_does_not_exist() -> None:
    client = FakeTradingClient(
        submit=Timeout("timed out"), lookup=_recorded_error("error_order_not_found")
    )

    with pytest.raises(BrokerRejected, match="timed out"):
        _submit(_broker(client))


def test_a_real_rejection_is_not_looked_up() -> None:
    rejected = _api_error('{"code":40310000,"message":"insufficient buying power"}', 403)
    client = FakeTradingClient(submit=rejected)  # a lookup here would fail its assert

    with pytest.raises(BrokerRejected, match="insufficient buying power"):
        _submit(_broker(client))


def _at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


@pytest.mark.parametrize(
    ("fixture", "status", "exits_active", "partial", "expected"),
    [
        pytest.param("order_pending", "pending", True, False, {}, id="pending"),
        pytest.param(
            "order_open",
            "open",
            True,
            False,
            {"entry_date": date(2026, 9, 28), "entry_price": Decimal("12.57")},
            id="open",
        ),
        pytest.param(
            "order_stop_filled",
            "closed",
            False,
            False,
            {
                "exit_reason": "stop",
                "exit_price": Decimal("11.94"),
                "exit_date": date(2026, 9, 30),
            },
            id="stop-filled",
        ),
        pytest.param(
            "order_target_filled",
            "closed",
            False,
            False,
            {
                "exit_reason": "target",
                "exit_price": Decimal("13.19"),
                "exit_date": date(2026, 10, 2),
            },
            id="target-filled",
        ),
        pytest.param(
            "order_entry_cancelled",
            "cancelled",
            False,
            False,
            {"cancel_reason": "entry canceled"},
            id="entry-cancelled",
        ),
        pytest.param("order_legs_cancelled", "open", False, False, {}, id="legs-cancelled"),
        pytest.param("order_partial", "pending", True, True, {}, id="partial"),
        pytest.param(
            "order_limit_pending",
            "pending",
            True,
            False,
            {"order_type": "limit", "limit_price": Decimal("9.69")},
            id="limit-pending",
        ),
        pytest.param(
            "order_limit_cancelled",
            "cancelled",
            False,
            False,
            {"cancel_reason": "entry canceled", "order_type": "limit"},
            id="limit-cancelled",
        ),
        pytest.param(
            "order_limit_filled",
            "open",
            True,
            False,
            {"entry_price": Decimal("9.65"), "entry_date": date(2026, 10, 6)},
            id="limit-filled",
        ),
        pytest.param(
            "order_limit_stopped",
            "closed",
            False,
            False,
            {"exit_reason": "stop", "exit_price": Decimal("9.30")},
            id="limit-stopped",
        ),
    ],
)
def test_live_order_mapping(
    fixture: str, status: str, exits_active: bool, partial: bool, expected: dict[str, Any]
) -> None:
    live = live_order(_order(fixture), submitted_on=SUBMITTED_ON, reference_price=REFERENCE)

    assert live.trade.status == status
    assert live.exits_active is exits_active
    assert live.partial is partial
    for field, value in expected.items():
        assert getattr(live.trade, field) == value
    assert live.trade.reference_price == REFERENCE


def test_legs_cancelled_reports_when_and_the_stop_and_target_prices() -> None:
    live = live_order(
        _order("order_legs_cancelled"), submitted_on=SUBMITTED_ON, reference_price=REFERENCE
    )

    assert live.exits_cancelled_at == _at("2026-10-01T14:30:00.200000Z")
    assert (live.trade.stop_loss, live.trade.take_profit) == (Decimal("11.94"), Decimal("13.19"))
    assert (
        live_order(
            _order("order_open"), submitted_on=SUBMITTED_ON, reference_price=REFERENCE
        ).exits_cancelled_at
        is None
    )
