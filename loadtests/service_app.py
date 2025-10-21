"""FastAPI application configured for deterministic load testing."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from application.api.service import create_app
from application.settings import AdminApiSettings
from loadtests.security import configure_security_overrides


def build_app() -> FastAPI:
    """Create a FastAPI instance with deterministic credentials for load tests."""

    configure_security_overrides()
    state_dir = Path("/tmp/tradepulse-loadtest")
    state_dir.mkdir(parents=True, exist_ok=True)
    settings = AdminApiSettings(
        audit_secret="loadtest-audit-secret-123456",
        kill_switch_store_path=state_dir / "kill_switch.sqlite",
        config_vault_path=state_dir / "config_vault.json",
    )
    return create_app(settings=settings)


app = build_app()


__all__ = ["app", "build_app"]
