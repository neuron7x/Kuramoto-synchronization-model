#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Validate the CALIB-GRID registry extension and witness map."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PHYSICS_DIR = ROOT / ".claude" / "physics"
REGISTRY = PHYSICS_DIR / "CALIB_GRID_INVARIANTS.yaml"
MAP_PATH = PHYSICS_DIR / "CALIB_GRID_WITNESS_MAP.json"
INV_RE = re.compile(r"INV-CALIB-[A-Z0-9-]+")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def registry_ids() -> set[str]:
    if not REGISTRY.exists():
        fail(f"missing registry: {REGISTRY}")
    ids: set[str] = set()
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\s+id:\s+(INV-CALIB-[A-Z0-9-]+)", line)
        if match:
            ids.add(match.group(1))
    if not ids:
        fail("extension registry contains no INV-CALIB-* ids")
    return ids


def test_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def main() -> None:
    if not MAP_PATH.exists():
        fail(f"missing witness map: {MAP_PATH}")
    ids = registry_ids()
    payload: dict[str, Any] = json.loads(MAP_PATH.read_text(encoding="utf-8"))
    files = payload.get("files", {})
    if not isinstance(files, dict) or not files:
        fail("map must define non-empty files object")

    total_witness = 0
    total_existing = 0
    total_governance = 0

    for relpath, spec in files.items():
        path = ROOT / relpath
        if not path.exists():
            fail(f"mapped file does not exist: {relpath}")
        funcs = test_functions(path)
        witnesses = spec.get("witnesses", {})
        existing = spec.get("existing_registry_witnesses", {})
        governance = spec.get("governance_pins", [])
        if not isinstance(witnesses, dict):
            fail(f"witnesses must be object: {relpath}")
        if not isinstance(existing, dict):
            fail(f"existing_registry_witnesses must be object: {relpath}")
        if not isinstance(governance, list):
            fail(f"governance_pins must be list: {relpath}")

        mapped = set(witnesses) | set(existing) | set(governance)
        unknown_funcs = sorted(mapped - funcs)
        if unknown_funcs:
            fail(f"mapped functions not found in {relpath}: {unknown_funcs}")

        overlap = (set(witnesses) & set(existing)) | (set(witnesses) & set(governance)) | (set(existing) & set(governance))
        if overlap:
            fail(f"function appears in multiple buckets in {relpath}: {sorted(overlap)}")

        unmapped = sorted(funcs - mapped)
        if unmapped:
            fail(f"unmapped test functions in {relpath}: {unmapped}")

        for fn, invs in witnesses.items():
            if not isinstance(invs, list) or not invs:
                fail(f"empty invariant list for {relpath}::{fn}")
            for inv in invs:
                if not isinstance(inv, str) or not INV_RE.fullmatch(inv):
                    fail(f"invalid extension invariant token: {relpath}::{fn} -> {inv!r}")
                if inv not in ids:
                    fail(f"extension invariant missing from registry: {inv}")
            total_witness += 1
        total_existing += len(existing)
        total_governance += len(governance)

    print("CALIB-GRID witness map validation PASS")
    print(f"  extension_ids: {len(ids)}")
    print(f"  extension_witnesses: {total_witness}")
    print(f"  existing_registry_witnesses: {total_existing}")
    print(f"  governance_pins: {total_governance}")


if __name__ == "__main__":
    main()
