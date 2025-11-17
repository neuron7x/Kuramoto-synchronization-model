from __future__ import annotations

from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

import pytest
from fastapi.testclient import TestClient

from application.api.system_access import create_system_app
from application.security.rbac import AuthorizationGateway, build_authorization_gateway
from application.settings import ApiRateLimitSettings, RateLimitPolicy
from application.system import (
    ExchangeAdapterConfig,
    TradePulseSystem,
    TradePulseSystemConfig,
)
from domain import Order
from execution.connectors import SimulatedExchangeConnector
from src.admin.remote_control import AdminIdentity
from src.audit.audit_logger import AuditLogger

TRADE_HEADERS = {"X-Trade-Environment": "production", "X-Trade-Desk": "execution"}


class _EagerFillConnector(SimulatedExchangeConnector):
    """Connector that immediately fills orders and exposes static positions."""

    def __init__(self, *, positions: list[dict[str, Any]] | None = None) -> None:
        super().__init__()
        self._positions = positions or [
            {
                "symbol": "BTCUSD",
                "quantity": 0.5,
                "entry_price": 48000.0,
                "current_price": 50000.0,
                "unrealized_pnl": 1000.0,
            }
        ]

    def get_positions(self) -> list[dict[str, Any]]:
        return list(self._positions)

    def place_order(self, order: Order, *, idempotency_key: str | None = None) -> Order:
        placed = super().place_order(order, idempotency_key=idempotency_key)
        fill_price = order.price or 50000.0
        placed.record_fill(order.quantity, fill_price)
        return placed


@pytest.fixture()
def system() -> TradePulseSystem:
    connector = _EagerFillConnector()
    config = TradePulseSystemConfig(
        venues=(ExchangeAdapterConfig(name="dummy", connector=connector),)
    )
    return TradePulseSystem(config)


@pytest.fixture()
def authorized_identity() -> AdminIdentity:
    return AdminIdentity(
        subject="integration-test", roles=("foundation:viewer", "trading:operator")
    )


@pytest.fixture()
def identity_dependency(authorized_identity: AdminIdentity):
    async def _dependency() -> AdminIdentity:
        return authorized_identity

    return _dependency


@pytest.fixture()
def authorization_gateway() -> AuthorizationGateway:
    policy_path = (
        Path(__file__).resolve().parents[2] / "configs" / "rbac" / "policy.yaml"
    )
    audit_logger = AuditLogger(secret="integration-rbac-secret")
    return build_authorization_gateway(
        policy_path=policy_path, audit_logger=audit_logger
    )


@pytest.fixture()
def client(
    system: TradePulseSystem,
    identity_dependency: Callable[[], Awaitable[AdminIdentity]],
    authorization_gateway: AuthorizationGateway,
) -> TestClient:
    app = create_system_app(
        system,
        identity_dependency=identity_dependency,
        reader_roles=("foundation:viewer",),
        trader_roles=("trading:operator",),
        authorization_gateway=authorization_gateway,
    )
    return TestClient(app)


def test_status_endpoint_reports_running_state(client: TestClient) -> None:
    response = client.get("/api/v1/status")
    payload = response.json()

    assert response.status_code == 200
    assert payload["status"] == "running"
    assert isinstance(payload["uptime_seconds"], (int, float))
    assert payload["uptime_seconds"] >= 0
    assert isinstance(payload["version"], str) and payload["version"]


def test_positions_endpoint_returns_normalised_payload(client: TestClient) -> None:
    response = client.get("/api/v1/positions")
    payload = response.json()

    assert response.status_code == 200
    assert "positions" in payload
    assert payload["positions"], "expected positions to be returned"
    position = payload["positions"][0]
    assert position["symbol"] == "BTCUSD"
    assert pytest.approx(position["quantity"], rel=1e-6) == 0.5
    assert pytest.approx(position["entry_price"], rel=1e-6) == 48000.0
    assert pytest.approx(position["current_price"], rel=1e-6) == 50000.0
    assert pytest.approx(position["unrealized_pnl"], rel=1e-6) == 1000.0


def test_order_submission_returns_filled_order(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "ETHUSD",
            "side": "buy",
            "order_type": "limit",
            "quantity": 1.0,
            "price": 1800.0,
        },
        headers=TRADE_HEADERS,
    )

    payload = response.json()
    assert response.status_code == 201
    assert payload["status"] == "filled"
    assert pytest.approx(payload["filled_quantity"], rel=1e-6) == 1.0
    assert pytest.approx(payload["average_price"], rel=1e-6) == 1800.0
    assert payload["order_id"]


def test_limit_order_requires_price_validation(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "ETHUSD",
            "side": "buy",
            "order_type": "limit",
            "quantity": 1.0,
        },
        headers=TRADE_HEADERS,
    )

    assert response.status_code == 422
    detail = response.json()
    assert detail["detail"][0]["msg"].startswith("Value error")


