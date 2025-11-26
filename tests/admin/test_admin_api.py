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
