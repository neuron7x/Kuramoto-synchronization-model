from __future__ import annotations

from fastapi.testclient import TestClient

from cortex_service.app.api import create_app
from cortex_service.app.config import (
    CortexSettings,
    DatabaseSettings,
    RegimeSettings,
    RiskSettings,
    ServiceMeta,
    SignalSettings,
)


def _test_settings() -> CortexSettings:
    return CortexSettings(
        service=ServiceMeta(),
        database=DatabaseSettings(),
        signals=SignalSettings(
            volatility_floor=1e-6,
            neighbor_coupling=0.4,
            valence_coupling=0.6,
            signal_gain=1.0,
        ),
        risk=RiskSettings(penalty_gain=1.5),
        regime=RegimeSettings(decay=0.2, min_valence=-1.0, max_valence=1.0, initial_valence=0.0),
    )


def test_signals_endpoint_computes_cognition() -> None:
    settings = _test_settings()
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.post(
        "/signals",
        json={
            "features": [0.12, -0.08, 0.03],
            "neighbors": [[0.1, 0.05], [-0.02, 0.04]],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"state", "signal", "coherence", "valence"}
    assert -1.0 <= payload["signal"] <= 1.0
    assert 0.0 <= payload["coherence"] <= 1.0
    assert -1.0 <= payload["valence"] <= 1.0


def test_risk_endpoint_returns_penalized_score() -> None:
    settings = _test_settings()
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.post(
        "/risk",
        json={
            "pnl_deltas": [0.4, -0.2, 0.1],
            "weights": [0.3, 0.5, 0.2],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert -1.0 <= payload["risk_score"] <= 1.0
    assert payload["risk_score"] < 0  # positive PnL reduces risk


def test_regime_endpoint_updates_valence() -> None:
    settings = _test_settings()
    app = create_app(settings=settings)
    client = TestClient(app)

    first = client.post("/regime", json={"feedback": 0.4})
    assert first.status_code == 200
    initial_valence = first.json()["valence"]

    second = client.post("/regime", json={"feedback": -0.3})
    assert second.status_code == 200
    updated_valence = second.json()["valence"]
    assert -1.0 <= updated_valence <= 1.0
    assert updated_valence != initial_valence

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["valence"] == updated_valence


def test_signals_rejects_empty_neighbors() -> None:
    settings = _test_settings()
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.post(
        "/signals",
        json={
            "features": [0.2, 0.1],
            "neighbors": [[0.1, 0.0], []],
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert "cannot be empty" in payload["detail"]


def test_risk_mismatched_lengths() -> None:
    settings = _test_settings()
    app = create_app(settings=settings)
    client = TestClient(app)

    response = client.post(
        "/risk",
        json={"pnl_deltas": [0.1, 0.2], "weights": [0.4]},
    )

    assert response.status_code == 400
    assert "same length" in response.json()["detail"]
