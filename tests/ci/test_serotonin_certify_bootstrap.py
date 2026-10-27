# SPDX-License-Identifier: MIT
"""Execution controls for the side-effect-only certification import preloads.

The real script's two import guards are extracted from its AST and executed
with an instrumented importlib, keeping its heavy data/science imports out of
the test process while testing the actual import and fail-open-on-absence logic.
Unexpected import-time failures must remain visible to the caller.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "serotonin_certify.py"
PRELOADS = ("sitecustomize", "core.neuro.serotonin.observability")


def _preload_code():
    """Compile the actual importlib guards, not a reimplemented twin."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
    guards = [
        node
        for node in tree.body
        if isinstance(node, ast.Try)
        and any(
            isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "importlib"
            and call.func.attr == "import_module"
            for call in ast.walk(node)
        )
    ]
    assert len(guards) == 2, "both startup preloads must remain explicit"
    return compile(ast.fix_missing_locations(ast.Module(body=guards, type_ignores=[])), str(SCRIPT), "exec")


def test_optional_preloads_are_executed_in_order() -> None:
    observed: list[str] = []

    def import_module(name: str) -> object:
        observed.append(name)
        return object()

    exec(_preload_code(), {"importlib": SimpleNamespace(import_module=import_module)})
    assert observed == list(PRELOADS)


def test_missing_optional_imports_do_not_block_following_preloads() -> None:
    observed: list[str] = []

    def import_module(name: str) -> None:
        observed.append(name)
        raise ImportError(name)

    exec(_preload_code(), {"importlib": SimpleNamespace(import_module=import_module)})
    assert observed == list(PRELOADS)


def test_unexpected_import_failure_is_not_swallowed() -> None:
    observed: list[str] = []

    def import_module(name: str) -> None:
        observed.append(name)
        raise RuntimeError("actual startup defect")

    with pytest.raises(RuntimeError, match="actual startup defect"):
        exec(_preload_code(), {"importlib": SimpleNamespace(import_module=import_module)})
    assert observed == [PRELOADS[0]]
