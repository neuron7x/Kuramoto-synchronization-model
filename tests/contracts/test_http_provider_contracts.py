# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "contract-import-token")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "contract-import-secret")
os.environ.setdefault("GEOSYNC_RBAC_AUDIT_SECRET", "contract-rbac-secret")

from application.api.service import FeatureResponse, PredictionResponse, create_app
from application.settings import AdminApiSettings
from domain import Signal, SignalAction
from src.admin.remote_control import AdminIdentity

API_V1_PREFIX = "/api/v1"


def _api_v1(path: str) -> str:
    return f"{API_V1_PREFIX}{path}"


BASELINE_DIR = Path("schemas/http/json/1.0.0")


class _ContractForecaster:
    """Deterministic forecaster used for provider contract validation."""

    def __init__(self) -> None:
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        records: list[dict[str, Any]] = []
        for offset in range(3):
            timestamp = start + timedelta(minutes=offset)
            records.append(
                {
                    "timestamp": timestamp,
                    "macd": 0.42 + offset * 0.01,
                    "macd_signal": 0.37 + offset * 0.01,
                    "macd_histogram": 0.05 + offset * 0.005,
                    "rsi": 61.2 + offset,
                    "return_1": 0.001 * (offset + 1),
                    "volatility_20": 0.02,
                    "queue_imbalance": 0.15,
                }
            )
        frame = pd.DataFrame.from_records(records)
        frame.set_index("timestamp", inplace=True)
        self._frame = frame

    def compute_features(self, payload) -> pd.DataFrame:  # type: ignore[override]
        return self._frame.copy()

    def _normalise_feature_row(self, row: pd.Series, *, strict: bool) -> pd.Series:  # type: ignore[override]
        return row

    def derive_signal(self, symbol: str, latest: pd.Series, horizon_seconds: int):  # type: ignore[override]
        signal = Signal(
            symbol=symbol,
            action=SignalAction.BUY,
            confidence=0.78,
            rationale="Contract test stub signal.",
            metadata={
                "horizon_seconds": horizon_seconds,
                "score": 0.42,
            },
        )
        return signal, 0.42


def _load_schema(filename: str) -> dict[str, Any]:
    return json.loads((BASELINE_DIR / filename).read_text(encoding="utf-8"))


def _sample_bars() -> list[dict[str, Any]]:
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    bars: list[dict[str, Any]] = []
    price = 42000.0
    for index in range(5):
        timestamp = base + timedelta(minutes=index)
        price += 5.0 if index % 2 == 0 else -2.5
        bars.append(
            {
                "timestamp": timestamp.isoformat(),
                "open": price - 1.0,
                "high": price + 2.0,
                "low": price - 2.5,
                "close": price,
                "volume": 100.0 + index,
                "bidVolume": 50.0 + index,
                "askVolume": 50.0 + index,
                "signedVolume": (-1) ** index * 5.0,
            }
        )
    return bars


def _feature_payload() -> dict[str, Any]:
    return {"symbol": "BTC-USD", "bars": _sample_bars()}


def _prediction_payload() -> dict[str, Any]:
    payload = _feature_payload()
    payload["horizon_seconds"] = 900
    return payload


@pytest.fixture()
def provider_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    def fake_verify_request_identity(*, require_client_certificate: bool = False):
        async def dependency(
            request: Request,  # noqa: ARG001 - required for FastAPI dependency signature
            credentials: object | None = None,
            settings: object | None = None,
        ) -> AdminIdentity:
            return AdminIdentity(subject="contract-suite", roles=("admin",))

        return dependency

    monkeypatch.setattr(
        "application.api.service.verify_request_identity",
        fake_verify_request_identity,
    )

    forecaster = _ContractForecaster()
    settings = AdminApiSettings(
        audit_secret="contract-audit-secret",
        kill_switch_store_path=tmp_path / "kill_switch.sqlite",
    )
    app = create_app(settings=settings, forecaster_factory=lambda: forecaster)
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()


def _assert_contract(
    name: str,
    payload: dict[str, Any],
    model: type[FeatureResponse] | type[PredictionResponse],
) -> None:
    schema = _load_schema(name)
    Draft202012Validator(schema).validate(payload)
    model.model_validate(payload)


def test_feature_provider_matches_contract(provider_client: TestClient) -> None:
    response = provider_client.post(_api_v1("/features"), json=_feature_payload())
    assert response.status_code == 200
    body = response.json()
    _assert_contract("feature_response.schema.json", body, FeatureResponse)


def test_prediction_provider_matches_contract(provider_client: TestClient) -> None:
    response = provider_client.post(_api_v1("/predictions"), json=_prediction_payload())
    assert response.status_code == 200
    body = response.json()
    _assert_contract("prediction_response.schema.json", body, PredictionResponse)


def test_idempotent_replay_respects_contract(provider_client: TestClient) -> None:
    headers = {"Idempotency-Key": "contract-idempotency"}
    first = provider_client.post(_api_v1("/features"), json=_feature_payload(), headers=headers)
    assert first.status_code == 200
    assert first.headers.get("Idempotency-Key") == "contract-idempotency"
    second = provider_client.post(_api_v1("/features"), json=_feature_payload(), headers=headers)
    assert second.status_code == 200
    assert second.headers.get("Idempotency-Key") == "contract-idempotency"
    assert second.headers.get("X-Idempotent-Replay") == "true"
    assert second.json() == first.json()
    _assert_contract("feature_response.schema.json", first.json(), FeatureResponse)
    _assert_contract("feature_response.schema.json", second.json(), FeatureResponse)
