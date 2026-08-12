#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002H Gate B — ricci_flow M1/M3 eligibility matrix.

Pre-registered at PR #683 (``docs/governance/D002H_PREREGISTRATION.yaml``,
merge sha ``1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5``). This script does
NOT modify the verifiers; it only invokes them and emits the verdict
matrix as a machine-readable artifact under
``artifacts/d002h/eligibility/d002h_ricci_eligibility.json``.

It is part of Gate B in the 7-gate canonical-run authorisation conjunction
(A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G) defined in
``docs/governance/D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md``. Gate B
PASS alone does NOT authorise canonical run — it only certifies that
ricci_flow is M1/M3-eligible at the locked canonical grid AT THIS COMMIT.

Eligibility methods
-------------------
* **M1 eligibility** — there is no public ``verify_m1_eligibility``
  symbol in :mod:`research.systemic_risk.d002g_null_mechanisms`. The
  M1 admissibility contract is encoded inside :func:`_realize_m1`:
  a cell is M1-ELIGIBLE iff
  ``realize_null(strategy="M1_INDEPENDENT_SEED", ...)`` succeeds
  (i.e. the substrate is seed-sensitive at this ``(N, lambda)``,
  raising :class:`BitIdenticalNullError` otherwise). This script
  invokes ``realize_null`` and translates the outcome into the
  ``ELIGIBLE_M1`` / ``INELIGIBLE_M1_BIT_IDENTICAL`` /
  ``INDETERMINATE_M1_*`` literal. No new verdict literal is coined —
  ``ELIGIBLE_M1`` and ``INELIGIBLE_M1_BIT_IDENTICAL`` are documented
  in the M1 module (the latter is the message body of
  :class:`BitIdenticalNullError`); the ``INDETERMINATE_M1_*`` family
  mirrors the M3 verifier's INDETERMINATE schema for symmetry.
* **M3 eligibility** — direct invocation of
  :func:`verify_m3_eligibility`. The module's contract refuses
  ``lambda_value <= 0`` by raising :class:`D002GNullInvalid`; cells
  with ``lambda_value == 0.0`` are therefore reported as
  ``N/A_M3_REQUIRES_LAMBDA_GT_ZERO`` per the M3 module's contract.

Scope guards
------------
* No new mechanism family. No new salt. No new tolerance constant.
* Reuses the deterministic seeding contract from
  :mod:`research.systemic_risk.d002g_null_mechanisms` exactly.
* Substrate code (``d002c_substrates.py``) and mechanism code
  (``d002g_null_mechanisms.py``) are NOT modified by this script.
* The script does NOT touch the D-002C claim ledger, does NOT
  start a canonical run, does NOT emit any canonical-run artifact.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Final

from research.systemic_risk.d002c_substrates import RicciFlowSubstrate
from research.systemic_risk.d002g_null_mechanisms import (
    M3_TOL_DEGREE_WASSERSTEIN,
    M3_TOL_DENSITY,
    M3_TOL_MARGINAL,
    M3_TOL_NON_DEGENERATE,
    M3_TOL_SPECTRAL_RADIUS,
    M3_TOPOLOGY_CONDITIONED_SALT,
    NULL_SEED_OFFSET,
    BitIdenticalNullError,
    D002GNullInvalid,
    realize_null,
    verify_m3_eligibility,
)

# Grid LOCKED at D002H_PREREGISTRATION.yaml — do NOT change without a
# fresh D-002J (or successor letter) pre-registration. Any drift is a
# governance violation and Gate C will fail-closed by definition.
LOCKED_N: Final[tuple[int, ...]] = (50, 100, 200)
LOCKED_LAMBDA: Final[tuple[float, ...]] = (0.0, 0.05, 0.10, 0.20, 0.40, 1.0)
LOCKED_BASE_SEED: Final[int] = 42
LOCKED_NULL_SEED_M3: Final[int] = 12345
SUBSTRATE_ID: Final[str] = "ricci_flow"

# Output path matches D002H_CANONICAL_RUN_AUTHORIZATION_GATES.md §B.
ARTIFACT_PATH: Final[Path] = Path("artifacts/d002h/eligibility/d002h_ricci_eligibility.json")

# Verdict literals — none of these are NEW; they all already exist in
# the M3 module or are spelled out in the M1 fail-closed message body.
M1_ELIGIBLE: Final[str] = "ELIGIBLE_M1"
M1_INELIGIBLE_BIT_IDENTICAL: Final[str] = "INELIGIBLE_M1_BIT_IDENTICAL"
M1_INDETERMINATE_PROVENANCE: Final[str] = "INDETERMINATE_M1_PROVENANCE_MISSING"
M3_NA_LAMBDA_ZERO: Final[str] = "N/A_M3_REQUIRES_LAMBDA_GT_ZERO"


