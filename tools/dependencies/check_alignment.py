# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate that dependency declarations stay aligned across manifests."""

from __future__ import annotations

import argparse
import sys
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def _normalize_requirement(
    requirement: Requirement,
) -> tuple[str, tuple[str, ...], str | None]:
    """Return a comparable key for a requirement (name + extras + marker)."""

    marker = str(requirement.marker) if requirement.marker is not None else None
    return (
        canonicalize_name(requirement.name),
        tuple(sorted(requirement.extras)),
        marker,
    )


def _load_requirement_lines(path: Path) -> Iterable[str]:
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-r") or line.startswith("--"):
            raise ValueError(
                f"Unsupported directive '{line}' found in {path}. "
                "Dependency alignment currently only supports plain requirement entries."
            )
        yield line


def _load_requirements(
    path: Path,
) -> Mapping[tuple[str, tuple[str, ...], str | None], Requirement]:
    requirements: dict[tuple[str, tuple[str, ...], str | None], Requirement] = {}
    for line in _load_requirement_lines(path):
        req = Requirement(line)
        requirements[_normalize_requirement(req)] = req
    return requirements


def _load_pyproject_dependencies(
    path: Path,
) -> Mapping[tuple[str, tuple[str, ...], str | None], Requirement]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    try:
        dependency_entries = document["project"]["dependencies"]
    except KeyError as exc:  # pragma: no cover - config error path
        raise KeyError("pyproject.toml is missing [project].dependencies") from exc

    requirements: dict[tuple[str, tuple[str, ...], str | None], Requirement] = {}
    for entry in dependency_entries:
        req = Requirement(entry)
        requirements[_normalize_requirement(req)] = req
    return requirements


def _format_requirement(requirement: Requirement) -> str:
    extras = f"[{','.join(sorted(requirement.extras))}]" if requirement.extras else ""
    spec = str(requirement.specifier) if requirement.specifier else ""
    marker = f"; {requirement.marker}" if requirement.marker else ""
    return f"{requirement.name}{extras}{spec}{marker}"


def _compare(
    base: Mapping[tuple[str, tuple[str, ...], str | None], Requirement],
    reference: Mapping[tuple[str, tuple[str, ...], str | None], Requirement],
) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    divergent: list[str] = []

    for key, requirement in sorted(base.items(), key=lambda item: item[0]):
        if key not in reference:
            missing.append(_format_requirement(requirement))
            continue

        ref_requirement = reference[key]
        if requirement.specifier != ref_requirement.specifier:
            divergent.append(
                f"{_format_requirement(requirement)} (pyproject declares {_format_requirement(ref_requirement)})"
            )

    return missing, divergent


def _find_unexpected(
    base: Mapping[tuple[str, tuple[str, ...], str | None], Requirement],
    reference: Mapping[tuple[str, tuple[str, ...], str | None], Requirement],
) -> list[str]:
    unexpected: list[str] = []
    for key, requirement in sorted(reference.items(), key=lambda item: item[0]):
        if key not in base:
            unexpected.append(_format_requirement(requirement))
    return unexpected


def check_alignment(requirements_file: Path, pyproject_file: Path) -> int:
    base_requirements = _load_requirements(requirements_file)
    pyproject_requirements = _load_pyproject_dependencies(pyproject_file)

    missing, divergent = _compare(base_requirements, pyproject_requirements)
    unexpected = _find_unexpected(base_requirements, pyproject_requirements)

    issues: dict[str, list[str]] = defaultdict(list)
    if missing:
        issues["Missing in pyproject"].extend(missing)
    if divergent:
        issues["Specifier mismatch"].extend(divergent)
    if unexpected:
        issues["Only in pyproject"].extend(unexpected)

    if not issues:
        print("✅ Dependency declarations in requirements.txt and pyproject.toml are aligned.")
        return 0

    print("❌ Dependency alignment issues detected:")
    for title, entries in issues.items():
        print(f"\n{title}:")
        for entry in entries:
            print(f"  - {entry}")
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ensure requirements.txt stays consistent with pyproject.toml dependencies.",
    )
    parser.add_argument(
        "--requirements-file",
        type=Path,
        default=Path("requirements.txt"),
        help="Path to the source requirements file (defaults to requirements.txt).",
    )
    parser.add_argument(
        "--pyproject-file",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to the pyproject.toml file (defaults to pyproject.toml in the repo root).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return check_alignment(args.requirements_file, args.pyproject_file)
    except (
        FileNotFoundError,
        KeyError,
        ValueError,
    ) as exc:  # pragma: no cover - CLI surface
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
