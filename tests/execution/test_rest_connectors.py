# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for authenticated REST/WebSocket execution connectors."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import hmac
import json
import time
from typing import Any, Callable
from urllib.parse import urlencode

import httpx
import pytest

from domain import Order, OrderSide, OrderStatus, OrderType
from execution.adapters import (
    BinanceRESTConnector,
    CoinbaseRESTConnector,
    KrakenRESTConnector,
    RESTWebSocketConnector,
)
from execution.connectors import TransientOrderError


class QueueWebSocketFactory:
    """Utility factory returning queue-backed async WebSocket mocks."""

    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] = asyncio.Queue()

    def __call__(self, url: str):  # pragma: no cover - exercised in integration behaviour
        factory = self

        class _QueueWebSocket:
            def __init__(self) -> None:
                self._closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                self._closed = True
                return False

            async def recv(self) -> str:
                while not self._closed:
                    try:
                        return await asyncio.wait_for(factory.queue.get(), timeout=0.05)
                    except asyncio.TimeoutError:
                        if self._closed:
                            raise
                        raise
                raise asyncio.CancelledError  # pragma: no cover - safety

        return _QueueWebSocket()


class _FailingClient:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def request(self, *args, **kwargs):  # pragma: no cover - exercised in tests
        raise self._exc

    def close(self) -> None:  # pragma: no cover - compatibility shim
        pass


class _TestRESTConnector(RESTWebSocketConnector):
    def __init__(self, client: Any) -> None:
        super().__init__(
            name="test",
            base_url="https://example.com",
            sandbox=True,
            http_client=client,
            ws_factory=lambda url: contextlib.nullcontext(),
        )

    def _resolve_credentials(self, credentials):
        return {}

    def _sign_request(self, method, path, *, params, json_payload, headers):
        return params, json_payload, headers, None

    def _order_endpoint(self):
        return "/orders"

    def _build_place_payload(self, order, idempotency_key):
        return {}

    def _parse_order(self, payload, *, original=None):
        raise NotImplementedError

    def _cancel_endpoint(self, order_id):
        return "/orders", {}

    def _fetch_endpoint(self, order_id):
        return "/orders", {}

    def _open_orders_endpoint(self):
        return "/orders", {}

    def _positions_endpoint(self):
        return "/positions", {}

    def _parse_positions(self, payload):
        return []

    def _handle_stream_message(self, payload):
        return None


@pytest.fixture()
def ws_factory() -> QueueWebSocketFactory:
    return QueueWebSocketFactory()


def _await_cache(
    connector,
    order_id: str,
    predicate: Callable[[Order], bool],
    *,
    timeout: float = 1.0,
) -> Order | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with connector._lock:  # type: ignore[attr-defined]
            cached = connector._orders.get(order_id)  # type: ignore[attr-defined]
        if cached and predicate(cached):
            return cached
        time.sleep(0.05)
    return None


