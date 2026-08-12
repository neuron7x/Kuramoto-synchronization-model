#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Emit deterministic metrics for TEST_WITNESS_MAP.json.

The score is governance data, not scientific evidence. It tells reviewers how
much of the current migration surface is mapped to registered invariant
witnesses and how much is explicitly quarantined as implementation-only tests.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MAP_PATH = ROOT / ".claude" / "physics" / "TEST_WITNESS_MAP.json"


def _test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def main() -> None:
    payload = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    files: dict[str, Any] = payload["files"]
    rows: list[dict[str, Any]] = []
    totals = {
        "files": 0,
        "test_functions": 0,
        "witness_functions": 0,
        "non_physics_functions": 0,
        "unmapped_functions": 0,
    }

    for relpath, spec in sorted(files.items()):
        funcs = _test_functions(ROOT / relpath)
        witnesses = set(spec.get("witnesses", {}))
        if spec.get("non_physics_file", False):
            non_physics = set(funcs)
        else:
            non_physics = set(spec.get("non_physics", []))
        mapped = witnesses | non_physics
        unmapped = sorted(funcs - mapped)
        row = {
            "file": relpath,
            "test_functions": len(funcs),
            "witness_functions": len(witnesses),
            "non_physics_functions": len(non_physics),
            "unmapped_functions": len(unmapped),
            "coverage": 1.0 - (len(unmapped) / len(funcs) if funcs else 0.0),
            "unmapped": unmapped,
        }
        rows.append(row)
        totals["files"] += 1
        totals["test_functions"] += len(funcs)
        totals["witness_functions"] += len(witnesses)
        totals["non_physics_functions"] += len(non_physics)
        totals["unmapped_functions"] += len(unmapped)

    totals["coverage"] = 1.0 - (
        totals["unmapped_functions"] / totals["test_functions"]
        if totals["test_functions"] else 0.0
    )
    result = {
        "schema_version": "1.0.0",
        "map": str(MAP_PATH.relative_to(ROOT)),
        "totals": totals,
        "files": rows,
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
