#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    cmd: list[str]


CHECKS = [
    Check("drift", [sys.executable, "scripts/check_epistemic_drift.py"]),
    Check("financial", [sys.executable, "scripts/validate_financial_contract.py"]),
    Check("claim_graph", [sys.executable, "scripts/generate_claim_graph.py"]),
    Check("claim_hashes", [sys.executable, "scripts/verify_claim_hashes.py"]),
    Check("guard_surface", [sys.executable, "scripts/verify_guard_surface.py"]),
    Check(
        "riee_core_tests",
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "tests/riee/test_riee_kernel.py",
            "tests/riee/test_riee_sdk_modes.py",
            "tests/riee/test_riee_telemetry.py",
        ],
    ),
]


def main() -> int:
    for check in CHECKS:
        print(f"==> {check.name}: {' '.join(check.cmd)}")
        proc = subprocess.run(check.cmd, check=False)
        if proc.returncode != 0:
            print(f"FAIL-CLOSED: {check.name} failed with code {proc.returncode}")
            return proc.returncode
    print("RIEE PRODUCTION READINESS: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
