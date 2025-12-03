"""Secret backend resolvers for HashiCorp Vault and AWS Secrets Manager."""

from __future__ import annotations

import base64
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping, Protocol

from interfaces.secrets.manager import VaultResolver

try:  # pragma: no cover - boto3 is optional at runtime
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover - provide lightweight fallbacks for tests
    BotoCoreError = ClientError = Exception  # type: ignore[misc, assignment]

from application.secrets.hashicorp import (
    StaticTokenAuthenticator,
    VaultClient,
    VaultClientConfig,
    VaultRequestError,
)

__all__ = [
    "AWSSecretsManagerBackendConfig",
    "HashicorpVaultBackendConfig",
    "SecretBackendConfigurationError",
    "SecretBackendError",
    "build_aws_secrets_manager_resolver",
    "build_hashicorp_vault_resolver",
]


class SecretBackendError(RuntimeError):
    """Raised when a backend resolver fails to load secrets."""


class SecretBackendConfigurationError(SecretBackendError):
    """Raised when backend configuration is invalid."""


def _parse_verify_setting(value: str | None) -> bool | str:
    """Normalise TLS verification values from environment settings."""

    if value is None:
        return True
    candidate = value.strip()
    if not candidate:
        return True
    lowered = candidate.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return candidate


def _read_optional_file(path: str | None) -> str | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        raise SecretBackendConfigurationError(f"Secret file {file_path} does not exist")
    return file_path.read_text(encoding="utf-8").strip()


class _VaultKeyValueClient(Protocol):
    def read_kv_secret(
        self,
        *,
        mount: str,
        path: str,
        version: int = 2,
        actor: str | None = None,
        ip_address: str | None = None,
    ) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class HashicorpVaultBackendConfig:
    """Configuration describing how to reach HashiCorp Vault."""

    address: str
    token: str
    namespace: str | None = None
    verify: bool | str = True
    timeout: float = 5.0
    default_mount: str | None = None
    kv_version: int = 2
    audit_actor: str = "live-runner"
    audit_ip: str = "127.0.0.1"

    @classmethod
    def from_environment(
        cls, prefix: str = "TRADEPULSE_VAULT_"
    ) -> "HashicorpVaultBackendConfig | None":
        """Build a configuration object from environment variables."""

        address = os.getenv(f"{prefix}ADDR") or os.getenv(f"{prefix}ADDRESS")
        token = os.getenv(f"{prefix}TOKEN")
        token_file = os.getenv(f"{prefix}TOKEN_FILE")
        namespace = os.getenv(f"{prefix}NAMESPACE")
        verify = _parse_verify_setting(os.getenv(f"{prefix}VERIFY"))
        timeout_value = os.getenv(f"{prefix}TIMEOUT") or os.getenv(
            f"{prefix}HTTP_TIMEOUT"
        )
        default_mount = os.getenv(f"{prefix}MOUNT")
        kv_version_value = os.getenv(f"{prefix}KV_VERSION")
        audit_actor = os.getenv(f"{prefix}AUDIT_ACTOR") or "live-runner"
        audit_ip = os.getenv(f"{prefix}AUDIT_IP") or "127.0.0.1"

        if not any([address, token, token_file]):
            return None
        if not address:
            raise SecretBackendConfigurationError(
                f"{prefix}ADDR must be set when enabling the Vault backend"
            )
        if not token:
            token = _read_optional_file(token_file)
        if not token:
            raise SecretBackendConfigurationError(
                f"Provide {prefix}TOKEN or {prefix}TOKEN_FILE for Vault access"
            )
        try:
            timeout = float(timeout_value) if timeout_value else 5.0
        except ValueError as exc:  # pragma: no cover - defensive
            raise SecretBackendConfigurationError(
                f"Invalid timeout configured via {prefix}TIMEOUT"
            ) from exc
        try:
            kv_version = int(kv_version_value) if kv_version_value else 2
        except ValueError as exc:  # pragma: no cover - defensive
            raise SecretBackendConfigurationError(
                f"Invalid KV engine version configured via {prefix}KV_VERSION"
            ) from exc
        return cls(
            address=address,
            token=token,
            namespace=namespace,
            verify=verify,
            timeout=timeout,
            default_mount=default_mount,
            kv_version=kv_version,
            audit_actor=audit_actor,
            audit_ip=audit_ip,
        )

    def create_client(
        self,
        *,
        session_factory: Callable[..., VaultClient] | None = None,
    ) -> VaultClient:
        """Instantiate a :class:`VaultClient` based on this configuration."""

        authenticator = StaticTokenAuthenticator(token=self.token)
        config = VaultClientConfig(
            address=self.address,
            namespace=self.namespace,
            verify=self.verify,
            timeout=self.timeout,
            audit_actor=self.audit_actor,
            audit_ip=self.audit_ip,
        )
        return VaultClient(config=config, authenticator=authenticator)


def _normalise_vault_path(path: str, default_mount: str | None) -> tuple[str, str]:
    candidate = path.strip().strip("/")
    if not candidate:
        raise SecretBackendError("Vault path must not be empty")
    segments = [segment for segment in candidate.split("/") if segment]
    if not segments:
        raise SecretBackendError("Vault path must contain a mount and key")
    if default_mount and len(segments) == 1:
        mount = default_mount.strip("/")
        key_segments = segments
    else:
        mount = segments[0]
        key_segments = segments[1:]
    if key_segments and key_segments[0] in {"data", "metadata"}:
        key_segments = key_segments[1:]
    if not key_segments:
        raise SecretBackendError(
            f"Vault secret path '{path}' does not include a key segment"
        )
    secret_path = "/".join(key_segments)
    return mount, secret_path


