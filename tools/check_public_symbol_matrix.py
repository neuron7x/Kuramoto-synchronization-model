#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Audit tool — verify research/systemic_risk public symbols are mapped.

Closes audit task T1 of the 9.9-upgrade plan. Reads
``research/systemic_risk/public_symbol_matrix.csv`` and the actual
``research.systemic_risk.__all__`` and asserts:

* every public symbol has exactly one row in the matrix
* every row in the matrix corresponds to a real public symbol
* no row has empty mandatory fields (symbol, module, role,
  invariant, test_file, failure_mode, ci_gate, status)

Exits 0 on PASS, non-zero on FAIL. CI calls this in
``research-integrity-gate.yml``.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MATRIX_PATH = REPO_ROOT / "research" / "systemic_risk" / "public_symbol_matrix.csv"

MANDATORY_FIELDS: tuple[str, ...] = (
    "symbol",
    "module",
    "role",
    "invariant",
    "test_file",
    "failure_mode",
    "ci_gate",
    "status",
)


def main() -> int:
    sys.path.insert(0, str(REPO_ROOT))
    import research.systemic_risk as pkg

    public_syms = set(pkg.__all__)

    if not MATRIX_PATH.is_file():
        print(f"FAIL: {MATRIX_PATH} not found")
        return 1

    with MATRIX_PATH.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)

    matrix_syms: set[str] = set()
    issues: list[str] = []
    for i, row in enumerate(rows, start=2):  # data starts at line 2
        sym = row.get("symbol", "").strip()
        if not sym:
            issues.append(f"line {i}: empty symbol field")
            continue
        if sym in matrix_syms:
            issues.append(f"line {i}: duplicate symbol {sym!r}")
        matrix_syms.add(sym)
        for f in MANDATORY_FIELDS:
            if not row.get(f, "").strip():
                issues.append(f"line {i} ({sym}): empty mandatory field {f!r}")

    missing = public_syms - matrix_syms
    extra = matrix_syms - public_syms
    for s in sorted(missing):
        issues.append(f"orphan public symbol (not in matrix): {s}")
    for s in sorted(extra):
        issues.append(f"phantom matrix row (no such public symbol): {s}")

    if issues:
        print("FAIL: research-integrity matrix audit")
        for line in issues[:30]:
            print(f"  {line}")
        if len(issues) > 30:
            print(f"  ... {len(issues) - 30} more issue(s)")
        return 1

    print(
        f"PASS: {len(rows)} rows; "
        f"{len(public_syms)} public symbols; 0 orphans; 0 phantoms; "
        f"all mandatory fields populated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
