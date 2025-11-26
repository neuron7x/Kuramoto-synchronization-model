"""Utilities that keep TradePulse's software supply chain trustworthy."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import yaml
from packaging.requirements import InvalidRequirement, Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from tools.compliance import generate_license_report as license_report

LOGGER = logging.getLogger(__name__)


class DependencyError(RuntimeError):
    """Raised when dependency metadata cannot be processed."""


@dataclass(frozen=True)
class Dependency:
    """Represents a pinned dependency from a requirements lock file."""

    name: str
    raw_requirement: str
    source: Path
    requirement: Requirement

    @property
    def canonical_name(self) -> str:
        return canonicalize_name(self.name)

    @property
    def version(self) -> str | None:
        specifiers = list(self.requirement.specifier)
        if len(specifiers) != 1:
            return None
        spec = specifiers[0]
        if spec.operator in {"==", "==="} and not spec.version.endswith(".*"):
            return spec.version
        return None

    @property
    def parsed_version(self) -> Version | None:
        value = self.version
        if not value:
            return None
        try:
            return Version(value)
        except InvalidVersion:
            LOGGER.debug("Unable to parse version '%s' for %s", value, self.name)
            return None

    @property
    def is_pinned(self) -> bool:
        if self.requirement.url:
            return True
        specifiers = list(self.requirement.specifier)
        if len(specifiers) != 1:
            return False
        spec = specifiers[0]
        return spec.operator in {"==", "==="} and not spec.version.endswith(".*")

    def to_component(self) -> dict[str, object]:
        component: dict[str, object] = {
            "type": "library",
            "name": self.name,
            "purl": f"pkg:pypi/{self.canonical_name}",
            "properties": [
                {
                    "name": "dependency.source",
                    "value": str(self.source),
                },
            ],
        }
        if self.version:
            component["version"] = self.version
            component["purl"] = f"pkg:pypi/{self.canonical_name}@{self.version}"
        if self.requirement.extras:
            component["properties"].append(
                {
                    "name": "python.extras",
                    "value": ",".join(sorted(self.requirement.extras)),
                }
            )
        if self.requirement.marker:
            component["properties"].append(
                {
                    "name": "python.marker",
                    "value": str(self.requirement.marker),
                }
            )
        return component


@dataclass(frozen=True)
class DenylistEntry:
    """Represents a compromised package rule."""

    name: str
    specifier: SpecifierSet | None
    reason: str
    references: tuple[str, ...]
    cves: tuple[str, ...]

    @property
    def canonical_name(self) -> str:
        return canonicalize_name(self.name)

    def matches(self, dependency: Dependency) -> bool:
        if dependency.canonical_name != self.canonical_name:
            return False
        if not self.specifier:
            return True
        version = dependency.parsed_version
        if version is None:
            # When the dependency is unpinned, err on the safe side.
            return True
        return version in self.specifier


@dataclass(frozen=True)
class AllowlistEntry:
    """Represents approved exceptions to dependency verification policies."""

    name: str
    specifier: SpecifierSet | None
    allow_unpinned: bool
    allow_multiple_versions: bool
    reason: str | None = None

    @property
    def canonical_name(self) -> str:
        return canonicalize_name(self.name)

    def matches(self, dependency: Dependency) -> bool:
        if dependency.canonical_name != self.canonical_name:
            return False
        if not self.specifier:
            return True
        version = dependency.parsed_version
        if version is None:
            # Refuse to honour specifier-scoped allowlist entries for unpinned
            # dependencies so the configured version range is actually
            # enforced.
            return False
        return version in self.specifier


class Severity:
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class VerificationIssue:
    dependency: Dependency
    message: str
    severity: str
    references: tuple[str, ...] = ()
    cves: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "dependency": {
                "name": self.dependency.name,
                "version": self.dependency.version,
                "source": str(self.dependency.source),
            },
            "message": self.message,
            "severity": self.severity,
        }
        if self.references:
            payload["references"] = list(self.references)
        if self.cves:
            payload["cves"] = list(self.cves)
        return payload


@dataclass(frozen=True)
class DependencyVerificationReport:
    generated_at: datetime
    dependencies: tuple[Dependency, ...]
    issues: tuple[VerificationIssue, ...]

    def has_failures(self) -> bool:
        return any(
            issue.severity in {Severity.ERROR, Severity.CRITICAL}
            for issue in self.issues
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": self.generated_at.replace(microsecond=0).isoformat(),
            "dependency_count": len(self.dependencies),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True)
class LicenseException:
    canonical_package: str | None
    normalized_license: str | None
    license_name: str | None
    reason: str
    expires_at: datetime | None

    def matches(
        self, dependency: Dependency, license_key: str, *, now: datetime
    ) -> bool:
        if (
            self.canonical_package
            and dependency.canonical_name != self.canonical_package
        ):
            return False
        if self.normalized_license and license_key != self.normalized_license:
            return False
        if self.expires_at and now >= self.expires_at:
            return False
        return True


@dataclass(frozen=True)
class LicensePolicy:
    allowed: frozenset[str]
    restricted: frozenset[str]
    forbidden: frozenset[str]
    aliases: Mapping[str, str]
    exceptions: tuple[LicenseException, ...]

    def normalise(self, license_name: str) -> tuple[str, str]:
        raw = str(license_name or "").strip()
        if not raw:
            return "", ""
        canonical = self.aliases.get(raw.casefold(), raw)
        normalised = re.sub(r"[^A-Z0-9]+", "", canonical.upper())
        return normalised, canonical

    def find_exception(
        self, dependency: Dependency, license_key: str, *, now: datetime
    ) -> LicenseException | None:
        for exception in self.exceptions:
            if exception.matches(dependency, license_key, now=now):
                return exception
        return None


@dataclass(frozen=True)
class LicenseIssue:
    dependency: Dependency
    licenses: tuple[str, ...]
    severity: str
    classification: str
    message: str
    exception_reason: str | None = None
    exception_expires: str | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "dependency": {
                "name": self.dependency.name,
                "version": self.dependency.version,
                "source": str(self.dependency.source),
            },
            "licenses": list(self.licenses),
            "severity": self.severity,
            "classification": self.classification,
            "message": self.message,
        }
        if self.exception_reason:
            payload["exception"] = {
                "reason": self.exception_reason,
                "expires": self.exception_expires,
            }
        return payload


@dataclass(frozen=True)
class VulnerabilityFinding:
    name: str
    version: str
    advisory: str
    severity: str
    fix_versions: tuple[str, ...]
    aliases: tuple[str, ...]
    description: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "advisory": self.advisory,
            "severity": self.severity,
            "fix_versions": list(self.fix_versions),
            "aliases": list(self.aliases),
            "description": self.description,
        }


@dataclass(frozen=True)
class ComplianceReport:
    generated_at: datetime
    dependency_report: DependencyVerificationReport
    license_issues: tuple[LicenseIssue, ...]
    vulnerabilities: tuple[VulnerabilityFinding, ...]

    def to_dict(self) -> dict[str, object]:
        dependency_report = self.dependency_report.to_dict()
        license_counts = _summarise_by_severity(
            issue.severity for issue in self.license_issues
        )
        vulnerability_counts = _summarise_by_severity(
            finding.severity for finding in self.vulnerabilities
        )
        remediation = [
            {
                "package": finding.name,
                "current_version": finding.version,
                "fix_versions": list(finding.fix_versions),
            }
            for finding in self.vulnerabilities
            if finding.fix_versions
        ]
        return {
            "generated_at": self.generated_at.replace(microsecond=0).isoformat(),
            "dependency_policy": dependency_report,
            "license_compliance": {
                "issues": [issue.to_dict() for issue in self.license_issues],
                "issue_count": len(self.license_issues),
                "severity": license_counts,
            },
            "vulnerabilities": {
                "findings": [finding.to_dict() for finding in self.vulnerabilities],
                "total": len(self.vulnerabilities),
                "severity": vulnerability_counts,
                "remediation": remediation,
            },
            "summary": {
                "dependency_issues": len(dependency_report["issues"]),
                "license_issues": len(self.license_issues),
                "vulnerability_findings": len(self.vulnerabilities),
            },
        }


def _parse_requirement(line: str, source: Path) -> Dependency:
    try:
        requirement = Requirement(line)
    except InvalidRequirement as exc:  # pragma: no cover - defensive
        raise DependencyError(f"Invalid requirement '{line}' in {source}") from exc
    name = requirement.name
    if not name:
        raise DependencyError(
            f"Missing package name in requirement '{line}' from {source}"
        )
    return Dependency(
        name=name, raw_requirement=line, source=source, requirement=requirement
    )


IGNORED_PREFIXES = ("-r ", "--", "http://", "https://", "git+", "svn+", "hg+")


def load_dependencies(requirement_files: Sequence[Path]) -> list[Dependency]:
    dependencies: list[Dependency] = []
    for path in requirement_files:
        if not path.exists():
            raise DependencyError(f"Requirements file not found: {path}")
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(IGNORED_PREFIXES):
                LOGGER.debug("Skipping non-package requirement line '%s'", line)
                continue
            dependency = _parse_requirement(line, path)
            dependencies.append(dependency)
    dependencies.sort(key=lambda dep: (dep.canonical_name, dep.version or ""))
    return dependencies


def load_denylist(path: Path) -> list[DenylistEntry]:
    if not path.exists():
        LOGGER.debug(
            "No denylist found at %s; skipping compromised dependency checks.", path
        )
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_entries = data.get("compromised", []) or []
    entries: list[DenylistEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            LOGGER.debug("Skipping malformed denylist entry: %s", item)
            continue
        name = item.get("name")
        if not name:
            LOGGER.debug("Skipping denylist entry without a name: %s", item)
            continue
        specifier_text = item.get("specifier")
        specifier = SpecifierSet(specifier_text) if specifier_text else None
        reason = item.get("reason") or "Flagged as compromised by security policy."
        references = tuple(item.get("references", []) or [])
        cves = tuple(item.get("cves", []) or [])
        entries.append(
            DenylistEntry(
                name=str(name),
                specifier=specifier,
                reason=str(reason),
                references=tuple(str(ref) for ref in references),
                cves=tuple(str(cve) for cve in cves),
            )
        )
    return entries


def load_allowlist(path: Path) -> list[AllowlistEntry]:
    if not path.exists():
        LOGGER.debug(
            "No allowlist found at %s; falling back to strict policy enforcement.", path
        )
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_entries = data.get("packages", []) or []
    entries: list[AllowlistEntry] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            LOGGER.debug("Skipping malformed allowlist entry: %s", item)
            continue
        name = item.get("name")
        if not name:
            LOGGER.debug("Skipping allowlist entry without a package name: %s", item)
            continue
        specifier_text = item.get("specifier")
        try:
            specifier = SpecifierSet(specifier_text) if specifier_text else None
        except Exception as exc:  # pragma: no cover - defensive parsing
            LOGGER.warning(
                "Ignoring allowlist entry for %s due to invalid specifier: %s",
                name,
                exc,
            )
            continue
        allow_unpinned = bool(item.get("allow_unpinned", False))
        allow_multiple_versions = bool(item.get("allow_multiple_versions", False))
        reason = item.get("reason")
        entries.append(
            AllowlistEntry(
                name=str(name),
                specifier=specifier,
                allow_unpinned=allow_unpinned,
                allow_multiple_versions=allow_multiple_versions,
                reason=str(reason) if reason else None,
            )
        )
    return entries


def verify_dependencies(
    dependencies: Sequence[Dependency],
    denylist: Sequence[DenylistEntry],
    *,
    allowlist: Sequence[AllowlistEntry] | None = None,
    require_pins: bool = True,
) -> DependencyVerificationReport:
    issues: list[VerificationIssue] = []
    seen: dict[str, Dependency] = {}

    allowlist_map: dict[str, list[AllowlistEntry]] = defaultdict(list)
    for entry in allowlist or ():
        allowlist_map[entry.canonical_name].append(entry)

    for dependency in dependencies:
        key = dependency.canonical_name
        entries = allowlist_map.get(key, [])
        allow_multi = any(
            entry.allow_multiple_versions and entry.matches(dependency)
            for entry in entries
        )
        if key in seen and seen[key].version != dependency.version and not allow_multi:
            issues.append(
                VerificationIssue(
                    dependency=dependency,
                    message=(
                        "Multiple versions detected for package "
                        f"'{dependency.name}' ({seen[key].version} and {dependency.version})."
                    ),
                    severity=Severity.ERROR,
                )
            )
        else:
            seen[key] = dependency

        allow_unpinned = any(
            entry.allow_unpinned and entry.matches(dependency) for entry in entries
        )
        if require_pins and not dependency.is_pinned and not allow_unpinned:
            issues.append(
                VerificationIssue(
                    dependency=dependency,
                    message="Dependency is not pinned to an exact version.",
                    severity=Severity.ERROR,
                )
            )

    denylist_map: dict[str, list[DenylistEntry]] = defaultdict(list)
    for entry in denylist:
        denylist_map[entry.canonical_name].append(entry)

    for dependency in dependencies:
        for entry in denylist_map.get(dependency.canonical_name, []):
            if entry.matches(dependency):
                issues.append(
                    VerificationIssue(
                        dependency=dependency,
                        message=entry.reason,
                        severity=Severity.CRITICAL,
                        references=entry.references,
                        cves=entry.cves,
                    )
                )

    report = DependencyVerificationReport(
        generated_at=datetime.now(tz=timezone.utc),
        dependencies=tuple(dependencies),
        issues=tuple(issues),
    )
    return report


def load_license_policy(path: Path) -> LicensePolicy:
    if not path.exists():
        raise DependencyError(f"License policy file not found: {path}")

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_aliases = data.get("aliases", {}) or {}
    alias_map: dict[str, str] = {}
    for alias, target in raw_aliases.items():
        if not isinstance(alias, str) or not isinstance(target, str):
            LOGGER.debug("Skipping malformed alias mapping: %s -> %s", alias, target)
            continue
        alias_map[alias.casefold()] = target.strip()

    allowed = frozenset(
        _normalise_license_collection(data.get("allowed", []), alias_map)
    )
    restricted = frozenset(
        _normalise_license_collection(data.get("restricted", []), alias_map)
    )
    forbidden = frozenset(
        _normalise_license_collection(data.get("forbidden", []), alias_map)
    )

    exceptions: list[LicenseException] = []
    for raw in data.get("exceptions", []) or []:
        if not isinstance(raw, dict):
            LOGGER.debug("Skipping malformed license exception entry: %s", raw)
            continue
        package = raw.get("package")
        canonical_package = canonicalize_name(package) if package else None
        license_name = raw.get("license")
        normalized_license = None
        display_license = None
        if license_name:
            normalized_license, display_license = _normalise_license_value(
                license_name, alias_map
            )
            if not normalized_license:
                LOGGER.debug(
                    "Unable to normalise license '%s' for exception involving %s",
                    license_name,
                    package,
                )
        reason = raw.get("reason") or "Exception approved by compliance team."
        expires_text = raw.get("expires")
        expires_at = _parse_exception_expiry(expires_text) if expires_text else None
        exceptions.append(
            LicenseException(
                canonical_package=canonical_package,
                normalized_license=normalized_license if normalized_license else None,
                license_name=display_license,
                reason=str(reason),
                expires_at=expires_at,
            )
        )

    # Ensure canonical values are resolvable even if not present in aliases.
    for value in list(allowed | restricted | forbidden):
        alias_map.setdefault(value.casefold(), value)

    return LicensePolicy(
        allowed=allowed,
        restricted=restricted,
        forbidden=forbidden,
        aliases=dict(alias_map),
        exceptions=tuple(exceptions),
    )


def build_license_inventory(
    sbom: Mapping[str, Any],
) -> dict[tuple[str, str | None], tuple[str, ...]]:
    components = sbom.get("components", []) if isinstance(sbom, Mapping) else []
    inventory: dict[tuple[str, str | None], tuple[str, ...]] = {}
    if not isinstance(components, Iterable):
        return inventory
    for component in components:
        if not isinstance(component, Mapping):
            continue
        name = component.get("name")
        if not name:
            continue
        canonical = canonicalize_name(str(name))
        version = component.get("version")
        version_key = str(version) if version else None
        licenses = tuple(license_report.extract_license_names(component) or ["UNKNOWN"])
        inventory[(canonical, version_key)] = licenses
        inventory.setdefault((canonical, None), licenses)
    return inventory


def evaluate_license_compliance(
    dependencies: Sequence[Dependency],
    sbom: Mapping[str, Any],
    policy: LicensePolicy,
    *,
    now: datetime | None = None,
) -> tuple[LicenseIssue, ...]:
    timestamp = now or datetime.now(timezone.utc)
    inventory = build_license_inventory(sbom)
    issues: list[LicenseIssue] = []
    for dependency in dependencies:
        key = (dependency.canonical_name, dependency.version)
        licenses = inventory.get(key) or inventory.get(
            (dependency.canonical_name, None)
        )
        resolved = tuple(licenses) if licenses else ("UNKNOWN",)
        issue = _evaluate_single_dependency_license(
            dependency, resolved, policy, timestamp
        )
        if issue:
            issues.append(issue)
    return tuple(issues)


def load_vulnerability_report(path: Path | None) -> tuple[VulnerabilityFinding, ...]:
    if not path:
        return ()
    if not path.exists():
        LOGGER.debug("Vulnerability report %s not found; skipping ingestion.", path)
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DependencyError(
            f"Failed to parse vulnerability report at {path}: {exc}"
        ) from exc

    findings: list[VulnerabilityFinding] = []
    packages = payload.get("packages")
    if isinstance(packages, list):
        for entry in packages:
            if not isinstance(entry, Mapping):
                continue
            findings.append(
                VulnerabilityFinding(
                    name=str(entry.get("name", "")),
                    version=str(entry.get("version", "")),
                    advisory=str(entry.get("advisory", "")),
                    severity=str(entry.get("severity", "unknown")).lower(),
                    fix_versions=tuple(
                        str(v) for v in entry.get("fix_versions", []) or []
                    ),
                    aliases=tuple(str(v) for v in entry.get("aliases", []) or []),
                    description=str(entry.get("description", "")),
                )
            )
    elif isinstance(payload.get("dependencies"), list):
        for dependency in payload["dependencies"]:
            name = str(dependency.get("name", ""))
            version = str(dependency.get("version", ""))
            for vuln in dependency.get("vulns", []) or []:
                findings.append(
                    VulnerabilityFinding(
                        name=name,
                        version=version,
                        advisory=str(vuln.get("id", "")),
                        severity=str(vuln.get("severity", "unknown")).lower(),
                        fix_versions=tuple(
                            str(v) for v in vuln.get("fix_versions", []) or []
                        ),
                        aliases=tuple(str(v) for v in vuln.get("aliases", []) or []),
                        description=str(vuln.get("description", "")),
                    )
                )
    return tuple(findings)


def build_compliance_report(
    dependency_report: DependencyVerificationReport,
    license_issues: Sequence[LicenseIssue],
    vulnerabilities: Sequence[VulnerabilityFinding],
) -> ComplianceReport:
    return ComplianceReport(
        generated_at=datetime.now(timezone.utc),
        dependency_report=dependency_report,
        license_issues=tuple(license_issues),
        vulnerabilities=tuple(vulnerabilities),
    )


def _normalise_license_value(value: str, alias_map: dict[str, str]) -> tuple[str, str]:
    canonical = alias_map.get(value.casefold(), value.strip())
    alias_map.setdefault(canonical.casefold(), canonical)
    normalised = re.sub(r"[^A-Z0-9]+", "", canonical.upper())
    return normalised, canonical


def _normalise_license_collection(
    values: Iterable[str] | None, alias_map: dict[str, str]
) -> list[str]:
    tokens: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            LOGGER.debug("Ignoring non-string license token in policy: %s", value)
            continue
        normalised, _ = _normalise_license_value(value, alias_map)
        if normalised:
            tokens.append(normalised)
    return tokens


def _parse_exception_expiry(raw: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        LOGGER.warning("Unable to parse license exception expiry '%s'", raw)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _evaluate_single_dependency_license(
    dependency: Dependency,
    licenses: Sequence[str],
    policy: LicensePolicy,
    now: datetime,
) -> LicenseIssue | None:
    processed: list[tuple[str, str]] = []
    for raw in licenses or ("UNKNOWN",):
        key, canonical = policy.normalise(raw)
        display = canonical or (raw or "UNKNOWN")
        processed.append((key, display))

    resolved_names = tuple(dict.fromkeys(name for _, name in processed if name))

    forbidden: list[str] = []
    restricted: list[str] = []
    unknown: list[str] = []
    exceptions_applied: list[tuple[str, LicenseException]] = []

    for key, display in processed:
        if not key:
            unknown.append(display)
            continue
        exception = policy.find_exception(dependency, key, now=now)
        if exception:
            exceptions_applied.append((display, exception))
            continue
        if key in policy.forbidden:
            forbidden.append(display)
        elif key in policy.restricted:
            restricted.append(display)
        elif key in policy.allowed:
            continue
        else:
            unknown.append(display)

    if forbidden:
        message = (
            "License(s) "
            + ", ".join(sorted({name for name in forbidden}))
            + " are forbidden by organisational policy."
        )
        return LicenseIssue(
            dependency=dependency,
            licenses=resolved_names,
            severity=Severity.CRITICAL,
            classification="forbidden",
            message=message,
        )

    if restricted:
        message = (
            "License(s) "
            + ", ".join(sorted({name for name in restricted}))
            + " require legal review before release."
        )
        return LicenseIssue(
            dependency=dependency,
            licenses=resolved_names,
            severity=Severity.WARNING,
            classification="restricted",
            message=message,
        )

    if unknown:
        message = (
            "Unable to determine licence information for "
            f"{dependency.name}. Observed tokens: "
            + ", ".join(sorted({name for name in unknown}))
        )
        return LicenseIssue(
            dependency=dependency,
            licenses=resolved_names,
            severity=Severity.WARNING,
            classification="unknown",
            message=message,
        )

    if exceptions_applied:
        reasons = sorted({exc.reason for _, exc in exceptions_applied})
        expiries = [exc.expires_at for _, exc in exceptions_applied if exc.expires_at]
        exception_message = "; ".join(reasons)
        expires_at = (
            max(expiries).replace(microsecond=0).isoformat() if expiries else None
        )
        message = (
            "License(s) "
            + ", ".join(sorted({name for name, _ in exceptions_applied}))
            + " approved via compliance exception."
        )
        return LicenseIssue(
            dependency=dependency,
            licenses=resolved_names,
            severity=Severity.WARNING,
            classification="exception",
            message=message,
            exception_reason=exception_message,
            exception_expires=expires_at,
        )

    return None


def _summarise_by_severity(values: Iterable[str]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for value in values:
        key = (value or "unknown").lower()
        summary[key] = summary.get(key, 0) + 1
    return summary


def build_cyclonedx_sbom(
    dependencies: Sequence[Dependency],
    *,
    component_name: str,
    component_version: str,
    source_description: str | None = None,
) -> dict[str, object]:
    components = [dependency.to_component() for dependency in dependencies]
    metadata: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "component": {
            "type": "application",
            "name": component_name,
            "version": component_version,
        },
        "tools": [
            {
                "vendor": "TradePulse",
                "name": "SupplyChainToolkit",
                "version": "2025.1",
            }
        ],
    }
    if source_description:
        metadata["component"]["description"] = source_description

    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{uuid4()}",
        "version": 1,
        "metadata": metadata,
        "components": components,
    }
    return sbom


def write_json_document(document: dict[str, object], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    LOGGER.info("Wrote JSON document to %s", destination)


def write_verification_report(
    report: DependencyVerificationReport, destination: Path
) -> None:
    write_json_document(report.to_dict(), destination)


def write_sbom(sbom: dict[str, object], destination: Path) -> None:
    write_json_document(sbom, destination)


def write_compliance_report(report: ComplianceReport, destination: Path) -> None:
    write_json_document(report.to_dict(), destination)


def append_compliance_archive(report: ComplianceReport, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report.to_dict(), sort_keys=True) + "\n")
