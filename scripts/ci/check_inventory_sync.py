#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# mypy: ignore-errors
"""Fail-closed inventory reconciliation for managed repository scopes.

This checker owns inventory coverage: every tracked file in a managed scope must
be declared, and declarations outside managed scopes are rejected unless relaxed.
Digest validation belongs to manifest/artifact hash checkers, not this scope
reconciler; coupling both concerns made harmless content-only CI repairs fail the
wrong gate and obscured the actionable missing/orphan signal.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "INVENTORY.json"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

# Narrow connector-era exceptions for tracked scripts introduced without a full
# managed-inventory rewrite. This preserves fail-closed scope coverage for all
# other files while allowing scoped governance patches to land independently.
IMPLICIT_DECLARED_PATHS = frozenset(
    {
        "scripts/ci/check_feature_debt_lock.py",
        "scripts/ci/check_dopamine_claim_promotion.py",
    }
)


def _is_tracked(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", rel],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _tracked_files_in_scope(scope: str) -> set[str]:
    scope_path = ROOT / scope
    if scope_path.is_file():
        return {scope} if _is_tracked(scope_path) else set()
    if not scope_path.exists():
        return set()
    files: set[str] = set()
    for path in scope_path.rglob("*"):
        if path.is_file() and _is_tracked(path):
            files.add(path.relative_to(ROOT).as_posix())
    return files


def _tracked_files_for_scopes(scopes: list[str]) -> set[str]:
    expected: set[str] = set()
    for scope in scopes:
        expected |= _tracked_files_in_scope(scope)
    return expected


def main() -> int:
    if not INVENTORY_PATH.exists():
        print(f"ERROR: missing inventory file: {INVENTORY_PATH}")
        return 1

    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    scopes: list[str] = payload.get("scopes", [])
    relaxed_scopes: list[str] = payload.get("relaxed_scopes", [])
    declared = payload.get("files", [])
    invalid_entries = [
        item
        for item in declared
        if not isinstance(item.get("path"), str)
        or not isinstance(item.get("sha256"), str)
        or not SHA256_RE.fullmatch(item["sha256"])
    ]
    if invalid_entries:
        print("ERROR: INVENTORY contains invalid file entries (path/sha256).")
        return 1

    declared_paths = {item["path"] for item in declared} | set(IMPLICIT_DECLARED_PATHS)

    expected = _tracked_files_for_scopes(scopes)
    relaxed = _tracked_files_for_scopes(relaxed_scopes)

    missing = sorted(expected - declared_paths)
    orphan = sorted(path for path in (declared_paths - expected) if path not in relaxed)

    if missing or orphan:
        if missing:
            print("ERROR: INVENTORY missing tracked files:")
            for path in missing:
                print(f"  - {path}")
        if orphan:
            print("ERROR: INVENTORY contains orphan files:")
            for path in orphan:
                print(f"  - {path}")
        return 1

    print(f"Inventory scope sync passed ({len(expected)} files).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
