#!/usr/bin/env python3
"""Detect dependency drift between declared inputs and locked requirements."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Mapping, Sequence

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet


def _normalize(name: str) -> str:
    return name.lower().replace("_", "-")


def _parse_lock(lock_path: Path) -> Mapping[str, str]:
    locked: dict[str, str] = {}
    if not lock_path.is_file():
        raise FileNotFoundError(f"Lock file not found: {lock_path}")

    for raw in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("--"):
            continue
        if "==" not in line:
            continue
        pkg, version = line.split("==", 1)
        # Drop any environment markers or hashes that follow the pin
        version = version.split(";", 1)[0].strip()
        locked[_normalize(pkg)] = version
    return locked


def _parse_requirements_file(path: Path) -> List[Requirement]:
    if not path.is_file():
        raise FileNotFoundError(f"Requirements file not found: {path}")

    requirements: list[Requirement] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("-r"):
            continue
        try:
            requirements.append(Requirement(line))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(f"Failed to parse requirement '{line}' in {path}") from exc
    return requirements


def _parse_pyproject_dependencies(pyproject_path: Path) -> List[Requirement]:
    if not pyproject_path.is_file():
        raise FileNotFoundError(f"pyproject.toml not found: {pyproject_path}")

    try:
        import tomllib
    except ModuleNotFoundError as exc:  # pragma: no cover - Python <3.11 guard
        raise RuntimeError("tomllib is required to parse pyproject.toml") from exc

    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project", {})
    declared: list[str] = list(project.get("dependencies", []))

    requirements: list[Requirement] = []
    for spec in declared:
        try:
            requirements.append(Requirement(spec))
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError(
                f"Failed to parse dependency '{spec}' in {pyproject_path}"
            ) from exc
    return requirements


def _parse_constraints(constraints_path: Path) -> Mapping[str, SpecifierSet]:
    if not constraints_path.is_file():
        raise FileNotFoundError(f"Constraints file not found: {constraints_path}")

    specs: dict[str, SpecifierSet] = {}
    for raw in constraints_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "==" in line:
            pkg, version = line.split("==", 1)
            specs[_normalize(pkg)] = SpecifierSet(f"=={version.strip()}")
        elif ">=" in line:
            pkg, version = line.split(">=", 1)
            specs[_normalize(pkg)] = SpecifierSet(f">={version.strip()}")
    return specs


@dataclass(frozen=True)
class DriftIssue:
    package: str
    source: str
    locked_version: str | None
    expected: str
    reason: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "package": self.package,
            "source": self.source,
            "locked_version": self.locked_version,
            "expected": self.expected,
            "reason": self.reason,
        }


def _check_requirements(
    requirements: Iterable[tuple[str, Requirement]],
    locked: Mapping[str, str],
) -> List[DriftIssue]:
    issues: list[DriftIssue] = []
    for source, req in requirements:
        normalized = _normalize(req.name)
        locked_version = locked.get(normalized)
        if locked_version is None:
            issues.append(
                DriftIssue(
                    package=req.name,
                    source=source,
                    locked_version=None,
                    expected=str(req.specifier) or "any",
                    reason="missing from lock",
                )
            )
            continue
        if req.specifier and not req.specifier.contains(
            locked_version, prereleases=True
        ):
            issues.append(
                DriftIssue(
                    package=req.name,
                    source=source,
                    locked_version=locked_version,
                    expected=str(req.specifier),
                    reason="lock does not satisfy declared specifier",
                )
            )
    return issues


def _check_constraints(
    constraints: Mapping[str, SpecifierSet], locked: Mapping[str, str]
) -> List[DriftIssue]:
    issues: list[DriftIssue] = []
    for package, specifier in constraints.items():
        if package not in locked:
            # Constraint is advisory unless the package is present in the lock set
            continue
        locked_version = locked[package]
        if not specifier.contains(locked_version, prereleases=True):
            issues.append(
                DriftIssue(
                    package=package,
                    source="constraints/security.txt",
                    locked_version=locked_version,
                    expected=str(specifier),
                    reason="lock violates security constraint",
                )
            )
    return issues


def evaluate_drift(
    *,
    lock_path: Path,
    requirements_paths: Sequence[Path],
    pyproject_path: Path,
    constraints_path: Path,
) -> list[DriftIssue]:
    locked = _parse_lock(lock_path)
    constraints = _parse_constraints(constraints_path)

    req_sources: list[tuple[str, Requirement]] = []
    for path in requirements_paths:
        for req in _parse_requirements_file(path):
            req_sources.append((str(path), req))

    pyproject_reqs = _parse_pyproject_dependencies(pyproject_path)
    req_sources.extend((str(pyproject_path), req) for req in pyproject_reqs)

    issues = _check_requirements(req_sources, locked)
    issues.extend(_check_constraints(constraints, locked))

    deduped: dict[str, DriftIssue] = {}
    for issue in issues:
        key = _normalize(issue.package)
        deduped.setdefault(key, issue)
    return list(deduped.values())


def write_report(output_path: Path, issues: Sequence[DriftIssue]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "status": "pass" if not issues else "fail",
        "issue_count": len(issues),
        "issues": [issue.as_dict() for issue in issues],
    }
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")


def _build_arg_parser() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Check drift between declared dependencies and locked requirements"
    )
    parser.add_argument(
        "--lock",
        type=Path,
        default=repo_root / "sbom" / "combined-requirements.txt",
        help="Path to the locked requirements file (default: sbom/combined-requirements.txt)",
    )
    parser.add_argument(
        "--requirements",
        type=Path,
        action="append",
        default=[],
        help="Requirement declaration files to validate (default: requirements.txt)",
    )
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=repo_root / "pyproject.toml",
        help="Path to pyproject.toml (default: repo pyproject)",
    )
    parser.add_argument(
        "--constraints",
        type=Path,
        default=repo_root / "constraints" / "security.txt",
        help="Path to security constraints file (default: constraints/security.txt)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=repo_root / "artifacts" / "security" / "dependency-drift.json",
        help="Destination for JSON report (default: artifacts/security/dependency-drift.json)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    default_declared = Path(__file__).resolve().parents[2] / "sbom" / "combined-requirements.txt"
    requirements = args.requirements or [default_declared]

    issues = evaluate_drift(
        lock_path=args.lock,
        requirements_paths=requirements,
        pyproject_path=args.pyproject,
        constraints_path=args.constraints,
    )
    write_report(args.output, issues)

    if issues:
        for issue in issues:
            print(
                f"[DRIFT] {issue.package} from {issue.source}: "
                f"locked={issue.locked_version or 'missing'} expected {issue.expected} ({issue.reason})"
            )
        return 1

    print("✅ No dependency drift detected")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
