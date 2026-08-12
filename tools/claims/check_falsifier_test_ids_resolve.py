#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed gate: every claim's ``falsifier.test_id`` resolves to a real test.

A claim in ``docs/CLAIMS.yaml`` may cite a falsifier as a pytest node id
(``path/to/test_x.py::test_name`` or ``...::TestClass::test_method``). ADR 0021
requires anchored claims to carry a falsifier — but nothing verified the cited
node still EXISTS. A renamed or deleted test leaves the claim asserting its tier
behind a falsifier pointer that points at nothing: silent falsifier rot.

This checker parses each cited node id and confirms (statically, via AST — no
pytest collection) that the file exists and defines the named test (or, for a
``Class::method`` id, that the class defines the method). Parametrised suffixes
(``[case]``) are stripped to the base name. It makes no scientific claim; it
refuses a claim whose falsifier carrier has rotted.

Exit codes::

    0  every falsifier.test_id resolves
    1  one or more cited test nodes do not resolve
    2  malformed invocation / unreadable CLAIMS.yaml
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CLAIMS = _ROOT / "docs" / "CLAIMS.yaml"


def _claims(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, dict):
        claims = doc.get("claims", [])
    else:
        claims = doc
    return [c for c in claims if isinstance(c, dict)]


def _falsifier_node_ids(claims: list[dict[str, Any]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for c in claims:
        fals = c.get("falsifier")
        if isinstance(fals, dict) and fals.get("test_id"):
            out.append((str(c.get("id", "<no-id>")), str(fals["test_id"])))
    return out


def _defines(tree: ast.Module, name: str) -> bool:
    """True if a top-level function ``name`` is defined in the module."""
    return any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name for n in tree.body
    )


def _class_defines(tree: ast.Module, cls: str, method: str) -> bool:
    for n in tree.body:
        if isinstance(n, ast.ClassDef) and n.name == cls:
            return any(
                isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and m.name == method
                for m in n.body
            )
    return False


def resolve_node_id(node_id: str, root: Path) -> str | None:
    """Return an error string if the node id does not resolve, else None."""
    path_part, sep, rest = node_id.partition("::")
    if not sep:
        return f"{node_id}: not a pytest node id (no '::')"
    target = (root / path_part).resolve()
    if not target.is_file():
        return f"{node_id}: file does not exist ({path_part})"
    parts = [p.split("[", 1)[0] for p in rest.split("::")]  # strip parametrise suffix
    try:
        tree = ast.parse(target.read_text(encoding="utf-8"), filename=str(target))
    except (SyntaxError, OSError) as exc:
        return f"{node_id}: cannot parse {path_part}: {exc}"
    if len(parts) == 1:
        if not _defines(tree, parts[0]):
            return f"{node_id}: test function '{parts[0]}' not defined in {path_part}"
    else:
        cls, method = parts[0], parts[-1]
        if not _class_defines(tree, cls, method):
            return f"{node_id}: '{cls}::{method}' not defined in {path_part}"
    return None


def check(claims_path: Path, root: Path = _ROOT) -> list[str]:
    doc = yaml.safe_load(claims_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for claim_id, node_id in _falsifier_node_ids(_claims(doc)):
        err = resolve_node_id(node_id, root)
        if err:
            errors.append(f"[{claim_id}] {err}")
    return errors


def main(argv: Sequence[str] | None = None, *, root: Path = _ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", default=str(_DEFAULT_CLAIMS))
    args = parser.parse_args(argv)
    try:
        errors = check(Path(args.claims), root)
    except (OSError, yaml.YAMLError) as exc:
        print(f"cannot read claims: {exc}", file=sys.stderr)
        return 2
    if errors:
        for e in errors:
            print(f"FALSIFIER ROT: {e}", file=sys.stderr)
        print(f"{len(errors)} claim falsifier(s) do not resolve.", file=sys.stderr)
        return 1
    print("all claim falsifier.test_id node ids resolve to real tests.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
