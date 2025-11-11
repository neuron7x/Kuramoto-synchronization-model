from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from application.api.service import create_app
from application.settings import AdminApiSettings, BackendRuntimeSettings


def _dashboard_snapshot_path() -> Path:
    return Path(__file__).resolve().parents[1] / "observability" / "data" / "production_snapshot.json"


def _admin_settings() -> AdminApiSettings:
    return AdminApiSettings(
        audit_secret=SecretStr("a" * 32),
        two_factor_secret=SecretStr("b" * 32),
        admin_environment="test",
    )


def _runtime_settings() -> BackendRuntimeSettings:
    return BackendRuntimeSettings(
        production_dashboard_snapshot=_dashboard_snapshot_path(),
        debug=False,
    )


def test_production_dashboard_endpoint_returns_payload() -> None:
    app = create_app(settings=_admin_settings(), runtime_settings=_runtime_settings())
    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard/production")
    assert response.status_code == 200
    payload = response.json()
    assert payload["environment"] == "test"
    assert payload["controls"]["killSwitch"]["enabled"] is False
    assert payload["metrics"]["grossExposure"]["value"] == 1230000.0
    assert payload["alerts"]


def test_production_dashboard_endpoint_handles_missing_snapshot(tmp_path: Path) -> None:
    settings = _admin_settings()
    runtime_settings = BackendRuntimeSettings(
        production_dashboard_snapshot=tmp_path / "missing.json",
        debug=False,
    )
    app = create_app(settings=settings, runtime_settings=runtime_settings)
    with TestClient(app) as client:
        response = client.get("/api/v1/dashboard/production")
    assert response.status_code == 200
    payload = response.json()
    assert payload["environment"] == settings.admin_environment
    assert payload["controls"]["circuitBreaker"]["state"] == "unknown"
    assert payload["alerts"] == []
