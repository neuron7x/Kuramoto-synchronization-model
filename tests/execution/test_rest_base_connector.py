# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from typing import Any, Mapping

import httpx
import pytest

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.adapters.base import RESTWebSocketConnector, SlidingWindowRateLimiter
from execution.connectors import OrderError, TransientOrderError


class DummyRESTConnector(RESTWebSocketConnector):
    """Minimal concrete connector used to exercise base behaviours."""

    def __init__(self, transport: httpx.BaseTransport) -> None:
        super().__init__(
            name="dummy",
            base_url="https://example.com",
            sandbox=True,
            http_client=httpx.Client(base_url="https://example.com", transport=transport),
        )

    def _resolve_credentials(self, credentials: Mapping[str, str] | None) -> Mapping[str, str]:
        return dict(credentials or {})

    def _sign_request(self, method: str, path: str, *, params, json_payload, headers):  # type: ignore[override]
        return params, json_payload, headers, None

    def _order_endpoint(self) -> str:
        return "/order"

    def _build_place_payload(self, order: Order, idempotency_key: str | None) -> dict[str, Any]:
        payload = {
            "symbol": order.symbol,
            "side": order.side.value,
            "type": order.order_type.value,
            "quantity": f"{order.quantity:.6f}",
        }
        if idempotency_key:
            payload["client_id"] = idempotency_key
        if order.price is not None:
            payload["price"] = f"{order.price:.2f}"
        return payload

    def _parse_order(self, payload: Mapping[str, Any], *, original: Order | None = None) -> Order:
        symbol = str(payload.get("symbol") or (original.symbol if original else ""))
        if not symbol:
            raise ValueError("order payload missing symbol")
        side_value = str(payload.get("side") or (original.side.value if original else "buy"))
        order_type_value = str(
            payload.get("type") or (original.order_type.value if original else "market")
        )
        order_id = str(payload.get("id") or payload.get("orderId") or payload.get("order_id") or "")
        if not order_id:
            raise ValueError("order payload missing id")
        price = payload.get("price")
        price = float(price) if price not in (None, "") else None
        quantity = float(
            payload.get("quantity")
            or payload.get("qty")
            or (original.quantity if original else 0.0)
        )
        filled = float(payload.get("filled") or payload.get("filled_quantity") or 0.0)
        status_value = str(payload.get("status") or "OPEN").upper()
        try:
            status = OrderStatus(status_value.lower())
        except ValueError:
            status = original.status if original is not None else OrderStatus.OPEN
        avg = payload.get("average_price")
        average_price = float(avg) if avg not in (None, "") else None
        return Order(
            symbol=symbol,
            side=OrderSide(side_value),
            quantity=(quantity if quantity > 0 else (original.quantity if original else 0.0)),
            price=price,
            order_type=OrderType(order_type_value),
            order_id=order_id,
            status=status,
            filled_quantity=filled,
            average_price=average_price,
        )

    def _cancel_endpoint(self, order_id: str) -> tuple[str, dict[str, Any]]:
        return "/order", {"id": order_id}

    def _fetch_endpoint(self, order_id: str) -> tuple[str, dict[str, Any]]:
        return "/order", {"id": order_id}

    def _open_orders_endpoint(self) -> tuple[str, dict[str, Any]]:
        return "/orders", {}

    def _positions_endpoint(self) -> tuple[str, dict[str, Any]]:
        return "/positions", {}

    def _parse_positions(self, payload: Mapping[str, Any] | list) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [dict(position) for position in payload]
        return [dict(position) for position in payload.get("positions", [])]

    def _handle_stream_message(
        self, payload: Mapping[str, Any]
    ) -> None:  # pragma: no cover - not exercised
        return None


