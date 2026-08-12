#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Import-architecture ratchet — fail-closed, monotone-down debt ledger.

GeoSync's canonical package is top-level ``geosync`` (``import geosync``
resolves there; 144 first-party imports vs 5 for the 2026-05-06-stale
``src/geosync`` fork). The release gate (``release_gate.py``) reports the
*totals*; this ratchet pins the *exact set* of first-party files that still
violate the single-canonical target and enforces that the set may only
**shrink**:

* a NEW first-party ``src.*`` import, or a NEW ``sys.path`` mutation, fails
  the build — no fresh architectural debt may enter;
* a baseline entry that no longer violates also fails, with a one-line fix
  (``--write``) — paying down debt must tighten the ledger, so it stays
  honest and trends to empty.

The migration target is both lists empty: one canonical ``geosync`` package
with no ``src.*`` imports and no runtime path manipulation, installable as a
wheel without namespace squatting. See the import-architecture ADR.

Usage::

    python scripts/ci/check_import_architecture.py            # verify
    python scripts/ci/check_import_architecture.py --write     # tighten ledger

Exit codes::

    0  — current debt == baseline (no new violator, no stale entry)
    1  — a new violator entered, or a fixed entry must be retired from the ledger
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / ".github" / "import_architecture_baseline.json"

_SRC_IMPORT_RE = re.compile(r"^\s*(from|import)\s+src(\.|\s|$)")
_PATH_HACK_RE = re.compile(r"sys\.path\.(insert|append)\s*\(")
_NON_SOURCE_PREFIXES: tuple[str, ...] = (
    "tests/",
    "test/",
    "devtools/",
    ".git/",
    "build/",
    "dist/",
    "node_modules/",
)


def _first_party_py() -> list[str]:
    proc = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    out: list[str] = []
    for rel in proc.stdout.splitlines():
        rel = rel.strip()
        if not rel.endswith(".py"):
            continue
        if any(rel.startswith(p) for p in _NON_SOURCE_PREFIXES):
            continue
        out.append(rel)
    return out


def _scan() -> tuple[set[str], set[str]]:
    src_imports: set[str] = set()
    path_hacks: set[str] = set()
    for rel in _first_party_py():
        try:
            lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        if any(_SRC_IMPORT_RE.search(line) for line in lines):
            src_imports.add(rel)
        if rel.rsplit("/", 1)[-1] != "conftest.py" and any(
            _PATH_HACK_RE.search(line) for line in lines
        ):
            path_hacks.add(rel)
    return src_imports, path_hacks


def _load_baseline() -> tuple[set[str], set[str]]:
    if not BASELINE_PATH.exists():
        return set(), set()
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return set(payload.get("src_imports", [])), set(payload.get("path_hacks", []))


def _write_baseline(src_imports: set[str], path_hacks: set[str]) -> None:
    existing = {}
    if BASELINE_PATH.exists():
        existing = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    payload = {
        "_doc": existing.get(
            "_doc",
            "Import-architecture debt ledger (RATCHET). First-party files that "
            "violate the single-canonical-geosync target. These sets may ONLY "
            "shrink; check_import_architecture.py enforces it. Target: empty.",
        ),
        "version": 1,
        "src_imports": sorted(src_imports),
        "path_hacks": sorted(path_hacks),
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import-architecture ratchet.")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Regenerate the baseline from the current tree (tighten the ledger).",
    )
    args = parser.parse_args(argv)

    cur_src, cur_hacks = _scan()

    if args.write:
        _write_baseline(cur_src, cur_hacks)
        print(f"Baseline tightened: {len(cur_src)} src.* imports, {len(cur_hacks)} path-hacks.")
        return 0

    base_src, base_hacks = _load_baseline()

    new_src = sorted(cur_src - base_src)
    new_hacks = sorted(cur_hacks - base_hacks)
    fixed_src = sorted(base_src - cur_src)
    fixed_hacks = sorted(base_hacks - cur_hacks)

    failed = False

    if new_src or new_hacks:
        failed = True
        print("ERROR: new import-architecture debt (the canonical-geosync ratchet only shrinks).")
        for f in new_src:
            print(f"  + src.* import: {f}")
        for f in new_hacks:
            print(f"  + sys.path hack: {f}")
        print("Fix: import from the canonical `geosync` package; do not mutate sys.path.")

    if fixed_src or fixed_hacks:
        failed = True
        print(
            f"Debt paid down ({len(fixed_src)} src.* + {len(fixed_hacks)} path-hacks fixed) "
            "but the ledger is stale. Tighten it so it stays honest:"
        )
        print("  python scripts/ci/check_import_architecture.py --write")

    if not failed:
        remaining = len(cur_src) + len(cur_hacks)
        print(
            f"Import-architecture ratchet held: {len(cur_src)} src.* imports + "
            f"{len(cur_hacks)} path-hacks (target 0). No new debt."
        )
        if remaining == 0:
            print("Ledger empty — single canonical geosync package achieved.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
