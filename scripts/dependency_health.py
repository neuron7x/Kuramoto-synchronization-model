"""Dependency health checks spanning Python, Node, and Go toolchains."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from packaging.markers import default_environment
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

LOGGER = logging.getLogger(__name__)

IGNORED_PREFIXES = ("-r ", "--", "http://", "https://", "git+", "svn+", "hg+")


class DependencyHealthError(RuntimeError):
    """Raised when dependency health checks cannot be executed."""


@dataclass(frozen=True)
class DependencyIssue:
    system: str
    path: Path
    message: str
    severity: str = "error"


@dataclass(frozen=True)
class RequirementSpec:
    requirement: Requirement
    source: Path
    applies: bool

    @property
    def canonical_name(self) -> str:
        return canonicalize_name(self.requirement.name)


@dataclass(frozen=True)
class LockedDependency:
    name: str
    version: str | None
    requirement: Requirement
    source: Path

    @property
    def canonical_name(self) -> str:
        return canonicalize_name(self.name)

    @property
    def parsed_version(self) -> Version | None:
        if not self.version:
            return None
        try:
            return Version(self.version)
        except InvalidVersion:
            LOGGER.debug("Unable to parse version '%s'", self.version)
            return None


@dataclass(frozen=True)
class DependencyHealthReport:
    issues: tuple[DependencyIssue, ...]

    def has_failures(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)


def build_marker_environment(python_version: str | None = None) -> Mapping[str, str]:
    environment = default_environment()
    if python_version:
        environment = dict(environment)
        environment["python_version"] = python_version
        environment["python_full_version"] = python_version
    return environment


def load_requirement_specs(
    files: Sequence[Path], *, environment: Mapping[str, str]
) -> list[RequirementSpec]:
    specs: list[RequirementSpec] = []
    for path in files:
        if not path.exists():
            raise DependencyHealthError(f"Requirements file not found: {path}")
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(IGNORED_PREFIXES):
                continue
            try:
                requirement = Requirement(line)
            except InvalidRequirement as exc:
                raise DependencyHealthError(
                    f"Invalid requirement '{line}' in {path}"
                ) from exc
            applies = (
                requirement.marker.evaluate(environment)
                if requirement.marker
                else True
            )
            specs.append(
                RequirementSpec(
                    requirement=requirement,
                    source=path,
                    applies=applies,
                )
            )
    return specs


def load_locked_dependencies(path: Path) -> dict[str, list[LockedDependency]]:
    if not path.exists():
        raise DependencyHealthError(f"Lock file not found: {path}")
    entries: dict[str, list[LockedDependency]] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(IGNORED_PREFIXES):
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement as exc:
            raise DependencyHealthError(
                f"Invalid requirement '{line}' in {path}"
            ) from exc
        name = requirement.name
        specifiers = list(requirement.specifier)
        version: str | None = None
        if len(specifiers) == 1:
            spec = specifiers[0]
            if spec.operator in {"==", "==="} and not spec.version.endswith(".*"):
                version = spec.version
        entry = LockedDependency(
            name=name,
            version=version,
            requirement=requirement,
            source=path,
        )
        entries.setdefault(entry.canonical_name, []).append(entry)
    return entries


def compare_requirements_to_lock(
    requirements: Sequence[RequirementSpec],
    *,
    lock_file: Path,
    system: str,
    enforce_pins: bool = False,
) -> list[DependencyIssue]:
    issues: list[DependencyIssue] = []
    locked = load_locked_dependencies(lock_file)

    for spec in requirements:
        if not spec.applies:
            continue
        requirement = spec.requirement
        name = spec.canonical_name
        if enforce_pins and not requirement.url and not requirement.specifier:
            issues.append(
                DependencyIssue(
                    system=system,
                    path=spec.source,
                    message=(
                        f"Requirement '{requirement.name}' is not pinned to an exact "
                        "version."
                    ),
                )
            )
        entries = locked.get(name, [])
        if not entries:
            issues.append(
                DependencyIssue(
                    system=system,
                    path=lock_file,
                    message=(
                        f"Locked dependencies missing '{requirement.name}' declared in "
                        f"{spec.source}."
                    ),
                )
            )
            continue
        if len(entries) > 1:
            versions = ", ".join(
                sorted({entry.version or "unresolved" for entry in entries})
            )
            issues.append(
                DependencyIssue(
                    system=system,
                    path=lock_file,
                    message=(
                        f"Multiple versions locked for '{requirement.name}': {versions}."
                    ),
                )
            )
        for entry in entries:
            if not entry.version:
                issues.append(
                    DependencyIssue(
                        system=system,
                        path=lock_file,
                        message=(
                            f"Locked dependency '{entry.name}' is not pinned to an "
                            "exact version."
                        ),
                    )
                )
                continue
            if requirement.specifier and entry.parsed_version:
                if entry.parsed_version not in requirement.specifier:
                    issues.append(
                        DependencyIssue(
                            system=system,
                            path=lock_file,
                            message=(
                                f"Locked version {entry.version} for '{entry.name}' "
                                f"does not satisfy '{requirement.specifier}' from "
                                f"{spec.source}."
                            ),
                        )
                    )
    return issues


def compare_constraints_to_lock(
    constraints: Sequence[RequirementSpec],
    *,
    lock_file: Path,
    system: str,
) -> list[DependencyIssue]:
    issues: list[DependencyIssue] = []
    locked = load_locked_dependencies(lock_file)
    for spec in constraints:
        if not spec.applies:
            continue
        entries = locked.get(spec.canonical_name, [])
        if not entries:
            continue
        for entry in entries:
            if not entry.version or not entry.parsed_version:
                continue
            if spec.requirement.specifier and (
                entry.parsed_version not in spec.requirement.specifier
            ):
                issues.append(
                    DependencyIssue(
                        system=system,
                        path=lock_file,
                        message=(
                            f"Locked version {entry.version} for '{entry.name}' "
                            f"violates constraint '{spec.requirement.specifier}' "
                            f"from {spec.source}."
                        ),
                    )
                )
    return issues


def check_python_dependencies(
    *,
    requirements: Sequence[Path],
    dev_requirements: Sequence[Path],
    backend_requirements: Sequence[Path],
    constraints: Sequence[Path],
    runtime_lock: Path,
    dev_lock: Path,
    python_version: str | None = None,
) -> DependencyHealthReport:
    environment = build_marker_environment(python_version)
    issues: list[DependencyIssue] = []

    runtime_specs = load_requirement_specs(requirements, environment=environment)
    dev_specs = load_requirement_specs(dev_requirements, environment=environment)
    backend_specs = load_requirement_specs(
        backend_requirements, environment=environment
    )
    constraint_specs = load_requirement_specs(constraints, environment=environment)

    issues.extend(
        compare_requirements_to_lock(
            runtime_specs,
            lock_file=runtime_lock,
            system="python",
        )
    )
    issues.extend(
        compare_requirements_to_lock(
            tuple(runtime_specs) + tuple(dev_specs),
            lock_file=dev_lock,
            system="python",
        )
    )
    if backend_specs:
        issues.extend(
            compare_requirements_to_lock(
                backend_specs,
                lock_file=runtime_lock,
                system="python",
                enforce_pins=True,
            )
        )

    for lock_file in (runtime_lock, dev_lock):
        issues.extend(
            compare_constraints_to_lock(
                constraint_specs,
                lock_file=lock_file,
                system="python",
            )
        )

    return DependencyHealthReport(issues=tuple(issues))


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        raise DependencyHealthError(f"JSON file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DependencyHealthError(f"Invalid JSON at {path}: {exc}") from exc


def check_node_dependencies(package_json: Path, package_lock: Path) -> DependencyHealthReport:
    issues: list[DependencyIssue] = []
    package_data = _load_json(package_json)
    lock_data = _load_json(package_lock)

    lock_version = lock_data.get("lockfileVersion")
    if lock_version not in {2, 3}:
        issues.append(
            DependencyIssue(
                system="node",
                path=package_lock,
                message=(
                    f"Unsupported lockfileVersion {lock_version}; expected 2 or 3."
                ),
            )
        )

    if package_data.get("name") and lock_data.get("name"):
        if package_data.get("name") != lock_data.get("name"):
            issues.append(
                DependencyIssue(
                    system="node",
                    path=package_lock,
                    message=(
                        "package-lock.json name does not match package.json "
                        f"({lock_data.get('name')} != {package_data.get('name')})."
                    ),
                )
            )

    if package_data.get("version") and lock_data.get("version"):
        if package_data.get("version") != lock_data.get("version"):
            issues.append(
                DependencyIssue(
                    system="node",
                    path=package_lock,
                    message=(
                        "package-lock.json version does not match package.json "
                        f"({lock_data.get('version')} != {package_data.get('version')})."
                    ),
                )
            )

    packages = lock_data.get("packages")
    root = packages.get("") if isinstance(packages, dict) else None
    if not isinstance(root, dict):
        issues.append(
            DependencyIssue(
                system="node",
                path=package_lock,
                message="package-lock.json does not contain root package metadata.",
            )
        )
        return DependencyHealthReport(issues=tuple(issues))

    root_deps = root.get("dependencies", {}) if isinstance(root, dict) else {}
    root_dev = root.get("devDependencies", {}) if isinstance(root, dict) else {}

    for name, version in (package_data.get("dependencies") or {}).items():
        if name not in root_deps:
            issues.append(
                DependencyIssue(
                    system="node",
                    path=package_lock,
                    message=(
                        f"Dependency '{name}@{version}' missing from package-lock.json."
                    ),
                )
            )
    for name, version in (package_data.get("devDependencies") or {}).items():
        if name not in root_dev:
            issues.append(
                DependencyIssue(
                    system="node",
                    path=package_lock,
                    message=(
                        f"Dev dependency '{name}@{version}' missing from package-lock.json."
                    ),
                )
            )
    return DependencyHealthReport(issues=tuple(issues))


def check_go_dependencies(go_mod: Path, go_sum: Path) -> DependencyHealthReport:
    issues: list[DependencyIssue] = []
    if not go_mod.exists():
        raise DependencyHealthError(f"go.mod not found: {go_mod}")
    if not go_sum.exists():
        raise DependencyHealthError(f"go.sum not found: {go_sum}")

    go_sum_lines = go_sum.read_text(encoding="utf-8").splitlines()
    go_sum_index: dict[str, set[str]] = {}
    for line in go_sum_lines:
        tokens = line.split()
        if len(tokens) >= 2:
            module = tokens[0]
            version = tokens[1]
            go_sum_index.setdefault(module, set()).add(version)

    requires = _parse_go_requires(go_mod)
    for module, version in requires:
        versions = go_sum_index.get(module, set())
        if version not in versions and f"{version}/go.mod" not in versions:
            issues.append(
                DependencyIssue(
                    system="go",
                    path=go_sum,
                    message=(
                        f"Missing go.sum entry for '{module} {version}'."
                    ),
                )
            )
    return DependencyHealthReport(issues=tuple(issues))


def _parse_go_requires(go_mod: Path) -> list[tuple[str, str]]:
    requires: list[tuple[str, str]] = []
    in_block = False
    for raw_line in go_mod.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("require ("):
            in_block = True
            continue
        if in_block and line.startswith(")"):
            in_block = False
            continue
        if line.startswith("require "):
            line = line.removeprefix("require ").strip()
        if not in_block and not raw_line.lstrip().startswith("require "):
            if not in_block:
                continue
        match = re.match(r"(?P<module>\S+)\s+(?P<version>\S+)", line)
        if not match:
            continue
        requires.append((match.group("module"), match.group("version")))
    return requires


def merge_reports(*reports: DependencyHealthReport) -> DependencyHealthReport:
    issues: list[DependencyIssue] = []
    for report in reports:
        issues.extend(report.issues)
    return DependencyHealthReport(issues=tuple(issues))
