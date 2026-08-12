# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Namespace policy enforcement for canonical GeoSync imports.

Rules
-----
- Canonical public namespace: ``geosync.*``
- Legacy namespace ``src.*`` is internal-only and should not be imported from
  production code outside a curated legacy allowlist.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

CANONICAL_NAMESPACE = "geosync"
LEGACY_NAMESPACE = "src"

# Temporary allowlist for legacy modules that still depend on the ``src`` shim.
# This list should only shrink over time.
LEGACY_ALLOWLIST = {
    Path("application/api/authorization.py"),
    Path("application/api/security.py"),
    Path("application/api/service.py"),
    Path("application/api/system_access.py"),
    Path("application/configuration/secure_store.py"),
    Path("application/secrets/hashicorp.py"),
    Path("application/secrets/manager.py"),
    Path("application/secrets/vault.py"),
    Path("application/security/rbac.py"),
    Path("application/settings.py"),
    Path("application/system.py"),
    Path("src/admin/remote_control.py"),
    Path("src/data/__init__.py"),
    Path("src/risk/risk_manager.py"),
    Path("src/system/action_control.py"),
    Path("src/system/integration.py"),
    Path("src/system/module_orchestrator.py"),
    Path("tools/security/dast_probe.py"),
    Path("geosync/risk/__init__.py"),
}

EXCLUDED_DIR_NAMES = {
    # Tests are intentionally excluded; the policy currently targets production modules only.
    "tests",
    ".git",
    ".venv",
    "venv",
    ".tox",
    ".mypy_cache",
    ".ruff_cache",
}
POLICY_NOTE = (
    f"Canonical namespace is '{CANONICAL_NAMESPACE}.*'. "
    f"Legacy '{LEGACY_NAMESPACE}.*' imports are restricted to the curated allowlist."
)
_DEFAULT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_ALLOWLIST_RESOLVED: set[Path] | None = None


@dataclass(frozen=True)
class Violation:
    path: Path
    lineno: int
    module: str


def _iter_python_files(base_dir: Path) -> Iterable[Path]:
    for path in base_dir.rglob("*.py"):
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        yield path


def _iter_src_imports(tree: ast.AST) -> Iterable[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name == LEGACY_NAMESPACE or name.startswith(f"{LEGACY_NAMESPACE}."):
                    yield node.lineno, name
        elif isinstance(node, ast.ImportFrom):
            module = node.module
            if module and (module == LEGACY_NAMESPACE or module.startswith(f"{LEGACY_NAMESPACE}.")):
                yield node.lineno, module


def _resolve_allowlist(root: Path, allowlist: set[Path] | None) -> set[Path]:
    if allowlist is None:
        if root == _DEFAULT_ROOT:
            global _DEFAULT_ALLOWLIST_RESOLVED
            if _DEFAULT_ALLOWLIST_RESOLVED is None:
                _DEFAULT_ALLOWLIST_RESOLVED = {(root / p).resolve() for p in LEGACY_ALLOWLIST}
            return _DEFAULT_ALLOWLIST_RESOLVED
        entries = LEGACY_ALLOWLIST
    else:
        entries = allowlist
    return {(root / p).resolve() for p in entries}


def find_namespace_violations(
    base_dir: Path, allowlist: set[Path] | None = None
) -> list[Violation]:
    root = base_dir.resolve()
    violations: list[Violation] = []
    normalized_allowlist = _resolve_allowlist(root, allowlist)

    for path in _iter_python_files(root):
        if path in normalized_allowlist:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except SyntaxError as exc:
            print(f"⚠️ Skipping {path}: {exc}", file=sys.stderr)
            continue
        for lineno, module in _iter_src_imports(tree):
            violations.append(Violation(path.relative_to(root), lineno, module))
    return violations


def main() -> int:
    repo_root = _DEFAULT_ROOT
    violations = find_namespace_violations(repo_root)
    if violations:
        print("❌ Namespace policy violations detected:")
        for violation in violations:
            print(f" - {violation.path}:{violation.lineno} imports {violation.module}")
        print(POLICY_NOTE)
        return 1
    print("✅ Namespace policy check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
