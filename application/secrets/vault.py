"""Encrypted secret vault with fine-grained access controls and rotation support."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping

from cryptography.fernet import Fernet, InvalidToken

from src.audit.audit_logger import AuditLogger

__all__ = [
    "SecretVault",
    "SecretVaultError",
    "SecretAccessPolicy",
    "SecretMetadata",
]


class SecretVaultError(RuntimeError):
    """Raised when secret vault operations cannot be completed."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(slots=True)
class SecretMetadata:
    """Non-sensitive metadata describing a stored secret."""

    name: str
    version: int
    created_at: datetime
    updated_at: datetime
    rotation_interval: timedelta | None = None
    labels: Dict[str, str] = field(default_factory=dict)

    def model_dump(self) -> dict[str, Any]:
        """Serialize the metadata to a JSON-compatible dict."""

        return {
            "name": self.name,
            "version": self.version,
            "created_at": _ensure_utc(self.created_at).isoformat(),
            "updated_at": _ensure_utc(self.updated_at).isoformat(),
            "rotation_interval_seconds": (
                self.rotation_interval.total_seconds()
                if self.rotation_interval
                else None
            ),
            "labels": dict(self.labels),
        }


class SecretAccessPolicy:
    """Role-based access policy for actors interacting with the vault."""

    def __init__(
        self,
        permissions: Mapping[str, Mapping[str, Iterable[str]]] | None = None,
    ) -> None:
        # permissions -> actor -> action -> iterable of secret names or "*"
        self._permissions: dict[str, dict[str, set[str]]] = {}
        if permissions:
            for actor, actions in permissions.items():
                normalized_actions: dict[str, set[str]] = {}
                for action, resources in actions.items():
                    normalized_actions[action] = {
                        resource.strip().lower() for resource in resources
                    }
                self._permissions[actor.lower()] = normalized_actions

    def grant(
        self,
        actor: str,
        *,
        actions: Mapping[str, Iterable[str]],
    ) -> None:
        """Grant the provided actions to *actor* for the given resources."""

        if not actor:
            raise ValueError("actor must be provided")
        actor_key = actor.lower()
        existing = self._permissions.setdefault(actor_key, {})
        for action, resources in actions.items():
            bucket = existing.setdefault(action, set())
            bucket.update(resource.strip().lower() for resource in resources)

    def is_allowed(self, actor: str, action: str, secret: str) -> bool:
        """Return whether *actor* is permitted to perform *action* on *secret*."""

        if not actor:
            return False
        actor_key = actor.lower()
        secret_key = secret.lower()
        actions = self._permissions.get(actor_key)
        if not actions:
            return False
        allowed_secrets = actions.get(action)
        if not allowed_secrets:
            return False
        return "*" in allowed_secrets or secret_key in allowed_secrets

    def require(self, actor: str, action: str, secret: str) -> None:
        """Ensure that *actor* has access, raising :class:`SecretVaultError` otherwise."""

        if not self.is_allowed(actor, action, secret):
            raise SecretVaultError(
                f"Access denied: actor '{actor}' cannot {action} secret '{secret}'"
            )


