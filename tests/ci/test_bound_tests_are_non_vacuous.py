# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GAP-4 — every artifact-bound test node must actually assert something.

The matrix/report gates bind an invariant to a test by checking a ``def name``
string exists. A gutted test body — the def line kept, the asserts deleted —
would satisfy that binding while proving nothing (it passes vacuously). This
cross-cutting meta-gate closes the hole for the whole apparatus at once: it walks
every inference-integrity artifact, collects every bound ``file::func`` test node,
and AST-verifies the function actually asserts (an ``assert`` statement or a
``pytest.raises`` / ``importorskip`` guard). One gate, no per-file edits.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIRS = ("artifacts/inference", "artifacts/concurrency", "artifacts/time",
                 "artifacts/cache", "artifacts/messaging", "artifacts/state",
                 "artifacts/risk", "artifacts/neuro", "artifacts/runtime_failure_matrix")


def _collect_test_nodes() -> set[str]:
    """Every 'file::func' string under any 'test' key in any inference artifact."""

    nodes: set[str] = set()

    def _walk(obj: object) -> None:
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "test" and isinstance(value, str) and "::" in value:
                    nodes.add(value)
                else:
                    _walk(value)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    for rel in ARTIFACT_DIRS:
        directory = ROOT / rel
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            _walk(json.loads(path.read_text(encoding="utf-8")))
    return nodes


def _function_asserts(path: Path, func: str) -> bool:
    """True iff `func` in `path` contains an assert / raises / importorskip guard."""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    target: ast.FunctionDef | ast.AsyncFunctionDef | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func:
            target = node
            break
    if target is None:
        return False
    for node in ast.walk(target):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Call):
            call = (ast.unparse(node.func) if hasattr(ast, "unparse") else "").lower()
            # Direct assertion forms, or delegation to an ``_assert*`` helper that
            # carries the check (a legitimate, common test factoring).
            if any(t in call for t in ("raises", "importorskip", "assert")) or call.endswith(".fail"):
                return True
    return False


def test_at_least_one_bound_test_node_exists() -> None:
    assert _collect_test_nodes(), "no artifact bound any test node — extractor is broken"


def test_every_bound_test_is_non_vacuous() -> None:
    vacuous: list[str] = []
    for node in sorted(_collect_test_nodes()):
        file_part, _, func = node.partition("::")
        func_name = func.split("::")[-1]  # Class::method -> method
        path = ROOT / file_part
        if not path.is_file():
            vacuous.append(f"{node} (missing file)")
        elif not _function_asserts(path, func_name):
            vacuous.append(f"{node} (no assert / raises)")
    assert not vacuous, "artifact-bound tests that prove nothing: " + "; ".join(vacuous)
