"""Unit tests for bootstrap helpers in application.api.service."""

from __future__ import annotations

import importlib
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

MODULE_PATH = "application.api.service"


def _reload_service_module(monkeypatch: pytest.MonkeyPatch) -> object:
    """Reload the service module with lazy bootstrap enabled."""

    monkeypatch.setenv("TRADEPULSE_BOOTSTRAP_STRATEGY", "lazy")
    module = importlib.import_module(MODULE_PATH)
    importlib.reload(module)
    return module


@pytest.fixture(autouse=True)
def cleanup_service_module() -> None:
    """Ensure the service module does not leak between tests."""

    yield
    sys.modules.pop(MODULE_PATH, None)


def test_bootstrap_lazy_strategy_skips_application_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lazy strategy should return the degraded placeholder without calling create_app."""

    service = _reload_service_module(monkeypatch)

    called = False

    def _should_not_run() -> None:
        nonlocal called
        called = True
        raise AssertionError("create_app should not be invoked when strategy=lazy")

    monkeypatch.setattr(service, "create_app", _should_not_run)

    app = service.bootstrap_application()

    assert isinstance(app, FastAPI)
    assert getattr(app.state, "degraded_reason") == (
        "Bootstrap disabled via TRADEPULSE_BOOTSTRAP_STRATEGY=lazy."
    )
    assert not called, "create_app was invoked despite lazy strategy"


def test_bootstrap_degraded_falls_back_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When degraded mode is enabled the bootstrap should surface a placeholder app."""

    service = _reload_service_module(monkeypatch)

    def _boom() -> None:
        raise RuntimeError("secret missing")

    monkeypatch.setattr(service, "create_app", _boom)
    monkeypatch.setenv("TRADEPULSE_BOOTSTRAP_STRATEGY", "degraded")

    app = service.bootstrap_application()

    assert isinstance(app, FastAPI)
    assert getattr(app.state, "degraded_reason") == (
        "Application bootstrap failed in degraded mode."
    )
    detail = getattr(app.state, "degraded_detail")
    assert detail is not None and "secret missing" in detail

    # Health endpoint should return degraded status without raising.
    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
