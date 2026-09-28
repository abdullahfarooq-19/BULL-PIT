"""M0 spike: verify Alpaca bracket-order assumptions A7-A9 (specs-plan.md sec11.1, 11.2).

Four steps, run separately (`uv run python scripts/spikes/alpaca_bracket.py <step> --confirm`):

  validate  Submits brackets expected to be rejected (fractional qty, bad
            leg prices) and one valid GTC bracket while the market is
            closed, reads it back, cancels it. Safe any time. (Phase 1)
  place     Submits a real 1-share market bracket during market hours,
            polls until filled, then re-submits the same client_order_id
            to check idempotency. (Phase 2, needs the market open)
  inspect   Reads the order and legs again, to see if they survived the
            overnight close. (Phase 2, next session)
  close     Cancels any open legs and flattens the position. (Phase 2)

Without --confirm, prints the plan and touches nothing (dry run).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import typer
from _common import save_json, section, settings
from alpaca.common.exceptions import APIError
from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
from alpaca.trading.requests import (
    ClosePositionRequest,
    GetOrdersRequest,
    MarketOrderRequest,
    StopLossRequest,
    TakeProfitRequest,
)

from bullpit.broker.clients import make_trading_client

SYMBOL = "F"  # Ford: liquid, typically $10-15/share -- picked for the $5-30 band
CLIENT_ORDER_ID = f"spike-m0-{SYMBOL.lower()}-1"
FILL_POLL_TIMEOUT_S = 300
FILL_POLL_INTERVAL_S = 5

app = typer.Typer(add_completion=False)


def _order_summary(order: Any) -> dict[str, Any]:
    legs = getattr(order, "legs", None) or []
    return {
        "id": str(order.id),
        "client_order_id": order.client_order_id,
        "symbol": order.symbol,
        "qty": str(order.qty),
        "status": str(order.status),
        "order_class": str(order.order_class),
        "time_in_force": str(order.time_in_force),
        "filled_avg_price": str(order.filled_avg_price) if order.filled_avg_price else None,
        "legs": [
            {
                "id": str(leg.id),
                "type": str(leg.type),
                "status": str(leg.status),
                "limit_price": str(leg.limit_price) if leg.limit_price else None,
                "stop_price": str(leg.stop_price) if leg.stop_price else None,
            }
            for leg in legs
        ],
    }


def _latest_trade_price(client: Any, symbol: str) -> float:
    from alpaca.data.historical.stock import StockHistoricalDataClient
    from alpaca.data.requests import StockLatestTradeRequest

    s = settings()
    data_client = StockHistoricalDataClient(
        api_key=s.require("ALPACA_API_KEY"), secret_key=s.require("ALPACA_SECRET_KEY")
    )
    trades = data_client.get_stock_latest_trade(StockLatestTradeRequest(symbol_or_symbols=symbol))
    return float(trades[symbol].price)


@app.command()
def validate(confirm: bool = typer.Option(False, "--confirm")) -> None:
    """A7 (rejections + leg-price validation) and A9 (closed-market bracket accepted)."""
    client = make_trading_client(settings())
    results: dict[str, Any] = {}

    section("Plan: validate")
    print(f"  Symbol: {SYMBOL}")
    print("  1. Submit a bracket with fractional qty (0.5) -- expect rejection")
    print("  2. Submit a bracket with an inverted take-profit/stop -- expect rejection")
    print("  3. Submit a valid whole-share GTC bracket, read it back, cancel it")
    if not confirm:
        print("\nDry run only. Pass --confirm to actually submit these orders.")
        return

    ref_price = _latest_trade_price(client, SYMBOL)
    print(f"  Reference price for {SYMBOL}: {ref_price}")

    # 1. Fractional quantity.
    try:
        client.submit_order(
            MarketOrderRequest(
                symbol=SYMBOL,
                qty=0.5,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(ref_price * 1.05, 2)),
                stop_loss=StopLossRequest(stop_price=round(ref_price * 0.95, 2)),
            )
        )
        results["fractional_qty"] = {"rejected": False}
        print("  UNEXPECTED: fractional-qty bracket was accepted")
    except APIError as exc:
        results["fractional_qty"] = {"rejected": True, "error": str(exc)}
        print(f"  fractional qty rejected as expected: {exc}")

    # 2. Inverted exits (take-profit below reference, stop above it).
    try:
        client.submit_order(
            MarketOrderRequest(
                symbol=SYMBOL,
                qty=1,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(ref_price * 0.95, 2)),
                stop_loss=StopLossRequest(stop_price=round(ref_price * 1.05, 2)),
            )
        )
        results["inverted_exits"] = {"rejected": False}
        print("  UNEXPECTED: inverted-exits bracket was accepted")
    except APIError as exc:
        results["inverted_exits"] = {"rejected": True, "error": str(exc)}
        print(f"  inverted exits rejected as expected: {exc}")

    # 3. Valid GTC bracket (market may be open or closed; either way we read
    #    it back and cancel immediately so it never risks filling here).
    order = client.submit_order(
        MarketOrderRequest(
            symbol=SYMBOL,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(ref_price * 1.05, 2)),
            stop_loss=StopLossRequest(stop_price=round(ref_price * 0.95, 2)),
            client_order_id=f"{CLIENT_ORDER_ID}-validate",
        )
    )
    readback = client.get_order_by_client_id(order.client_order_id)
    results["valid_gtc_bracket"] = _order_summary(readback)
    print(f"  valid GTC bracket accepted: {results['valid_gtc_bracket']}")

    client.cancel_order_by_id(order.id)
    time.sleep(2)
    after_cancel = client.get_order_by_client_id(order.client_order_id)
    results["valid_gtc_bracket_after_cancel_status"] = str(after_cancel.status)
    print(f"  status after cancel: {after_cancel.status}")

    save_json("alpaca_bracket_validate", results)


@app.command()
def place(confirm: bool = typer.Option(False, "--confirm")) -> None:
    """A7 (fill + overnight persistence, checked next in `inspect`) and A8 (idempotency)."""
    client = make_trading_client(settings())
    results: dict[str, Any] = {}

    section("Plan: place")
    print(f"  Submit a 1-share market bracket on {SYMBOL}, time_in_force=GTC,")
    print(f"  client_order_id={CLIENT_ORDER_ID}. Poll until filled, then re-submit")
    print("  the same client_order_id to check it's rejected as a duplicate.")
    if not confirm:
        print("\nDry run only. Pass --confirm to actually submit this order.")
        return

    ref_price = _latest_trade_price(client, SYMBOL)
    order = client.submit_order(
        MarketOrderRequest(
            symbol=SYMBOL,
            qty=1,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.GTC,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=round(ref_price * 1.05, 2)),
            stop_loss=StopLossRequest(stop_price=round(ref_price * 0.95, 2)),
            client_order_id=CLIENT_ORDER_ID,
        )
    )
    print(f"  submitted: {order.id}, status={order.status}")

    deadline = time.time() + FILL_POLL_TIMEOUT_S
    filled = order
    while time.time() < deadline:
        filled = client.get_order_by_client_id(CLIENT_ORDER_ID)
        if str(filled.status) in ("OrderStatus.FILLED", "filled"):
            break
        time.sleep(FILL_POLL_INTERVAL_S)
    results["after_fill_poll"] = _order_summary(filled)
    print(f"  after poll: {results['after_fill_poll']}")

    try:
        dup = client.submit_order(
            MarketOrderRequest(
                symbol=SYMBOL,
                qty=1,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC,
                order_class=OrderClass.BRACKET,
                take_profit=TakeProfitRequest(limit_price=round(ref_price * 1.05, 2)),
                stop_loss=StopLossRequest(stop_price=round(ref_price * 0.95, 2)),
                client_order_id=CLIENT_ORDER_ID,
            )
        )
        results["duplicate_client_order_id"] = {"rejected": False, "id": str(dup.id)}
        print("  UNEXPECTED: duplicate client_order_id was accepted")
    except APIError as exc:
        results["duplicate_client_order_id"] = {"rejected": True, "error": str(exc)}
        print(f"  duplicate client_order_id rejected as expected: {exc}")

    save_json("alpaca_bracket_place", results)


@app.command(name="inspect")
def inspect_cmd(confirm: bool = typer.Option(False, "--confirm", "-y")) -> None:
    """A7: did the GTC legs survive the overnight close?"""
    client = make_trading_client(settings())
    section("Plan: inspect")
    print(f"  Read back client_order_id={CLIENT_ORDER_ID} and its legs.")
    if not confirm:
        print("\nDry run only. Pass --confirm to actually query.")
        return

    order = client.get_order_by_client_id(CLIENT_ORDER_ID)
    result = _order_summary(order)
    print(f"  {result}")
    save_json("alpaca_bracket_inspect", result)


@app.command()
def close(confirm: bool = typer.Option(False, "--confirm")) -> None:
    """Cancel any open legs and flatten the position."""
    client = make_trading_client(settings())
    section("Plan: close")
    print(f"  Cancel open orders for {SYMBOL} and close the position.")
    if not confirm:
        print("\nDry run only. Pass --confirm to actually close.")
        return

    orders = client.get_orders(GetOrdersRequest(symbols=[SYMBOL], status="open"))
    for o in orders:
        client.cancel_order_by_id(o.id)
        print(f"  cancelled {o.id}")

    try:
        close_order = client.close_position(SYMBOL, ClosePositionRequest(percentage="100"))
        result = {"closed": True, "order": _order_summary(close_order)}
    except APIError as exc:
        result = {"closed": False, "error": str(exc)}
    print(f"  {result}")
    save_json("alpaca_bracket_close", result)


if __name__ == "__main__":
    app()
