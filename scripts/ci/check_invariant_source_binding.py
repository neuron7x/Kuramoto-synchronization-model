#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Invariant source/test binding gate — fail-closed typed binding over physics.

The physics invariant registry (``.claude/physics/INVARIANTS.yaml``) declares,
per invariant, a ``source:`` (the module — optionally ``file::symbol``) and a
``tests:`` path (the executable witness). Those bindings are the typed link
between a stated physical property and the code that realizes/checks it. Nothing
previously verified them fail-closed in CI: ``physics_evidence_matrix.py`` only
renders a ✓/✗ matrix (file-level, no ``::symbol`` check) and runs in no workflow;
``validate_tests.py`` self-check explicitly *delegates* path integrity to that
generator.

This gate closes the loop. For every invariant that declares a ``source:`` or
``tests:`` path it asserts:

* the file exists, and
* if the token is ``file::symbol``, the symbol is actually defined in that file
  (``def`` / ``async def`` / ``class`` / module-level assignment).

It does **not** touch, run, or modify any physics — it is a read-only typed-
binding integrity check (Rule Zero safe: no solver, no kernel, no claim).

Exit codes::
    0  — every declared source/tests binding resolves (file + symbol)
    1  — at least one binding is broken (file or symbol missing)
    2  — the invariant registry is absent
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / ".claude" / "physics" / "INVARIANTS.yaml"

_ID = re.compile(r"^\s+id:\s+(INV-[A-Z0-9][A-Z0-9-]*)\s*$")
_FIELD = re.compile(r"^\s+(source|tests):\s+(.+?)\s*$")


def _parse_registry(text: str) -> list[dict[str, str]]:
    """Lightweight block parser: collect id + source + tests per invariant."""
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        m = _ID.match(line)
        if m:
            rows.append({"id": m.group(1)})
            continue
        f = _FIELD.match(line)
        if f and rows:
            rows[-1][f.group(1)] = f.group(2).strip().strip("\"'")
    return rows


def _symbol_defined(path: Path, symbol: str) -> bool:
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return bool(
            re.search(rf"^\s*(?:async\s+def|def|class)\s+{re.escape(symbol)}\b", text, re.M)
        )
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                return True
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == symbol:
                    return True
    return bool(re.search(rf"^\s*{re.escape(symbol)}\s*[:=]", text, re.M))


def _tokens(value: str) -> list[str]:
    return [t for t in re.split(r"[,\s]+", value) if "/" in t]


def check() -> tuple[list[dict[str, str]], int, int]:
    text = REGISTRY.read_text(encoding="utf-8")
    rows = _parse_registry(text)
    broken: list[dict[str, str]] = []
    checked = 0
    for row in rows:
        for field in ("source", "tests"):
            value = row.get(field)
            if not value:
                continue
            for token in _tokens(value):
                checked += 1
                rel, _, symbol = token.partition("::")
                path = ROOT / rel
                if not path.is_file():
                    broken.append(
                        {"id": row["id"], "field": field, "token": token, "reason": "FILE_MISSING"}
                    )
                elif symbol and not _symbol_defined(path, symbol):
                    broken.append(
                        {
                            "id": row["id"],
                            "field": field,
                            "token": token,
                            "reason": "SYMBOL_MISSING",
                        }
                    )
    return broken, len(rows), checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", type=Path, default=ROOT / "artifacts" / "invariant_source_binding.json"
    )
    args = parser.parse_args(argv)

    if not REGISTRY.is_file():
        print(f"ERROR: {REGISTRY.relative_to(ROOT)} missing", file=sys.stderr)
        return 2

    broken, n_inv, n_checked = check()
    verdict = "PASS" if not broken else "FAIL"
    report = {
        "verdict": verdict,
        "invariants": n_inv,
        "bindings_checked": n_checked,
        "broken": broken,
    }
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for b in broken:
        print(
            f"BROKEN BINDING: {b['id']} {b['field']} -> {b['token']} ({b['reason']})",
            file=sys.stderr,
        )
    print(
        f"INVARIANT SOURCE BINDING: {verdict} — {n_checked} bindings checked across "
        f"{n_inv} invariants, {len(broken)} broken"
    )
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