def _evaluate_m1(substrate: RicciFlowSubstrate, *, N: int, lambda_value: float) -> dict[str, Any]:
    """Evaluate M1 eligibility by attempting realisation.

    Returns a small payload with ``status`` + diagnostics. Status is one of
    :data:`M1_ELIGIBLE`, :data:`M1_INELIGIBLE_BIT_IDENTICAL`,
    :data:`M1_INDETERMINATE_PROVENANCE`. No silent INELIGIBLE — any
    unexpected substrate exception surfaces as ``INDETERMINATE_M1_*``
    with the exception class name in metadata.
    """
    t0 = time.time()
    try:
        realization = realize_null(
            substrate,
            strategy="M1_INDEPENDENT_SEED",
            base_seed=LOCKED_BASE_SEED,
            N=int(N),
            lambda_value=float(lambda_value),
        )
    except BitIdenticalNullError as exc:
        return {
            "status": M1_INELIGIBLE_BIT_IDENTICAL,
            "eligibility_reason": str(exc),
            "evaluate_walltime_seconds": round(time.time() - t0, 3),
            "null_seed": LOCKED_BASE_SEED + NULL_SEED_OFFSET,
        }
    except D002GNullInvalid as exc:
        # Should not occur on ricci_flow at lambda >= 0, N >= 4. If it
        # does, document it honestly — fail the cell rather than silently
        # passing.
        return {
            "status": M1_INDETERMINATE_PROVENANCE,
            "eligibility_reason": f"realize_null rejected inputs: {exc!s}",
            "evaluate_walltime_seconds": round(time.time() - t0, 3),
            "null_seed": LOCKED_BASE_SEED + NULL_SEED_OFFSET,
        }
    except Exception as exc:
        # Substrate raised something we did not expect. Per the
        # operating law: no silent INELIGIBLE — record the type honestly
        # so downstream auditors can triage. Gate B FAILs on this cell.
        return {
            "status": M1_INDETERMINATE_PROVENANCE,
            "eligibility_reason": (f"substrate raised {type(exc).__name__}: {exc!s}"),
            "evaluate_walltime_seconds": round(time.time() - t0, 3),
            "null_seed": LOCKED_BASE_SEED + NULL_SEED_OFFSET,
        }

    return {
        "status": M1_ELIGIBLE,
        "eligibility_reason": "realize_null(strategy='M1_INDEPENDENT_SEED') succeeded",
        "evaluate_walltime_seconds": round(time.time() - t0, 3),
        "null_seed": int(realization.null_seed),
        "payload_sha256": str(realization.payload_sha256),
    }


def _evaluate_m3(substrate: RicciFlowSubstrate, *, N: int, lambda_value: float) -> dict[str, Any]:
    """Evaluate M3 eligibility by direct verifier invocation.

    Per the M3 module's contract, ``verify_m3_eligibility`` raises
    :class:`D002GNullInvalid` when ``lambda_value <= 0``. The caller
    must NOT invoke this helper for ``lambda_value == 0`` — those
    cells are reported as :data:`M3_NA_LAMBDA_ZERO` at the cell-
    assembly level.
    """
    t0 = time.time()
    verdict = verify_m3_eligibility(
        substrate,
        N=int(N),
        lambda_value=float(lambda_value),
        base_seed=LOCKED_BASE_SEED,
        null_seed=LOCKED_NULL_SEED_M3,
    )
    walltime = round(time.time() - t0, 3)
    match_payload: dict[str, Any] | None
    if verdict.match_report is not None:
        match_payload = {
            "degree_wasserstein": float(verdict.match_report.degree_wasserstein),
            "block_histogram_l1": float(verdict.match_report.block_histogram_l1),
            "spectral_radius_rel_err": float(verdict.match_report.spectral_radius_rel_err),
            "density_rel_err": float(verdict.match_report.density_rel_err),
            "all_within_tolerance": bool(verdict.match_report.all_within_tolerance),
            "failed_marginal": verdict.match_report.failed_marginal,
        }
    else:
        match_payload = None
    summary_sha: str | None = (
        verdict.summary.summary_sha256 if verdict.summary is not None else None
    )
    return {
        "status": str(verdict.status),
        "eligibility_reason": str(verdict.eligibility_reason),
        "match_report": match_payload,
        "summary_sha256": summary_sha,
        "evaluate_walltime_seconds": walltime,
        "null_seed": LOCKED_NULL_SEED_M3,
    }


