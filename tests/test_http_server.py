"""FastAPI HTTP server: health, snapshot, SSE stream."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import coherence_bridge.http_server as http_mod
from coherence_bridge.mock_engine import MockEngine


@pytest.fixture(autouse=True)
def setup_engine():
    http_mod.engine = MockEngine()
    http_mod.writer = MagicMock()
    yield
    http_mod.engine = None
    http_mod.writer = None


@pytest.fixture
def client():
    return TestClient(http_mod.app)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["healthy"] is True
    assert len(data["instruments"]) >= 3


def test_snapshot_valid_instrument(client: TestClient) -> None:
    resp = client.get("/signal/EURUSD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["instrument"] == "EURUSD"
    assert 0.0 <= data["order_parameter_R"] <= 1.0
    assert data["timestamp_ns"] > 0
    assert data["regime"] in {"COHERENT", "METASTABLE", "DECOHERENT", "CRITICAL"}
    assert "sequence_number" in data


def test_snapshot_unknown_instrument(client: TestClient) -> None:
    resp = client.get("/signal/NONEXISTENT")
    assert resp.status_code == 404


def test_sse_stream_endpoint_route_registered(client: TestClient) -> None:
    """Verify /stream route is registered and documented in OpenAPI."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/stream" in paths
    assert "get" in paths["/stream"]
    # Verify query params exist in schema
    params = paths["/stream"]["get"].get("parameters", [])
    param_names = {p["name"] for p in params}
    assert "instruments" in param_names
    assert "interval_ms" in param_names


def test_snapshot_has_all_12_fields(client: TestClient) -> None:
    """Signal contract: all 12 fields required."""
    resp = client.get("/signal/EURUSD")
    data = resp.json()
    required = {
        "timestamp_ns",
        "instrument",
        "gamma",
        "order_parameter_R",
        "ricci_curvature",
        "lyapunov_max",
        "regime",
        "regime_confidence",
        "regime_duration_s",
        "signal_strength",
        "risk_scalar",
        "sequence_number",
    }
    assert set(data.keys()) == required


def test_all_instruments_accessible(client: TestClient) -> None:
    """Every instrument from /health should be queryable via /signal."""
    health = client.get("/health").json()
    for inst in health["instruments"]:
        resp = client.get(f"/signal/{inst}")
        assert resp.status_code == 200
        assert resp.json()["instrument"] == inst
