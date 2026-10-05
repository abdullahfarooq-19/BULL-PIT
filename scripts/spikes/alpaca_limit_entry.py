"""M11.1 spike: does Alpaca accept a limit-entry bracket order, and how does it read back?

Run with `uv run python scripts/spikes/alpaca_limit_entry.py --confirm`.

Places a 1-share GTC limit-entry bracket far below the market (so it can never
fill), reads it back through bullpit's own `live_order` mapper, then cancels it
and reads it again. Also submits two invalid brackets that must be rejected.
Raw order JSON goes to scripts/spikes/output/ (git-ignored). Safe any time,
market open or closed. Without --confirm it prints the plan and touches nothing.
"""

from __future__ import annotations

import sys
import time
import uuid
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import typer
from _common import save_json, section, settings
from alpaca.common.exceptions import APIError
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from bullpit.broker.alpaca import live_order
from bullpit.broker.clients import make_trading_client

SYMBOL = "F"
LIMIT_DISCOUNT = 0.80  # entry 20% below the last trade: never fills during the probe
TAKE_PROFIT_UP = 1.06
STOP_DOWN = 0.96

app = typer.Typer(add_completion=False)


def _summary(order: Any) -> dict[str, Any]:
    return {
        "id": str(order.id),
        "client_order_id": order.client_order_id,
        "type": str(order.type),
        "order_class": str(order.order_class),
        "time_in_force": str(order.time_in_force),
        "status": str(order.status),
        "qty": str(order.qty),
        "limit_price": str(order.limit_price) if order.limit_price else None,
        "filled_qty": str(order.filled_qty),
        "legs": [
            {
                "type": str(leg.type),
                "status": str(leg.status),
                "limit_price": str(leg.limit_price) if leg.limit_price else None,
                "stop_price": str(leg.stop_price) if leg.stop_price else None,
            }
            for leg in order.legs or []
        ],
    }


def _request(
    limit: float, take_profit: float, stop: float, client_order_id: str | None = None
) -> LimitOrderRequest:
    return LimitOrderRequest(
        symbol=SYMBOL,
        qty=1,
        side=OrderSide.BUY,
        time_in_force=TimeInForce.GTC,
        order_class=OrderClass.BRACKET,
        limit_price=limit,
        take_profit=TakeProfitRequest(limit_price=take_profit),
        stop_loss=StopLossRequest(stop_price=stop),
        client_order_id=client_order_id,
    )


@app.command()
def probe(confirm: bool = typer.Option(False, "--confirm")) -> None:
    section("Plan: probe")
    print(
        f"  {SYMBOL}, 1 share, GTC limit-entry bracket at {LIMIT_DISCOUNT:.0%} of the last trade."
    )
    print(
        "  1. Two invalid brackets (take-profit below the limit; stop above it): expect rejection"
    )
    print("  2. One valid bracket: read it back, map it with live_order, cancel, read it again")
    if not confirm:
        print("\nDry run only. Pass --confirm to submit.")
        return

    cfg = settings()
    client = make_trading_client(cfg)
    data = StockHistoricalDataClient(
        api_key=cfg.require("ALPACA_API_KEY"), secret_key=cfg.require("ALPACA_SECRET_KEY")
    )
    last = float(
        data.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=SYMBOL))[SYMBOL].price
    )
    limit = round(last * LIMIT_DISCOUNT, 2)
    take_profit = round(limit * TAKE_PROFIT_UP, 2)
    stop = round(limit * STOP_DOWN, 2)
    results: dict[str, Any] = {
        "last_trade": last,
        "limit": limit,
        "take_profit": take_profit,
        "stop": stop,
    }
    print(f"  last trade {last}, limit {limit}, take-profit {take_profit}, stop {stop}")

    for name, bad in (
        # Each keeps stop < take-profit, so only the limit comparison can reject it.
        ("take_profit_below_limit", _request(limit, round(limit * 0.98, 2), stop)),
        ("stop_above_limit", _request(limit, take_profit, round(limit * 1.02, 2))),
    ):
        try:
            client.submit_order(bad)
            results[name] = {"rejected": False}
            print(f"  UNEXPECTED: {name} was accepted")
        except APIError as exc:
            results[name] = {"rejected": True, "error": str(exc)}
            print(f"  {name} rejected as expected: {exc}")

    cid = f"spike-m11-{uuid.uuid4().hex[:8]}"
    placed = client.submit_order(_request(limit, take_profit, stop, cid))
    placed_read = client.get_order_by_client_id(cid)
    results["valid_limit_bracket"] = _summary(placed_read)
    save_json("order_limit_pending", placed_read.model_dump(mode="json"))
    print(f"  accepted: {results['valid_limit_bracket']}")

    mapped = live_order(
        placed_read,
        submitted_on=placed_read.submitted_at.date(),
        reference_price=Decimal(str(last)),
    )
    results["mapped_before_cancel"] = {
        "status": mapped.trade.status,
        "exits_active": mapped.exits_active,
        "exits_cancelled_at": str(mapped.exits_cancelled_at),
    }
    print(f"  mapped by live_order before cancel: {results['mapped_before_cancel']}")

    client.cancel_order_by_id(placed.id)
    time.sleep(3)
    cancelled = client.get_order_by_client_id(cid)
    results["after_cancel"] = _summary(cancelled)
    save_json("order_limit_cancelled", cancelled.model_dump(mode="json"))
    mapped = live_order(
        cancelled, submitted_on=cancelled.submitted_at.date(), reference_price=Decimal(str(last))
    )
    results["mapped_after_cancel"] = {
        "status": mapped.trade.status,
        "cancel_reason": mapped.trade.cancel_reason,
        "exits_active": mapped.exits_active,
        "exits_cancelled_at": str(mapped.exits_cancelled_at),
    }
    print(f"  after cancel: {results['after_cancel']}")
    print(f"  mapped by live_order after cancel: {results['mapped_after_cancel']}")

    still_open = client.get_orders(GetOrdersRequest(symbols=[SYMBOL], status="open"))
    results["open_orders_left"] = [
        o.client_order_id for o in still_open if o.client_order_id == cid
    ]
    print(f"  probe orders still open: {results['open_orders_left']}")
    save_json("alpaca_limit_entry", results)


if __name__ == "__main__":
    app()
