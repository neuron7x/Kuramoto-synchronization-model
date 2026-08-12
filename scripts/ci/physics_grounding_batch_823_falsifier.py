#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Inverse probe for the #823 physics-grounding batch acceptor.

Runs the physics test validator on every file this batch grounded and exits
non-zero if any file reports a non-zero L1..L5 issue total. This fires iff the
INV-* grounding or NON_PHYSICS classification added by the batch is later
removed or regressed — proving the grounding is real and machine-enforced,
not decorative.

Exit codes:
    0  every bound file validates clean (Total = 0).
    1  at least one bound file regressed (non-zero validator total).
    2  usage / environment error.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = REPO_ROOT / ".claude" / "physics" / "validate_tests.py"

BOUND_FILES: tuple[str, ...] = (
    "tests/unit/physics/test_T9_kuramoto_finite_size_sweep.py",
    "tests/unit/physics/test_T10_ricci_universal_upper_bound.py",
    "tests/unit/physics/test_T17_cryptobiosis_exact_zero.py",
    "tests/unit/physics/test_T_dro1_gamma_algebraic.py",
    "tests/unit/physics/test_inv_dro2_risk_scalar.py",
    "tests/unit/physics/test_T18b_second_order_stability_guard.py",
    "tests/unit/physics/test_conservation_aliases.py",
    "tests/physics/test_dimensional_homogeneity.py",
    "tests/research/robustness/test_kuramoto_candidate_set.py",
    "tests/research/robustness/test_kuramoto_no_interference.py",
)


def main() -> int:
    if not VALIDATOR.is_file():
        print(f"ERROR: validator not found at {VALIDATOR}", file=sys.stderr)
        return 2
    regressions: list[str] = []
    for rel in BOUND_FILES:
        target = REPO_ROOT / rel
        if not target.is_file():
            print(f"ERROR: bound file missing: {rel}", file=sys.stderr)
            return 2
        # validate_tests.py exits 0 only when every L1..L5 issue total is 0.
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), str(target)],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
        if proc.returncode != 0:
            regressions.append(rel)
            print(f"REGRESSED: {rel}\n{proc.stdout}", file=sys.stderr)
    if regressions:
        print(
            "FALSIFIER FIRED: physics grounding regressed on " + ", ".join(regressions),
            file=sys.stderr,
        )
        return 1
    print(f"OK: all {len(BOUND_FILES)} bound files validate clean (Total = 0).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
