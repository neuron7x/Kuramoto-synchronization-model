# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Lock the wrapper-first laziness contract (ADR-0024 / #945, act TASK 8).

The canonical console-script wrappers re-home only the *entrypoint target* into
``geosync.*`` while the broad scientific/runtime subsystems they front
(``core.kuramoto`` = 35 modules / 21 importers / INV-routing;
``application.runtime`` = 93 modules, BLOCKED_IMPORT_GRAPH) stay packaged and
ledgered. The wrappers MUST import those legacy namespaces lazily — inside
``main()`` only — so that importing the wrapper module has zero import-time side
effects (no FastAPI/TLS/control-platform construction, no scientific imports).

This AST test fails the build if a future edit hoists a ``core.*``/
``application.*`` import to module top level.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

CASES = [
    ("geosync/kuramoto/cli.py", "core"),
    ("geosync/runtime/server.py", "application"),
]


def _top_level_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    tops: set[str] = set()
    for node in tree.body:  # module top level only
        if isinstance(node, ast.Import):
            tops.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            tops.add(node.module.split(".")[0])
    return tops


def _function_imports(source: str, func: str) -> set[str]:
    tree = ast.parse(source)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func:
            for sub in ast.walk(node):
                if isinstance(sub, ast.Import):
                    out.update(a.name.split(".")[0] for a in sub.names)
                elif isinstance(sub, ast.ImportFrom) and sub.module:
                    out.add(sub.module.split(".")[0])
    return out


@pytest.mark.parametrize("rel,banned", CASES)
def test_wrapper_has_no_top_level_legacy_import(rel: str, banned: str) -> None:
    source = (ROOT / rel).read_text(encoding="utf-8")
    assert banned not in _top_level_imports(source), (
        f"{rel} imports '{banned}.*' at module top level — breaks the lazy "
        f"wrapper contract (import-time side effects). Move it inside main()."
    )


def test_kuramoto_wrapper_delegates_lazily() -> None:
    source = (ROOT / "geosync/kuramoto/cli.py").read_text(encoding="utf-8")
    assert "core" in _function_imports(source, "main"), (
        "geosync.kuramoto.cli.main must lazily delegate to core.kuramoto.cli"
    )


def test_server_wrapper_delegates_lazily() -> None:
    source = (ROOT / "geosync/runtime/server.py").read_text(encoding="utf-8")
    assert "application" in _function_imports(source, "main"), (
        "geosync.runtime.server.main must lazily delegate to application.runtime.server"
    )
