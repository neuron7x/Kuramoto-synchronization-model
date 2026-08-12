# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from core.compat import UTC

os.environ.setdefault("CORTEX__DATABASE__URL", "'sqlite+pysqlite:///:memory:'")
os.environ.setdefault("CORTEX__DATABASE__POOL_SIZE", "1")
os.environ.setdefault("CORTEX__DATABASE__POOL_TIMEOUT", "30")

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
        database=DatabaseSettings(
            url="sqlite+pysqlite:///:memory:", pool_size=1, pool_timeout=30, echo=False
        ),
        signals=SignalSettings(
            smoothing_factor=0.2,
            rescale_min=-1.0,
            rescale_max=1.0,
            volatility_floor=1e-6,
        ),
        risk=RiskSettings(
            max_absolute_exposure=2.0, var_confidence=0.95, stress_scenarios=(0.8, 0.5)
        ),
        regime=RegimeSettings(decay=0.2, min_valence=-1.0, max_valence=1.0, confidence_floor=0.1),
    )


def _sqlite_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def test_signals_endpoint_computes_ensemble() -> None:
    settings = _test_settings()
    engine = _sqlite_engine()
    app = create_app(settings=settings, engine=engine)
    client = TestClient(app)

    response = client.post(
        "/signals",
        json={
            "as_of": datetime.now(tz=UTC).isoformat(),
            "features": [
                {
                    "instrument": "AAPL",
                    "name": "momentum",
                    "value": 1.3,
                    "mean": 0.2,
                    "std": 0.5,
                    "weight": 1.5,
                },
                {
                    "instrument": "AAPL",
                    "name": "volatility",
                    "value": 0.4,
                    "mean": 0.3,
                    "std": 0.2,
                    "weight": 0.7,
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["signals"][0]["instrument"] == "AAPL"
    assert -1.0 <= payload["signals"][0]["strength"] <= 1.0
    assert payload["synchrony"] >= 0.0


def test_risk_endpoint_returns_metrics() -> None:
    settings = _test_settings()
    engine = _sqlite_engine()
    app = create_app(settings=settings, engine=engine)
    client = TestClient(app)

    response = client.post(
        "/risk",
        json={
            "exposures": [
                {
                    "portfolio_id": "alpha",
                    "instrument": "AAPL",
                    "exposure": 0.7,
                    "leverage": 1.2,
                    "as_of": datetime.now(tz=UTC).isoformat(),
                    "limit": 1.0,
                    "volatility": 0.3,
                }
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["score"] >= 0.0
    assert payload["value_at_risk"] >= 0.0


def test_regime_endpoint_persists_state() -> None:
    settings = _test_settings()
    engine = _sqlite_engine()
    app = create_app(settings=settings, engine=engine)
    client = TestClient(app)

    first = client.post(
        "/regime",
        json={
            "feedback": 0.4,
            "volatility": 0.2,
            "as_of": datetime.now(tz=UTC).isoformat(),
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/regime",
        json={
            "feedback": -0.3,
            "volatility": 0.1,
            "as_of": datetime.now(tz=UTC).isoformat(),
        },
    )
    assert second.status_code == 200
    assert second.json()["label"] in {"bullish", "bearish", "neutral", "indeterminate"}


def test_memory_round_trip() -> None:
    settings = _test_settings()
    engine = _sqlite_engine()
    app = create_app(settings=settings, engine=engine)
    client = TestClient(app)

    as_of = datetime.now(tz=UTC).isoformat()
    store = client.post(
        "/memory",
        json={
            "exposures": [
                {
                    "portfolio_id": "alpha",
                    "instrument": "AAPL",
                    "exposure": 1.1,
                    "leverage": 1.2,
                    "as_of": as_of,
                    "limit": 2.0,
                    "volatility": 0.2,
                }
            ]
        },
    )
    assert store.status_code == 202

    fetch = client.get("/memory/alpha")
    assert fetch.status_code == 200
    payload = fetch.json()
    assert payload["portfolio_id"] == "alpha"
    assert payload["exposures"]
