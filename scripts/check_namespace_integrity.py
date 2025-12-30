"""Architecture guardrail: enforce canonical TradePulse namespace layout.

Rules enforced:
- Canonical runtime namespace lives under ``src/tradepulse`` and every package
  there must declare ``__CANONICAL__ = True``.
- Shim namespaces (e.g. top-level ``tradepulse``) must declare
  ``__CANONICAL__ = False``.
- No other module outside the canonical root may claim to be canonical.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_ROOT = REPO_ROOT / "src" / "tradepulse"
SHIM_PATHS = {REPO_ROOT / "tradepulse" / "__init__.py"}


@dataclass(frozen=True)
class Violation:
    path: Path
    reason: str


def _iter_canonical_inits(root: Path) -> Iterable[Path]:
    yield from (root / "src" / "tradepulse").rglob("__init__.py")


def _has_flag(path: Path, expected: bool) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, SyntaxError):
        return False
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if any(isinstance(target, ast.Name) and target.id == "__CANONICAL__" for target in node.targets):
                if isinstance(node.value, ast.Constant):
                    return bool(node.value.value) is expected
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "__CANONICAL__":
                if isinstance(node.value, ast.Constant):
                    return bool(node.value.value) is expected
    return False


def check_namespace_integrity(repo_root: Path = REPO_ROOT) -> list[Violation]:
    violations: list[Violation] = []

    canonical_root = repo_root / CANONICAL_ROOT.relative_to(REPO_ROOT)
    if not canonical_root.exists():
        violations.append(Violation(canonical_root, "missing canonical namespace root"))
        return violations

    for init_file in _iter_canonical_inits(repo_root):
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
        if path in SHIM_PATHS or path.is_relative_to(canonical_root):
            continue
        if _has_flag(path, True):
            violations.append(
                Violation(
                    path.relative_to(repo_root),
                    "only src/tradepulse packages may be canonical",
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
