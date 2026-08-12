#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generate the D-002G-M3 eligibility matrix artifact.

Runs :func:`verify_m3_eligibility` over the locked prereg grid
(substrates × N × λ × base_seed × null_seed) and emits both:

  * ``artifacts/d002g/m3/m3_null_domain_verdicts.json`` — machine-
    readable matrix the implementation report consumes.
  * stdout — human-readable summary.

Strict scope: this script ONLY runs the M3 verifier. It does NOT
launch a canonical D-002G run, does NOT touch the D002C ledger, does
NOT emit a tier promotion, and does NOT authorise a canonical run.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from research.systemic_risk.d002c_substrates import (
    BlockStructuredSubstrate,
    RicciFlowSubstrate,
    TemporalKtSubstrate,
)
from research.systemic_risk.d002g_null_mechanisms import (
    M3_TOL_DEGREE_WASSERSTEIN,
    M3_TOL_DENSITY,
    M3_TOL_MARGINAL,
    M3_TOL_NON_DEGENERATE,
    M3_TOL_SPECTRAL_RADIUS,
    M3_TOPOLOGY_CONDITIONED_SALT,
    verify_m3_eligibility,
)

LAMBDA = 0.4
BASE_SEED = 42
NULL_SEED = 12345
N_GRID = (50, 100, 200)
SUBSTRATES = {
    "ricci_flow": RicciFlowSubstrate(),
    "block_structured": BlockStructuredSubstrate(),
    "temporal_coupling": TemporalKtSubstrate(),
}

# Prior verdicts (carried from P1/P2/P3 ledgers — NOT re-evaluated here).
M1_PRIOR = {
    "ricci_flow": "ELIGIBLE_M1",
    "block_structured": "INELIGIBLE_M1_BIT_IDENTICAL",
    "temporal_coupling": "INELIGIBLE_M1_BIT_IDENTICAL",
}
M2_EDGE_PRIOR = {
    "ricci_flow": "ELIGIBLE_M2",
    "block_structured": "INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL",
    "temporal_coupling": "INELIGIBLE_M2_DEGENERATE_SHUFFLE_POOL",
}
M2_NODE_PRIOR = {
    "ricci_flow": "INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED",
    "block_structured": "INELIGIBLE_M2_NODE_PAYLOAD_TOPOLOGY_COUPLED",
    "temporal_coupling": "INELIGIBLE_M2_NODE_PAYLOAD_DEGENERATE_POOL",
}
M2_INJ_PRIOR = {
    "ricci_flow": "INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE",
    "block_structured": "INELIGIBLE_M2_INJECTION_SEQUENCE_DEGENERATE",
    "temporal_coupling": "INELIGIBLE_M2_INJECTION_SEQUENCE_CONTRACT_VIOLATION",
}


def _final_null_domain(
    sid: str,
    m1: str,
    m2_edge: str,
    m2_node: str,
    m2_inj: str,
    m3: str,
) -> str:
    if m1 == "ELIGIBLE_M1":
        return "M1"
    if m2_edge == "ELIGIBLE_M2":
        return "M2_EDGE_WEIGHT"
    if m2_node == "ELIGIBLE_M2_NODE_PAYLOAD":
        return "M2_NODE_PAYLOAD"
    if m2_inj == "ELIGIBLE_M2_INJECTION_SEQUENCE":
        return "M2_INJECTION_SEQUENCE"
    if m3 == "ELIGIBLE_M3":
        return "M3"
    return "M4_REQUIRED"


def _b1_contribution(final_domain: str) -> str:
    if final_domain in ("M1", "M2_EDGE_WEIGHT", "M2_NODE_PAYLOAD", "M2_INJECTION_SEQUENCE", "M3"):
        return "ELIGIBLE"
    if final_domain == "M4_REQUIRED":
        return "INELIGIBLE"
    return "INDETERMINATE"


