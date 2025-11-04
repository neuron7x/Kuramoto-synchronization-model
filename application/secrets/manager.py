"""Secret management utilities with support for rotation and auditing."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, Iterator, Mapping

if TYPE_CHECKING:
    from src.security import AccessController

    from .vault import SecretVault

from src.audit.audit_logger import AuditLogger

__all__ = [
    "ManagedSecret",
    "ManagedSecretConfig",
    "SecretManager",
    "SecretManagerError",
    "secret_caller_context",
    "managed_secret_from_vault",
]


class SecretManagerError(RuntimeError):
    """Raised when managed secrets cannot be resolved."""


@dataclass(slots=True)
class ManagedSecretConfig:
    """Configuration describing how a secret should be sourced."""

    name: str
    path: Path | None = None
    resolver: Callable[[], str] | None = None
    min_length: int = 16
    required_permission: str | None = None


class ManagedSecret:
    """Represent a secret value that can refresh itself from disk."""

    def __init__(
        self,
        *,
        config: ManagedSecretConfig,
        fallback: str | None,
        refresh_interval_seconds: float,
        logger: logging.Logger | None = None,
    ) -> None:
        self._config = config
        self._refresh_interval = max(0.0, refresh_interval_seconds)
        self._logger = logger or logging.getLogger("tradepulse.secrets")
        self._lock = threading.Lock()
        self._value: str | None = None
        self._has_fallback = fallback is not None
        self._last_refresh = 0.0
        if fallback is not None:
            self._ensure_min_length(fallback)
            self._value = fallback
        if config.path is None and config.resolver is None and self._value is None:
            raise SecretManagerError(
                f"Secret '{config.name}' must provide a fallback value or managed path."
            )
        if config.path is not None or config.resolver is not None:
            # Attempt an eager refresh so missing files are detected on startup. If the refresh fails but a fallback value is
            # available we continue using the fallback and log the failure so operators can investigate.
            try:
                self._refresh(force=True)
            except SecretManagerError as exc:
                if self._value is None:
                    raise
                self._logger.warning(
                    "Falling back to static secret after refresh failure",
                    extra={"secret": config.name, "path": str(config.path)},
                    exc_info=(type(exc), exc, exc.__traceback__),
                )

    def get_secret(self) -> str:
        """Return the secret value, refreshing it when stale."""

        with self._lock:
            self._refresh()
            if self._value is None:
                raise SecretManagerError(
                    f"Secret '{self._config.name}' is unavailable after refresh."
                )
            return self._value

    def force_refresh(self) -> None:
        """Refresh the secret irrespective of the configured interval."""

        with self._lock:
            self._refresh(force=True)

    def _refresh(self, *, force: bool = False) -> None:
        if self._config.path is None and self._config.resolver is None:
            return
        now = time.monotonic()
        if (
            not force
            and self._refresh_interval
            and now - self._last_refresh < self._refresh_interval
        ):
            return
        secret: str | None = None
        if self._config.path is not None:
            try:
                secret = self._config.path.read_text(encoding="utf-8").strip()
            except FileNotFoundError as exc:
                self._logger.warning(
                    "Managed secret file missing",
                    extra={"secret": self._config.name, "path": str(self._config.path)},
                )
                if self._value is not None:
                    self._last_refresh = now
                    return
                raise SecretManagerError(
                    f"Secret '{self._config.name}' missing at {self._config.path}"
                ) from exc
            if not secret:
                self._logger.warning(
                    "Managed secret file is empty",
                    extra={"secret": self._config.name, "path": str(self._config.path)},
                )
                if self._value is not None:
                    self._last_refresh = now
                    return
                raise SecretManagerError(
                    f"Secret '{self._config.name}' read from {self._config.path} is empty."
                )
        if secret is None and self._config.resolver is not None:
            try:
                secret = self._config.resolver()
            except Exception as exc:  # pragma: no cover - defensive logging
                self._logger.error(
                    "Managed secret resolver failed",
                    extra={"secret": self._config.name},
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
                if self._value is not None:
                    self._last_refresh = now
                    return
                raise SecretManagerError(
                    f"Secret '{self._config.name}' resolver failed"
                ) from exc
            if not secret:
                self._logger.warning(
                    "Managed secret resolver returned empty value",
                    extra={"secret": self._config.name},
                )
                if self._value is not None:
                    self._last_refresh = now
                    return
                raise SecretManagerError(
                    f"Secret '{self._config.name}' resolved empty value"
                )
        try:
            assert secret is not None
            self._ensure_min_length(secret)
        except SecretManagerError:
            self._logger.warning(
                "Managed secret failed minimum length check",
                extra={"secret": self._config.name, "path": str(self._config.path)},
            )
            if self._value is not None:
                self._last_refresh = now
                return
            raise
        if secret != self._value:
            self._logger.info(
                "Managed secret rotated",
                extra={"secret": self._config.name, "path": str(self._config.path)},
            )
        self._value = secret
        self._last_refresh = now

    def _ensure_min_length(self, secret: str) -> None:
        if len(secret) < self._config.min_length:
            raise SecretManagerError(
                f"Secret '{self._config.name}' must be at least {self._config.min_length} characters."
            )

    @property
    def config(self) -> ManagedSecretConfig:
        """Return the immutable configuration associated with the secret."""

        return self._config

    @property
    def has_fallback(self) -> bool:
        """Return whether a fallback value was configured for the secret."""

        return self._has_fallback

    def describe(self) -> dict[str, Any]:
        """Return non-sensitive metadata describing the managed secret."""

        path = self._config.path
        metadata: dict[str, Any] = {
            "name": self._config.name,
            "path": str(path) if path is not None else None,
            "min_length": self._config.min_length,
            "has_fallback": self._has_fallback,
            "cached": self._value is not None,
            "refresh_interval_seconds": self._refresh_interval,
        }
        if self._config.resolver is not None:
            metadata["uses_resolver"] = True
        return metadata


class SecretManager:
    """Coordinate retrieval of managed secrets for the application."""

    def __init__(
        self,
        secrets: Mapping[str, ManagedSecret],
        *,
        audit_logger: AuditLogger | None = None,
        audit_logger_factory: Callable[["SecretManager"], AuditLogger] | None = None,
        access_controller: "AccessController" | None = None,
    ) -> None:
        if not secrets:
            raise ValueError("At least one secret must be managed")
        self._secrets: Dict[str, ManagedSecret] = dict(secrets)
        self._audit_state = threading.local()
        self._audit_logger: AuditLogger | None = None
        self._access_controller = access_controller
        if audit_logger is not None and audit_logger_factory is not None:
            raise ValueError(
                "Provide either audit_logger or audit_logger_factory, not both"
            )
        if audit_logger is not None:
            self._audit_logger = audit_logger
        elif audit_logger_factory is not None:
            self._audit_logger = audit_logger_factory(self)

    @property
    def audit_logger(self) -> AuditLogger | None:
        """Return the audit logger bound to the secret manager, if any."""

        return self._audit_logger

    def get(self, name: str) -> str:
        secret = self._secrets.get(name)
        if secret is None:
            self._audit_operation(name=name, operation="get", status="missing")
            raise SecretManagerError(f"Unknown secret '{name}'")
        self._enforce_access(secret)
        try:
            value = secret.get_secret()
        except SecretManagerError:
            self._audit_operation(name=name, operation="get", status="error")
            raise
        self._audit_operation(name=name, operation="get", status="success")
        return value

    def provider(self, name: str) -> Callable[[], str]:
        secret = self._secrets.get(name)
        if secret is None:
            self._audit_operation(name=name, operation="provider", status="missing")
            raise SecretManagerError(f"Unknown secret '{name}'")
        self._enforce_access(secret)
        self._audit_operation(name=name, operation="provider", status="issued")

        def _resolver() -> str:
            try:
                self._enforce_access(secret)
                value = secret.get_secret()
            except SecretManagerError:
                self._audit_operation(
                    name=name, operation="provider_access", status="error"
                )
                raise
            self._audit_operation(
                name=name, operation="provider_access", status="success"
            )
            return value

        return _resolver

    def force_refresh(self, name: str) -> None:
        secret = self._secrets.get(name)
        if secret is None:
            self._audit_operation(
                name=name, operation="force_refresh", status="missing"
            )
            raise SecretManagerError(f"Unknown secret '{name}'")
        try:
            secret.force_refresh()
        except SecretManagerError:
            self._audit_operation(name=name, operation="force_refresh", status="error")
            raise
        self._audit_operation(name=name, operation="force_refresh", status="success")

    def _audit_operation(
        self,
        *,
        name: str,
        operation: str,
        status: str,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        if self._audit_logger is None:
            return
        if getattr(self._audit_state, "active", False):
            return
        context = _SECRET_CALLER_CONTEXT.get()
        actor = context.get("actor") or "system"
        ip_address = context.get("ip_address") or "127.0.0.1"
        secret = self._secrets.get(name)
        details: dict[str, Any] = {
            "operation": operation,
            "status": status,
            "secret": self._describe_secret(name, secret),
        }
        if extra is not None:
            details.update(dict(extra))
        setattr(self._audit_state, "active", True)
        try:
            self._audit_logger.log_event(
                event_type=f"secret_{operation}",
                actor=actor,
                ip_address=ip_address,
                details=details,
            )
        finally:
            setattr(self._audit_state, "active", False)

    def _describe_secret(
        self, name: str, secret: ManagedSecret | None
    ) -> dict[str, Any]:
        if secret is None:
            return {"name": name, "managed": False}
        metadata = secret.describe()
        metadata.setdefault("name", name)
        managed = secret.config.path is not None or secret.config.resolver is not None
        metadata["managed"] = managed
        return metadata

    def _enforce_access(self, secret: ManagedSecret) -> None:
        controller = self._access_controller
        permission = secret.config.required_permission
        if controller is None or not permission:
            return
        context = dict(_SECRET_CALLER_CONTEXT.get())
        actor = context.get("actor")
        roles_value = context.get("roles")
        roles: Iterable[str]
        if isinstance(roles_value, str):
            roles = (roles_value,)
        elif isinstance(roles_value, Iterable):
            roles = tuple(str(role) for role in roles_value)
        else:
            roles = ()
        controller.require(
            permission,
            actor=actor,
            roles=roles,
            resource=secret.config.name,
        )


_SECRET_CALLER_CONTEXT: ContextVar[dict[str, object]] = ContextVar(
    "secret_caller_context",
    default={"actor": "system", "ip_address": "127.0.0.1", "roles": ()},
)


@contextmanager
def secret_caller_context(
    *, actor: str, ip_address: str, **extra: object
) -> Iterator[None]:
    """Temporarily override the caller context for secret access auditing."""

    current = dict(_SECRET_CALLER_CONTEXT.get())
    current.update({"actor": actor, "ip_address": ip_address, **extra})
    token = _SECRET_CALLER_CONTEXT.set(current)
    try:
        yield
    finally:
        _SECRET_CALLER_CONTEXT.reset(token)


def managed_secret_from_vault(
    *,
    vault: "SecretVault",
    vault_secret_name: str,
    managed_name: str | None = None,
    refresh_interval_seconds: float = 30.0,
    min_length: int = 32,
) -> ManagedSecret:
    """Create a :class:`ManagedSecret` backed by a :class:`SecretVault` secret."""

    from .vault import build_vault_resolver

    config = ManagedSecretConfig(
        name=managed_name or vault_secret_name,
        path=None,
        min_length=min_length,
        resolver=build_vault_resolver(
            vault=vault,
            secret_name=vault_secret_name,
            context_provider=_SECRET_CALLER_CONTEXT.get,
        ),
    )
    return ManagedSecret(
        config=config,
        fallback=None,
        refresh_interval_seconds=refresh_interval_seconds,
    )