def test_binance_rest_connector_signs_and_streams(
    monkeypatch: pytest.MonkeyPatch, ws_factory: QueueWebSocketFactory
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/time") and request.method == "GET":
            return httpx.Response(200, json={"serverTime": int(1_700_000_000_000)})
        if path.endswith("/exchangeInfo") and request.method == "GET":
            return httpx.Response(200, json={"symbols": []})
        if path.endswith("/userDataStream") and request.method == "POST":
            assert request.headers["X-MBX-APIKEY"] == "key"
            return httpx.Response(200, json={"listenKey": "listen-key"})
        if path.endswith("/order") and request.method == "POST":
            params = dict(request.url.params)
            assert params["symbol"] == "BTCUSDT"
            assert "signature" in params
            assert params["newClientOrderId"] == "abc-123"
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "orderId": "100",
                    "status": "NEW",
                    "side": "BUY",
                    "type": "LIMIT",
                    "origQty": "0.5",
                    "executedQty": "0.0",
                    "price": "20000.0",
                },
            )
        if path.endswith("/order") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "orderId": request.url.params.get("orderId"),
                    "status": "FILLED",
                    "side": "BUY",
                    "type": "LIMIT",
                    "origQty": "0.5",
                    "executedQty": "0.5",
                    "price": "20000.0",
                    "cummulativeQuoteQty": "10000",
                },
            )
        if path.endswith("/openOrders") and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "BTCUSDT",
                        "orderId": "101",
                        "status": "NEW",
                        "side": "SELL",
                        "type": "LIMIT_MAKER",
                        "origQty": "0.1",
                        "executedQty": "0.0",
                        "price": "21000.0",
                    }
                ],
            )
        if path.endswith("/account") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "balances": [
                        {"asset": "BTC", "free": "0.25", "locked": "0.25"},
                        {"asset": "USDT", "free": "1000", "locked": "0"},
                    ]
                },
            )
        if path.endswith("/order") and request.method == "DELETE":
            return httpx.Response(200, json={"status": "CANCELED"})
        raise AssertionError(f"Unhandled request {request.method} {path}")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://testnet.binance.vision", transport=transport)
    connector = BinanceRESTConnector(sandbox=True, http_client=client, ws_factory=ws_factory)
    monkeypatch.setattr("execution.adapters.binance.time.time", lambda: 1_700_000_000.0)

    connector.connect({"api_key": "key", "api_secret": "secret"})
    assert requests and requests[0].url.path.endswith("/userDataStream")

    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.5,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )
    submitted = connector.place_order(order, idempotency_key="abc-123")
    assert submitted.order_id == "100"
    assert submitted.order_type is OrderType.LIMIT
    asyncio.run(
        ws_factory.queue.put(
            json.dumps(
                {
                    "e": "executionReport",
                    "s": "BTCUSDT",
                    "i": "100",
                    "X": "PARTIALLY_FILLED",
                    "z": "0.25",
                    "q": "0.5",
                    "ap": "20500.0",
                    "S": "BUY",
                    "o": "TAKE_PROFIT_LIMIT",
                }
            )
        )
    )
    cached = _await_cache(connector, "100", lambda o: o.filled_quantity >= 0.25)
    assert cached is not None
    assert cached.filled_quantity == pytest.approx(0.25)
    assert cached.average_price == pytest.approx(20500.0)
    assert cached.order_type is OrderType.STOP_LIMIT

    fetched = connector.fetch_order("100")
    assert fetched.status == OrderStatus.FILLED
    assert fetched.filled_quantity == pytest.approx(0.5)

    open_orders = connector.open_orders()
    assert len(open_orders) == 1
    assert open_orders[0].order_id == "101"
    assert open_orders[0].order_type is OrderType.LIMIT

    positions = connector.get_positions()
    assert any(pos["symbol"] == "BTC" and pos["qty"] == pytest.approx(0.5) for pos in positions)

    assert connector.cancel_order("100") is True

    connector.disconnect()
    client.close()


@pytest.mark.parametrize(
    "exception_factory",
    [
        lambda request: httpx.ConnectTimeout("boom", request=request),
        lambda request: httpx.NetworkError("reset", request=request),
    ],
)
def test_rest_connector_translates_httpx_errors(exception_factory) -> None:
    request = httpx.Request("GET", "https://example.com/orders")
    exc = exception_factory(request)
    client = _FailingClient(exc)
    connector = _TestRESTConnector(client)
    connector._connected = True  # type: ignore[attr-defined]
    with pytest.raises(TransientOrderError):
        connector._request("GET", "/orders")


def test_binance_cancel_replace(
    monkeypatch: pytest.MonkeyPatch, ws_factory: QueueWebSocketFactory
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path.endswith("/time") and request.method == "GET":
            return httpx.Response(200, json={"serverTime": int(1_700_000_000_000)})
        if path.endswith("/exchangeInfo") and request.method == "GET":
            return httpx.Response(200, json={"symbols": []})
        if path.endswith("/userDataStream") and request.method == "POST":
            return httpx.Response(200, json={"listenKey": "listen-key"})
        if path.endswith("/order") and request.method == "POST":
            params = dict(request.url.params)
            if "cancelOrderId" in params:
                return httpx.Response(
                    200,
                    json={
                        "newOrderResponse": {
                            "symbol": "BTCUSDT",
                            "orderId": "200",
                            "status": "NEW",
                            "side": "BUY",
                            "type": "STOP_LOSS_LIMIT",
                            "origQty": "0.5",
                            "price": "20100",
                            "stopPrice": "19900",
                        }
                    },
                )
            return httpx.Response(
                200,
                json={
                    "symbol": "BTCUSDT",
                    "orderId": "100",
                    "status": "NEW",
                    "side": "BUY",
                    "type": "LIMIT",
                    "origQty": "0.5",
                    "price": "20000",
                },
            )
        if path.endswith("/order/cancelReplace") and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "newOrderResponse": {
                        "symbol": "BTCUSDT",
                        "orderId": "200",
                        "status": "NEW",
                        "side": "BUY",
                        "type": "STOP_LOSS_LIMIT",
                        "origQty": "0.5",
                        "price": "20100",
                        "stopPrice": "19900",
                    }
                },
            )
        if path.endswith("/order") and request.method == "DELETE":
            return httpx.Response(200, json={"status": "CANCELED"})
        raise AssertionError(f"Unhandled request {request.method} {path}")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://testnet.binance.vision", transport=transport)
    connector = BinanceRESTConnector(sandbox=True, http_client=client, ws_factory=ws_factory)
    monkeypatch.setattr("execution.adapters.binance.time.time", lambda: 1_700_000_000.0)

    connector.connect({"api_key": "key", "api_secret": "secret"})

    base_order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.5,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )
    placed = connector.place_order(base_order, idempotency_key="orig")
    assert placed.order_id == "100"

    replacement = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.5,
        price=20100.0,
        stop_price=19900.0,
        order_type=OrderType.STOP_LIMIT,
    )
    updated = connector.cancel_replace_order("100", replacement, idempotency_key="replace")
    assert updated.order_id == "200"
    assert updated.order_type is OrderType.STOP_LIMIT

    connector.disconnect()
    client.close()


