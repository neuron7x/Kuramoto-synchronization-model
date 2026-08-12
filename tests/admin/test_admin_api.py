# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for admin API endpoints."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from admin.api import create_admin_app
from execution.compliance import RiskCompliance, RiskConfig
from execution.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


@pytest.fixture
def risk_compliance():
    """Create a RiskCompliance instance for testing."""
    config = RiskConfig(
        kill_switch=False,
        max_notional_per_order=10000.0,
        max_gross_exposure=50000.0,
    )
    return RiskCompliance(config)


@pytest.fixture
def circuit_breaker():
    """Create a CircuitBreaker instance for testing."""
    config = CircuitBreakerConfig()
    return CircuitBreaker(config)


@pytest.fixture
def admin_app(risk_compliance, circuit_breaker):
    """Create admin app with risk compliance and circuit breaker."""
    return create_admin_app(
        risk_compliance=risk_compliance,
        circuit_breaker=circuit_breaker,
    )


@pytest.fixture
def client(admin_app):
    """Create test client."""
    return TestClient(admin_app)


@pytest.fixture(autouse=True)
def set_admin_token():
    """Set admin API token for tests."""
    os.environ["ADMIN_API_TOKEN"] = "test-secret-token"
    yield
    os.environ.pop("ADMIN_API_TOKEN", None)


class TestAdminAPI:
    """Test suite for admin API endpoints."""

    def test_health_check_no_auth(self, client):
        """Test health check endpoint works without auth."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"

    def test_toggle_kill_switch_enable(self, client, risk_compliance):
        """Test enabling kill switch via API."""
        response = client.post(
            "/admin/risk/kill_switch",
            json={"enabled": True},
            headers={"Authorization": "Bearer test-secret-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["kill_switch"] is True
        assert risk_compliance._config.kill_switch is True

    def test_toggle_kill_switch_disable(self, client, risk_compliance):
        """Test disabling kill switch via API."""
        risk_compliance.set_kill_switch(True)

        response = client.post(
            "/admin/risk/kill_switch",
            json={"enabled": False},
            headers={"Authorization": "Bearer test-secret-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["kill_switch"] is False
        assert risk_compliance._config.kill_switch is False

    def test_toggle_kill_switch_unauthorized(self, client):
        """Test kill switch endpoint rejects invalid token."""
        response = client.post(
            "/admin/risk/kill_switch",
            json={"enabled": True},
            headers={"Authorization": "Bearer wrong-token"},
        )

        assert response.status_code == 401

    def test_toggle_kill_switch_no_token(self, client):
        """Test kill switch endpoint rejects missing token."""
        response = client.post(
            "/admin/risk/kill_switch",
            json={"enabled": True},
        )

        # HTTPBearer returns 401 when credentials are missing
        assert response.status_code == 401

    def test_get_risk_state(self, client, risk_compliance):
        """Test getting risk state via API."""
        risk_compliance.set_kill_switch(True)

        response = client.get(
            "/admin/risk/state",
            headers={"Authorization": "Bearer test-secret-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["kill_switch"] is True
        assert data["max_notional_per_order"] == 10000.0
        assert data["max_gross_exposure"] == 50000.0
        assert "timestamp" in data

    def test_get_risk_state_with_circuit_breaker(self, client, circuit_breaker):
        """Test risk state includes circuit breaker info."""
        response = client.get(
            "/admin/risk/state",
            headers={"Authorization": "Bearer test-secret-token"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "circuit_breaker_state" in data
        assert data["circuit_breaker_state"] == "closed"
        assert "circuit_breaker_ttl" in data

    def test_get_risk_state_unauthorized(self, client):
        """Test risk state endpoint rejects invalid token."""
        response = client.get(
            "/admin/risk/state",
            headers={"Authorization": "Bearer wrong-token"},
        )

        assert response.status_code == 401

    def test_app_without_risk_compliance(self):
        """Test API gracefully handles missing risk compliance."""
        app = create_admin_app(risk_compliance=None, circuit_breaker=None)
        client = TestClient(app)

        response = client.post(
            "/admin/risk/kill_switch",
            json={"enabled": True},
            headers={"Authorization": "Bearer test-secret-token"},
        )

        assert response.status_code == 503

    def test_app_without_admin_token_configured(self, client):
        """Test API rejects requests when token not configured."""
        os.environ.pop("ADMIN_API_TOKEN", None)

        response = client.post(
            "/admin/risk/kill_switch",
            json={"enabled": True},
            headers={"Authorization": "Bearer any-token"},
        )

        assert response.status_code == 500

    def test_token_comparison_is_constant_time(self, client, monkeypatch):
        """DEFECT 6: the admin token check must use hmac.compare_digest.

        A `!=` string compare leaks length/prefix timing on the kill-switch
        gate. We assert the wrong-token path is routed through
        ``hmac.compare_digest`` (and still rejects with 401).
        """
        import admin.api as admin_api

        calls: list[tuple[str, str]] = []
        real_compare = admin_api.hmac.compare_digest

        def _spy(a, b):
            calls.append((a, b))
            return real_compare(a, b)

        monkeypatch.setattr(admin_api.hmac, "compare_digest", _spy)

        response = client.post(
            "/admin/risk/kill_switch",
            json={"enabled": True},
            headers={"Authorization": "Bearer wrong-token"},
        )

        assert response.status_code == 401
        assert calls, "verify_token must route the token check through hmac.compare_digest"
        # Operands are encoded to bytes before compare_digest (DS-22): bytes-vs-bytes
        # is total and never raises TypeError on non-ASCII input.
        assert calls[-1] == (b"wrong-token", b"test-secret-token")

    def test_non_ascii_bearer_token_is_401_not_500(self):
        """DS-22 [DoS]: a non-ASCII Bearer token must not crash verify_token.

        ``hmac.compare_digest`` over two ``str`` operands raises ``TypeError``
        the moment either contains a non-ASCII code point, which FastAPI turns
        into an unhandled HTTP 500 (fail-closed but 500-spammable). Encoding
        both operands to bytes makes the compare total, so a bad Unicode token
        is a clean 401 rejection. We exercise ``verify_token`` directly because
        HTTP header transport is latin-1 and cannot carry the repro payload.
        """
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials

        from admin.api import verify_token

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="паролькириличний")
        with pytest.raises(HTTPException) as exc_info:
            verify_token(credentials=creds)
        # 401 (clean reject), NOT a bubbled-up TypeError -> 500.
        assert exc_info.value.status_code == 401

    def test_correct_token_still_authorizes_after_bytes_fix(self, client, risk_compliance):
        """DS-22 non-vacuous twin: the exact token still authorizes post-fix."""
        response = client.post(
            "/admin/risk/kill_switch",
            json={"enabled": True},
            headers={"Authorization": "Bearer test-secret-token"},
        )

        assert response.status_code == 200
        assert risk_compliance._config.kill_switch is True
