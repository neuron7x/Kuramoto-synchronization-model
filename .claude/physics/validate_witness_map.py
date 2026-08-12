#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate TEST_WITNESS_MAP.json against real test files and invariants.

This checker is intentionally separate from validate_tests.py. It gives the
batch migration a compact, auditable path: function -> INV-* mapping lives in a
sidecar when changing large legacy test files is impractical.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PHYSICS_DIR = ROOT / ".claude" / "physics"
INVARIANTS = PHYSICS_DIR / "INVARIANTS.yaml"
MAP_PATH = PHYSICS_DIR / "TEST_WITNESS_MAP.json"
INV_RE = re.compile(r"INV-[A-Z0-9][A-Z0-9-]*")


def load_invariant_ids() -> set[str]:
    ids: set[str] = set()
    for line in INVARIANTS.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s+id:\s+(INV-[A-Z0-9][A-Z0-9-]*)", line)
        if match:
            ids.add(match.group(1))
    return ids


def test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if not MAP_PATH.exists():
        fail(f"missing witness map: {MAP_PATH}")
    payload = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    files: dict[str, Any] = payload.get("files", {})
    if not isinstance(files, dict) or not files:
        fail("TEST_WITNESS_MAP.json must contain a non-empty object field: files")

    invariant_ids = load_invariant_ids()
    mapped_witnesses = 0
    mapped_non_physics = 0

    for relpath, spec in files.items():
        path = ROOT / relpath
        if not path.exists():
            fail(f"mapped file does not exist: {relpath}")
        if not isinstance(spec, dict):
            fail(f"file spec must be an object: {relpath}")
        funcs = test_functions(path)
        witnesses = spec.get("witnesses", {})
        non_physics = spec.get("non_physics", [])
        non_physics_file = bool(spec.get("non_physics_file", False))

        if non_physics_file and (witnesses or non_physics):
            fail(f"non_physics_file cannot also define witnesses/non_physics: {relpath}")
        if non_physics_file:
            mapped_non_physics += len(funcs)
            continue

        if not isinstance(witnesses, dict):
            fail(f"witnesses must be an object: {relpath}")
        if not isinstance(non_physics, list):
            fail(f"non_physics must be a list: {relpath}")

        witness_funcs = set(witnesses)
        non_physics_funcs = set(non_physics)
        overlap = sorted(witness_funcs & non_physics_funcs)
        if overlap:
            fail(f"function mapped as witness and non_physics in {relpath}: {overlap}")

        unknown = sorted((witness_funcs | non_physics_funcs) - funcs)
        if unknown:
            fail(f"mapped functions not found in {relpath}: {unknown}")

        for func_name, invs in witnesses.items():
            if not isinstance(invs, list) or not invs:
                fail(f"witness mapping must be a non-empty list: {relpath}::{func_name}")
            for inv in invs:
                if not isinstance(inv, str) or not INV_RE.fullmatch(inv):
                    fail(f"invalid invariant token: {relpath}::{func_name} -> {inv!r}")
                if inv not in invariant_ids:
                    fail(f"unknown invariant id: {relpath}::{func_name} -> {inv}")
            mapped_witnesses += 1
        mapped_non_physics += len(non_physics_funcs)

    print("Witness map validation PASS")
    print(f"  files: {len(files)}")
    print(f"  witness functions: {mapped_witnesses}")
    print(f"  non-physics functions: {mapped_non_physics}")


if __name__ == "__main__":
    main()
