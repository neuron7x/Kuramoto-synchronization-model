#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Test skip/xfail ratchet — fail-closed, monotone-down debt ledger.

A large suite with many silent ``skip``/``xfail`` markers can hide missing
dependencies, platform assumptions, unavailable data or a quietly weakened
gate. This freezes today's per-file skip/xfail count in
``docs/SKIP_RATCHET_BASELINE.json`` and enforces that it may only shrink: any
new skipped file, or any file whose skip count rises, fails the build; any
file that drops below its frozen count must tighten the ledger (``--write``).

Counted markers (stdlib AST, no pytest import):

* ``@pytest.mark.skip`` / ``.skipif``
* ``@pytest.mark.xfail``
* ``pytest.skip(...)`` / ``pytest.xfail(...)`` calls
* bare ``@skip`` / ``@skipif`` / ``@xfail`` decorators

Usage::

    python scripts/ci/check_skip_ratchet.py            # verify (CI)
    python scripts/ci/check_skip_ratchet.py --write     # tighten the ledger

Exit codes::

    0  — current skip debt <= baseline, no stale entry
    1  — a new/grown skip entered, or a removed skip left the ledger stale
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = ROOT / "docs" / "SKIP_RATCHET_BASELINE.json"
TEST_ROOTS = ("tests", "test")
_MARKERS = frozenset({"skip", "skipif", "xfail"})


def _attr_tail(node: ast.expr) -> str | None:
    """Trailing attribute/name of an expression (``pytest.mark.skip`` -> ``skip``)."""
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Call):
        return _attr_tail(node.func)
    return None


def _count_file(source: str, rel: str) -> int:
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError:
        return 0
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for dec in node.decorator_list:
                if _attr_tail(dec) in _MARKERS:
                    count += 1
        elif isinstance(node, ast.Call):
            tail = _attr_tail(node.func)
            if tail in {"skip", "xfail"} and isinstance(node.func, ast.Attribute):
                count += 1  # pytest.skip(...) / pytest.xfail(...) call form
    return count


def _scan() -> dict[str, int]:
    out: dict[str, int] = {}
    for root in TEST_ROOTS:
        base = ROOT / root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            n = _count_file(path.read_text(encoding="utf-8", errors="replace"), rel)
            if n:
                out[rel] = n
    return out


def _load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        return {}
    return dict(json.loads(BASELINE_PATH.read_text(encoding="utf-8")).get("skips", {}))


def _write_baseline(skips: dict[str, int]) -> None:
    payload = {
        "_doc": (
            "Test skip/xfail debt ledger (RATCHET). Per-file count of skip / "
            "skipif / xfail markers under tests/. May ONLY shrink; "
            "scripts/ci/check_skip_ratchet.py fails on any new or grown entry "
            "and on any removed entry left stale. Target: empty."
        ),
        "schema_version": "1.0",
        "skips": {k: skips[k] for k in sorted(skips)},
    }
    BASELINE_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Test skip/xfail ratchet.")
    parser.add_argument("--write", action="store_true", help="Tighten the ledger.")
    args = parser.parse_args(argv)

    cur = _scan()
    if args.write:
        _write_baseline(cur)
        print(f"Skip ledger tightened: {sum(cur.values())} markers in {len(cur)} files.")
        return 0

    base = _load_baseline()
    rose = sorted(f for f, n in cur.items() if n > base.get(f, 0))
    dropped = sorted(f for f, n in base.items() if cur.get(f, 0) < n)
    failed = False
    if rose:
        failed = True
        print("ERROR: new/grown test-skip debt (the skip ratchet only shrinks):")
        for f in rose:
            print(f"  + {f}: {base.get(f, 0)} -> {cur[f]}")
    if dropped:
        failed = True
        print(f"{len(dropped)} file(s) un-skipped but ledger stale — tighten it:")
        print("  python scripts/ci/check_skip_ratchet.py --write")
    if failed:
        return 1
    print(f"Skip ratchet held: {sum(cur.values())} markers in {len(cur)} files (target 0).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
