from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import pytest
import yaml

from application.runtime.init_control_platform import _merge_precedence
from application.settings import ApiServerSettings, BackendRuntimeSettings


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "TRADEPULSE_API_SERVER_HOST",
        "TRADEPULSE_API_SERVER_PORT",
        "TRADEPULSE_API_SERVER_ALLOW_PLAINTEXT",
        "TRADEPULSE_BACKEND_DEBUG",
        "TRADEPULSE_BACKEND_CONTROLLERS_REQUIRED",
    ):
        monkeypatch.delenv(key, raising=False)


def _write_yaml(path: Path, payload: Mapping[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_yaml_baseline_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    payload = {
        "runtime": {"controllers_required": False, "gate_defaults": {"min_position_multiplier": 0.1}},
        "server": {"host": "127.0.0.1", "port": 9100, "allow_plaintext": True},
    }
    _write_yaml(tmp_path / "config.yaml", payload)

    runtime = _merge_precedence(
        settings_cls=BackendRuntimeSettings, yaml_section=payload["runtime"], cli_overrides=None
    )
    server = _merge_precedence(
        settings_cls=ApiServerSettings, yaml_section=payload["server"], cli_overrides=None
    )

    assert runtime.controllers_required is False
    assert runtime.gate_defaults["min_position_multiplier"] == 0.1
    assert server.host == "127.0.0.1"
    assert server.port == 9100
    assert server.allow_plaintext is True


def test_env_overrides_yaml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    payload = {
        "runtime": {"controllers_required": False},
        "server": {"host": "0.0.0.0", "port": 8000, "allow_plaintext": True},
    }
    _write_yaml(tmp_path / "config.yaml", payload)
    monkeypatch.setenv("TRADEPULSE_API_SERVER_HOST", "10.0.0.1")
    monkeypatch.setenv("TRADEPULSE_API_SERVER_PORT", "8443")
    monkeypatch.setenv("TRADEPULSE_API_SERVER_ALLOW_PLAINTEXT", "true")

    runtime = _merge_precedence(
        settings_cls=BackendRuntimeSettings, yaml_section=payload["runtime"], cli_overrides=None
    )
    server = _merge_precedence(
        settings_cls=ApiServerSettings, yaml_section=payload["server"], cli_overrides=None
    )

    assert runtime.controllers_required is False
    assert server.host == "10.0.0.1"
    assert server.port == 8443


def test_cli_overrides_env_and_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    monkeypatch.setenv("TRADEPULSE_API_SERVER_HOST", "10.1.1.1")
    monkeypatch.setenv("TRADEPULSE_API_SERVER_PORT", "8080")
    yaml_section = {"host": "1.2.3.4", "port": 9000, "allow_plaintext": True}
    cli_overrides = {"host": "192.168.0.10", "port": 9443}

    server = _merge_precedence(
        settings_cls=ApiServerSettings, yaml_section=yaml_section, cli_overrides=cli_overrides
    )

    assert server.host == "192.168.0.10"
    assert server.port == 9443
    assert server.allow_plaintext is True


def test_unknown_keys_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_env(monkeypatch)
    yaml_section = {"host": "localhost", "port": 7000, "allow_plaintext": True, "unexpected": "value"}

    server = _merge_precedence(
        settings_cls=ApiServerSettings, yaml_section=yaml_section, cli_overrides=None
    )

    dumped = server.model_dump()
    assert "unexpected" not in dumped
    assert dumped["host"] == "localhost"
