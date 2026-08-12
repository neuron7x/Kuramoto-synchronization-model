"""T7: module does not import from forbidden areas and does not mention
closed-line identifiers (combo_v1 / combo_v2)."""

from __future__ import annotations

import ast
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[3] / "core" / "cross_asset_kuramoto"
FORBIDDEN_PREFIXES: tuple[str, ...] = ("backtest", "execution", "strategies")
FORBIDDEN_STRINGS: tuple[str, ...] = ("combo_v1", "combo_v2")


def _all_py_files() -> list[Path]:
    return sorted(MODULE_DIR.rglob("*.py"))


def test_no_forbidden_imports() -> None:
    offenders: list[str] = []
    for path in _all_py_files():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                if root in FORBIDDEN_PREFIXES:
                    offenders.append(f"{path.name}: from {node.module} import ...")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root in FORBIDDEN_PREFIXES:
                        offenders.append(f"{path.name}: import {alias.name}")
    assert not offenders, "forbidden imports detected:\n" + "\n".join(offenders)


def test_no_combo_identifier_references() -> None:
    offenders: list[str] = []
    for path in _all_py_files():
        text = path.read_text()
        for needle in FORBIDDEN_STRINGS:
            if needle in text:
                offenders.append(f"{path.name}: {needle!r} appears")
    assert not offenders, "combo_v1/combo_v2 references detected:\n" + "\n".join(offenders)
