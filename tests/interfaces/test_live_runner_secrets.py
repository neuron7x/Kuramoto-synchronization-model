# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path
from typing import Mapping
from unittest.mock import MagicMock

import httpx
import pytest

from interfaces.execution.common import AuthenticatedRESTExecutionConnector, HMACSigner
from interfaces.live_runner import LiveTradingRunner


def test_live_runner_uses_environment_vault_backend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    config_path = tmp_path / "live.toml"
    config_path.write_text(
        """
[loop]
state_dir = "state"

[[venues]]
name = "dummy"
class = "tests.interfaces.dummies.DummyConnector"
sandbox = true

  [venues.credentials]
  env_prefix = "DUMMY"
  required = ["API_KEY", "API_SECRET"]

    [venues.credentials.secret_backend]
    adapter = "vault"
    path_env = "DUMMY_VAULT_PATH"

      [venues.credentials.secret_backend.field_mapping]
      API_KEY = "api_key"
      API_SECRET = "api_secret"
""".strip(),
        encoding="utf-8",
    )

    store = {"secret/data/dummy": {"api_key": "vault-key", "api_secret": "vault-secret"}}

    monkeypatch.setenv("GEOSYNC_VAULT_ADDR", "https://vault.geosync.local")
    monkeypatch.setenv("GEOSYNC_VAULT_TOKEN", "vault-token")
    monkeypatch.setenv("DUMMY_VAULT_PATH", "secret/data/dummy")

    def _fake_build(config, **_):  # type: ignore[no-untyped-def]
        assert config.address == "https://vault.geosync.local"
        return lambda path: dict(store[path])

    monkeypatch.setattr("interfaces.secrets.backends.build_hashicorp_vault_resolver", _fake_build)
    monkeypatch.setattr("interfaces.live_runner.build_hashicorp_vault_resolver", _fake_build)

    runner = LiveTradingRunner(config_path=config_path)

    credentials = runner._credentials["dummy"]  # noqa: SLF001 - inspection helper
    assert credentials["API_KEY"] == "vault-key"
    assert credentials["API_SECRET"] == "vault-secret"


class _DummyAuthConnector(AuthenticatedRESTExecutionConnector):
    """In-memory connector used to validate credential rotation behaviour."""

    def __init__(self, resolver) -> None:
        super().__init__(
            "DUMMY",
            sandbox=True,
            base_url="https://example.invalid",
            sandbox_url="https://example.invalid",
            ws_url=None,
            credential_provider=None,
            optional_credential_keys=None,
            vault_resolver=resolver,
            vault_path="secret/path",
            enable_stream=False,
            http_client=MagicMock(spec=httpx.Client),
        )

    def _default_headers(self) -> dict[str, str]:
        return {}


def test_live_runner_loads_credentials_from_secret_backend(tmp_path: Path) -> None:
    config_path = tmp_path / "live.toml"
    config_path.write_text(
        """
[loop]
state_dir = "state"

[[venues]]
name = "dummy"
class = "tests.interfaces.dummies.DummyConnector"
sandbox = true

  [venues.credentials]
  env_prefix = "DUMMY"
  required = ["API_KEY", "API_SECRET"]

    [venues.credentials.secret_backend]
    adapter = "vault"
    path = "secret/data/dummy"

      [venues.credentials.secret_backend.field_mapping]
      API_KEY = "api_key"
      API_SECRET = "api_secret"
""".strip(),
        encoding="utf-8",
    )

    store = {"secret/data/dummy": {"api_key": "vault-key", "api_secret": "vault-secret"}}

    def resolver(path: str) -> Mapping[str, str]:
        return dict(store[path])

    runner = LiveTradingRunner(config_path=config_path, secret_backends={"vault": resolver})

    credentials = runner._credentials["dummy"]  # noqa: SLF001 - inspection helper
    assert credentials["API_KEY"] == "vault-key"
    assert credentials["API_SECRET"] == "vault-secret"

    connector = runner.connectors["dummy"]
    connector.connect(credentials)  # type: ignore[attr-defined]
    assert connector.last_credentials["API_KEY"] == "vault-key"


def test_authenticated_connector_refreshes_credentials_via_vault_resolver() -> None:
    store = {"secret/path": {"API_KEY": "initial", "API_SECRET": "alpha"}}

    def resolver(path: str) -> Mapping[str, str]:
        return dict(store[path])

    connector = _DummyAuthConnector(resolver)
    connector.connect()
    assert connector.credentials["API_KEY"] == "initial"
    assert isinstance(connector._signer, HMACSigner)  # noqa: SLF001

    store["secret/path"] = {"API_KEY": "rotated", "API_SECRET": "omega"}
    connector._refresh_credentials()  # noqa: SLF001 - exercising rotation hook

    assert connector.credentials["API_KEY"] == "rotated"
    assert isinstance(connector._signer, HMACSigner)
