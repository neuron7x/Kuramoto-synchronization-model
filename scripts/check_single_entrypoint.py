# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Guardrail: enforce single canonical entrypoint per major subsystem.

Canonicals:
- control CLI: ``geosync/cli/geosync_cli.py``
- API server: ``cortex_service/app/__main__.py``
- calibration tooling: ``scripts/calibrate_controllers.py``

Any additional entrypoint-like modules must be explicitly allowlisted as legacy
to avoid proliferating ways to run the system.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CANONICAL_ENTRYPOINTS = {
    "control_cli": Path("geosync/cli/geosync_cli.py"),
    "api_server": Path("cortex_service/app/__main__.py"),
    "calibration": Path("scripts/calibrate_controllers.py"),
}

LEGACY_ENTRYPOINTS = {
    Path("geosync/cli/amm_cli.py"),
    Path("scripts/__main__.py"),
    Path("tacl/__main__.py"),
    Path("tools/vendor/fpma/__main__.py"),
    Path("tools/synthetic_l2/__main__.py"),
    Path("src/geosync/sdk/mlsdm/__main__.py"),
}

# The CLI package was re-homed from the repo-root ``cli/`` into the canonical
# ``geosync.cli`` namespace (#1158, ADR-0024); discover its modules there.
ENTRYPOINT_DIRS = [Path("geosync/cli")]


@dataclass(frozen=True)
class Violation:
    path: Path
    reason: str


_EXCLUDED_DIRS = frozenset({".venv", "venv", ".tox", "node_modules", "__pycache__"})


def _discover_entrypoints(root: Path) -> set[Path]:
    discovered: set[Path] = set()
    for directory in ENTRYPOINT_DIRS:
        target = root / directory
        if target.is_dir():
            for candidate in target.glob("*.py"):
                # A package initializer is never a CLI entrypoint; skip it so a
                # plain `__init__.py` (package marker) is not mis-flagged.
                if candidate.name == "__init__.py":
                    continue
                discovered.add(candidate.resolve())
    for main_file in root.rglob("__main__.py"):
        # Skip files inside excluded directories (e.g. .venv third-party packages)
        if any(part in _EXCLUDED_DIRS for part in main_file.parts):
            continue
        discovered.add(main_file.resolve())
    return discovered


def check_single_entrypoint(repo_root: Path = REPO_ROOT) -> list[Violation]:
    violations: list[Violation] = []

    for name, rel_path in CANONICAL_ENTRYPOINTS.items():
        abs_path = repo_root / rel_path
        if not abs_path.exists():
            violations.append(Violation(rel_path, f"canonical {name} entrypoint missing"))
    if violations:
        return violations

    canonical_paths = {(repo_root / p).resolve() for p in CANONICAL_ENTRYPOINTS.values()}
    legacy_paths = {
        (repo_root / p).resolve() for p in LEGACY_ENTRYPOINTS if (repo_root / p).exists()
    }
    for extra in _discover_entrypoints(repo_root):
        if extra in canonical_paths or extra in legacy_paths:
            continue
        violations.append(
            Violation(
                extra.relative_to(repo_root),
                "non-canonical entrypoint detected (declare canonical or mark as legacy)",
            )
        )

    return violations


def main() -> int:
    violations = check_single_entrypoint()
    if violations:
        print("❌ Entry point validation failed:")
        for violation in violations:
            print(f" - {violation.path}: {violation.reason}")
        return 1
    print("✅ Entry points are canonicalised.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
