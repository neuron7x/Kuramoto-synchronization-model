from __future__ import annotations

import base64
import hmac
import json
from urllib.parse import urlencode

import httpx
import pytest

from domain import Order, OrderSide, OrderType
from execution.connectors import OrderError
from interfaces.execution.binance import BinanceExecutionConnector
from interfaces.execution.coinbase import CoinbaseExecutionConnector
from interfaces.execution.common import HMACSigner, is_rate_limited


@pytest.fixture()
def fixed_time(monkeypatch):
    monkeypatch.setattr("time.time", lambda: 1_700_000_000.0)


def test_binance_signature_is_deterministic(fixed_time) -> None:
    connector = BinanceExecutionConnector(sandbox=True, enable_stream=False)
    connector._signer = HMACSigner("secret")  # type: ignore[attr-defined]
    connector._credentials = {"API_KEY": "key", "API_SECRET": "secret"}  # type: ignore[attr-defined]

    params, headers, body = connector._apply_signature(
        "POST",
        "/api/v3/order",
        {"symbol": "BTCUSDT", "quantity": 1, "price": 100},
        {},
        None,
    )

    expected = {
        "price": 100,
        "quantity": 1,
        "recvWindow": connector.RECV_WINDOW,
        "symbol": "BTCUSDT",
        "timestamp": 1_700_000_000_000,
    }
    query = urlencode(sorted((k, str(v)) for k, v in expected.items()))
    expected_sig = hmac.new(b"secret", query.encode(), digestmod="sha256").hexdigest()

    assert headers["X-MBX-APIKEY"] == "key"
    assert params["signature"] == expected_sig
    assert body is None


def test_coinbase_signature_is_deterministic(fixed_time) -> None:
    connector = CoinbaseExecutionConnector(sandbox=True, enable_stream=False)
    connector._signer = HMACSigner("ignored")  # type: ignore[attr-defined]
    connector._credentials = {  # type: ignore[attr-defined]
        "API_KEY": "key",
        "API_SECRET": "secret",
        "API_PASSPHRASE": "pass",
    }

    params, headers, body = connector._apply_signature(
        "POST",
        "/api/v3/brokerage/orders",
        {},
        {},
        {"side": "BUY", "product_id": "BTC-USD", "order_configuration": {}},
    )

    payload = json.dumps(body, separators=(",", ":"))
    message = f"1700000000POST/api/v3/brokerage/orders{payload}"
    digest = hmac.new(b"secret", message.encode(), digestmod="sha256").digest()
    expected_sig = base64.b64encode(digest).decode()

    assert headers["CB-ACCESS-KEY"] == "key"
    assert headers["CB-ACCESS-PASSPHRASE"] == "pass"
    assert headers["CB-ACCESS-SIGN"] == expected_sig
    assert params == {}


def test_binance_http_error_maps_to_order_error(monkeypatch) -> None:
    connector = BinanceExecutionConnector(sandbox=True, enable_stream=False)
    connector._signer = HMACSigner("secret")  # type: ignore[attr-defined]
    connector._credentials = {"API_KEY": "key", "API_SECRET": "secret"}  # type: ignore[attr-defined]

    order = Order(
        symbol="BTCUSDT",
        side=OrderSide.BUY,
        quantity=0.1,
        price=10_000.0,
        order_type=OrderType.LIMIT,
    )

    request = httpx.Request("POST", "https://api.binance.com/api/v3/order")
    response = httpx.Response(429, request=request)
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)

    def _raise(*_: object, **__: object):
        raise exc

    monkeypatch.setattr(connector, "_request", _raise)

    with pytest.raises(OrderError):
        connector.place_order(order)


def test_rate_limit_detection() -> None:
    req = httpx.Request("GET", "https://example.com")
    resp_429 = httpx.Response(429, request=req)
    resp_header = httpx.Response(
        200, headers={"X-RateLimit-Remaining": "0"}, request=req
    )

    assert is_rate_limited(resp_429)
    assert is_rate_limited(resp_header)