def evaluate_cell(N: int, lambda_value: float) -> dict[str, Any]:
    """Evaluate one (N, λ) cell on ricci_flow and assemble the cell verdict."""
    substrate = RicciFlowSubstrate()
    m1_payload = _evaluate_m1(substrate, N=int(N), lambda_value=float(lambda_value))
    if lambda_value > 0.0:
        m3_payload = _evaluate_m3(substrate, N=int(N), lambda_value=float(lambda_value))
        m3_status = m3_payload["status"]
        m3_match = m3_payload["match_report"]
        m3_summary_sha = m3_payload["summary_sha256"]
        m3_reason = m3_payload["eligibility_reason"]
        m3_walltime = m3_payload["evaluate_walltime_seconds"]
        m3_null_seed: int | None = int(m3_payload["null_seed"])
    else:
        m3_status = M3_NA_LAMBDA_ZERO
        m3_match = None
        m3_summary_sha = None
        m3_reason = (
            "verify_m3_eligibility refuses lambda_value <= 0 per module "
            "contract (M3 conditions on K_precursor at lambda > 0)"
        )
        m3_walltime = 0.0
        m3_null_seed = None

    m1_ok = m1_payload["status"] == M1_ELIGIBLE
    m3_ok = (m3_status == "ELIGIBLE_M3") or (m3_status == M3_NA_LAMBDA_ZERO)
    cell_pass = bool(m1_ok and m3_ok)
    return {
        "substrate_id": SUBSTRATE_ID,
        "N": int(N),
        "lambda_value": float(lambda_value),
        "base_seed": LOCKED_BASE_SEED,
        "m1_status": m1_payload["status"],
        "m1_eligibility_reason": m1_payload["eligibility_reason"],
        "m1_null_seed": int(m1_payload["null_seed"]),
        "m1_payload_sha256": m1_payload.get("payload_sha256"),
        "m1_evaluate_walltime_seconds": m1_payload["evaluate_walltime_seconds"],
        "m3_status": m3_status,
        "m3_eligibility_reason": m3_reason,
        "m3_null_seed": m3_null_seed,
        "m3_match_report": m3_match,
        "m3_summary_sha256": m3_summary_sha,
        "m3_evaluate_walltime_seconds": m3_walltime,
        "cell_gate_b_pass": cell_pass,
    }


def build_payload() -> dict[str, Any]:
    """Build the Gate B artifact payload over the locked grid."""
    cells: list[dict[str, Any]] = []
    for N in LOCKED_N:
        for lam in LOCKED_LAMBDA:
            cells.append(evaluate_cell(int(N), float(lam)))
    all_pass = all(bool(c["cell_gate_b_pass"]) for c in cells)
    payload: dict[str, Any] = {
        "schema_version": "D002H-GATE-B-v1",
        "study_id": "D-002H",
        "gate": "B",
        "substrate_scope": [SUBSTRATE_ID],
        "grid": {
            "N": list(LOCKED_N),
            "lambda_values": list(LOCKED_LAMBDA),
            "base_seed": LOCKED_BASE_SEED,
            "null_seed_M3": LOCKED_NULL_SEED_M3,
        },
        "tolerances": {
            "tol_marginal": M3_TOL_MARGINAL,
            "tol_non_degenerate": M3_TOL_NON_DEGENERATE,
            "tol_density": M3_TOL_DENSITY,
            "tol_spectral_radius": M3_TOL_SPECTRAL_RADIUS,
            "tol_degree_wasserstein": M3_TOL_DEGREE_WASSERSTEIN,
        },
        "salt": M3_TOPOLOGY_CONDITIONED_SALT,
        "null_seed_offset_M1": NULL_SEED_OFFSET,
        "cells": cells,
        "n_cells_evaluated": len(cells),
        "n_cells_pass": sum(1 for c in cells if bool(c["cell_gate_b_pass"])),
        "gate_b_verdict": "PASS" if all_pass else "FAIL",
        "canonical_run_authorized": False,
        "downstream_gates_remaining": ["C", "D", "E", "F", "G"],
        "d002h_prereg_path": "docs/governance/D002H_PREREGISTRATION.yaml",
        "d002h_prereg_parent_merge_sha": ("1b59ce5326a8e8bd8aaaf9666a06075d34b4f6a5"),
        "d002c_ledger_touched": False,
        "substrate_code_edited": False,
        "mechanism_code_edited": False,
    }
    return payload


def main() -> int:
    payload = build_payload()
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    verdict = payload["gate_b_verdict"]
    n_pass = payload["n_cells_pass"]
    n_total = payload["n_cells_evaluated"]
    print(f"wrote {ARTIFACT_PATH}")
    print(f"Gate B verdict: {verdict} ({n_pass}/{n_total} cells PASS)")
    print(
        "canonical_run_authorized: False (Gate B alone is one term of the "
        "A ∧ B ∧ C ∧ D ∧ E ∧ F ∧ G conjunction)"
    )
    for cell in payload["cells"]:
        print(
            f"  N={cell['N']:3d} λ={cell['lambda_value']:.2f}  "
            f"M1={cell['m1_status']:35s} "
            f"M3={cell['m3_status']:35s} "
            f"pass={cell['cell_gate_b_pass']}"
        )
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
