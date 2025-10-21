"""High-level dependency management utilities for TradePulse.

The module centralises logic for producing deterministic lock files,
evaluating dependency health, and orchestrating updates while enforcing
strict semantic versioning policies.  The API is intentionally decoupled
from network access so it can operate in restricted or offline
environments while still providing comprehensive metadata driven
workflows.

All helpers lean on ``packaging`` primitives for correctness and expose
pure functions where possible to simplify reasoning and testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Dict, Iterable, Iterator, Mapping, MutableMapping, Sequence

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import Version


class DependencyResolutionError(RuntimeError):
    """Raised when a dependency cannot be resolved from the repository."""


class RepositoryConfigurationError(RuntimeError):
    """Raised when repository metadata is malformed or inconsistent."""


class LicensePolicyError(RuntimeError):
    """Raised when a license policy document is invalid."""


@dataclass(frozen=True)
class VulnerabilityRecord:
    """Represents an advisory associated with a concrete package version."""

    identifier: str
    severity: str
    fix_versions: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.identifier,
            "severity": self.severity,
            "fix_versions": list(self.fix_versions),
            "aliases": list(self.aliases),
            "description": self.description,
        }


@dataclass(frozen=True)
class PackageMetadata:
    """Metadata about a package version maintained by the repository."""

    name: str
    version: Version
    dependencies: tuple[str, ...] = ()
    licenses: tuple[str, ...] = ()
    python_versions: tuple[str, ...] = ()
    mirror_url: str | None = None
    vulnerabilities: tuple[VulnerabilityRecord, ...] = ()

    @property
    def canonical_name(self) -> str:
        return canonicalize_name(self.name)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": str(self.version),
            "dependencies": list(self.dependencies),
            "licenses": list(self.licenses),
            "python_versions": list(self.python_versions),
            "mirror_url": self.mirror_url,
            "vulnerabilities": [record.to_dict() for record in self.vulnerabilities],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "PackageMetadata":
        try:
            name = str(payload["name"])
            version = Version(str(payload["version"]))
        except Exception as exc:  # pragma: no cover - defensive
            raise RepositoryConfigurationError(
                f"Invalid package metadata payload: {payload}") from exc

        dependencies = tuple(str(value) for value in payload.get("dependencies", ()) or ())
        licenses = tuple(str(value) for value in payload.get("licenses", ()) or ())
        python_versions = tuple(str(value) for value in payload.get("python_versions", ()) or ())
        mirror_url = payload.get("mirror_url")
        if mirror_url is not None:
            mirror_url = str(mirror_url)

        vulns: list[VulnerabilityRecord] = []
        for raw in payload.get("vulnerabilities", ()) or ():
            if not isinstance(raw, Mapping):  # pragma: no cover - defensive
                raise RepositoryConfigurationError(
                    f"Malformed vulnerability record for {name}: {raw}")
            vulns.append(
                VulnerabilityRecord(
                    identifier=str(raw.get("id")),
                    severity=str(raw.get("severity", "unknown")),
                    fix_versions=tuple(str(item) for item in raw.get("fix_versions", ()) or ()),
                    aliases=tuple(str(item) for item in raw.get("aliases", ()) or ()),
                    description=str(raw.get("description", "")),
                )
            )

        return cls(
            name=name,
            version=version,
            dependencies=dependencies,
            licenses=licenses,
            python_versions=python_versions,
            mirror_url=mirror_url,
            vulnerabilities=tuple(vulns),
        )


class DependencyRepository:
    """In-memory representation of package metadata with optional caching."""

    def __init__(
        self,
        packages: Iterable[PackageMetadata] | None = None,
        *,
        cache_path: Path | None = None,
        offline: bool = False,
        mirrors: Mapping[str, str] | None = None,
    ) -> None:
        self._packages: MutableMapping[str, list[PackageMetadata]] = {}
        self._default_mirror: str | None = None
        self._mirrors: MutableMapping[str, str] = {}
        self.cache_path = cache_path
        self.offline = offline

        if cache_path and cache_path.exists():
            self._load_cache(cache_path)

        if packages:
            for metadata in packages:
                self._add(metadata)
            if cache_path:
                self.save_cache()

        if mirrors:
            for name, url in mirrors.items():
                if name == "*":
                    self._default_mirror = url
                else:
                    self._mirrors[canonicalize_name(name)] = url

    def _load_cache(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        packages = payload.get("packages", [])
        if packages:
            for raw in packages:
                metadata = PackageMetadata.from_dict(raw)
                self._add(metadata)
        mirrors = payload.get("mirrors") or {}
        for name, url in mirrors.items():
            if name == "*":
                self._default_mirror = str(url)
            else:
                self._mirrors[canonicalize_name(name)] = str(url)

    def save_cache(self) -> None:
        if not self.cache_path:
            return
        payload = {
            "packages": [metadata.to_dict() for metadata in self.iter_packages()],
            "mirrors": {"*": self._default_mirror} | {name: url for name, url in self._mirrors.items()},
        }
        if payload["mirrors"].get("*") is None:
            del payload["mirrors"]["*"]
        path = self.cache_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _add(self, metadata: PackageMetadata) -> None:
        bucket = self._packages.setdefault(metadata.canonical_name, [])
        bucket.append(metadata)
        bucket.sort(key=lambda item: item.version)
        if metadata.mirror_url:
            self._mirrors[metadata.canonical_name] = metadata.mirror_url

    def iter_packages(self) -> Iterator[PackageMetadata]:
        for bucket in self._packages.values():
            yield from bucket

    def available_versions(self, name: str) -> tuple[Version, ...]:
        canonical = canonicalize_name(name)
        versions = tuple(metadata.version for metadata in self._packages.get(canonical, ()))
        if versions:
            return versions
        if self.offline:
            raise DependencyResolutionError(
                f"Package '{name}' not present in offline repository cache")
        return ()

    def metadata_for(self, name: str, version: Version) -> PackageMetadata:
        canonical = canonicalize_name(name)
        for candidate in self._packages.get(canonical, ()):
            if candidate.version == version:
                return candidate
        raise DependencyResolutionError(
            f"Metadata for {name}=={version} is unavailable in the repository")

    def resolve(self, requirement: Requirement) -> PackageMetadata:
        canonical = canonicalize_name(requirement.name)
        candidates = self._packages.get(canonical)
        if not candidates:
            raise DependencyResolutionError(f"Unable to resolve dependency '{requirement.name}'")
        matches: list[PackageMetadata] = []
        specifier = requirement.specifier if requirement.specifier else SpecifierSet()
        for candidate in candidates:
            version = candidate.version
            if specifier and version not in specifier:
                continue
            if not requirement.marker or requirement.marker.evaluate({"python_version": "3.11"}):
                matches.append(candidate)
        if not matches:
            raise DependencyResolutionError(
                f"No versions satisfy the constraint '{requirement}'")
        return matches[-1]

    def mirror_for(self, name: str) -> str | None:
        canonical = canonicalize_name(name)
        return self._mirrors.get(canonical, self._default_mirror)

    @classmethod
    def from_json(cls, path: Path, *, cache_path: Path | None = None, offline: bool = False) -> "DependencyRepository":
        payload = json.loads(path.read_text(encoding="utf-8"))
        packages = [PackageMetadata.from_dict(entry) for entry in payload.get("packages", [])]
        mirrors = payload.get("mirrors") or None
        return cls(packages, cache_path=cache_path, offline=offline, mirrors=mirrors)


@dataclass(frozen=True)
class LockedDependency:
    """Represents a resolved package pinned in a lock file."""

    name: str
    version: Version
    dependencies: tuple[str, ...] = ()

    @property
    def canonical_name(self) -> str:
        return canonicalize_name(self.name)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": str(self.version),
            "dependencies": list(self.dependencies),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "LockedDependency":
        try:
            name = str(payload["name"])
            version = Version(str(payload["version"]))
        except Exception as exc:  # pragma: no cover - defensive
            raise RepositoryConfigurationError(
                f"Malformed locked dependency payload: {payload}") from exc
        dependencies = tuple(str(value) for value in payload.get("dependencies", ()) or ())
        return cls(name=name, version=version, dependencies=dependencies)

    def requirement_line(self) -> str:
        return f"{self.name}=={self.version}"


@dataclass(frozen=True)
class Lockfile:
    """Immutable representation of the repository lock state."""

    generated_at: datetime
    packages: tuple[LockedDependency, ...]
    mirrors: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.replace(microsecond=0).isoformat(),
            "packages": [package.to_dict() for package in self.packages],
            "mirrors": dict(self.mirrors),
        }

    def write(self, path: Path) -> None:
        payload = self.to_dict()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "Lockfile":
        raw_timestamp = payload.get("generated_at")
        timestamp = (
            datetime.fromisoformat(str(raw_timestamp))
            if raw_timestamp
            else datetime.now(timezone.utc)
        )
        packages = tuple(LockedDependency.from_dict(entry) for entry in payload.get("packages", ()))
        mirrors = payload.get("mirrors") or {}
        canonical_mirrors = {
            canonicalize_name(key) if key != "*" else key: str(value)
            for key, value in mirrors.items()
        }
        return cls(generated_at=timestamp, packages=packages, mirrors=canonical_mirrors)

    @classmethod
    def load(cls, path: Path) -> "Lockfile":
        payload = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_dict(payload)

    def get(self, name: str) -> LockedDependency | None:
        canonical = canonicalize_name(name)
        for package in self.packages:
            if package.canonical_name == canonical:
                return package
        return None

    def requirement_lines(self) -> tuple[str, ...]:
        return tuple(package.requirement_line() for package in self.packages)

    def as_lookup(self) -> dict[str, LockedDependency]:
        return {package.canonical_name: package for package in self.packages}


def generate_lockfile(requirements: Sequence[str], repository: DependencyRepository) -> Lockfile:
    """Resolve *requirements* into a deterministic :class:`Lockfile`."""

    seen: Dict[str, LockedDependency] = {}
    queue: list[Requirement] = [Requirement(req) for req in requirements]

    while queue:
        requirement = queue.pop(0)
        metadata = repository.resolve(requirement)
        canonical = metadata.canonical_name
        if canonical in seen:
            continue
        dependency_names: list[str] = []
        for raw in metadata.dependencies:
            dep = Requirement(raw)
            dependency_names.append(canonicalize_name(dep.name))
            queue.append(dep)
        seen[canonical] = LockedDependency(
            name=metadata.name,
            version=metadata.version,
            dependencies=tuple(sorted(set(dependency_names))),
        )

    packages = tuple(sorted(seen.values(), key=lambda item: item.canonical_name))
    mirrors = {
        canonicalize_name(name): url
        for name, url in (
            (pkg.name, repository.mirror_for(pkg.name))
            for pkg in packages
        )
        if url
    }
    return Lockfile(generated_at=datetime.now(timezone.utc), packages=packages, mirrors=mirrors)


def find_duplicate_dependencies(lockfile: Lockfile) -> tuple[str, ...]:
    seen: Dict[str, str] = {}
    duplicates: list[str] = []
    for package in lockfile.packages:
        version = str(package.version)
        previous = seen.get(package.canonical_name)
        if previous is None:
            seen[package.canonical_name] = version
            continue
        if previous != version:
            duplicates.append(package.name)
    return tuple(sorted(set(duplicates)))


@dataclass(frozen=True)
class SemverPolicy:
    allow_major: bool = False
    allow_minor: bool = False
    allow_patch: bool = True

    def allows(self, current: Version, candidate: Version) -> bool:
        if candidate <= current:
            return False
        if candidate.major != current.major:
            return self.allow_major
        if candidate.minor != current.minor:
            return self.allow_minor
        if candidate.micro != current.micro:
            return self.allow_patch
        return False


@dataclass(frozen=True)
class UpdateCandidate:
    name: str
    current_version: Version
    target_version: Version
    reason: str


def plan_constrained_updates(
    lockfile: Lockfile,
    repository: DependencyRepository,
    *,
    policy: SemverPolicy | None = None,
) -> tuple[UpdateCandidate, ...]:
    policy = policy or SemverPolicy()
    plans: list[UpdateCandidate] = []
    for package in lockfile.packages:
        versions = repository.available_versions(package.name)
        if not versions:
            continue
        eligible = [version for version in versions if policy.allows(package.version, version)]
        if not eligible:
            continue
        target = eligible[-1]
        level = "major" if target.major != package.version.major else (
            "minor" if target.minor != package.version.minor else "patch"
        )
        plans.append(
            UpdateCandidate(
                name=package.name,
                current_version=package.version,
                target_version=target,
                reason=f"Latest {level} update available",
            )
        )
    return tuple(sorted(plans, key=lambda item: canonicalize_name(item.name)))


def render_dependency_graph(lockfile: Lockfile) -> str:
    lines = ["digraph dependencies {\n"]
    for package in lockfile.packages:
        label = f"{package.name}\\n{package.version}"
        lines.append(f'  "{package.canonical_name}" [label="{label}"];\n')
    for package in lockfile.packages:
        for dep in package.dependencies:
            lines.append(f'  "{package.canonical_name}" -> "{dep}";\n')
    lines.append("}\n")
    return "".join(lines)


@dataclass(frozen=True)
class VulnerabilityFinding:
    name: str
    version: Version
    advisory: VulnerabilityRecord


def detect_vulnerabilities(lockfile: Lockfile, repository: DependencyRepository) -> tuple[VulnerabilityFinding, ...]:
    findings: list[VulnerabilityFinding] = []
    for package in lockfile.packages:
        metadata = repository.metadata_for(package.name, package.version)
        for advisory in metadata.vulnerabilities:
            findings.append(
                VulnerabilityFinding(name=package.name, version=package.version, advisory=advisory)
            )
    return tuple(findings)


@dataclass(frozen=True)
class LicensePolicy:
    allowed: frozenset[str]
    restricted: frozenset[str]
    forbidden: frozenset[str]
    exceptions: frozenset[str] = frozenset()

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "LicensePolicy":
        try:
            allowed = frozenset(str(item) for item in payload.get("allowed", ()))
            restricted = frozenset(str(item) for item in payload.get("restricted", ()))
            forbidden = frozenset(str(item) for item in payload.get("forbidden", ()))
            exceptions = frozenset(str(item) for item in payload.get("exceptions", ()))
        except Exception as exc:  # pragma: no cover - defensive
            raise LicensePolicyError("Malformed license policy payload") from exc
        return cls(allowed=allowed, restricted=restricted, forbidden=forbidden, exceptions=exceptions)


@dataclass(frozen=True)
class LicenseIssue:
    dependency: LockedDependency
    licenses: tuple[str, ...]
    severity: str
    classification: str
    message: str


def evaluate_license_compliance(
    lockfile: Lockfile,
    repository: DependencyRepository,
    policy: LicensePolicy,
) -> tuple[LicenseIssue, ...]:
    issues: list[LicenseIssue] = []
    for package in lockfile.packages:
        metadata = repository.metadata_for(package.name, package.version)
        normalized = tuple(sorted(metadata.licenses)) or ("<unknown>",)
        classification = "allowed"
        severity = "info"
        message = "Compliant with policy"
        for license_name in normalized:
            if license_name in policy.exceptions:
                classification = "exception"
                severity = "warning"
                message = "License allowed via exception"
                break
            if license_name in policy.forbidden:
                classification = "forbidden"
                severity = "critical"
                message = "License forbidden by policy"
                break
            if license_name in policy.restricted:
                classification = "restricted"
                severity = "warning"
                message = "License requires review"
        if classification != "allowed":
            issues.append(
                LicenseIssue(
                    dependency=package,
                    licenses=normalized,
                    severity=severity,
                    classification=classification,
                    message=message,
                )
            )
    return tuple(issues)


def prune_lockfile(lockfile: Lockfile, used_packages: Iterable[str]) -> Lockfile:
    keep: set[str] = {canonicalize_name(name) for name in used_packages}
    graph = lockfile.as_lookup()
    queue = list(keep)
    while queue:
        name = queue.pop(0)
        dependency = graph.get(name)
        if not dependency:
            continue
        for child in dependency.dependencies:
            if child not in keep:
                keep.add(child)
                queue.append(child)

    retained = tuple(package for package in lockfile.packages if package.canonical_name in keep)
    return Lockfile(generated_at=datetime.now(timezone.utc), packages=retained, mirrors=lockfile.mirrors)


def generate_restore_plan(lockfile: Lockfile, python_executable: str = "python") -> tuple[str, ...]:
    commands = [
        f"{python_executable} -m pip install --no-deps {package.requirement_line()}"
        for package in lockfile.packages
    ]
    return tuple(commands)


def build_compatibility_matrix(
    lockfile: Lockfile,
    repository: DependencyRepository,
    python_versions: Iterable[str],
) -> dict[str, dict[str, bool]]:
    matrix: dict[str, dict[str, bool]] = {}
    for package in lockfile.packages:
        metadata = repository.metadata_for(package.name, package.version)
        supported = set(metadata.python_versions)
        entry: dict[str, bool] = {}
        for version in python_versions:
            entry[str(version)] = str(version) in supported
        matrix[package.name] = entry
    return matrix


@dataclass(frozen=True)
class PackageDelta:
    name: str
    old_version: Version | None
    new_version: Version | None


@dataclass(frozen=True)
class PackageChangeReport:
    added: tuple[PackageDelta, ...]
    removed: tuple[PackageDelta, ...]
    updated: tuple[PackageDelta, ...]

    def to_dict(self) -> dict[str, object]:
        def _serialise(entries: tuple[PackageDelta, ...]) -> list[dict[str, object]]:
            return [
                {
                    "name": entry.name,
                    "old_version": str(entry.old_version) if entry.old_version else None,
                    "new_version": str(entry.new_version) if entry.new_version else None,
                }
                for entry in entries
            ]

        return {
            "added": _serialise(self.added),
            "removed": _serialise(self.removed),
            "updated": _serialise(self.updated),
        }


def compare_lockfiles(old: Lockfile, new: Lockfile) -> PackageChangeReport:
    old_map = old.as_lookup()
    new_map = new.as_lookup()

    added: list[PackageDelta] = []
    removed: list[PackageDelta] = []
    updated: list[PackageDelta] = []

    for name, dependency in new_map.items():
        previous = old_map.get(name)
        if previous is None:
            added.append(
                PackageDelta(name=dependency.name, old_version=None, new_version=dependency.version)
            )
        elif previous.version != dependency.version:
            updated.append(
                PackageDelta(name=dependency.name, old_version=previous.version, new_version=dependency.version)
            )

    for name, dependency in old_map.items():
        if name not in new_map:
            removed.append(
                PackageDelta(name=dependency.name, old_version=dependency.version, new_version=None)
            )

    key = lambda item: canonicalize_name(item.name)
    return PackageChangeReport(
        added=tuple(sorted(added, key=key)),
        removed=tuple(sorted(removed, key=key)),
        updated=tuple(sorted(updated, key=key)),
    )

