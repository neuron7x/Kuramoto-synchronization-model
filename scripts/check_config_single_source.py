# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Guardrail: ensure a single canonical config source per subsystem.

We currently bless the ``config/`` directory as canonical. Known subsystems and
their canonical files:
- mlsdm runtime: ``config/default_config.yaml``
- dopamine controller: ``config/dopamine.yaml``
- thermo controller: ``config/thermo_config.yaml``

Any duplicate config with the same filename must be explicitly allowlisted as
legacy to avoid silent precedence changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_CONFIGS = {
    "mlsdm": Path("config/default_config.yaml"),
    "dopamine": Path("config/dopamine.yaml"),
    "thermo": Path("config/thermo_config.yaml"),
}

LEGACY_DUPLICATE_ALLOWLIST = {
    "dopamine": {Path("configs/dopamine.yaml")},
}

ALLOWED_CONFIG_ROOTS = {
    Path("config"),
    Path("configs"),
    Path("conf"),
}


@dataclass(frozen=True)
class Violation:
    path: Path
    reason: str


def _iter_top_config_dirs(root: Path) -> Iterable[Path]:
    for child in root.iterdir():
        if child.is_dir() and "config" in child.name.lower():
            yield child


def check_config_single_source(repo_root: Path = REPO_ROOT) -> list[Violation]:
    violations: list[Violation] = []

    for key, rel_path in CANONICAL_CONFIGS.items():
        abs_path = repo_root / rel_path
        if not abs_path.exists():
            violations.append(Violation(rel_path, f"canonical config for {key} missing"))

    for dir_path in _iter_top_config_dirs(repo_root):
        if dir_path.relative_to(repo_root) not in ALLOWED_CONFIG_ROOTS:
            violations.append(
                Violation(
                    dir_path.relative_to(repo_root),
                    "unexpected config root detected; declare canonical or legacy",
                )
            )

    for key, rel_path in CANONICAL_CONFIGS.items():
        canonical_abs = (repo_root / rel_path).resolve()
        allowlist = {(repo_root / p).resolve() for p in LEGACY_DUPLICATE_ALLOWLIST.get(key, set())}
        for duplicate in repo_root.rglob(rel_path.name):
            duplicate_resolved = duplicate.resolve()
            if duplicate_resolved == canonical_abs:
                continue
            if duplicate_resolved in allowlist:
                continue
            violations.append(
                Violation(
                    duplicate.relative_to(repo_root),
                    f"duplicate config for {key} not marked legacy or removed",
                )
            )

    return violations


def main() -> int:
    violations = check_config_single_source()
    if violations:
        print("❌ Config single-source validation failed:")
        for violation in violations:
            print(f" - {violation.path}: {violation.reason}")
        print("Canonical roots: config/")
        return 1
    print("✅ Config single-source policy enforced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
