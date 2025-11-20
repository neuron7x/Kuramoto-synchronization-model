from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from interfaces.secrets.backends import (
    AWSSecretsManagerBackendConfig,
    HashicorpVaultBackendConfig,
    SecretBackendConfigurationError,
    SecretBackendError,
    build_aws_secrets_manager_resolver,
    build_hashicorp_vault_resolver,
)


class _DummyVaultClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def read_kv_secret(
        self,
        *,
        mount: str,
        path: str,
        version: int = 2,
        actor: str | None = None,
        ip_address: str | None = None,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "mount": mount,
                "path": path,
                "version": version,
                "actor": actor,
                "ip_address": ip_address,
            }
        )
        return {"api_key": "vault-key", "api_secret": "vault-secret", "count": 3}


def test_hashicorp_config_from_environment_reads_token_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    token_path = tmp_path / "token"
    token_path.write_text("vault-token\n", encoding="utf-8")
    monkeypatch.setenv("TRADEPULSE_VAULT_ADDR", "https://vault.tradepulse.local")
    monkeypatch.delenv("TRADEPULSE_VAULT_TOKEN", raising=False)
    monkeypatch.setenv("TRADEPULSE_VAULT_TOKEN_FILE", str(token_path))

    config = HashicorpVaultBackendConfig.from_environment()

    assert config is not None
    assert config.address == "https://vault.tradepulse.local"
    assert config.token == "vault-token"


def test_hashicorp_config_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEPULSE_VAULT_ADDR", "https://vault.tradepulse.local")
    monkeypatch.delenv("TRADEPULSE_VAULT_TOKEN", raising=False)
    monkeypatch.delenv("TRADEPULSE_VAULT_TOKEN_FILE", raising=False)

    with pytest.raises(SecretBackendConfigurationError):
        HashicorpVaultBackendConfig.from_environment()


def test_hashicorp_resolver_fetches_secret_payload() -> None:
    config = HashicorpVaultBackendConfig(
        address="https://vault.tradepulse.local",
        token="vault-token",
        default_mount="secret",
        kv_version=2,
        namespace=None,
    )
    client = _DummyVaultClient()
    context = {"actor": "runner", "ip_address": "10.0.0.5"}
    resolver = build_hashicorp_vault_resolver(
        config,
        client_factory=lambda _: client,
        context_provider=lambda: context,
    )

    payload = resolver("secret/data/demo")

    assert payload["api_key"] == "vault-key"
    assert payload["api_secret"] == "vault-secret"
    assert payload["count"] == "3"
    assert client.calls[0]["mount"] == "secret"
    assert client.calls[0]["path"] == "demo"
    assert client.calls[0]["actor"] == "runner"
    assert client.calls[0]["ip_address"] == "10.0.0.5"


def test_hashicorp_resolver_supports_default_mount() -> None:
    config = HashicorpVaultBackendConfig(
        address="https://vault.tradepulse.local",
        token="vault-token",
        default_mount="secret",
        kv_version=2,
        namespace=None,
    )
    client = _DummyVaultClient()
    resolver = build_hashicorp_vault_resolver(config, client_factory=lambda _: client)

    payload = resolver("strategy/demo")

    assert payload["api_key"] == "vault-key"
    assert client.calls[0]["mount"] == "strategy"
    assert client.calls[0]["path"] == "demo"


def test_hashicorp_resolver_rejects_invalid_path() -> None:
    config = HashicorpVaultBackendConfig(
        address="https://vault.tradepulse.local",
        token="vault-token",
    )
    client = _DummyVaultClient()
    resolver = build_hashicorp_vault_resolver(config, client_factory=lambda _: client)

    with pytest.raises(SecretBackendError):
        resolver("secret")


def test_aws_config_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRADEPULSE_AWS_SECRETS_MANAGER_ENABLED", "true")
    monkeypatch.setenv("TRADEPULSE_AWS_SECRETS_REGION", "eu-central-1")

    config = AWSSecretsManagerBackendConfig.from_environment()

    assert config is not None
    assert config.region_name == "eu-central-1"


def test_aws_resolver_parses_json_secret() -> None:
    config = AWSSecretsManagerBackendConfig(region_name="us-east-1")

    class _DummyClient:
        def get_secret_value(self, *, SecretId: str) -> Mapping[str, Any]:  # type: ignore[override]
            assert SecretId == "app/demo"
            return {"SecretString": json.dumps({"apiKey": "value", "retries": 2})}

    resolver = build_aws_secrets_manager_resolver(
        config, client_factory=lambda _: _DummyClient()
    )

    payload = resolver("app/demo")

    assert payload["apiKey"] == "value"
    assert payload["retries"] == "2"


def test_aws_resolver_decodes_binary_secret() -> None:
    config = AWSSecretsManagerBackendConfig(region_name="us-east-1")

    class _DummyClient:
        def get_secret_value(self, *, SecretId: str) -> Mapping[str, Any]:  # type: ignore[override]
            assert SecretId == "app/binary"
            encoded = base64.b64encode(b"binary-secret").decode("ascii")
            return {"SecretBinary": encoded}

    resolver = build_aws_secrets_manager_resolver(
        config, client_factory=lambda _: _DummyClient()
    )

    payload = resolver("app/binary")

    assert payload["value"] == "binary-secret"


def test_aws_resolver_errors_when_payload_missing() -> None:
    config = AWSSecretsManagerBackendConfig(region_name="us-east-1")

    class _DummyClient:
        def get_secret_value(self, *, SecretId: str) -> Mapping[str, Any]:  # type: ignore[override]
            assert SecretId == "app/invalid"
            return {}

    resolver = build_aws_secrets_manager_resolver(
        config, client_factory=lambda _: _DummyClient()
    )

    with pytest.raises(SecretBackendError):
        resolver("app/invalid")
