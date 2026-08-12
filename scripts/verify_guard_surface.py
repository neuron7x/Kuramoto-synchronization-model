from __future__ import annotations

from pathlib import Path

REQUIRED_FILES = [
    Path("runtime/riee/engine.py"),
    Path("runtime/riee/sdk.py"),
    Path("runtime/riee/telemetry.py"),
    Path("scripts/check_epistemic_drift.py"),
    Path("scripts/validate_financial_contract.py"),
    Path("scripts/generate_claim_graph.py"),
    Path("scripts/claims_lifecycle.py"),
    Path("scripts/verify_claim_hashes.py"),
    Path("tests/tools/test_runtime_cost_profiler.py"),
    Path("tests/tools/test_check_epistemic_drift.py"),
    Path("tests/tools/test_validate_financial_contract_adversarial.py"),
    Path("tests/adversarial_invariants/test_invariant_fail_closed.py"),
    Path("tests/riee/test_riee_kernel.py"),
    Path("tests/riee/test_riee_sdk_modes.py"),
    Path("tests/riee/test_riee_telemetry.py"),
]


def main() -> int:
    missing = [str(p) for p in REQUIRED_FILES if not p.exists()]
    if missing:
        print("GUARD SURFACE VIOLATION: missing required files:")
        for m in missing:
            print(f" - {m}")
        return 1
    print("OK: guard surface complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