def test_coinbase_rest_connector_handles_auth_and_stream(
    monkeypatch: pytest.MonkeyPatch, ws_factory: QueueWebSocketFactory
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        host = request.url.host
        if host == "api.coinbase.com" and path.endswith("/time"):
            return httpx.Response(200, json={"data": {"epoch": 1_700_000_000}})
        if path.endswith("/orders") and request.method == "POST":
            assert request.headers["CB-ACCESS-KEY"] == "key"
            assert request.headers["CB-ACCESS-PASSPHRASE"] == "pass"
            assert "CB-ACCESS-SIGN" in request.headers
            body = json.loads(request.content.decode())
            assert body["product_id"] == "BTC-USD"
            return httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "cb-1",
                        "product_id": "BTC-USD",
                        "side": "BUY",
                        "order_type": "LIMIT_LIMIT_GTC",
                        "size": "0.1",
                        "filled_size": "0.0",
                        "status": "OPEN",
                        "limit_price": "21000.0",
                    }
                },
            )
        if path.endswith("/orders/cb-1") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "cb-1",
                        "product_id": "BTC-USD",
                        "side": "BUY",
                        "order_type": "LIMIT",
                        "size": "0.1",
                        "filled_size": "0.1",
                        "status": "FILLED",
                        "average_filled_price": "21000.0",
                    }
                },
            )
        if path.endswith("/orders/open") and request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "order_id": "cb-2",
                        "product_id": "BTC-USD",
                        "side": "SELL",
                        "order_type": "LIMIT_LIMIT_GTC",
                        "size": "0.1",
                        "filled_size": "0.0",
                        "status": "OPEN",
                        "limit_price": "22000.0",
                    }
                ],
            )
        if path.endswith("/accounts") and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "accounts": [
                        {"currency": "BTC", "available_balance": {"value": "0.4"}},
                        {"currency": "USD", "available_balance": {"value": "1000"}},
                    ]
                },
            )
        if path.endswith("/orders/cb-1") and request.method == "DELETE":
            return httpx.Response(200, json={"success": True})
        raise AssertionError(f"Unhandled request {request.method} {path}")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        base_url="https://api-public.sandbox.exchange.coinbase.com/api/v3/brokerage",
        transport=transport,
    )
    connector = CoinbaseRESTConnector(sandbox=True, http_client=client, ws_factory=ws_factory)
    monkeypatch.setattr("execution.adapters.coinbase.time.time", lambda: 1_700_000_000)

    connector.connect(
        {"api_key": "key", "api_secret": base64_secret("secret"), "passphrase": "pass"}
    )

    order = Order(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=0.1,
        price=21000.0,
        order_type=OrderType.LIMIT,
    )
    submitted = connector.place_order(order, idempotency_key="cb-order")
    assert submitted.order_id == "cb-1"
    assert submitted.order_type is OrderType.LIMIT

    asyncio.run(
        ws_factory.queue.put(
            json.dumps(
                {
                    "type": "order_update",
                    "order": {
                        "order_id": "cb-1",
                        "product_id": "BTC-USD",
                        "side": "BUY",
                        "order_type": "MARKET_MARKET_IOC",
                        "size": "0.1",
                        "filled_size": "0.05",
                        "status": "PARTIALLY_FILLED",
                        "average_filled_price": "21500.0",
                    },
                }
            )
        )
    )
    cached = _await_cache(connector, "cb-1", lambda o: o.filled_quantity >= 0.05)
    assert cached is not None
    assert cached.status == OrderStatus.PARTIALLY_FILLED
    assert cached.order_type is OrderType.MARKET

    fetched = connector.fetch_order("cb-1")
    assert fetched.status == OrderStatus.FILLED

    open_orders = connector.open_orders()
    assert any(order.order_id == "cb-2" for order in open_orders)
    assert any(
        order.order_id == "cb-2" and order.order_type is OrderType.LIMIT for order in open_orders
    )

    positions = connector.get_positions()
    assert any(pos["symbol"] == "BTC" and pos["qty"] == pytest.approx(0.4) for pos in positions)

    assert connector.cancel_order("cb-1") is True

    connector.disconnect()
    client.close()

    # Coinbase signing produces deterministic headers for each request
    assert any("CB-ACCESS-SIGN" in req.headers for req in requests)