def test_market_order_requires_reference_price(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "ETHUSD",
            "side": "buy",
            "quantity": 0.5,
        },
        headers=TRADE_HEADERS,
    )

    assert response.status_code == 422
    detail = response.json()
    assert any(
        "reference_price" in error.get("msg", "") for error in detail.get("detail", [])
    )


def test_market_order_uses_reference_price_for_risk_validation(
    client: TestClient, system: TradePulseSystem, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, float] = {}

    def _capture(symbol: str, side: str, qty: float, price: float) -> None:
        captured.update(symbol=symbol, side=side, qty=qty, price=price)

    monkeypatch.setattr(system.risk_manager, "validate_order", _capture)

    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "ETHUSD",
            "side": "buy",
            "quantity": 0.25,
            "reference_price": 1900.0,
        },
        headers=TRADE_HEADERS,
    )

    assert response.status_code == 201
    assert captured["price"] == 1900.0


def test_trade_denied_when_trade_attributes_missing(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "ETHUSD",
            "side": "buy",
            "order_type": "limit",
            "quantity": 1.0,
            "price": 1800.0,
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["detail"]["failure_reason"] == "attribute_mismatch"


def test_trade_denied_when_desk_not_authorized(client: TestClient) -> None:
    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "ETHUSD",
            "side": "buy",
            "order_type": "limit",
            "quantity": 1.0,
            "price": 1800.0,
        },
        headers={**TRADE_HEADERS, "X-Trade-Desk": "research"},
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["detail"]["failure_reason"] == "attribute_mismatch"
    required_roles = payload["detail"]["required_roles"]
    assert "trading:operator" in required_roles


def test_trader_role_is_required(system: TradePulseSystem) -> None:
    async def _limited_identity() -> AdminIdentity:
        return AdminIdentity(subject="integration-test", roles=("foundation:viewer",))

    gateway = build_authorization_gateway(
        policy_path=Path(__file__).resolve().parents[2]
        / "configs"
        / "rbac"
        / "policy.yaml",
        audit_logger=AuditLogger(secret="integration-rbac-secret"),
    )
    app = create_system_app(
        system,
        identity_dependency=_limited_identity,
        reader_roles=("foundation:viewer",),
        trader_roles=("trading:operator",),
        authorization_gateway=gateway,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "BTCUSD",
            "side": "buy",
            "quantity": 1.0,
            "reference_price": 42000.0,
        },
        headers=TRADE_HEADERS,
    )

    assert response.status_code == 403
    payload = response.json()
    required_roles = payload["detail"]["required_roles"]
    assert "trading:operator" in required_roles
    assert payload["detail"]["failure_reason"] == "missing_role"


def test_order_submission_emits_notification(
    system: TradePulseSystem,
    identity_dependency: Callable[[], Awaitable[AdminIdentity]],
    authorization_gateway: AuthorizationGateway,
) -> None:
    events: list[dict[str, Any]] = []

    class _Recorder:
        async def dispatch(
            self,
            event: str,
            *,
            subject: str,
            message: str,
            metadata: Mapping[str, Any] | None = None,
        ) -> None:
            events.append(
                {
                    "event": event,
                    "subject": subject,
                    "message": message,
                    "metadata": dict(metadata or {}),
                }
            )

    recorder = _Recorder()
    app = create_system_app(
        system,
        identity_dependency=identity_dependency,
        authorization_gateway=authorization_gateway,
        notification_dispatcher=recorder,
    )
    client = TestClient(app)

    response = client.post(
        "/api/v1/orders",
        json={
            "symbol": "ETHUSD",
            "side": "buy",
            "order_type": "limit",
            "quantity": 1.0,
            "price": 1800.0,
        },
        headers=TRADE_HEADERS,
    )

    assert response.status_code == 201
    assert events, "expected notification to be dispatched"
    assert events[0]["event"] == "order.submitted"
    assert events[0]["metadata"]["symbol"] == "ETHUSD"


def test_rate_limit_blocks_excessive_requests(
    system: TradePulseSystem,
    identity_dependency: Callable[[], Awaitable[AdminIdentity]],
    authorization_gateway: AuthorizationGateway,
) -> None:
    rate_settings = ApiRateLimitSettings(
        default_policy=RateLimitPolicy(max_requests=2, window_seconds=60.0)
    )
    app = create_system_app(
        system,
        identity_dependency=identity_dependency,
        reader_roles=("foundation:viewer",),
        trader_roles=("trading:operator",),
        authorization_gateway=authorization_gateway,
        rate_limit_settings=rate_settings,
    )
    client = TestClient(app)

    first = client.get("/api/v1/status")
    second = client.get("/api/v1/status")
    assert first.status_code == 200
    assert second.status_code == 200

    blocked = client.get("/api/v1/status")
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "Rate limit exceeded for this client."