class SecretVault:
    """Persist secrets encrypted at rest and audited on access."""

    def __init__(
        self,
        *,
        storage_path: Path,
        master_key: bytes,
        access_policy: SecretAccessPolicy | None = None,
        audit_logger: AuditLogger | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        if not storage_path:
            raise ValueError("storage_path must be provided")
        self._path = storage_path
        self._fernet = Fernet(master_key)
        self._lock = threading.RLock()
        self._clock = clock
        self._audit_logger = audit_logger
        self._policy = access_policy or SecretAccessPolicy(
            {"system": {"read": {"*"}, "write": {"*"}}}
        )
        self._records: dict[str, dict[str, Any]] = {}
        self._metadata: dict[str, SecretMetadata] = {}
        self._load()

    # ------------------------------------------------------------------
    # Secret management primitives
    # ------------------------------------------------------------------
    @staticmethod
    def generate_key() -> bytes:
        """Return a randomly generated Fernet-compatible key."""

        return Fernet.generate_key()

    @property
    def storage_path(self) -> Path:
        return self._path

    def register_policy(self, policy: SecretAccessPolicy) -> None:
        """Replace the access policy used by the vault."""

        if policy is None:
            raise ValueError("policy must not be None")
        self._policy = policy

    def set_policy_rules(
        self, permissions: Mapping[str, Mapping[str, Iterable[str]]]
    ) -> None:
        """Convenience helper to replace the current access rules."""

        self._policy = SecretAccessPolicy(permissions)

    def put_secret(
        self,
        name: str,
        value: str,
        *,
        actor: str,
        ip_address: str,
        labels: Mapping[str, str] | None = None,
        rotation_interval: timedelta | None = None,
    ) -> SecretMetadata:
        """Create or update a secret value in the vault."""

        if not name:
            raise ValueError("name must be provided")
        if not value:
            raise ValueError("value must be provided")
        if not actor:
            raise ValueError("actor must be provided")
        name_key = name.lower()
        with self._lock:
            existing_metadata = self._metadata.get(name_key)
            action = "write"
            self._policy.require(actor, action, name_key)
            now = self._clock()
            now = _ensure_utc(now)
            version = 1
            if existing_metadata is not None:
                version = existing_metadata.version + 1
            label_data: dict[str, str] = (
                dict(existing_metadata.labels) if existing_metadata is not None else {}
            )
            if labels is not None:
                label_data.update(labels)
            metadata = SecretMetadata(
                name=name,
                version=version,
                created_at=existing_metadata.created_at if existing_metadata else now,
                updated_at=now,
                rotation_interval=(
                    rotation_interval
                    if rotation_interval is not None
                    else (
                        existing_metadata.rotation_interval
                        if existing_metadata
                        else None
                    )
                ),
                labels=label_data,
            )
            ciphertext = self._fernet.encrypt(value.encode("utf-8")).decode("utf-8")
            self._records[name_key] = {
                "ciphertext": ciphertext,
            }
            self._metadata[name_key] = metadata
            self._persist_locked()
            self._audit(
                event_type="secret_write",
                actor=actor,
                ip_address=ip_address,
                details={
                    "secret": metadata.model_dump(),
                    "labels": dict(metadata.labels),
                    "rotation_interval_seconds": (
                        metadata.rotation_interval.total_seconds()
                        if metadata.rotation_interval
                        else None
                    ),
                },
            )
            return metadata

    def access_secret(
        self,
        name: str,
        *,
        actor: str,
        ip_address: str,
        include_metadata: bool = False,
    ) -> str | tuple[str, SecretMetadata]:
        """Return the plaintext secret, auditing the access."""

        if not name:
            raise ValueError("name must be provided")
        if not actor:
            raise ValueError("actor must be provided")
        name_key = name.lower()
        with self._lock:
            self._policy.require(actor, "read", name_key)
            try:
                record = self._records[name_key]
                metadata = self._metadata[name_key]
            except KeyError as exc:
                raise SecretVaultError(f"Unknown secret '{name}'") from exc
            try:
                value = self._fernet.decrypt(
                    record["ciphertext"].encode("utf-8")
                ).decode("utf-8")
            except InvalidToken as exc:
                raise SecretVaultError(f"Failed to decrypt secret '{name}'") from exc
            self._audit(
                event_type="secret_read",
                actor=actor,
                ip_address=ip_address,
                details={"secret": metadata.model_dump()},
            )
            if include_metadata:
                return value, metadata
            return value

    def rotate_secret(
        self,
        name: str,
        *,
        generator: Callable[[], str],
        actor: str,
        ip_address: str,
        reason: str | None = None,
    ) -> SecretMetadata:
        """Rotate the secret using *generator*, auditing the change."""

        if generator is None:
            raise ValueError("generator must be provided")
        value = generator()
        if not value:
            raise SecretVaultError("Generated secret must not be empty")
        metadata = self.put_secret(
            name,
            value,
            actor=actor,
            ip_address=ip_address,
        )
        self._audit(
            event_type="secret_rotated",
            actor=actor,
            ip_address=ip_address,
            details={
                "secret": metadata.model_dump(),
                "reason": reason or "scheduled_rotation",
            },
        )
        return metadata

    def list_metadata(self) -> list[SecretMetadata]:
        """Return metadata for all stored secrets."""

        with self._lock:
            return [replace(metadata) for metadata in self._metadata.values()]

    def get_metadata(self, name: str) -> SecretMetadata:
        """Return a copy of the metadata for *name*."""

        if not name:
            raise ValueError("name must be provided")
        with self._lock:
            metadata = self._metadata.get(name.lower())
            if metadata is None:
                raise SecretVaultError(f"Unknown secret '{name}'")
            return replace(metadata)

    def set_rotation_interval(
        self, name: str, interval: timedelta | None, *, actor: str, ip_address: str
    ) -> SecretMetadata:
        """Update the rotation interval for the specified secret."""

        if not name:
            raise ValueError("name must be provided")
        name_key = name.lower()
        with self._lock:
            self._policy.require(actor, "write", name_key)
            metadata = self._metadata.get(name_key)
            if metadata is None:
                raise SecretVaultError(f"Unknown secret '{name}'")
            metadata.rotation_interval = interval
            metadata.updated_at = _ensure_utc(self._clock())
            self._persist_locked()
            self._audit(
                event_type="secret_rotation_interval_updated",
                actor=actor,
                ip_address=ip_address,
                details={
                    "secret": metadata.model_dump(),
                    "rotation_interval_seconds": (
                        interval.total_seconds() if interval else None
                    ),
                },
            )
            return metadata

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._persist_locked()
            return
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._persist_locked()
            return
        if not raw.strip():
            self._persist_locked()
            return
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SecretVaultError("Corrupted secret vault storage") from exc
        secrets = payload.get("secrets", {})
        for name, record in secrets.items():
            ciphertext = record.get("ciphertext")
            if not ciphertext:
                continue
            created_at = record.get("created_at")
            updated_at = record.get("updated_at")
            rotation_seconds = record.get("rotation_interval_seconds")
            metadata = SecretMetadata(
                name=name,
                version=int(record.get("version", 1)),
                created_at=(
                    datetime.fromisoformat(created_at) if created_at else _utc_now()
                ),
                updated_at=(
                    datetime.fromisoformat(updated_at) if updated_at else _utc_now()
                ),
                rotation_interval=(
                    timedelta(seconds=rotation_seconds) if rotation_seconds else None
                ),
                labels=dict(record.get("labels") or {}),
            )
            self._metadata[name.lower()] = metadata
            self._records[name.lower()] = {"ciphertext": ciphertext}

    def _persist_locked(self) -> None:
        secrets: dict[str, MutableMapping[str, Any]] = {}
        for name_key, metadata in self._metadata.items():
            record = self._records.get(name_key)
            if not record:
                continue
            secrets[metadata.name] = {
                "ciphertext": record["ciphertext"],
                "version": metadata.version,
                "created_at": _ensure_utc(metadata.created_at).isoformat(),
                "updated_at": _ensure_utc(metadata.updated_at).isoformat(),
                "rotation_interval_seconds": (
                    metadata.rotation_interval.total_seconds()
                    if metadata.rotation_interval
                    else None
                ),
                "labels": dict(metadata.labels),
            }
        payload = {"secrets": secrets}
        tmp_path = self._path.with_suffix(".tmp")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(tmp_path, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            # Best effort on non-POSIX systems.
            pass

    def _audit(
        self,
        *,
        event_type: str,
        actor: str,
        ip_address: str,
        details: Mapping[str, Any],
    ) -> None:
        if self._audit_logger is None:
            return
        try:
            self._audit_logger.log_event(
                event_type=event_type,
                actor=actor,
                ip_address=ip_address,
                details=details,
            )
        except Exception:
            # Never allow audit failures to break primary flows. The audit logger
            # already records failures internally for SRE follow-up.
            pass


def build_vault_resolver(
    *,
    vault: SecretVault,
    secret_name: str,
    context_provider: Callable[[], Mapping[str, str]],
) -> Callable[[], str]:
    """Return a resolver suitable for :class:`ManagedSecretConfig` resolvers."""

    def _resolver() -> str:
        context = context_provider()
        actor = context.get("actor", "system")
        ip_address = context.get("ip_address", "127.0.0.1")
        return vault.access_secret(
            secret_name,
            actor=actor,
            ip_address=ip_address,
        )

    return _resolver
