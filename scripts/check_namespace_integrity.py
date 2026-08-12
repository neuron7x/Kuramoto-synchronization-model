# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Architecture guardrail: enforce canonical GeoSync namespace layout.

Rules enforced:
- Canonical runtime namespace lives under ``src/geosync`` and every package
  there must declare ``__CANONICAL__ = True``.
- Shim namespaces (e.g. top-level ``geosync``) must declare
  ``__CANONICAL__ = False``.
- No other module outside the canonical root may claim to be canonical.

Deprecated-shim exemption
-------------------------
A package physically located under ``src/geosync`` is normally canonical. The
exception is a *deprecated re-export shim*: a package whose canonical
implementation was moved to a DIFFERENT package (e.g. ``src/geosync/risk`` is a
shim whose real implementation now lives in top-level ``geosync.risk``). Such a
shim is NOT canonical — forcing ``__CANONICAL__ = True`` on it would be a false
claim that the module is the source of truth when it merely re-exports another
package. These modules instead declare ``__DEPRECATED_SHIM__ = True`` and are
exempt from the ``__CANONICAL__ = True`` requirement.

The exemption is opt-in and explicit: it only skips modules that self-declare
``__DEPRECATED_SHIM__ = True``. A genuinely-canonical package that merely forgot
its ``__CANONICAL__`` flag carries no such marker and is still flagged, so the
exemption cannot mask a real missing-canonical violation.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = REPO_ROOT / "src" / "geosync"
SHIM_PATHS = {REPO_ROOT / "geosync" / "__init__.py"}

# Directories to skip during the broad ``__CANONICAL__`` flag scan so that
# non-source trees are not inadvertently flagged. Two classes are excluded:
#   * named build/vendor dirs (``venv``, ``node_modules``, ``__pycache__``);
#   * ANY hidden directory (a path part starting with ``.``) — this covers
#     ``.venv``, ``.tox``, ``.git``, ``.mypy_cache`` and, critically,
#     ``.claude/worktrees/agent-*`` where ephemeral agent worktrees carry their
#     own ``src/geosync`` tree. Canonical runtime source never lives in a hidden
#     directory, so scanning them only produces false violations on dev machines
#     (and is invisible on CI's clean checkout, masking the bug). See
#     tests/test_architecture_guards.py::test_namespace_integrity_ignores_hidden_dirs.
_EXCLUDED_DIRS = frozenset({"venv", "node_modules", "__pycache__", "build", "dist"})


def _is_scannable(path: Path, repo_root: Path) -> bool:
    """True iff ``path`` is inside a real source tree (not hidden/vendor)."""
    rel_parts = path.relative_to(repo_root).parts
    if any(part.startswith(".") for part in rel_parts):
        return False
    return not any(part in _EXCLUDED_DIRS for part in rel_parts)


@dataclass(frozen=True)
class Violation:
    path: Path
    reason: str


def _iter_canonical_inits(root: Path) -> Iterable[Path]:
    yield from (root / "src" / "geosync").rglob("__init__.py")


def _module_flag(path: Path, name: str) -> bool | None:
    """Return the module-level boolean constant ``name``, or ``None`` if absent.

    Only top-level ``name = <constant>`` / ``name: <type> = <constant>``
    assignments are considered (module-scope flags, not nested ones).
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, SyntaxError, UnicodeDecodeError):
        return None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
                if isinstance(node.value, ast.Constant):
                    return bool(node.value.value)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name:
                if isinstance(node.value, ast.Constant):
                    return bool(node.value.value)
    return None


def _has_flag(path: Path, expected: bool) -> bool:
    return _module_flag(path, "__CANONICAL__") is expected


def _is_deprecated_shim(path: Path) -> bool:
    """A module that explicitly self-declares ``__DEPRECATED_SHIM__ = True``.

    Such modules live physically under ``src/geosync`` but only re-export a
    canonical implementation that lives in a different package, so they are
    exempt from the ``__CANONICAL__ = True`` requirement (see module docstring).
    """
    return _module_flag(path, "__DEPRECATED_SHIM__") is True


def check_namespace_integrity(repo_root: Path = REPO_ROOT) -> list[Violation]:
    violations: list[Violation] = []

    canonical_root = repo_root / CANONICAL_ROOT.relative_to(REPO_ROOT)
    if not canonical_root.exists():
        violations.append(Violation(canonical_root, "missing canonical namespace root"))
        return violations

    for init_file in _iter_canonical_inits(repo_root):
        # Deprecated re-export shims (explicitly self-declared) are NOT canonical
        # — their real implementation lives in another package. Marking them
        # __CANONICAL__ = True would be a false claim, so they are exempt.
        if _is_deprecated_shim(init_file):
            continue
        if not _has_flag(init_file, True):
            violations.append(
                Violation(
                    init_file.relative_to(repo_root),
                    "canonical package missing __CANONICAL__ = True",
                )
            )

    for shim in SHIM_PATHS:
        if shim.exists() and not _has_flag(shim, False):
            violations.append(
                Violation(
                    shim.relative_to(repo_root),
                    "shim package must declare __CANONICAL__ = False",
                )
            )

    for path in repo_root.rglob("*.py"):
        # Skip hidden/vendor trees (.venv, .git, .claude/worktrees, build, …) –
        # they must not declare __CANONICAL__ = True and scanning them only
        # yields false violations from ephemeral worktrees that carry their own
        # src/geosync tree (see _is_scannable).
        if not _is_scannable(path, repo_root):
            continue
        if path in SHIM_PATHS or path.is_relative_to(canonical_root):
            continue
        if _has_flag(path, True):
            violations.append(
                Violation(
                    path.relative_to(repo_root),
                    "only src/geosync packages may be canonical",
                )
            )

    return violations


def main() -> int:
    violations = check_namespace_integrity()
    if violations:
        print("❌ Namespace integrity violations detected:")
        for violation in violations:
            print(f" - {violation.path}: {violation.reason}")
        return 1
    print("✅ Namespace integrity verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
