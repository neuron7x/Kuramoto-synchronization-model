#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Assertion-free test ratchet — a test that cannot fail is not a test.

The 2026-07 assessment found test functions with no recognized check: they
execute code and pass by not crashing. That is smoke at best, and it inflates
"passed" counts with items that can only catch exceptions. This gate freezes
the existing set as debt and fail-closes on NEW assertion-free tests.

Recognition is deliberately generous (the first assessment instrument
mis-reported 14.9% because it missed ``pytest.raises``/``approx``/``warns``):
an ``assert`` statement anywhere in the function, ``pytest.raises`` /
``warns`` / ``deprecated_call`` / ``fail`` / ``approx``, ``self.assert*``,
any call whose name contains ``assert``/``expect``, or delegation to a local
helper whose name starts with ``check_``/``verify_``/``_assert`` counts as a
check. A function that still has none of these is genuinely assertion-free.

Usage::

    python scripts/ci/check_assertion_free_tests.py                 # gate
    python scripts/ci/check_assertion_free_tests.py --list          # findings
    python scripts/ci/check_assertion_free_tests.py --write-baseline

Exit codes: 0 — held; 1 — new assertion-free test (or baseline missing).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / ".github" / "assertion_free_tests_baseline.json"

_CHECK_CALL_MARKERS = (
    "assert",
    "expect",
    "raises",
    "warns",
    "deprecated_call",
    "approx",
    "fail",
    "verify",
)


def _call_name(node: ast.Call) -> str:
    func = node.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts)).lower()


def _has_check(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Assert):
            return True
        if isinstance(node, ast.Raise):
            # a test that raises on violation (custom guard) can fail
            return True
        if isinstance(node, ast.Call):
            name = _call_name(node)
            if any(marker in name for marker in _CHECK_CALL_MARKERS):
                return True
            if name.split(".")[-1].startswith(("check_", "_check")):
                return True
    return False


def _iter_test_fns(tree: ast.AST) -> "list[ast.FunctionDef | ast.AsyncFunctionDef]":
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    ]


def scan() -> list[str]:
    findings: list[str] = []
    for path in sorted(REPO.glob("tests/**/test_*.py")):
        rel = path.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            findings.append(f"{rel}::<unparseable>")
            continue
        for fn in _iter_test_fns(tree):
            if not _has_check(fn):
                findings.append(f"{rel}::{fn.name}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)

    findings = scan()

    if args.list:
        for f in findings:
            print(f"  {f}")

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {
                    "_doc": (
                        "Frozen debt: test functions with no recognized check — they "
                        "pass by not crashing. The gate fails on NEW entries. Add a "
                        "real assertion (or delete the non-test) and re-run with "
                        "--write-baseline to ratchet down."
                    ),
                    "count": len(findings),
                    "tests": sorted(findings),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote baseline: {len(findings)} assertion-free test(s)")
        return 0

    if not BASELINE.is_file():
        print("no baseline — run with --write-baseline")
        return 1

    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    allowed = set(base.get("tests", []))
    current = set(findings)
    new = sorted(current - allowed)
    fixed = sorted(allowed - current)

    print(f"assertion-free gate: {len(current)} finding(s), baseline {len(allowed)}")
    if new:
        print(f"\nassertion-free gate FAILED: {len(new)} NEW assertion-free test(s)\n")
        for item in new:
            print(f"  {item}")
        print("\n  A test that cannot fail is not a test. Add a real check.")
        return 1
    if fixed:
        print(f"{len(fixed)} fixed since baseline — ratchet down with --write-baseline")
    print("assertion-free gate held: no new assertion-free tests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
