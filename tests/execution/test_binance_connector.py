from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlencode

import httpx
import pytest

from domain import Order, OrderType
from interfaces.execution.binance import BinanceExecutionConnector


class DummyWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self._messages = iter(messages)

    def __enter__(self) -> "DummyWebSocket":
        return self

    def __exit__(
        self, exc_type, exc, tb
    ) -> None:  # pragma: no cover - interface compliance
        return None

    def recv(self) -> str:
        try:
            return next(self._messages)
        except StopIteration as exc:  # pragma: no cover - defensive
            raise ConnectionError("stream closed") from exc

    def close(self) -> None:  # pragma: no cover - interface compliance
        pass


@pytest.fixture(autouse=True)
def _freeze_time(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = 1660000000.0
    monkeypatch.setattr("interfaces.execution.binance.time.time", lambda: fixed)


def test_binance_signature_and_idempotency() -> None:
    call_counts: dict[str, int] = {"post": 0, "get": 0}
    expected_timestamp = str(int(1660000000.0 * 1000))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v3/order":
            call_counts["post"] += 1
            assert request.headers["X-MBX-APIKEY"] == "test-key"
            params = request.url.params.multi_items()
            filtered = [(k, v) for k, v in params if k != "signature"]
            query = urlencode(sorted(filtered))
            signature = dict(params)["signature"]
            expected = hmac.new(
                b"test-secret", query.encode(), hashlib.sha256
            ).hexdigest()
            assert signature == expected
            assert dict(params)["timestamp"] == expected_timestamp
            body = {"orderId": 4242, "status": "NEW", "executedQty": "0"}
            return httpx.Response(200, json=body)
        if request.method == "GET" and request.url.path == "/api/v3/order":
            call_counts["get"] += 1
            body = {
                "symbol": "BTCUSDT",
                "orderId": 4242,
                "status": "NEW",
                "origQty": "1",
            }
            return httpx.Response(200, json=body)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    connector = BinanceExecutionConnector(
        sandbox=True, enable_stream=False, transport=transport
    )
    connector.connect(credentials={"API_KEY": "test-key", "API_SECRET": "test-secret"})

    order = Order(
        symbol="BTCUSDT", side="buy", quantity=1.0, order_type=OrderType.MARKET
    )

    first = connector.place_order(order, idempotency_key="idem-1")
    second = connector.place_order(order, idempotency_key="idem-1")

    assert first.order_id == second.order_id
    assert call_counts["post"] == 1  # second call reconciles without resubmitting
    assert call_counts["get"] == 1


def test_binance_rate_limit_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "interfaces.execution.common.time.sleep",
        lambda value: sleep_calls.append(value),
    )

    call_sequence = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v3/order":
            call_sequence.append("order")
            if len(call_sequence) == 1:
                return httpx.Response(
                    429, json={"code": -1003, "msg": "Too many requests"}
                )
            return httpx.Response(
                200, json={"orderId": 1001, "status": "NEW", "executedQty": "0"}
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    connector = BinanceExecutionConnector(
        sandbox=True, enable_stream=False, transport=httpx.MockTransport(handler)
    )
    connector.connect(credentials={"API_KEY": "test-key", "API_SECRET": "test-secret"})

    order = Order(
        symbol="BTCUSDT", side="buy", quantity=1.0, order_type=OrderType.MARKET
    )
    result = connector.place_order(order)

    assert result.order_id is not None
    assert call_sequence.count("order") == 2
    assert sleep_calls, "rate limiter should trigger sleep backoff"


def test_binance_stream_emits_fill_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v3/userDataStream":
            return httpx.Response(200, json={"listenKey": "abc123"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    message = json.dumps(
        {
            "e": "executionReport",
            "s": "BTCUSDT",
            "i": 555,
            "c": "idem-stream",
            "X": "FILLED",
            "l": "0.5",
            "L": "30000",
            "E": 1660000000,
        }
    )

    ws = DummyWebSocket([message])
    connector = BinanceExecutionConnector(
        sandbox=True,
        enable_stream=True,
        transport=httpx.MockTransport(handler),
        ws_factory=lambda url: ws,
    )
    connector.connect(credentials={"API_KEY": "test-key", "API_SECRET": "test-secret"})

    event = connector.next_event(timeout=1.0)
    assert event is not None
    assert event["type"] == "fill"
    assert event["order_id"] == "555"
    assert connector.stream_is_healthy()
    connector.disconnect()


def test_binance_stream_emits_balance_event() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v3/userDataStream":
            return httpx.Response(200, json={"listenKey": "abc123"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    message = json.dumps(
        {
            "e": "outboundAccountPosition",
            "E": 1660000001,
            "B": [
                {"a": "BTC", "f": "0.25", "l": "0.10"},
                {"a": "USDT", "f": "1000", "l": "0"},
            ],
        }
    )

    ws = DummyWebSocket([message])
    connector = BinanceExecutionConnector(
        sandbox=True,
        enable_stream=True,
        transport=httpx.MockTransport(handler),
        ws_factory=lambda url: ws,
    )
    connector.connect(credentials={"API_KEY": "test-key", "API_SECRET": "test-secret"})

    event = connector.next_event(timeout=1.0)
    assert event is not None
    assert event["type"] == "balance"
    balances = {entry["asset"]: entry for entry in event["balances"]}
    assert balances["BTC"]["free"] == pytest.approx(0.25)
    assert balances["BTC"]["locked"] == pytest.approx(0.10)
    assert balances["USDT"]["free"] == pytest.approx(1000)

    connector.disconnect()