def build_hashicorp_vault_resolver(
    config: HashicorpVaultBackendConfig,
    *,
    client_factory: (
        Callable[[HashicorpVaultBackendConfig], _VaultKeyValueClient] | None
    ) = None,
    context_provider: Callable[[], Mapping[str, str]] | None = None,
) -> VaultResolver:
    """Return a resolver that fetches secrets from HashiCorp Vault."""

    client: _VaultKeyValueClient
    if client_factory is not None:
        client = client_factory(config)
    else:
        client = config.create_client()

    lock = threading.RLock()

    def _resolver(path: str) -> Mapping[str, str]:
        mount, secret_path = _normalise_vault_path(path, config.default_mount)
        context: Mapping[str, str] = context_provider() if context_provider else {}
        actor = context.get("actor") if isinstance(context, Mapping) else None
        ip_address = context.get("ip_address") if isinstance(context, Mapping) else None
        with lock:
            try:
                payload = client.read_kv_secret(
                    mount=mount,
                    path=secret_path,
                    version=config.kv_version,
                    actor=actor,
                    ip_address=ip_address,
                )
            except VaultRequestError as exc:
                raise SecretBackendError(
                    f"Failed to read Vault secret at '{path}': {exc}"
                ) from exc
        if not isinstance(payload, Mapping):
            raise SecretBackendError(
                f"Vault secret at '{path}' did not return a mapping"
            )
        return {str(key): str(value) for key, value in payload.items()}

    return _resolver


@dataclass(slots=True)
class AWSSecretsManagerBackendConfig:
    """Configuration describing how to access AWS Secrets Manager."""

    region_name: str | None = None
    profile_name: str | None = None
    endpoint_url: str | None = None
    verify: bool | str = True

    @classmethod
    def from_environment(
        cls, prefix: str = "TRADEPULSE_AWS_SECRETS_"
    ) -> "AWSSecretsManagerBackendConfig | None":
        """Return configuration derived from environment variables."""

        enabled = os.getenv(f"{prefix}MANAGER_ENABLED")
        if enabled is None:
            return None
        if enabled.strip().lower() not in {"1", "true", "yes", "on"}:
            return None
        region = (
            os.getenv(f"{prefix}REGION")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
        )
        profile = os.getenv(f"{prefix}PROFILE")
        endpoint = os.getenv(f"{prefix}ENDPOINT")
        verify = _parse_verify_setting(os.getenv(f"{prefix}VERIFY"))
        return cls(
            region_name=region,
            profile_name=profile,
            endpoint_url=endpoint,
            verify=verify,
        )


def _decode_secret_binary(value: Any) -> str:
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
    elif isinstance(value, str):
        raw = base64.b64decode(value.encode("utf-8"))
    else:
        raise SecretBackendError("Unsupported binary payload type from Secrets Manager")
    return raw.decode("utf-8")


def _normalise_secret_payload(payload: Mapping[str, Any]) -> Mapping[str, str]:
    normalized: MutableMapping[str, str] = {}
    for key, value in payload.items():
        normalized[str(key)] = str(value)
    return normalized


def build_aws_secrets_manager_resolver(
    config: AWSSecretsManagerBackendConfig,
    *,
    client_factory: Callable[[AWSSecretsManagerBackendConfig], Any] | None = None,
) -> VaultResolver:
    """Return a resolver backed by AWS Secrets Manager."""

    if client_factory is not None:
        client = client_factory(config)
    else:  # pragma: no cover - exercised in integration environments
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional dependency guard
            raise SecretBackendError(
                "boto3 is required to use the AWS Secrets Manager backend"
            ) from exc
        session_kwargs: MutableMapping[str, Any] = {}
        if config.profile_name:
            session_kwargs["profile_name"] = config.profile_name
        if config.region_name:
            session_kwargs["region_name"] = config.region_name
        try:
            session = boto3.session.Session(**session_kwargs)
            client_kwargs: MutableMapping[str, Any] = {"verify": config.verify}
            if config.endpoint_url:
                client_kwargs["endpoint_url"] = config.endpoint_url
            client = session.client("secretsmanager", **client_kwargs)
        except (
            BotoCoreError
        ) as exc:  # pragma: no cover - relies on boto3 runtime errors
            raise SecretBackendError(
                f"Failed to create AWS Secrets Manager client: {exc}"
            ) from exc

    lock = threading.RLock()

    def _resolver(secret_id: str) -> Mapping[str, str]:
        with lock:
            try:
                response = client.get_secret_value(SecretId=secret_id)
            except (ClientError, BotoCoreError) as exc:
                raise SecretBackendError(
                    f"Failed to fetch secret '{secret_id}' from AWS Secrets Manager: {exc}"
                ) from exc
        if "SecretString" in response and response["SecretString"] is not None:
            secret_string = response["SecretString"]
            if not isinstance(secret_string, str):
                raise SecretBackendError("SecretString payload must be a string value")
            try:
                parsed = json.loads(secret_string)
            except json.JSONDecodeError:
                return {"value": secret_string}
            if isinstance(parsed, Mapping):
                return _normalise_secret_payload(parsed)
            return {"value": secret_string}
        if "SecretBinary" in response and response["SecretBinary"] is not None:
            return {"value": _decode_secret_binary(response["SecretBinary"])}
        raise SecretBackendError(
            f"Secret '{secret_id}' did not include a SecretString or SecretBinary payload"
        )

    return _resolver