def build_matrix() -> dict[str, Any]:
    cells: list[dict[str, Any]] = []
    for sid, sub in SUBSTRATES.items():
        for N in N_GRID:
            t0 = time.time()
            v = verify_m3_eligibility(
                sub,
                N=N,
                lambda_value=LAMBDA,
                base_seed=BASE_SEED,
                null_seed=NULL_SEED,
            )
            dt = time.time() - t0
            m3_status = v.status
            m1 = M1_PRIOR[sid]
            m2_edge = M2_EDGE_PRIOR[sid]
            m2_node = M2_NODE_PRIOR[sid]
            m2_inj = M2_INJ_PRIOR[sid]
            final = _final_null_domain(sid, m1, m2_edge, m2_node, m2_inj, m3_status)
            cells.append(
                {
                    "substrate_id": sid,
                    "N": N,
                    "lambda_value": LAMBDA,
                    "base_seed": BASE_SEED,
                    "null_seed": NULL_SEED,
                    "M1": m1,
                    "M2_EDGE_WEIGHT": m2_edge,
                    "M2_NODE_PAYLOAD": m2_node,
                    "M2_INJECTION_SEQUENCE": m2_inj,
                    "M3": m3_status,
                    "FINAL_NULL_DOMAIN": final,
                    "B1_contribution": _b1_contribution(final),
                    "failure_reason": v.eligibility_reason if m3_status != "ELIGIBLE_M3" else "n/a",
                    "artifact_path": "artifacts/d002g/m3/m3_null_domain_verdicts.json",
                    "payload_sha256": (v.summary.summary_sha256 if v.summary is not None else None),
                    "verify_walltime_seconds": round(dt, 3),
                }
            )
    matrix = {
        "scope": {
            "lambda_value": LAMBDA,
            "base_seed": BASE_SEED,
            "null_seed": NULL_SEED,
            "N_grid": list(N_GRID),
            "substrates": list(SUBSTRATES.keys()),
        },
        "tolerances": {
            "tol_marginal": M3_TOL_MARGINAL,
            "tol_non_degenerate": M3_TOL_NON_DEGENERATE,
            "tol_density": M3_TOL_DENSITY,
            "tol_spectral_radius": M3_TOL_SPECTRAL_RADIUS,
            "tol_degree_wasserstein": M3_TOL_DEGREE_WASSERSTEIN,
        },
        "salt": M3_TOPOLOGY_CONDITIONED_SALT,
        "cells": cells,
    }
    # B1 closure decision aggregated across cells.
    eligible_substrates: set[str] = set()
    ineligible_substrates: set[str] = set()
    for c in cells:
        if c["B1_contribution"] == "ELIGIBLE":
            eligible_substrates.add(c["substrate_id"])
        elif c["B1_contribution"] == "INELIGIBLE":
            ineligible_substrates.add(c["substrate_id"])
    # All three substrates must be ELIGIBLE for B1 to close-for-eligibility.
    all_substrates = set(SUBSTRATES.keys())
    if eligible_substrates >= all_substrates:
        b1_status = "CLOSED_FOR_ELIGIBILITY_ONLY"
        decision = "M3_ELIGIBLE_FOR_BLOCKED_SUBSTRATES_B1_ELIGIBILITY_ONLY"
    elif eligible_substrates & all_substrates and ineligible_substrates & all_substrates:
        b1_status = "OPEN_REQUIRES_M4"
        if {"block_structured", "temporal_coupling"} <= ineligible_substrates:
            decision = "M3_INELIGIBLE_M4_REQUIRED"
        else:
            decision = "M3_PARTIAL_ELIGIBILITY_B1_STILL_OPEN"
    else:
        b1_status = "OPEN_REQUIRES_M4"
        decision = "M3_INELIGIBLE_M4_REQUIRED"
    matrix["b1_status"] = b1_status
    matrix["decision"] = decision
    matrix["canonical_run_authorized"] = False  # B2 still OPEN, no auth artifact
    matrix["d002c_ledger_touched"] = False
    return matrix


def main() -> None:
    matrix = build_matrix()
    out_dir = Path("artifacts/d002g/m3")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "m3_null_domain_verdicts.json"
    out_path.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"B1 status: {matrix['b1_status']}")
    print(f"Decision: {matrix['decision']}")
    print("Per-cell summary:")
    for c in matrix["cells"]:
        print(
            f"  {c['substrate_id']:22s} N={c['N']:3d}  M3={c['M3']:50s}  final={c['FINAL_NULL_DOMAIN']}"
        )


if __name__ == "__main__":
    main()
