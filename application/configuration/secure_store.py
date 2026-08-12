# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Centralised configuration and secret management primitives.

This module orchestrates secure access to configuration secrets, templates, and
rotation policies used across GeoSync deployments. It wraps
:class:`~application.secrets.vault.SecretVault` with higher-level concepts such
as isolated namespaces, CI-friendly injection helpers, and repository leak
scanners to provide a cohesive security baseline.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, MutableMapping

from application.secrets.rotation import SecretRotationPolicy, SecretRotator
from application.secrets.vault import (
    SecretAccessPolicy,
    SecretMetadata,
    SecretVault,
    SecretVaultError,
)
from core.config.template_manager import ConfigTemplateManager
from core.utils.security import SecretDetector
from src.audit.audit_logger import AuditLogger

__all__ = [
    "CentralConfigurationStore",
    "ConfigurationStoreError",
    "NamespaceDefinition",
]


class ConfigurationStoreError(RuntimeError):
    """Raised when secure configuration operations cannot be completed."""


@dataclass(slots=True, frozen=True)
class NamespaceDefinition:
    """Describe an isolated namespace for configuration and secrets."""

    name: str
    readers: frozenset[str] = field(default_factory=lambda: frozenset({"system"}))
    writers: frozenset[str] = field(default_factory=lambda: frozenset({"system"}))
    allow_ci: bool = False
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("namespace name must be provided")
        if not self.readers and not self.writers:
            raise ValueError("namespace must define at least one reader or writer")
        for bucket_name, bucket in ("readers", self.readers), ("writers", self.writers):
            if any(not actor or not actor.strip() for actor in bucket):
                raise ValueError(f"{bucket_name} cannot contain empty actors")


