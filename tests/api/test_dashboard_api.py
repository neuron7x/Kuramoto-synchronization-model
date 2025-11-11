from __future__ import annotations

from fastapi.testclient import TestClient

from runtime.dashboard_api import app


def test_snapshot_endpoint_exposes_all_routes() -> None:
    client = TestClient(app)
    response = client.get("/dashboard/snapshot")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) >= {"route", "overview", "orders", "positions", "pnl", "signals", "community", "monitoring"}


def test_route_endpoints_return_consistent_payloads() -> None:
    client = TestClient(app)
    routes = [
        "overview",
        "monitoring",
        "positions",
        "orders",
        "pnl",
        "signals",
        "community",
    ]
    for route in routes:
        response = client.get(f"/dashboard/{route}")
        assert response.status_code == 200, route
        assert response.json() is not None


def test_stream_produces_messages() -> None:
    client = TestClient(app)
    with client.websocket_connect("/dashboard/stream") as websocket:
        snapshot = websocket.receive_json()
        assert snapshot["type"] == "snapshot"
        update = websocket.receive_json()
        assert update["type"] in {"orders", "positions", "pnl", "signals", "monitoring"}