def test_sliding_window_rate_limiter_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    current = {"value": 0.0}
    sleep_calls: list[float] = []

    def clock() -> float:
        return current["value"]

    def fake_sleep(duration: float) -> None:
        sleep_calls.append(duration)
        current["value"] += duration

    limiter = SlidingWindowRateLimiter(max_requests=2, interval_seconds=1.0, clock=clock)
    monkeypatch.setattr("execution.adapters.base.time.sleep", fake_sleep)

    limiter.acquire()
    limiter.acquire()
    limiter.acquire()  # advances simulated clock via fake_sleep
    limiter.acquire(weight=0)  # no additional delay when weight is zero

    assert current["value"] >= 1.0
    assert sleep_calls and all(call <= 0.5 for call in sleep_calls)


def test_sliding_window_rate_limiter_validation() -> None:
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(max_requests=0, interval_seconds=1.0)
    with pytest.raises(ValueError):
        SlidingWindowRateLimiter(max_requests=1, interval_seconds=0.0)


def test_rest_connector_idempotency_and_caches() -> None:
    post_calls = 0
    delete_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls, delete_calls
        if request.method == "POST" and request.url.path == "/order":
            post_calls += 1
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "id": "order-1",
                    "side": "buy",
                    "type": "limit",
                    "quantity": "1",
                    "filled": "0",
                    "status": "OPEN",
                    "price": "100",
                },
            )
        if request.method == "GET" and request.url.path == "/order":
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "id": request.url.params.get("id", "order-1"),
                    "side": "buy",
                    "type": "market",
                    "quantity": "1",
                    "filled": "1",
                    "status": "FILLED",
                    "average_price": "101",
                },
            )
        if request.method == "GET" and request.url.path == "/orders":
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "BTCUSDT",
                        "id": "open-2",
                        "side": "sell",
                        "type": "limit",
                        "quantity": "0.5",
                        "filled": "0",
                        "status": "OPEN",
                        "price": "150",
                    }
                ],
            )
        if request.method == "GET" and request.url.path == "/positions":
            return httpx.Response(
                200, json=[{"symbol": "BTC", "qty": 1.0, "side": "long", "price": 0.0}]
            )
        if request.method == "DELETE" and request.url.path == "/order":
            delete_calls += 1
            return httpx.Response(200, json={"status": "CANCELED"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    connector = DummyRESTConnector(httpx.MockTransport(handler))
    connector.connect({})

    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=1.0,
        price=100.0,
        order_type=OrderType.LIMIT,
    )
    first = connector.place_order(order, idempotency_key="idem-1")
    second = connector.place_order(order, idempotency_key="idem-1")
    assert first.order_id == "order-1"
    assert first.order_id == second.order_id
    assert post_calls == 1

    fetched = connector.fetch_order("order-1")
    assert fetched.status is OrderStatus.FILLED
    assert fetched.average_price == pytest.approx(101.0)

    open_orders = connector.open_orders()
    assert len(open_orders) == 1
    assert open_orders[0].order_type is OrderType.LIMIT

    positions = connector.get_positions()
    assert positions == [{"symbol": "BTC", "qty": 1.0, "side": "long", "price": 0.0}]

    assert connector.cancel_order("order-1") is True
    assert delete_calls == 1

    connector.disconnect()


def test_rest_connector_error_handling() -> None:
    def rate_limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limit"})

    connector = DummyRESTConnector(httpx.MockTransport(rate_limited))
    connector.connect({})
    order = Order(symbol="BTCUSDT", side=OrderSide.BUY, quantity=1.0, order_type=OrderType.MARKET)
    with pytest.raises(TransientOrderError):
        connector.place_order(order)
    connector.disconnect()

    def invalid_json(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, text="not json")
        return httpx.Response(
            200,
            json={
                "symbol": "BTCUSDT",
                "id": "order-1",
                "side": "buy",
                "type": "limit",
                "quantity": "1",
            },
        )

    connector = DummyRESTConnector(httpx.MockTransport(invalid_json))
    connector.connect({})
    with pytest.raises(OrderError):
        connector.fetch_order("missing")
    connector.disconnect()
