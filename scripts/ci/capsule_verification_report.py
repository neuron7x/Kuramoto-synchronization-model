#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Capsule verification report (TASK 933).

Runs the three capsule-focused gates as isolated subprocesses and emits a
machine-readable JSON report:

  * schema          — every capsule manifest validates against the schema;
  * reproduction    — the bundle regenerates bit-for-bit (run from a foreign cwd
                      so working-directory import leakage is exposed);
  * secret_boundary — no smuggled secret / disallowed file in the capsule tree.

Fail-closed: exits non-zero if any layer fails. Designed for the clean-clone
reproducible-capsule workflow, which uploads the JSON report as evidence.

Usage::

    python scripts/ci/capsule_verification_report.py --out report.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LAYERS: tuple[tuple[str, list[str], bool], ...] = (
    ("schema", ["scripts/ci/check_capsule_schema.py"], False),
    # reproduction runs from a foreign cwd to expose working-directory leakage.
    ("reproduction", ["scripts/reproduce/mfn_capsule.py", "--verify"], True),
    ("secret_boundary", ["tools/security/validate_capsule_secret_boundary.py"], False),
)


def _run(rel_argv: list[str], foreign_cwd: bool) -> tuple[int, str]:
    argv = [sys.executable, str(ROOT / rel_argv[0]), *rel_argv[1:]]
    cwd = tempfile.gettempdir() if foreign_cwd else str(ROOT)
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("capsule_verification.json"))
    args = parser.parse_args(argv)

    layers: dict[str, dict[str, object]] = {}
    overall_ok = True
    for name, rel_argv, foreign in LAYERS:
        rc, output = _run(rel_argv, foreign)
        ok = rc == 0
        overall_ok = overall_ok and ok
        layers[name] = {"status": "PASS" if ok else "FAIL", "exit_code": rc, "output": output}
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
        if not ok:
            print(output)

    report = {
        "schema_version": "geosync.capsule_verification_report.v1",
        "capsule_root": "artifacts/reproducible_capsules",
        "overall": "PASS" if overall_ok else "FAIL",
        "layers": layers,
    }
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"report → {args.out}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
