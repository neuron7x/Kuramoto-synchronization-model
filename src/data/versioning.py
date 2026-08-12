# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for governing model and dataset versions across their lifecycle.

This module provides a single in-memory implementation that can be leveraged by
tests, prototype services or command line tooling that need deterministic
behaviour without persisting state.  The focus is on correctness and
expressiveness: semantic versions, compatibility contracts, format migrations,
access gates, operational tags, cataloguing helpers, provenance tracking,
rollback control and lifecycle enforcement are all supported out of the box.

The design deliberately keeps the policy surface small.  It is easy to swap the
registry implementation for a persistent backend because all domain concepts are
plain dataclasses with rich validation.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping

__all__ = [
    "AccessDeniedError",
    "AccessGate",
    "CompatibilityContract",
    "FormatMigration",
    "LifecycleState",
    "LineageRecord",
    "OperationalTag",
    "RollbackRecord",
    "SemanticVersion",
    "VersionCatalog",
    "VersionEntry",
    "VersionRegistry",
    "VersioningError",
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VersioningError(RuntimeError):
    """Base exception for all version registry errors."""


class AccessDeniedError(VersioningError):
    """Raised when an access gate rejects a request."""


class LifecycleState(Enum):
    """Recognised lifecycle states for a versioned artefact."""

    DRAFT = "draft"
    STAGING = "staging"
    PRODUCTION = "production"
    DEPRECATED = "deprecated"
    RETIRED = "retired"

    @property
    def terminal(self) -> bool:
        """Return whether the state is terminal (no further transitions allowed)."""

        return self is LifecycleState.RETIRED


_ALLOWED_TRANSITIONS: Mapping[LifecycleState, set[LifecycleState]] = {
    LifecycleState.DRAFT: {LifecycleState.STAGING, LifecycleState.RETIRED},
    LifecycleState.STAGING: {LifecycleState.PRODUCTION, LifecycleState.DEPRECATED},
    LifecycleState.PRODUCTION: {LifecycleState.DEPRECATED},
    LifecycleState.DEPRECATED: {LifecycleState.PRODUCTION, LifecycleState.RETIRED},
    LifecycleState.RETIRED: set(),
}


@dataclass(frozen=True, order=True)
class SemanticVersion:
    """Semantic version following the MAJOR.MINOR.PATCH specification."""

    major: int
    minor: int
    patch: int

    _SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        """Create a :class:`SemanticVersion` instance from *value*.

        Parameters
        ----------
        value:
            String representation formatted as ``MAJOR.MINOR.PATCH``.
        """

        match = cls._SEMVER_RE.match(value.strip())
        if not match:
            msg = (
                f"Invalid semantic version '{value}'. Expected <major>.<minor>.<patch>."
            )
            raise ValueError(msg)
        major, minor, patch = (int(group) for group in match.groups())
        return cls(major=major, minor=minor, patch=patch)

    def __str__(self) -> str:  # pragma: no cover - trivial proxy
        return f"{self.major}.{self.minor}.{self.patch}"

    def bump(
        self, *, major: bool = False, minor: bool = False, patch: bool = True
    ) -> "SemanticVersion":
        """Return a new version incremented according to semantic version rules."""

        if sum(map(bool, (major, minor, patch))) != 1:
            msg = "Exactly one of 'major', 'minor', or 'patch' must be set."
            raise ValueError(msg)
        if major:
            return SemanticVersion(self.major + 1, 0, 0)
        if minor:
            return SemanticVersion(self.major, self.minor + 1, 0)
        return SemanticVersion(self.major, self.minor, self.patch + 1)

    def is_backward_compatible_with(self, other: "SemanticVersion") -> bool:
        """Return whether this version can be used where *other* was expected."""

        if self.major != other.major:
            return False
        if self.minor < other.minor:
            return False
        if self.minor == other.minor and self.patch < other.patch:
            return False
        return True


@dataclass(frozen=True)
class CompatibilityContract:
    """Contract describing the interface guarantees for a model or dataset."""

    name: str
    schema_version: SemanticVersion
    input_schema: str
    output_schema: str
    additional_checks: tuple[str, ...] = ()

    def is_compatible_with(self, other: "CompatibilityContract") -> bool:
        """Return whether *other* satisfies this contract."""

        if self.name != other.name:
            return False
        if not other.schema_version.is_backward_compatible_with(self.schema_version):
            return False
        if self.input_schema != other.input_schema:
            return False
        if self.output_schema != other.output_schema:
            return False
        missing_checks = set(self.additional_checks) - set(other.additional_checks)
        return not missing_checks


GateCondition = Callable[[Mapping[str, Any]], bool]


@dataclass(frozen=True)
class AccessGate:
    """Runtime guard that controls who can access a version."""

    name: str
    condition: GateCondition
    description: str = ""

    def is_open(self, context: Mapping[str, Any]) -> bool:
        try:
            return bool(self.condition(context))
        except Exception as exc:  # pragma: no cover - defensive guard
            msg = f"Gate '{self.name}' evaluation failed"
            raise VersioningError(msg) from exc


@dataclass(frozen=True)
class OperationalTag:
    """Machine-readable tag used to express operational posture."""

    name: str
    description: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def __hash__(self) -> int:  # pragma: no cover - trivial hash composition
        items = tuple(sorted(self.metadata.items()))
        return hash((self.name, self.description, items))


@dataclass(frozen=True)
class LineageRecord:
    """Capture provenance information for reproducibility and audits."""

    parent_versions: tuple[str, ...]
    data_fingerprint: str
    created_by: str
    created_at: datetime = field(default_factory=_utcnow)
    notes: str | None = None

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None:
            object.__setattr__(
                self, "created_at", self.created_at.replace(tzinfo=timezone.utc)
            )
        else:
            object.__setattr__(
                self, "created_at", self.created_at.astimezone(timezone.utc)
            )


@dataclass(frozen=True)
class FormatMigration:
    """Transformation capable of converting payloads between versions."""

    source: SemanticVersion
    target: SemanticVersion
    apply: Callable[[Any], Any]

    def can_migrate(self, source: SemanticVersion, target: SemanticVersion) -> bool:
        return self.source == source and self.target == target

    def run(self, payload: Any) -> Any:
        return self.apply(payload)


@dataclass(frozen=True)
class RollbackRecord:
    """Describe a rollback action for traceability."""

    target_version: str
    restored_version: str
    reason: str
    performed_by: str
    created_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:  # pragma: no cover - trivial timezone guard
        if self.created_at.tzinfo is None:
            object.__setattr__(
                self, "created_at", self.created_at.replace(tzinfo=timezone.utc)
            )
        else:
            object.__setattr__(
                self, "created_at", self.created_at.astimezone(timezone.utc)
            )


@dataclass
class VersionEntry:
    """Single model or dataset version tracked by the registry."""

    identifier: str
    kind: str
    semantic_version: SemanticVersion
    contract: CompatibilityContract
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    lifecycle_state: LifecycleState = LifecycleState.DRAFT
    is_active: bool = False
    tags: set[str] = field(default_factory=set)
    operational_tags: set[OperationalTag] = field(default_factory=set)
    access_gates: tuple[AccessGate, ...] = ()
    migrations: dict[SemanticVersion, FormatMigration] = field(default_factory=dict)
    lineage: list[LineageRecord] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def mark_updated(self) -> None:
        self.updated_at = _utcnow()

    @property
    def version_id(self) -> str:
        return f"{self.identifier}:{self.semantic_version}"

    def ensure_access(self, context: Mapping[str, Any]) -> None:
        for gate in self.access_gates:
            if not gate.is_open(context):
                raise AccessDeniedError(
                    f"Access gate '{gate.name}' denied access to {self.version_id}"
                )

    def add_lineage(self, record: LineageRecord) -> None:
        self.lineage.append(record)
        self.mark_updated()

    def add_migration(self, migration: FormatMigration) -> None:
        self.migrations[migration.target] = migration
        self.mark_updated()


class VersionCatalog:
    """Read-only catalog view for introspection and reporting."""

    def __init__(self, entries: Mapping[str, VersionEntry]):
        self._entries = entries

    def list_versions(
        self,
        *,
        identifier: str | None = None,
        kind: str | None = None,
        state: LifecycleState | None = None,
        active_only: bool = False,
    ) -> list[VersionEntry]:
        result: list[VersionEntry] = []
        for entry in self._entries.values():
            if identifier and entry.identifier != identifier:
                continue
            if kind and entry.kind != kind:
                continue
            if state and entry.lifecycle_state is not state:
                continue
            if active_only and not entry.is_active:
                continue
            result.append(entry)
        result.sort(key=lambda e: (e.identifier, e.semantic_version))
        return result


class VersionRegistry:
    """In-memory registry that captures model and dataset version metadata."""

    def __init__(self) -> None:
        self._entries: dict[str, VersionEntry] = {}
        self._catalog_index: dict[str, list[str]] = defaultdict(list)
        self._rollback_history: list[RollbackRecord] = []

    @staticmethod
    def _make_key(identifier: str, version: SemanticVersion) -> str:
        return f"{identifier}:{version}"

    def register_version(
        self,
        identifier: str,
        *,
        kind: str,
        version: SemanticVersion | str,
        contract: CompatibilityContract,
        tags: Iterable[str] | None = None,
        operational_tags: Iterable[OperationalTag] | None = None,
        access_gates: Iterable[AccessGate] | None = None,
        lineage: LineageRecord | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> VersionEntry:
        semver = SemanticVersion.parse(version) if isinstance(version, str) else version
        key = self._make_key(identifier, semver)
        if key in self._entries:
            msg = f"Version '{key}' is already registered."
            raise VersioningError(msg)

        entry = VersionEntry(
            identifier=identifier,
            kind=kind,
            semantic_version=semver,
            contract=contract,
            tags=set(sorted(tags or [])),
            operational_tags=set(operational_tags or ()),
            access_gates=tuple(access_gates or ()),
            metadata=dict(metadata or {}),
        )
        if lineage:
            entry.add_lineage(lineage)

        self._entries[key] = entry
        self._catalog_index[identifier].append(key)
        return entry

    def get(self, identifier: str, version: SemanticVersion | str) -> VersionEntry:
        semver = SemanticVersion.parse(version) if isinstance(version, str) else version
        key = self._make_key(identifier, semver)
        try:
            return self._entries[key]
        except KeyError as exc:
            msg = f"Version '{key}' is not registered."
            raise VersioningError(msg) from exc

    def promote(
        self,
        identifier: str,
        version: SemanticVersion | str,
        *,
        target_state: LifecycleState,
    ) -> VersionEntry:
        entry = self.get(identifier, version)
        if target_state not in _ALLOWED_TRANSITIONS[entry.lifecycle_state]:
            msg = (
                f"Cannot transition {entry.version_id} from {entry.lifecycle_state.value} "
                f"to {target_state.value}."
            )
            raise VersioningError(msg)
        entry.lifecycle_state = target_state
        entry.mark_updated()
        return entry

    def set_active(
        self, identifier: str, version: SemanticVersion | str, *, active: bool
    ) -> VersionEntry:
        entry = self.get(identifier, version)
        if active and entry.lifecycle_state not in {
            LifecycleState.STAGING,
            LifecycleState.PRODUCTION,
        }:
            msg = (
                f"Only staging or production versions can be activated. "
                f"{entry.version_id} is {entry.lifecycle_state.value}."
            )
            raise VersioningError(msg)
        entry.is_active = active
        entry.mark_updated()
        return entry

    def validate_contract(
        self,
        identifier: str,
        version: SemanticVersion | str,
        *,
        against: CompatibilityContract,
    ) -> bool:
        entry = self.get(identifier, version)
        return entry.contract.is_compatible_with(against)

    def add_migration(
        self,
        identifier: str,
        version: SemanticVersion | str,
        migration: FormatMigration,
    ) -> VersionEntry:
        entry = self.get(identifier, version)
        entry.add_migration(migration)
        return entry

    def migrate_payload(
        self,
        identifier: str,
        source_version: SemanticVersion | str,
        target_version: SemanticVersion | str,
        payload: Any,
    ) -> Any:
        entry = self.get(identifier, source_version)
        target_semver = (
            SemanticVersion.parse(target_version)
            if isinstance(target_version, str)
            else target_version
        )
        migration = entry.migrations.get(target_semver)
        if not migration:
            msg = (
                f"No migration registered to convert {entry.version_id} to "
                f"{identifier}:{target_semver}."
            )
            raise VersioningError(msg)
        return migration.run(payload)

    def ensure_access(
        self,
        identifier: str,
        version: SemanticVersion | str,
        context: Mapping[str, Any],
    ) -> VersionEntry:
        entry = self.get(identifier, version)
        entry.ensure_access(context)
        return entry

    def record_rollback(
        self,
        *,
        target_version: str,
        restored_version: str,
        reason: str,
        performed_by: str,
    ) -> RollbackRecord:
        record = RollbackRecord(
            target_version=target_version,
            restored_version=restored_version,
            reason=reason,
            performed_by=performed_by,
        )
        self._rollback_history.append(record)
        return record

    def rollback_history(self) -> list[RollbackRecord]:
        return list(self._rollback_history)

    def catalog(self) -> VersionCatalog:
        return VersionCatalog(self._entries.copy())

    def active_versions(self, *, kind: str | None = None) -> list[VersionEntry]:
        catalog = self.catalog()
        return catalog.list_versions(kind=kind, active_only=True)
