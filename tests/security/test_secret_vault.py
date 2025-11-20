from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from application.secrets.manager import (
    SecretManager,
    managed_secret_from_vault,
    secret_caller_context,
)
from application.secrets.rotation import SecretRotationPolicy, SecretRotator
from application.secrets.secure_channel import SecureChannel
from application.secrets.vault import SecretAccessPolicy, SecretVault, SecretVaultError


@dataclass(slots=True)
class _RecordedEvent:
    event_type: str
    actor: str
    details: dict


class _InMemoryAuditLogger:
    def __init__(self) -> None:
        self.events: list[_RecordedEvent] = []

    def log_event(
        self, *, event_type: str, actor: str, ip_address: str, details: dict
    ) -> None:
        self.events.append(_RecordedEvent(event_type, actor, dict(details)))


class _MutableClock:
    def __init__(self, start: datetime) -> None:
        self._current = start

    def advance(self, delta: timedelta) -> None:
        self._current += delta

    def __call__(self) -> datetime:
        return self._current


def _build_policy(secret_name: str) -> SecretAccessPolicy:
    return SecretAccessPolicy(
        {
            "alice": {"read": {secret_name}, "write": {secret_name}},
            "auditor": {"read": {secret_name}},
            "system": {"read": {secret_name}, "write": {secret_name}},
        }
    )


def test_secret_vault_enforces_access_policy(tmp_path: Path) -> None:
    key = SecretVault.generate_key()
    audit_logger = _InMemoryAuditLogger()
    secret_name = "db/password"
    vault = SecretVault(
        storage_path=tmp_path / "vault.json",
        master_key=key,
        access_policy=_build_policy(secret_name),
        audit_logger=audit_logger,
    )
    vault.put_secret(
        secret_name,
        "super-secret-password-1234567890",
        actor="alice",
        ip_address="10.0.0.1",
    )
    retrieved = vault.access_secret(secret_name, actor="auditor", ip_address="10.0.0.2")
    assert retrieved == "super-secret-password-1234567890"
    assert any(event.event_type == "secret_read" for event in audit_logger.events)
    with pytest.raises(SecretVaultError):
        vault.access_secret(secret_name, actor="intruder", ip_address="10.0.0.3")


def test_secret_rotator_performs_rotation(tmp_path: Path) -> None:
    key = SecretVault.generate_key()
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    clock = _MutableClock(start)
    secret_name = "jwt/issuer"
    vault = SecretVault(
        storage_path=tmp_path / "vault.json",
        master_key=key,
        access_policy=_build_policy(secret_name),
        audit_logger=_InMemoryAuditLogger(),
        clock=clock,
    )
    vault.put_secret(
        secret_name,
        "initial-secret-value-1234567890123456",
        actor="alice",
        ip_address="10.0.0.1",
    )
    metadata_before = vault.get_metadata(secret_name)
    clock.advance(timedelta(hours=1))
    rotator = SecretRotator(
        vault,
        [
            SecretRotationPolicy(
                secret_name=secret_name,
                interval=timedelta(minutes=30),
                generator=lambda: "rotated-secret-value-abcdefghijklmnop",
                actor="alice",
                ip_address="10.0.0.1",
                reason="unit_test",
            )
        ],
        clock=clock,
    )
    clock.advance(timedelta(hours=1))
    rotated_metadata = rotator.evaluate()
    assert (
        rotated_metadata and rotated_metadata[0].version == metadata_before.version + 1
    )


def test_secret_manager_resolves_vault_secret(tmp_path: Path) -> None:
    key = SecretVault.generate_key()
    secret_name = "services/api-token"
    vault = SecretVault(
        storage_path=tmp_path / "vault.json",
        master_key=key,
        access_policy=_build_policy(secret_name),
    )
    vault.put_secret(
        secret_name,
        "token-abcdefghijklmnopqrstuvwxyz123456",
        actor="alice",
        ip_address="10.0.0.1",
    )
    manager = SecretManager(
        {
            "api_token": managed_secret_from_vault(
                vault=vault,
                vault_secret_name=secret_name,
                managed_name="api_token",
                refresh_interval_seconds=0.0,
            )
        }
    )
    with secret_caller_context(actor="auditor", ip_address="10.0.0.5"):
        assert manager.get("api_token") == "token-abcdefghijklmnopqrstuvwxyz123456"


def test_secure_channel_round_trip() -> None:
    channel = SecureChannel(secret_provider=lambda: "x" * 64)
    payload = {"order_id": "abc123", "amount": 42}
    associated = {"component": "order_router"}
    encrypted = channel.wrap_json(payload, associated_data=associated)
    decrypted = channel.unwrap_json(encrypted, associated_data=associated)
    assert decrypted == payload
    with pytest.raises(ValueError):
        channel.unwrap_json(encrypted, associated_data={"component": "different"})
