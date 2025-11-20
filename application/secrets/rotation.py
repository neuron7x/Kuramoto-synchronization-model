"""Utilities for managing automatic secret rotation policies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Sequence

from .vault import SecretMetadata, SecretVault, SecretVaultError

__all__ = [
    "SecretRotationPolicy",
    "SecretRotator",
    "SecretRotationError",
]


class SecretRotationError(RuntimeError):
    """Raised when secret rotation fails."""


@dataclass(slots=True)
class SecretRotationPolicy:
    """Describe how and when a secret should be rotated."""

    secret_name: str
    interval: timedelta
    generator: Callable[[], str]
    actor: str = "system"
    ip_address: str = "127.0.0.1"
    reason: str = "scheduled_rotation"

    def is_due(self, metadata: SecretMetadata, *, now: datetime) -> bool:
        last_rotation = metadata.updated_at
        interval = metadata.rotation_interval or self.interval
        return now - last_rotation >= interval


class SecretRotator:
    """Evaluate rotation policies and rotate secrets when due."""

    def __init__(
        self,
        vault: SecretVault,
        policies: Sequence[SecretRotationPolicy] | None = None,
        *,
        clock: Callable[[], datetime],
        logger: logging.Logger | None = None,
    ) -> None:
        self._vault = vault
        self._clock = clock
        self._logger = logger or logging.getLogger("tradepulse.secrets.rotation")
        self._policies: list[SecretRotationPolicy] = list(policies or [])

    def register_policy(self, policy: SecretRotationPolicy) -> None:
        if not policy.secret_name:
            raise ValueError("policy.secret_name must be provided")
        if policy.interval <= timedelta(0):
            raise ValueError("policy.interval must be positive")
        self._policies.append(policy)

    def evaluate(self) -> list[SecretMetadata]:
        """Evaluate all policies and rotate secrets that are due."""

        rotated: list[SecretMetadata] = []
        now = self._clock()
        for policy in list(self._policies):
            try:
                metadata = self._vault.get_metadata(policy.secret_name)
            except SecretVaultError:
                self._logger.warning(
                    "Skipping rotation for unknown secret",
                    extra={"secret": policy.secret_name},
                )
                continue
            if not policy.is_due(metadata, now=now):
                continue
            try:
                rotated_metadata = self._vault.rotate_secret(
                    policy.secret_name,
                    generator=policy.generator,
                    actor=policy.actor,
                    ip_address=policy.ip_address,
                    reason=policy.reason,
                )
            except Exception as exc:  # pragma: no cover - logged for SRE follow-up
                self._logger.error(
                    "Secret rotation failed",
                    extra={"secret": policy.secret_name},
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
                raise SecretRotationError(
                    f"Failed to rotate secret '{policy.secret_name}'"
                ) from exc
            rotated.append(rotated_metadata)
        return rotated

    def list_policies(self) -> List[SecretRotationPolicy]:
        """Return registered policies."""

        return list(self._policies)
