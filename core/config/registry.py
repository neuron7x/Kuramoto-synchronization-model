"""Centralized configuration registry with versioning and governance controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from threading import RLock
from typing import Any, Iterable, Mapping, MutableMapping, Protocol

import copy
import hashlib
import json

from packaging.version import InvalidVersion, Version

__all__ = [
    "ConfigRegistry",
    "ConfigRegistryError",
    "ConfigValidationError",
    "ConfigApprovalError",
    "ConfigCompatibilityError",
    "ConfigPublicationError",
    "ConfigVersionError",
    "Environment",
    "InMemoryConfigStorage",
]


class ConfigRegistryError(RuntimeError):
    """Base exception for registry errors."""


class ConfigValidationError(ConfigRegistryError):
    """Raised when configuration payload validation fails."""


class ConfigApprovalError(ConfigRegistryError):
    """Raised when approval related rules are violated."""


class ConfigCompatibilityError(ConfigRegistryError):
    """Raised when a profile is not compatible with the running code."""


class ConfigPublicationError(ConfigRegistryError):
    """Raised when a profile cannot be published to a target environment."""


class ConfigVersionError(ConfigRegistryError):
    """Raised when version constraints are not satisfied."""


class Environment(str, Enum):
    """Supported deployment environments for configuration publication."""

    STAGE = "stage"
    PROD = "prod"


@dataclass(frozen=True, slots=True)
class ConfigAuditRecord:
    """Audit metadata for configuration lifecycle actions."""

    timestamp: datetime
    actor: str
    action: str
    message: str | None = None


@dataclass(frozen=True, slots=True)
class ConfigApproval:
    """Represents an approval granted to a configuration version."""

    approver: str
    comment: str | None
    timestamp: datetime


@dataclass(slots=True)
class ConfigVersionRecord:
    """Immutable snapshot of a configuration profile at a specific version."""

    version: Version
    payload: Mapping[str, Any]
    checksum: str
    created_at: datetime
    created_by: str
    change_reason: str | None
    required_approvals: int
    approvals: list[ConfigApproval] = field(default_factory=list)
    audit_log: list[ConfigAuditRecord] = field(default_factory=list)

    def approval_count(self) -> int:
        return len(self.approvals)

    def has_approval_from(self, actor: str) -> bool:
        return any(approval.approver == actor for approval in self.approvals)

    def add_audit_entry(self, entry: ConfigAuditRecord) -> None:
        self.audit_log.append(entry)

    def clone(self) -> "ConfigVersionRecord":
        return ConfigVersionRecord(
            version=self.version,
            payload=copy.deepcopy(self.payload),
            checksum=self.checksum,
            created_at=self.created_at,
            created_by=self.created_by,
            change_reason=self.change_reason,
            required_approvals=self.required_approvals,
            approvals=list(self.approvals),
            audit_log=list(self.audit_log),
        )


@dataclass(slots=True)
class ProfileHistory:
    """Lifecycle history for a configuration profile."""

    name: str
    versions: MutableMapping[Version, ConfigVersionRecord] = field(default_factory=dict)
    published: MutableMapping[Environment, Version] = field(default_factory=dict)
    audit_log: list[ConfigAuditRecord] = field(default_factory=list)

    def clone(self) -> "ProfileHistory":
        return ProfileHistory(
            name=self.name,
            versions={version: record.clone() for version, record in self.versions.items()},
            published=dict(self.published),
            audit_log=list(self.audit_log),
        )


class ConfigValidator(Protocol):
    """Callable contract for configuration validators."""

    def __call__(self, profile_name: str, payload: Mapping[str, Any]) -> None:  # pragma: no cover - protocol definition
        ...


class CompatibilityPolicy(Protocol):
    """Callable contract for compatibility enforcement."""

    def ensure(self, profile_name: str, version: Version, payload: Mapping[str, Any]) -> None:  # pragma: no cover - protocol definition
        ...


class ReleaseCheck(Protocol):
    """Callable contract for automated release checks."""

    def __call__(self, profile_name: str, version: Version, payload: Mapping[str, Any]) -> None:  # pragma: no cover - protocol definition
        ...


class ConfigStorageBackend(Protocol):
    """Persistence contract for configuration histories."""

    def read(self, profile_name: str) -> ProfileHistory | None:  # pragma: no cover - protocol definition
        ...

    def write(self, profile_name: str, history: ProfileHistory) -> None:  # pragma: no cover - protocol definition
        ...

    def list_names(self) -> list[str]:  # pragma: no cover - protocol definition
        ...


class InMemoryConfigStorage:
    """Simple storage backend backed by an in-memory dictionary."""

    def __init__(self) -> None:
        self._store: dict[str, ProfileHistory] = {}
        self._lock = RLock()

    def read(self, profile_name: str) -> ProfileHistory | None:
        with self._lock:
            history = self._store.get(profile_name)
            return history.clone() if history else None

    def write(self, profile_name: str, history: ProfileHistory) -> None:
        with self._lock:
            self._store[profile_name] = history.clone()

    def list_names(self) -> list[str]:
        with self._lock:
            return sorted(self._store)


def _ensure_mapping(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        msg = "Configuration payloads must be mapping-like objects"
        raise ConfigValidationError(msg)
    return copy.deepcopy(dict(payload))


def _stable_checksum(payload: Mapping[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class ConfigRegistry:
    """Manage configuration profiles with governance controls."""

    def __init__(
        self,
        *,
        storage: ConfigStorageBackend | None = None,
        validators: Iterable[ConfigValidator] | None = None,
        compatibility_policies: Iterable[CompatibilityPolicy] | None = None,
        release_checks: Iterable[ReleaseCheck] | None = None,
    ) -> None:
        self._storage = storage or InMemoryConfigStorage()
        self._validators = list(validators or [])
        self._compatibility_policies = list(compatibility_policies or [])
        self._release_checks = list(release_checks or [])
        self._lock = RLock()

    def register_profile(
        self,
        profile_name: str,
        version: str | Version,
        payload: Mapping[str, Any],
        *,
        actor: str,
        change_reason: str | None = None,
        required_approvals: int = 1,
    ) -> Version:
        """Register a new configuration version in draft state."""

        version_obj = self._parse_version(version)
        normalized_payload = _ensure_mapping(payload)
        if required_approvals < 0:
            raise ConfigApprovalError("required_approvals must be non-negative")

        with self._lock:
            history = self._load_history(profile_name)
            if version_obj in history.versions:
                msg = (
                    f"Version {version_obj} already exists for profile '{profile_name}'"
                )
                raise ConfigVersionError(msg)

            self._ensure_version_is_newer(history, version_obj)
            self._run_validators(profile_name, normalized_payload)

            checksum = _stable_checksum(normalized_payload)
            record = ConfigVersionRecord(
                version=version_obj,
                payload=normalized_payload,
                checksum=checksum,
                created_at=_utcnow(),
                created_by=actor,
                change_reason=change_reason,
                required_approvals=required_approvals,
            )
            audit_entry = ConfigAuditRecord(
                timestamp=_utcnow(),
                actor=actor,
                action="register",
                message=change_reason,
            )
            record.add_audit_entry(audit_entry)
            history.versions[version_obj] = record
            history.audit_log.append(audit_entry)
            self._persist(profile_name, history)
            return version_obj

    def approve_profile(
        self,
        profile_name: str,
        version: str | Version,
        *,
        approver: str,
        comment: str | None = None,
    ) -> None:
        """Register an approval for a configuration version."""

        version_obj = self._parse_version(version)
        with self._lock:
            history = self._load_history(profile_name)
            record = self._get_version_record(history, version_obj)
            if record.required_approvals == 0:
                msg = (
                    f"Version {version_obj} of '{profile_name}' does not require approvals"
                )
                raise ConfigApprovalError(msg)
            if record.has_approval_from(approver):
                msg = (
                    f"Approver '{approver}' has already approved version {version_obj}"
                )
                raise ConfigApprovalError(msg)
            approval = ConfigApproval(
                approver=approver,
                comment=comment,
                timestamp=_utcnow(),
            )
            record.approvals.append(approval)
            audit_entry = ConfigAuditRecord(
                timestamp=_utcnow(),
                actor=approver,
                action="approve",
                message=comment,
            )
            record.add_audit_entry(audit_entry)
            history.audit_log.append(audit_entry)
            self._persist(profile_name, history)

    def publish_profile(
        self,
        profile_name: str,
        version: str | Version,
        *,
        actor: str,
        environments: Iterable[Environment | str] | None = None,
        comment: str | None = None,
    ) -> None:
        """Publish a configuration version to one or more environments atomically."""

        version_obj = self._parse_version(version)
        environments = tuple(
            Environment(env) if not isinstance(env, Environment) else env
            for env in (environments or (Environment.STAGE,))
        )
        if not environments:
            raise ConfigPublicationError("At least one environment must be specified")

        with self._lock:
            history = self._load_history(profile_name)
            record = self._get_version_record(history, version_obj)
            self._ensure_approvals_satisfied(profile_name, record)
            self._run_validators(profile_name, record.payload)
            self._run_compatibility(profile_name, record)

            for env in environments:
                if env == Environment.PROD:
                    self._run_release_checks(profile_name, record)

            for env in environments:
                history.published[env] = version_obj

            audit_entry = ConfigAuditRecord(
                timestamp=_utcnow(),
                actor=actor,
                action="publish",
                message=comment or ", ".join(env.value for env in environments),
            )
            record.add_audit_entry(audit_entry)
            history.audit_log.append(audit_entry)
            self._persist(profile_name, history)

    def rollback_profile(
        self,
        profile_name: str,
        *,
        environment: Environment | str,
        target_version: str | Version,
        actor: str,
        reason: str | None = None,
    ) -> None:
        """Rollback an environment to a previously registered configuration version."""

        env = environment if isinstance(environment, Environment) else Environment(environment)
        version_obj = self._parse_version(target_version)

        with self._lock:
            history = self._load_history(profile_name)
            record = self._get_version_record(history, version_obj)
            if history.published.get(env) == version_obj:
                return

            self._ensure_approvals_satisfied(profile_name, record)
            self._run_compatibility(profile_name, record)
            if env == Environment.PROD:
                self._run_release_checks(profile_name, record)

            history.published[env] = version_obj
            audit_entry = ConfigAuditRecord(
                timestamp=_utcnow(),
                actor=actor,
                action="rollback",
                message=reason,
            )
            record.add_audit_entry(audit_entry)
            history.audit_log.append(audit_entry)
            self._persist(profile_name, history)

    def get_active_version(self, profile_name: str, environment: Environment | str) -> Version | None:
        env = environment if isinstance(environment, Environment) else Environment(environment)
        history = self._storage.read(profile_name)
        if history is None:
            return None
        return history.published.get(env)

    def get_active_payload(self, profile_name: str, environment: Environment | str) -> Mapping[str, Any] | None:
        env = environment if isinstance(environment, Environment) else Environment(environment)
        history = self._storage.read(profile_name)
        if history is None:
            return None
        version = history.published.get(env)
        if version is None:
            return None
        record = history.versions.get(version)
        return copy.deepcopy(record.payload) if record else None

    def list_versions(self, profile_name: str) -> list[Version]:
        history = self._storage.read(profile_name)
        if history is None:
            return []
        return sorted(history.versions)

    def audit_trail(self, profile_name: str) -> list[ConfigAuditRecord]:
        history = self._storage.read(profile_name)
        if history is None:
            return []
        return list(history.audit_log)

    def pending_approvals(self, profile_name: str, version: str | Version) -> int:
        version_obj = self._parse_version(version)
        history = self._storage.read(profile_name)
        if history is None:
            raise ConfigVersionError(
                f"Profile '{profile_name}' has no registered versions"
            )
        record = history.versions.get(version_obj)
        if record is None:
            raise ConfigVersionError(
                f"Version {version_obj} is not registered for '{profile_name}'"
            )
        required = max(record.required_approvals - record.approval_count(), 0)
        return required

    def _load_history(self, profile_name: str) -> ProfileHistory:
        history = self._storage.read(profile_name)
        if history is None:
            history = ProfileHistory(name=profile_name)
        return history

    def _persist(self, profile_name: str, history: ProfileHistory) -> None:
        self._storage.write(profile_name, history)

    def _parse_version(self, version: str | Version) -> Version:
        if isinstance(version, Version):
            return version
        try:
            return Version(version)
        except InvalidVersion as exc:
            msg = f"Invalid version identifier '{version}'"
            raise ConfigVersionError(msg) from exc

    def _get_version_record(
        self, history: ProfileHistory, version: Version
    ) -> ConfigVersionRecord:
        record = history.versions.get(version)
        if record is None:
            msg = f"Version {version} is not registered for profile '{history.name}'"
            raise ConfigVersionError(msg)
        return record

    def _ensure_version_is_newer(self, history: ProfileHistory, version: Version) -> None:
        if not history.versions:
            return
        latest = max(history.versions)
        if version <= latest:
            msg = (
                f"Version {version} must be greater than existing latest version {latest}"
            )
            raise ConfigVersionError(msg)

    def _ensure_approvals_satisfied(
        self, profile_name: str, record: ConfigVersionRecord
    ) -> None:
        required = record.required_approvals
        if required == 0:
            return
        if record.approval_count() < required:
            pending = required - record.approval_count()
            msg = (
                f"Version {record.version} of '{profile_name}' requires {required} approvals;"
                f" {pending} still pending"
            )
            raise ConfigApprovalError(msg)

    def _run_validators(self, profile_name: str, payload: Mapping[str, Any]) -> None:
        for validator in self._validators:
            try:
                validator(profile_name, payload)
            except ConfigValidationError:
                raise
            except Exception as exc:  # noqa: BLE001 - propagate wrapped validation errors
                msg = (
                    f"Validator {validator!r} rejected payload for profile '{profile_name}'"
                )
                raise ConfigValidationError(msg) from exc

    def _run_compatibility(
        self, profile_name: str, record: ConfigVersionRecord
    ) -> None:
        for policy in self._compatibility_policies:
            try:
                policy.ensure(profile_name, record.version, record.payload)
            except ConfigCompatibilityError:
                raise
            except Exception as exc:  # noqa: BLE001
                msg = (
                    f"Compatibility policy {policy!r} rejected version {record.version}"
                )
                raise ConfigCompatibilityError(msg) from exc

    def _run_release_checks(
        self, profile_name: str, record: ConfigVersionRecord
    ) -> None:
        for check in self._release_checks:
            try:
                check(profile_name, record.version, record.payload)
            except ConfigPublicationError:
                raise
            except Exception as exc:  # noqa: BLE001
                msg = (
                    f"Release check {check!r} failed for version {record.version}"
                )
                raise ConfigPublicationError(msg) from exc

