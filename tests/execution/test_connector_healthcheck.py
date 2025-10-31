from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from execution.adapters.binance import BinanceRESTConnector
from execution.adapters.coinbase import CoinbaseRESTConnector
from execution.adapters.healthcheck import (
    HealthCheckOverrides,
    override_healthcheck,
)
from execution.adapters.kraken import KrakenRESTConnector
from execution.health import ConnectorHealth, HealthCheck, HealthStatus
from execution.live_loop import LiveExecutionLoop, LiveLoopConfig
from execution.risk import RiskLimits, RiskManager
from execution.connectors import ExecutionConnector


def _ws_payloads() -> tuple[list[str], list[float]]:
    payloads = [json.dumps({"p": "100.0"}) for _ in range(3)]
    intervals = [120.0, 110.0]
    return payloads, intervals


def _binance_client_factory() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/time"):
            return httpx.Response(200, json={"serverTime": 1_700_000_000_000})
        if path.endswith("/account"):
            assert "signature" in request.url.params
            return httpx.Response(200, json={"balances": []})
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    return httpx.Client(base_url="https://testnet.binance.vision", transport=transport)


def _coinbase_client_factory(success: bool = True) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/products"):
            return httpx.Response(200, json={"products": []})
        if path.endswith("/accounts"):
            status = 200 if success else 401
            payload = {"accounts": []} if success else {"error": "unauthorised"}
            return httpx.Response(status, json=payload)
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    return httpx.Client(
        base_url="https://api-public.sandbox.exchange.coinbase.com/api/v3/brokerage",
        transport=transport,
    )


def _kraken_client_factory() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/Time"):
            return httpx.Response(200, json={"result": {"unixtime": 1_700_000_000}})
        if path.endswith("/Balance"):
            assert request.headers.get("API-Sign")
            return httpx.Response(200, json={"error": [], "result": {"ZUSD": "10"}})
        if path.endswith("/GetWebSocketsToken"):
            return httpx.Response(200, json={"error": [], "result": {"token": "abc"}})
        return httpx.Response(404, json={})

    transport = httpx.MockTransport(handler)
    return httpx.Client(base_url="https://api.sandbox.kraken.com", transport=transport)


@pytest.mark.parametrize(
    "credentials",
    [
        {"api_key": "key", "api_secret": "secret"},
    ],
)
def test_binance_healthcheck_success(credentials: dict[str, str]) -> None:
    async def probe(url: str, count: int, timeout: float):  # pragma: no cover - async shim
        return _ws_payloads()

    overrides = HealthCheckOverrides(
        http_client_factory=_binance_client_factory,
        websocket_probe=probe,
    )
    with override_healthcheck("binance.spot", overrides):
        connector = BinanceRESTConnector(sandbox=True)
        health = connector.healthcheck(credentials)
    assert health.status is HealthStatus.OK
    assert any(check.name == "rest-latency" for check in health.checks)


def test_coinbase_healthcheck_auth_failure_marks_fail() -> None:
    async def probe(url: str, count: int, timeout: float):
        return _ws_payloads()

    overrides = HealthCheckOverrides(
        http_client_factory=lambda: _coinbase_client_factory(success=False),
        websocket_probe=probe,
    )
    credentials = {
        "api_key": "key",
        "api_secret": base64.b64encode(b"secret").decode(),
        "passphrase": "phrase",
    }
    with override_healthcheck("coinbase.advanced-trade", overrides):
        connector = CoinbaseRESTConnector(sandbox=True)
        health = connector.healthcheck(credentials)
    assert health.status is HealthStatus.FAIL
    assert any(check.status is HealthStatus.FAIL for check in health.checks)


def test_kraken_healthcheck_success() -> None:
    async def probe(url: str, count: int, timeout: float):
        return _ws_payloads()

    overrides = HealthCheckOverrides(
        http_client_factory=_kraken_client_factory,
        websocket_probe=probe,
    )
    credentials = {
        "api_key": "key",
        "api_secret": base64.b64encode(b"secret").decode(),
    }
    with override_healthcheck("kraken.spot", overrides):
        connector = KrakenRESTConnector(sandbox=True)
        health = connector.healthcheck(credentials)
    assert health.status is HealthStatus.OK
    assert health.metadata.get("status") == "OK"


def test_live_loop_refuses_to_start_when_health_not_ok(tmp_path: Path) -> None:
    class BadConnector(ExecutionConnector):
        def __init__(self) -> None:
            super().__init__(sandbox=True)

        def connect(self, credentials=None):  # pragma: no cover - unused
            raise AssertionError("connect should not be invoked")

        def healthcheck(self, credentials=None):
            return ConnectorHealth(
                status=HealthStatus.FAIL,
                checks=(
                    HealthCheck(name="probe", status=HealthStatus.FAIL, detail="forced"),
                ),
            )

    state_dir = tmp_path / "state"
    config = LiveLoopConfig(state_dir=state_dir)
    connectors = {"bad": BadConnector()}
    risk_manager = RiskManager(RiskLimits())
    loop = LiveExecutionLoop(connectors, risk_manager, config=config)

    with pytest.raises(RuntimeError):
        loop.start(cold_start=True)
