#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Inverse probe for the Law T1–T7 registry reconciliation.

This is the falsifier bound to ``registry-reconcile-law-T1-T7-invariants``. It
fires (exits non-zero) iff the reconciliation it guards is later removed or
regressed, distinguishing a genuinely-registered constitutional invariant from
a decorative CLAUDE.md prose token.

It asserts, fail-closed:

#. every one of the twenty Law T1–T7 constitutional invariants
   (INV-KR1..3, INV-LY1..4, INV-CAL1..3, INV-TAU1..3, INV-DET1..3,
   INV-PIN1..4) is present in ``.claude/physics/INVARIANTS.yaml`` — the
   authoritative registry, not CLAUDE.md prose — and the canonical count
   reads exactly ``EXPECTED_COUNT`` (so a silent drop of any of them, or a
   double-count, trips the gate);
#. the invariant source/test binding gate still resolves every binding
   (the new ``source:``/``tests:`` paths point at real files);
#. the physics-docs canon gate still classifies all registry sections into
   exactly one domain (so the six new ``law_t*`` sections never become an
   unclassified physics surface).

Exit codes::

    0  reconciliation intact
    1  at least one reconciled invariant lost, miscounted, unbound, or
       unclassified
    2  a substrate is unreadable / a sub-gate could not run
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVARIANTS_PATH = ROOT / ".claude" / "physics" / "INVARIANTS.yaml"
ID_LINE_RE = re.compile(r"^\s*id:\s*(INV-[A-Za-z0-9_-]+)\s*$")

# The twenty constitutional invariants registered by this reconciliation.
RECONCILED_IDS: tuple[str, ...] = (
    "INV-KR1",
    "INV-KR2",
    "INV-KR3",
    "INV-LY1",
    "INV-LY2",
    "INV-LY3",
    "INV-LY4",
    "INV-CAL1",
    "INV-CAL2",
    "INV-CAL3",
    "INV-TAU1",
    "INV-TAU2",
    "INV-TAU3",
    "INV-DET1",
    "INV-DET2",
    "INV-DET3",
    "INV-PIN1",
    "INV-PIN2",
    "INV-PIN3",
    "INV-PIN4",
)

# The canonical registry count after reconciliation (112 baseline + 20).
EXPECTED_COUNT = 132


def _collect_invariant_ids(path: Path = INVARIANTS_PATH) -> list[str]:
    if not path.is_file():
        raise FileNotFoundError(f"INVARIANTS registry not found at {path}")
    seen: set[str] = set()
    ordered: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = ID_LINE_RE.match(raw_line)
        if match is None:
            continue
        invariant_id = match.group(1)
        if invariant_id in seen:
            continue
        seen.add(invariant_id)
        ordered.append(invariant_id)
    return ordered


def _run(argv: list[str]) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout + proc.stderr)


def main() -> int:
    failures: list[str] = []

    # 1. registry membership + canonical count (zero-dependency authority).
    try:
        invariant_ids = _collect_invariant_ids()
    except Exception as exc:  # pragma: no cover - filesystem guard
        print(f"ERROR: cannot read invariants registry: {exc}", file=sys.stderr)
        return 2

    registered = set(invariant_ids)
    missing = [inv for inv in RECONCILED_IDS if inv not in registered]
    if missing:
        failures.append(f"unregistered Law T1-T7 invariants: {missing}")
    count = len(invariant_ids)
    if count != EXPECTED_COUNT:
        failures.append(f"registry count {count} != expected {EXPECTED_COUNT}")

    # 2. source/test binding integrity (paths resolve).
    code, out = _run(["scripts/ci/check_invariant_source_binding.py"])
    if code != 0:
        failures.append(f"source-binding gate FAILED:\n{out.strip()[-400:]}")

    # 3. canon classification completeness (no unclassified law_t* section).
    code, out = _run(["scripts/ci/check_physics_docs_canon.py"])
    if code != 0:
        failures.append(f"physics-docs-canon gate FAILED:\n{out.strip()[-400:]}")

    if failures:
        print("REGISTRY RECONCILIATION FALSIFIER FIRED:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print(
        f"OK: all {len(RECONCILED_IDS)} Law T1-T7 invariants registered; "
        f"count={EXPECTED_COUNT}; source-binding + canon gates green."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
