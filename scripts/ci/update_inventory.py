#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Update INVENTORY.json file hashes for managed scopes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_PATH = ROOT / "INVENTORY.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Update INVENTORY.json checksums.")
    parser.add_argument("--write", action="store_true", help="Write updated inventory to disk.")
    args = parser.parse_args()

    if not INVENTORY_PATH.exists():
        raise SystemExit(f"Missing inventory: {INVENTORY_PATH}")

    payload = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    scopes: list[str] = payload.get("scopes", [])

    files: set[str] = set()
    for scope in scopes:
        files |= _tracked_files_in_scope(scope)

    payload["files"] = [{"path": rel, "sha256": _sha256(ROOT / rel)} for rel in sorted(files)]

    encoded = json.dumps(payload, indent=2) + "\n"
    if args.write:
        INVENTORY_PATH.write_text(encoded, encoding="utf-8")
        print(f"Updated {INVENTORY_PATH.relative_to(ROOT)} with {len(files)} files.")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
