# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Enforce canonical serotonin controller namespace and shim purity."""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_MODULE = "geosync.core.neuro.serotonin.serotonin_controller"
NON_CANONICAL_MODULE = "core.neuro.serotonin.serotonin_controller"
CANONICAL_PATH = REPO_ROOT / "src/geosync/core/neuro/serotonin/serotonin_controller.py"
NON_CANONICAL_PATH = REPO_ROOT / "core/neuro/serotonin/serotonin_controller.py"
ALLOWED_ASSIGNMENTS = {"__CANONICAL__", "__all__", "_generate_config_table"}
EXCLUDED_DIRS = {
    "tests",
    ".git",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
}


@dataclass(frozen=True)
class ImportViolation:
    path: Path
    lineno: int
    module: str


def _iter_python_files(base_dir: Path) -> Iterable[Path]:
    for path in base_dir.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _has_disallowed_logic(tree: ast.AST) -> bool:
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return True
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = []
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        targets.append(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                targets.append(node.target.id)
            if any(name not in ALLOWED_ASSIGNMENTS for name in targets):
                return True
    return False


def _assert_flag(tree: ast.AST, expected: bool) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = None
            if isinstance(node, ast.Assign):
                if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
                    continue
                target = node.targets[0].id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                target = node.target.id
            if target == "__CANONICAL__":
                try:
                    value = ast.literal_eval(node.value)  # type: ignore[arg-type]
                except (ValueError, SyntaxError, TypeError):
                    return False
                return value is expected
    return False


def find_non_canonical_imports(base_dir: Path) -> list[ImportViolation]:
    violations: list[ImportViolation] = []
    for path in _iter_python_files(base_dir):
        try:
            tree = _parse(path)
        except (SyntaxError, FileNotFoundError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name == NON_CANONICAL_MODULE or name.startswith(f"{NON_CANONICAL_MODULE}."):
                        violations.append(ImportViolation(path, node.lineno, name))
            elif isinstance(node, ast.ImportFrom):
                module = node.module
                if module and (
                    module == NON_CANONICAL_MODULE or module.startswith(f"{NON_CANONICAL_MODULE}.")
                ):
                    violations.append(ImportViolation(path, node.lineno, module))
    return violations


def run_checks(base_dir: Path = REPO_ROOT) -> list[str]:
    errors: list[str] = []

    if not CANONICAL_PATH.exists():
        errors.append(f"Canonical file missing: {CANONICAL_PATH}")
    else:
        canon_tree = _parse(CANONICAL_PATH)
        if not _assert_flag(canon_tree, expected=True):
            errors.append(f"{CANONICAL_PATH} must define __CANONICAL__ = True")

    if not NON_CANONICAL_PATH.exists():
        errors.append(f"Non-canonical shim missing: {NON_CANONICAL_PATH}")
    else:
        shim_tree = _parse(NON_CANONICAL_PATH)
        if _has_disallowed_logic(shim_tree):
            errors.append(f"{NON_CANONICAL_PATH} must remain a pure re-export shim")
        if not _assert_flag(shim_tree, expected=False):
            errors.append(f"{NON_CANONICAL_PATH} must define __CANONICAL__ = False")

    for violation in find_non_canonical_imports(base_dir):
        if violation.path.resolve() == NON_CANONICAL_PATH.resolve():
            continue
        errors.append(
            f"{violation.path.relative_to(base_dir)}:{violation.lineno} "
            f"imports non-canonical module {violation.module}"
        )
    return errors


def main() -> int:
    errors = run_checks()
    if errors:
        print("❌ Serotonin namespace enforcement failed:")
        for err in errors:
            print(f" - {err}")
        print(f"Canonical module: {CANONICAL_MODULE} (shim: {NON_CANONICAL_MODULE})")
        return 1
    print("✅ Serotonin namespace enforcement passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
