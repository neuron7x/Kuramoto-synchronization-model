from __future__ import annotations

import types

import pytest

from application.runtime.server import enforce_prod_server_flags
from interfaces.streamlit_security import enforce_dev_only_dashboard


def test_uvicorn_reload_blocked_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEPULSE_ENV", "production")
    config = types.SimpleNamespace(reload=True)

    with pytest.raises(RuntimeError):
        enforce_prod_server_flags(config)  # type: ignore[arg-type]


def test_uvicorn_reload_allowed_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEPULSE_ENV", "production")
    config = types.SimpleNamespace(reload=False)

    enforce_prod_server_flags(config)  # type: ignore[arg-type]


def test_streamlit_dashboard_blocked_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEPULSE_ENV", "production")
    monkeypatch.delenv("ALLOW_STREAMLIT_PROD", raising=False)

    with pytest.raises(RuntimeError):
        enforce_dev_only_dashboard()


def test_streamlit_dashboard_opt_in_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEPULSE_ENV", "production")
    monkeypatch.setenv("ALLOW_STREAMLIT_PROD", "1")

    enforce_dev_only_dashboard()
