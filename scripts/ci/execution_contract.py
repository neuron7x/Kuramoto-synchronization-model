#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""K.execution — execution-realism scope contract (Path A: out-of-scope).

Tribunal for the gate ``K.execution``. GeoSync's canonical product category
(``PRODUCT_CATEGORY.md``, ``CLAUDE.md``) is a *verification-first research
platform* — explicitly not a live-venue execution product and not an
asserted market edge. Rather than claim an execution-realism model it does
not gate (fills, slippage, adverse selection, latency, recovery), this probe
takes the honest path: it declares execution realism **out of scope** with a
machine-readable exclusion, and binds that exclusion to an *enforced* claim
boundary.

The exclusion is only credible if the repository cannot quietly re-sell
itself as a live-trading product. So this probe is GREEN iff:

1. the out-of-scope contract artifact is written, AND
2. ``scripts/ci/check_claim_boundary.py`` exits 0 — i.e. no unreviewed
   live-trading / alpha / signal-product wording on the canonical surface.

If the claim boundary scanner fails, the exclusion is contradicted by the
prose and this gate goes RED. The exclusion and the firewall stand or fall
together.

Output: ``artifacts/execution/contract.json``. Exit 0 iff GREEN.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import Any

from scripts.ci.proof_common import ROOT, write_artifact

ARTIFACT = "artifacts/execution/contract.json"

EXCLUDED_DIMENSIONS: tuple[str, ...] = (
    "fills",
    "slippage",
    "fees",
    "adverse_selection",
    "latency",
    "recovery_behavior",
)

# Wording that, if it appeared unreviewed on the canonical surface, would
# contradict the out-of-scope declaration. Enforcement is delegated to the
# claim-boundary scanner; this list documents the boundary intent.
FORBIDDEN_EXECUTION_WORDING: tuple[str, ...] = (
    "live-trading",
    "production trading",
    "deployable strategy",
    "alpha engine",
    "tradable signal",
)


def run() -> dict[str, Any]:
    boundary = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "ci" / "check_claim_boundary.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    boundary_ok = boundary.returncode == 0
    status = "PASS" if boundary_ok else "FAIL"
    return {
        "gate": "K.execution",
        "schema_version": "1.0",
        "scope": "OUT_OF_SCOPE",
        "rationale": (
            "GeoSync is a verification-first quantitative research platform; "
            "execution realism (fills/slippage/adverse-selection/latency/recovery) "
            "is explicitly not modelled or claimed. The execution-realism harness "
            "in the codebase is internal substrate, not a live-execution promise."
        ),
        "excluded_dimensions": list(EXCLUDED_DIMENSIONS),
        "forbidden_wording": list(FORBIDDEN_EXECUTION_WORDING),
        "claim_boundary_enforced": boundary_ok,
        "claim_boundary_evidence": (
            boundary.stdout.strip().splitlines()[-1]
            if boundary.stdout.strip()
            else "check_claim_boundary exited " + str(boundary.returncode)
        ),
        "status": status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=ARTIFACT, help="artifact output path")
    args = parser.parse_args(argv)
    payload = run()
    path = write_artifact(args.json, payload)
    print(f"[K.execution] scope={payload['scope']} status={payload['status']} -> {path}")
    print(f"  claim_boundary_enforced={payload['claim_boundary_enforced']}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
