# SPDX-License-Identifier: MIT
"""Execute the real AST for optional dependency checks, without import side effects."""

from __future__ import annotations

import ast
import io
import sys
from pathlib import Path
from types import CodeType, ModuleType, SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "scripts" / "commands" / "build_core.py"
DOPAMINE = ROOT / "tools" / "validate_dopamine_config.py"


class MissingBuildBackend(RuntimeError):
    """Synthetic command error for the production build dependency guard."""


def _guard(path: Path, *, function: str | None, dependency: str) -> CodeType:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    body = tree.body
    if function is not None:
        selected = [
            node
            for node in body
            if isinstance(node, ast.FunctionDef) and node.name == function
        ]
        assert len(selected) == 1
        body = selected[0].body
        found = [
            node
            for node in body
            if isinstance(node, ast.Try)
            and any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "import_module"
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == "importlib"
                and child.args
                and isinstance(child.args[0], ast.Constant)
                and child.args[0].value == dependency
                for child in ast.walk(node)
            )
        ]
    else:
        found = [
            node
            for node in body
            if isinstance(node, ast.Try)
            and any(
                isinstance(stmt, ast.ImportFrom) and stmt.module == dependency
                for stmt in node.body
            )
        ]
    assert len(found) == 1, "exactly one dependency guard must remain executable"
    module = ast.fix_missing_locations(ast.Module(body=found, type_ignores=[]))
    return compile(module, str(path), "exec")


def test_build_backend_available_executes_import() -> None:
    seen: list[str] = []

    def importer(name: str) -> object:
        seen.append(name)
        return object()

    exec(
        _guard(BUILD, function="_build_distributions", dependency="build"),
        {
            "importlib": SimpleNamespace(import_module=importer),
            "CommandError": MissingBuildBackend,
        },
    )
    assert seen == ["build"]


def test_missing_build_backend_remains_a_command_error() -> None:
    def missing(name: str) -> None:
        raise ModuleNotFoundError(name)

    with pytest.raises(MissingBuildBackend, match="Python build backend is missing"):
        exec(
            _guard(BUILD, function="_build_distributions", dependency="build"),
            {
                "importlib": SimpleNamespace(import_module=missing),
                "CommandError": MissingBuildBackend,
            },
        )


def test_unexpected_build_backend_error_remains_visible() -> None:
    def broken(name: str) -> None:
        raise RuntimeError("broken build initialization")

    with pytest.raises(RuntimeError, match="broken build initialization"):
        exec(
            _guard(BUILD, function="_build_distributions", dependency="build"),
            {
                "importlib": SimpleNamespace(import_module=broken),
                "CommandError": MissingBuildBackend,
            },
        )


def test_dopamine_validator_loads_real_import_contract() -> None:
    fake = ModuleType("jsonschema")
    setattr(fake, "Draft7Validator", type("Draft7Validator", (), {}))
    with patch.dict(sys.modules, {"jsonschema": fake}):
        globals_dict: dict[str, object] = {"sys": SimpleNamespace(stderr=io.StringIO())}
        exec(_guard(DOPAMINE, function=None, dependency="jsonschema"), globals_dict)
    assert globals_dict["Draft7Validator"] is getattr(fake, "Draft7Validator")


def test_dopamine_validator_fails_closed_when_schema_package_missing() -> None:
    stderr = io.StringIO()
    with patch.dict(sys.modules, {"jsonschema": None}):
        with pytest.raises(SystemExit) as raised:
            exec(
                _guard(DOPAMINE, function=None, dependency="jsonschema"),
                {
                    "sys": SimpleNamespace(
                        stderr=stderr,
                        exit=lambda code: (_ for _ in ()).throw(SystemExit(code)),
                    )
                },
            )
    assert raised.value.code == 1
    assert "jsonschema package required" in stderr.getvalue()