def test_coinbase_cancel_replace(
    monkeypatch: pytest.MonkeyPatch, ws_factory: QueueWebSocketFactory
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        host = request.url.host
        if host == "api.coinbase.com" and path.endswith("/time"):
            return httpx.Response(200, json={"data": {"epoch": 1_700_000_000}})
        if path.endswith("/orders") and request.method == "POST":
            return httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "cb-1",
                        "product_id": "BTC-USD",
                        "side": "BUY",
                        "order_type": "LIMIT_LIMIT_GTC",
                        "size": "0.1",
                        "filled_size": "0.0",
                        "status": "OPEN",
                        "limit_price": "21000.0",
                    }
                },
            )
        if path.endswith("/orders/edit") and request.method == "POST":
            body = json.loads(request.content.decode())
            assert (
                body["order_configuration"]["stop_limit_stop_limit_gtc"]["stop_price"]
                == "20500.0000000000"
            )
            return httpx.Response(
                200,
                json={
                    "order": {
                        "order_id": "cb-2",
                        "product_id": "BTC-USD",
                        "side": "BUY",
                        "order_type": "STOP_LIMIT_STOP_LIMIT_GTC",
                        "size": "0.1",
                        "filled_size": "0.0",
                        "status": "OPEN",
                        "limit_price": "20750.0",
                        "stop_price": "20500.0",
                    }
                },
            )
        if path.endswith("/userDataStream"):
            return httpx.Response(404)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(
        base_url="https://api-public.sandbox.exchange.coinbase.com/api/v3/brokerage",
        transport=transport,
    )
    connector = CoinbaseRESTConnector(sandbox=True, http_client=client, ws_factory=ws_factory)
    monkeypatch.setattr("execution.adapters.coinbase.time.time", lambda: 1_700_000_000)

    connector.connect(
        {"api_key": "key", "api_secret": base64_secret("secret"), "passphrase": "pass"}
    )

    original = Order(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=0.1,
        price=21000.0,
        order_type=OrderType.LIMIT,
    )
    placed = connector.place_order(original, idempotency_key="orig")
    assert placed.order_id == "cb-1"

    replacement = Order(
        symbol="BTC-USD",
        side=OrderSide.BUY,
        quantity=0.1,
        price=20750.0,
        stop_price=20500.0,
        order_type=OrderType.STOP_LIMIT,
    )
    updated = connector.cancel_replace_order("cb-1", replacement, idempotency_key="replace")
    assert updated.order_id == "cb-2"
    assert updated.order_type is OrderType.STOP_LIMIT

    connector.disconnect()
    client.close()


def base64_secret(secret: str) -> str:
    import base64

    return base64.b64encode(secret.encode("utf-8")).decode("utf-8")


def _kraken_signature(secret: bytes, path: str, request: httpx.Request) -> str:
    if request.content:
        params = httpx.QueryParams(request.content.decode("utf-8"))
    else:
        params = request.url.params
    ordered = dict(params.multi_items())
    nonce = ordered.get("nonce", "")
    payload = urlencode(ordered)
    digest = hashlib.sha256((str(nonce) + payload).encode("utf-8")).digest()
    signature = hmac.new(secret, path.encode("utf-8") + digest, hashlib.sha512).digest()
    return base64.b64encode(signature).decode("utf-8")


