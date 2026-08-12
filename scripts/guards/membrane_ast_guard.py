#!/usr/bin/env python3
"""Fail-closed AST membrane guard for geosync -> coherence_bridge isolation."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "geosync"

DYNAMIC_IMPORT_FUNCS = {
    ("importlib", "import_module"),
    (None, "__import__"),
}
EXEC_FUNCS = {(None, "exec"), (None, "eval")}


def _literal_str(node: ast.AST, consts: dict[str, str]) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return consts.get(node.id)
    return None


def _collect_str_constants(tree: ast.AST) -> dict[str, str]:
    consts: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            lit = _literal_str(node.value, consts)
            if lit is not None:
                consts[node.targets[0].id] = lit
    return consts


def _func_ref(node: ast.Call) -> tuple[str | None, str | None]:
    if isinstance(node.func, ast.Name):
        return None, node.func.id
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        return node.func.value.id, node.func.attr
    return None, None


def scan_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    consts = _collect_str_constants(tree)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                if n.name == "coherence_bridge" or n.name.startswith("coherence_bridge."):
                    violations.append(f"{path}:{node.lineno}: static import {n.name}")

        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "coherence_bridge" or node.module.startswith("coherence_bridge."):
                violations.append(f"{path}:{node.lineno}: from-import {node.module}")

        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Attribute):
            if (
                isinstance(node.value.value, ast.Name)
                and node.value.value.id == "sys"
                and node.value.attr == "modules"
            ):
                lit = _literal_str(node.slice, consts)  # py3.10 uses expr directly
                if lit and "coherence_bridge" in lit:
                    violations.append(f"{path}:{node.lineno}: sys.modules injection {lit!r}")

        if isinstance(node, ast.Call):
            fn_mod, fn_name = _func_ref(node)

            if (fn_mod, fn_name) in DYNAMIC_IMPORT_FUNCS and node.args:
                lit = _literal_str(node.args[0], consts)
                if lit and "coherence_bridge" in lit:
                    violations.append(
                        f"{path}:{node.lineno}: dynamic import {fn_mod or ''}.{fn_name}({lit!r})"
                    )

            if (fn_mod, fn_name) == (None, "getattr") and len(node.args) >= 2:
                target = _literal_str(node.args[1], consts)
                if target == "__import__":
                    violations.append(f"{path}:{node.lineno}: getattr(..., '__import__') bypass")

            if (fn_mod, fn_name) in EXEC_FUNCS and node.args:
                payload = _literal_str(node.args[0], consts)
                if payload and "coherence_bridge" in payload:
                    violations.append(
                        f"{path}:{node.lineno}: {fn_name} payload references coherence_bridge"
                    )

    return violations


def main() -> int:
    violations: list[str] = []
    for py in TARGET.rglob("*.py"):
        violations.extend(scan_file(py))

    if violations:
        print("MEMBRANE VIOLATIONS DETECTED:")
        for v in violations:
            print(v)
        return 1

    print("Membrane AST guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
