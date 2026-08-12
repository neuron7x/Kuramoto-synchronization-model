# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import logging

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

    def log_event(self, *, event_type: str, actor: str, ip_address: str, details: dict) -> None:
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
    assert rotated_metadata and rotated_metadata[0].version == metadata_before.version + 1


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


def test_rotator_preserves_constructor_policies() -> None:
    """`list(policies or [])` must KEEP the policies passed at construction.

    Under `Or -> And` it becomes `list(policies and [])` -> `[]` whenever a non-empty policy
    list is supplied, silently discarding every rotation policy the caller registered. A
    rotator that forgets its policies rotates nothing and reports success.
    """
    from unittest.mock import MagicMock

    policy = SecretRotationPolicy(
        secret_name="svc/token",
        interval=timedelta(minutes=30),
        generator=lambda: "value",
    )
    rotator = SecretRotator(MagicMock(), [policy], clock=lambda: datetime.now(timezone.utc))
    assert list(rotator._policies) == [policy]  # noqa: SLF001 -- pinning constructor state


def test_rotator_falls_back_to_a_real_logger_when_none_supplied() -> None:
    """`logger or logging.getLogger(...)` must yield a usable logger, not None.

    Under `Or -> And` the default (logger=None) collapses to `None and getLogger(...)` -> None,
    so the first `self._logger.warning(...)` on the unknown-secret path raises AttributeError
    instead of recording the skip. A custom logger, conversely, must be the one used.
    """
    from unittest.mock import MagicMock

    default_rotator = SecretRotator(MagicMock(), clock=lambda: datetime.now(timezone.utc))
    assert default_rotator._logger is not None  # noqa: SLF001 -- fallback must be a real logger

    custom = logging.getLogger("test.rotation.custom")
    injected = SecretRotator(MagicMock(), clock=lambda: datetime.now(timezone.utc), logger=custom)
    assert injected._logger is custom  # noqa: SLF001 -- an injected logger must be used verbatim


def test_register_policy_rejects_nonpositive_interval_only() -> None:
    """`if policy.interval <= timedelta(0): raise` — a rotation interval must be positive.

    Under `LtE -> Gt` the check inverts: a POSITIVE interval is rejected and a zero/negative
    one is accepted, so every valid policy fails to register and an invalid never-rotates
    policy sails through. Both directions are pinned.
    """
    from unittest.mock import MagicMock

    rotator = SecretRotator(MagicMock(), clock=lambda: datetime.now(timezone.utc))

    def _policy(interval: timedelta) -> SecretRotationPolicy:
        return SecretRotationPolicy(secret_name="svc/token", interval=interval, generator=lambda: "v")

    with pytest.raises(ValueError, match="interval must be positive"):
        rotator.register_policy(_policy(timedelta(0)))
    with pytest.raises(ValueError, match="interval must be positive"):
        rotator.register_policy(_policy(timedelta(seconds=-1)))

    # A positive interval must be accepted, not rejected.
    rotator.register_policy(_policy(timedelta(minutes=30)))
    assert len(rotator._policies) == 1  # noqa: SLF001 -- exactly the accepted policy