def test_kraken_rest_connector_signs_and_streams(
    monkeypatch: pytest.MonkeyPatch, ws_factory: QueueWebSocketFactory
) -> None:
    raw_secret = b"very-secret-key"
    api_secret = base64.b64encode(raw_secret).decode("utf-8")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        assert request.headers["API-Key"] == "key"
        if request.method != "POST":
            raise AssertionError("Kraken private endpoints must use POST")
        if path.endswith("/GetWebSocketsToken"):
            expected = _kraken_signature(raw_secret, path, request)
            assert request.headers["API-Sign"] == expected
            return httpx.Response(200, json={"result": {"token": "ws-token"}})
        expected_signature = _kraken_signature(raw_secret, path, request)
        assert request.headers["API-Sign"] == expected_signature
        if path.endswith("/AddOrder"):
            params = httpx.QueryParams(request.content.decode("utf-8"))
            assert not request.url.params
            assert params["pair"] == "BTCUSD"
            assert params["ordertype"] == "limit"
            return httpx.Response(
                200,
                json={
                    "result": {
                        "txid": ["O123"],
                        "descr": {
                            "pair": "BTCUSD",
                            "type": "buy",
                            "ordertype": "limit",
                            "price": "20000.0",
                        },
                        "status": "open",
                        "vol": "0.5",
                        "vol_exec": "0.0",
                    }
                },
            )
        if path.endswith("/QueryOrders"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "O123": {
                            "status": "closed",
                            "descr": {
                                "pair": "BTCUSD",
                                "type": "buy",
                                "ordertype": "limit",
                                "price": "20000.0",
                            },
                            "vol": "0.5",
                            "vol_exec": "0.5",
                            "avg_price": "20050.0",
                        }
                    }
                },
            )
        if path.endswith("/OpenOrders"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "open": {
                            "O124": {
                                "status": "open",
                                "descr": {
                                    "pair": "ETHUSD",
                                    "type": "sell",
                                    "ordertype": "limit",
                                    "price": "1500.0",
                                },
                                "vol": "1.0",
                                "vol_exec": "0.0",
                            }
                        }
                    }
                },
            )
        if path.endswith("/Balance"):
            return httpx.Response(
                200,
                json={"result": {"XXBT": "0.25", "ZUSD": "1000"}},
            )
        if path.endswith("/CancelOrder"):
            return httpx.Response(200, json={"result": {"count": 1}})
        raise AssertionError(f"Unhandled Kraken request {request.method} {path}")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(base_url="https://api.sandbox.kraken.com", transport=transport)
    connector = KrakenRESTConnector(sandbox=True, http_client=client, ws_factory=ws_factory)
    monkeypatch.setattr("execution.adapters.kraken.time.time", lambda: 1_700_000_000.0)

    connector.connect({"api_key": "key", "api_secret": api_secret, "otp": "000000"})
    assert requests and requests[0].url.path.endswith("/GetWebSocketsToken")

    order = Order(
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=0.5,
        price=20000.0,
        order_type=OrderType.LIMIT,
    )
    submitted = connector.place_order(order, idempotency_key="abc")
    assert submitted.order_id == "O123"
    assert submitted.status is OrderStatus.OPEN

    asyncio.run(
        ws_factory.queue.put(
            json.dumps(
                {
                    "event": "execution",
                    "order": {
                        "ordertxid": "O123",
                        "status": "partial",
                        "vol": "0.5",
                        "vol_exec": "0.25",
                        "avg_price": "20010.0",
                        "pair": "BTCUSD",
                        "type": "buy",
                        "ordertype": "limit",
                    },
                }
            )
        )
    )
    cached = _await_cache(connector, "O123", lambda o: o.filled_quantity >= 0.25)
    assert cached is not None
    assert cached.filled_quantity == pytest.approx(0.25)
    assert cached.average_price == pytest.approx(20010.0)

    fetched = connector.fetch_order("O123")
    assert fetched.status == OrderStatus.FILLED
    assert fetched.average_price == pytest.approx(20050.0)

    open_orders = connector.open_orders()
    assert any(order.order_id == "O124" for order in open_orders)

    positions = connector.get_positions()
    assert {p["symbol"] for p in positions} == {"XXBT", "ZUSD"}

    assert connector.cancel_order("O123") is True
