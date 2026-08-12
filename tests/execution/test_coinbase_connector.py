# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any

import httpx
import pytest

from domain import Order, OrderType
from interfaces.execution.coinbase import CoinbaseExecutionConnector


@pytest.fixture(autouse=True)
def _freeze_time(monkeypatch: pytest.MonkeyPatch) -> None:
    fixed = 1660001000
    monkeypatch.setattr("interfaces.execution.coinbase.time.time", lambda: fixed)


def _signature_for(payload: dict[str, Any], timestamp: int, method: str, path: str) -> str:
    body = json.dumps(payload, separators=(",", ":"))
    message = f"{timestamp}{method}{path}{body}".encode()
    return base64.b64encode(hmac.new(b"coinbase-secret", message, hashlib.sha256).digest()).decode()


def test_coinbase_signature_and_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    order_body = {
        "client_order_id": "idem-coin",
        "product_id": "BTC-USD",
        "side": "buy",
        "order_configuration": {"market_market_ioc": {"base_size": "1"}},
    }

    call_counts: dict[str, int] = {"post": 0, "get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v3/brokerage/orders":
            call_counts["post"] += 1
            timestamp = request.headers["CB-ACCESS-TIMESTAMP"]
            assert request.headers["CB-ACCESS-KEY"] == "coinbase-key"
            expected = _signature_for(order_body, int(timestamp), request.method, request.url.path)
            assert request.headers["CB-ACCESS-SIGN"] == expected
            assert request.headers["CB-ACCESS-PASSPHRASE"] == "coinbase-pass"
            return httpx.Response(200, json={"order_id": "order-1", "status": "OPEN"})
        if request.method == "GET" and request.url.path.startswith(
            "/api/v3/brokerage/orders/historical/"
        ):
            call_counts["get"] += 1
            return httpx.Response(
                200,
                json={
                    "order_id": "order-1",
                    "status": "OPEN",
                    "product_id": "BTC-USD",
                    "order_configuration": {
                        "limit_limit_gtc": {"base_size": "1", "limit_price": "30000"}
                    },
                },
            )
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    connector = CoinbaseExecutionConnector(
        sandbox=True,
        enable_stream=False,
        transport=httpx.MockTransport(handler),
    )
    connector.connect(
        credentials={
            "API_KEY": "coinbase-key",
            "API_SECRET": "coinbase-secret",
            "API_PASSPHRASE": "coinbase-pass",
        }
    )

    order = Order(symbol="BTC-USD", side="buy", quantity=1.0, order_type=OrderType.MARKET)
    first = connector.place_order(order, idempotency_key="idem-coin")
    second = connector.place_order(order, idempotency_key="idem-coin")

    assert first.order_id == second.order_id == "order-1"
    assert call_counts["post"] == 1
    assert call_counts["get"] == 1


def test_coinbase_rate_limit_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_calls: list[float] = []
    monkeypatch.setattr(
        "interfaces.execution.common.time.sleep",
        lambda value: sleep_calls.append(value),
    )

    call_sequence: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/v3/brokerage/orders":
            call_sequence.append("orders")
            if len(call_sequence) == 1:
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(200, json={"order_id": "order-2", "status": "OPEN"})
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    connector = CoinbaseExecutionConnector(
        sandbox=True,
        enable_stream=False,
        transport=httpx.MockTransport(handler),
    )
    connector.connect(
        credentials={
            "API_KEY": "coinbase-key",
            "API_SECRET": "coinbase-secret",
            "API_PASSPHRASE": "coinbase-pass",
        }
    )

    order = Order(symbol="BTC-USD", side="buy", quantity=1.0, order_type=OrderType.MARKET)
    response = connector.place_order(order)

    assert response.order_id == "order-2"
    assert call_sequence.count("orders") == 2
    assert sleep_calls