class CentralConfigurationStore:
    """Coordinate secure configuration across namespaces and runtimes."""

    def __init__(
        self,
        *,
        vault: SecretVault,
        template_manager: ConfigTemplateManager,
        audit_logger: AuditLogger | None = None,
        secret_detector: SecretDetector | None = None,
        rotator: SecretRotator | None = None,
        clock: Callable[[], datetime] | None = None,
        access_policy: SecretAccessPolicy | None = None,
    ) -> None:
        self._vault = vault
        self._template_manager = template_manager
        self._audit_logger = audit_logger
        self._detector = secret_detector or SecretDetector()
        clock_fn = clock or (lambda: datetime.now(timezone.utc))
        self._rotator = rotator or SecretRotator(vault=vault, clock=clock_fn)
        self._namespaces: dict[str, NamespaceDefinition] = {}
        self._namespace_secrets: dict[str, set[str]] = {}
        self._policy = access_policy or SecretAccessPolicy(
            {"system": {"read": {"*"}, "write": {"*"}}}
        )
        self._vault.register_policy(self._policy)

    # ------------------------------------------------------------------
    # Namespace management
    # ------------------------------------------------------------------
    def register_namespace(self, definition: NamespaceDefinition) -> None:
        """Register a namespace and synchronise access policies."""

        key = definition.name.strip().lower()
        existing = self._namespaces.get(key)
        if existing is not None and existing != definition:
            raise ConfigurationStoreError(
                f"Conflicting namespace definition for '{definition.name}'"
            )
        self._namespaces[key] = definition
        hydrated_secrets = self._hydrate_namespace_secrets(definition)
        for secret in hydrated_secrets:
            self._grant_access(definition, secret)
        self._audit(
            event_type="config_namespace_registered",
            actor="system",
            ip_address="127.0.0.1",
            details={
                "namespace": definition.name,
                "readers": sorted(definition.readers),
                "writers": sorted(definition.writers),
                "allow_ci": definition.allow_ci,
            },
        )

    def list_namespaces(self) -> list[NamespaceDefinition]:
        """Return the known namespace definitions."""

        return list(self._namespaces.values())

    # ------------------------------------------------------------------
    # Secret primitives
    # ------------------------------------------------------------------
    def write_secret(
        self,
        namespace: str,
        name: str,
        value: str,
        *,
        actor: str,
        ip_address: str,
        labels: Mapping[str, str] | None = None,
        rotation_interval: timedelta | None = None,
    ) -> SecretMetadata:
        """Persist an encrypted secret inside *namespace*."""

        if not value:
            raise ConfigurationStoreError("secret value must not be empty")
        definition = self._get_namespace(namespace)
        self._enforce_actor(definition, actor, for_write=True)
        qualified_name = self._qualified_secret_name(definition.name, name)
        self._namespace_secrets.setdefault(definition.name.lower(), set()).add(name)
        self._grant_access(definition, name)
        try:
            metadata = self._vault.put_secret(
                qualified_name,
                value,
                actor=actor,
                ip_address=ip_address,
                labels=self._merge_labels(namespace, name, labels),
                rotation_interval=rotation_interval,
            )
        except SecretVaultError as exc:
            raise ConfigurationStoreError(str(exc)) from exc
        self._audit_secret_event(
            event_type="config_secret_written",
            namespace=definition.name,
            name=name,
            actor=actor,
            ip_address=ip_address,
            metadata=metadata,
        )
        return metadata

    def read_secret(
        self,
        namespace: str,
        name: str,
        *,
        actor: str,
        ip_address: str,
        include_metadata: bool = False,
    ) -> str | tuple[str, SecretMetadata]:
        """Return the decrypted secret, optionally with metadata."""

        definition = self._get_namespace(namespace)
        self._enforce_actor(definition, actor, for_write=False)
        qualified_name = self._qualified_secret_name(definition.name, name)
        try:
            value, metadata = self._vault.access_secret(
                qualified_name,
                actor=actor,
                ip_address=ip_address,
                include_metadata=True,
            )
        except SecretVaultError as exc:
            raise ConfigurationStoreError(str(exc)) from exc
        self._audit_secret_event(
            event_type="config_secret_read",
            namespace=definition.name,
            name=name,
            actor=actor,
            ip_address=ip_address,
            metadata=metadata,
        )
        if include_metadata:
            return value, metadata
        return value

    def write_configuration(
        self,
        namespace: str,
        name: str,
        payload: Mapping[str, Any],
        *,
        actor: str,
        ip_address: str,
        labels: Mapping[str, str] | None = None,
        rotation_interval: timedelta | None = None,
    ) -> SecretMetadata:
        """Persist structured configuration as encrypted JSON."""

        serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        combined_labels = {"type": "configuration"}
        if labels:
            combined_labels.update(labels)
        return self.write_secret(
            namespace,
            name,
            serialized,
            actor=actor,
            ip_address=ip_address,
            labels=combined_labels,
            rotation_interval=rotation_interval,
        )

    def read_configuration(
        self,
        namespace: str,
        name: str,
        *,
        actor: str,
        ip_address: str,
        include_metadata: bool = False,
    ) -> dict[str, Any] | tuple[dict[str, Any], SecretMetadata]:
        """Return structured configuration payloads."""

        raw = self.read_secret(
            namespace,
            name,
            actor=actor,
            ip_address=ip_address,
            include_metadata=include_metadata,
        )
        if include_metadata:
            raw_value, metadata = raw
            return json.loads(raw_value), metadata
        return json.loads(raw)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Rotation orchestration
    # ------------------------------------------------------------------
    def register_rotation_policy(
        self,
        namespace: str,
        name: str,
        *,
        interval: timedelta,
        generator: Callable[[], str],
        actor: str = "system",
        ip_address: str = "127.0.0.1",
        reason: str = "scheduled_rotation",
    ) -> SecretRotationPolicy:
        """Register a rotation policy for a managed secret."""

        definition = self._get_namespace(namespace)
        qualified_name = self._qualified_secret_name(definition.name, name)
        policy = SecretRotationPolicy(
            secret_name=qualified_name,
            interval=interval,
            generator=generator,
            actor=actor,
            ip_address=ip_address,
            reason=reason,
        )
        self._rotator.register_policy(policy)
        self._audit(
            event_type="config_secret_rotation_policy_registered",
            actor=actor,
            ip_address=ip_address,
            details={
                "namespace": definition.name,
                "name": name,
                "interval_seconds": interval.total_seconds(),
                "reason": reason,
            },
        )
        return policy

    def evaluate_rotations(self) -> list[SecretMetadata]:
        """Evaluate registered rotation policies and return updated metadata."""

        rotated = self._rotator.evaluate()
        if not rotated:
            return rotated
        self._audit(
            event_type="config_secret_rotation_evaluated",
            actor="system",
            ip_address="127.0.0.1",
            details={"rotated": [metadata.model_dump() for metadata in rotated]},
        )
        return rotated

    # ------------------------------------------------------------------
    # Template rendering and CI helpers
    # ------------------------------------------------------------------
    def render_environment_template(
        self,
        template_name: str,
        destination: Path,
        *,
        context: Mapping[str, Any] | None = None,
        actor: str,
        ip_address: str,
    ) -> Path:
        """Render a configuration template for the requested environment."""

        rendered = self._template_manager.render(
            template_name,
            destination,
            context or {},
        )
        self._audit(
            event_type="config_template_rendered",
            actor=actor,
            ip_address=ip_address,
            details={
                "template": template_name,
                "destination": str(destination),
                "context_keys": sorted((context or {}).keys()),
            },
        )
        return rendered

    def inject_into_ci(
        self,
        namespace: str,
        assignments: Mapping[str, str],
        *,
        actor: str,
        ip_address: str,
        environment: MutableMapping[str, str],
    ) -> dict[str, Any]:
        """Inject secrets into a CI environment with audit metadata."""

        definition = self._get_namespace(namespace)
        if not definition.allow_ci:
            raise ConfigurationStoreError(
                f"Namespace '{definition.name}' does not permit CI injection"
            )
        metadata_summary: dict[str, Any] = {}
        for env_var, secret_name in assignments.items():
            value, metadata = self.read_secret(
                definition.name,
                secret_name,
                actor=actor,
                ip_address=ip_address,
                include_metadata=True,
            )
            environment[env_var] = value
            metadata_summary[env_var] = {
                "namespace": definition.name,
                "secret": secret_name,
                "version": metadata.version,
            }
        self._audit(
            event_type="config_ci_injection",
            actor=actor,
            ip_address=ip_address,
            details={
                "namespace": definition.name,
                "variables": sorted(assignments.keys()),
            },
        )
        return metadata_summary

    # ------------------------------------------------------------------
    # Leak detection
    # ------------------------------------------------------------------
    def scan_repository_for_leaks(
        self,
        root: Path,
        *,
        actor: str = "system",
        ip_address: str = "127.0.0.1",
    ) -> dict[str, list[tuple[str, int, str]]]:
        """Execute an in-repo secret detection scan and audit results."""

        findings = self._detector.scan_directory(str(root))
        self._audit(
            event_type="config_repository_scan",
            actor=actor,
            ip_address=ip_address,
            details={
                "root": str(root),
                "findings": len(findings),
            },
        )
        return findings

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _qualified_secret_name(self, namespace: str, name: str) -> str:
        if not name or not name.strip():
            raise ConfigurationStoreError("secret name must be provided")
        return f"{namespace.strip()}/{name.strip()}"

    def _get_namespace(self, namespace: str) -> NamespaceDefinition:
        key = namespace.strip().lower()
        definition = self._namespaces.get(key)
        if definition is None:
            raise ConfigurationStoreError(f"Unknown namespace '{namespace}'")
        return definition

    def _enforce_actor(
        self,
        definition: NamespaceDefinition,
        actor: str,
        *,
        for_write: bool,
    ) -> None:
        normalized = actor.strip().lower()
        if not normalized:
            raise ConfigurationStoreError("actor must be provided")
        allowed_readers = {reader.lower() for reader in definition.readers}
        allowed_writers = {writer.lower() for writer in definition.writers}
        if for_write and normalized not in allowed_writers:
            raise ConfigurationStoreError(
                f"Actor '{actor}' is not permitted to write namespace '{definition.name}'"
            )
        if (
            not for_write
            and normalized not in allowed_readers
            and normalized not in allowed_writers
        ):
            raise ConfigurationStoreError(
                f"Actor '{actor}' is not permitted to read namespace '{definition.name}'"
            )

    def _hydrate_namespace_secrets(self, definition: NamespaceDefinition) -> set[str]:
        """Load persisted secrets for *definition* and cache their names."""

        key = definition.name.strip().lower()
        secrets = self._namespace_secrets.setdefault(key, set())
        namespace_key = definition.name.strip().lower()
        try:
            metadata_records = self._vault.list_metadata()
        except SecretVaultError as exc:  # pragma: no cover - defensive, list_metadata doesn't raise
            raise ConfigurationStoreError(str(exc)) from exc
        for metadata in metadata_records:
            namespace_part, separator, secret_part = metadata.name.partition("/")
            if not separator:
                continue
            if namespace_part.strip().lower() != namespace_key:
                continue
            secret_name = secret_part.strip()
            if not secret_name:
                continue
            secrets.add(secret_name)
        return set(secrets)

    def _grant_access(self, definition: NamespaceDefinition, secret: str) -> None:
        qualified = self._qualified_secret_name(definition.name, secret)
        for reader in definition.readers:
            self._policy.grant(reader, actions={"read": [qualified]})
        for writer in definition.writers:
            self._policy.grant(writer, actions={"write": [qualified], "read": [qualified]})

    def _merge_labels(
        self,
        namespace: str,
        name: str,
        labels: Mapping[str, str] | None,
    ) -> dict[str, str]:
        merged = {"namespace": namespace, "name": name}
        if labels:
            merged.update(labels)
        return merged

    def _audit_secret_event(
        self,
        *,
        event_type: str,
        namespace: str,
        name: str,
        actor: str,
        ip_address: str,
        metadata: SecretMetadata,
    ) -> None:
        details = metadata.model_dump()
        details.update({"namespace": namespace, "name": name})
        self._audit(event_type=event_type, actor=actor, ip_address=ip_address, details=details)

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
            # Never allow auxiliary audit failures to break primary flows.
            pass
