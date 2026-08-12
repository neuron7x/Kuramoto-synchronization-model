# SPDX-License-Identifier: MIT
"""CTC-FALSIFY-001 L2 orchestrator — schema-valid, hash-bound, fail-closed.

Pre-data reference verdict: INADMISSIBLE_NO_PAIRED_DATA (designed success)
after the L2 estimator passes its in-silico self-validation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from research.ctc_falsify.l2 import config_l2 as cfg
from research.ctc_falsify.l2.gates_l2 import decide_l2, run_self_validation


def _repro_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run() -> dict[str, Any]:
    v = run_self_validation()
    verdict = decide_l2(v, real_dataset_bound=False)
    cfg_hash = cfg.config_hash()

    self_validation = {
        "surrogate_all_matched": v.surrogate_all_matched,
        "mean_nplus_residual_z": v.mean_nplus_residual_z,
        "max_confound_residual_z": v.max_confound_residual_z,
        "nplus_recovered": v.nplus_recovered,
        "confounds_not_flagged": v.confounds_not_flagged,
        "n_validation_seeds": v.n_validation_seeds,
        "worst_rate_rel_err": v.worst_rate_rel_err,
        "worst_power_rel_err": v.worst_power_rel_err,
    }
    result: dict[str, Any] = {
        "experiment_id": cfg.L2_ID,
        "verdict": verdict,
        "claim": cfg.CLAIM,
        "boundary": cfg.BOUNDARY,
        "estimand": "standardized_residual_z = (SFC_obs - mean(SFC_surr)) / std(SFC_surr)",
        "primary_endpoint": "fraction of pair-directions with residual_z > Z_GATE",
        "joint_surrogate": "phase-randomized B, envelope-reimposed, A fixed (rate+power+common-drive matched)",
        "self_validation": self_validation,
        "thresholds": {
            "z_gate": cfg.Z_GATE,
            "nplus_residual_min_z": cfg.NPLUS_RESIDUAL_MIN_Z,
            "confound_residual_max_z": cfg.CONFOUND_RESIDUAL_MAX_Z,
            "symmetric_alpha": cfg.SYMMETRIC_ALPHA,
            "symmetric_delta": cfg.SYMMETRIC_DELTA,
            "mde_residual_z": cfg.MDE_RESIDUAL_Z,
            "min_sessions": cfg.MIN_SESSIONS,
        },
        "real_dataset_bound": False,
        "config_hash": cfg_hash,
    }
    result["repro_hash"] = _repro_hash(
        {
            "verdict": verdict,
            "config_hash": cfg_hash,
            "self_validation": self_validation,
        }
    )
    return result


def write_evidence(result: dict[str, Any]) -> str:
    cfg.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    cfg.RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return str(cfg.RESULT_PATH)


def main() -> None:
    result = run()
    path = write_evidence(result)
    sv = result["self_validation"]
    print(f"EXPERIMENT: {result['experiment_id']}")
    print(f"VERDICT: {result['verdict']}")
    print(
        "SELF-VALIDATION: surrogate_matched="
        f"{sv['surrogate_all_matched']} nplus_z={sv['mean_nplus_residual_z']:.3f} "
        f"(min {cfg.NPLUS_RESIDUAL_MIN_Z}) max_confound_z={sv['max_confound_residual_z']:.3f} "
        f"(max {cfg.CONFOUND_RESIDUAL_MAX_Z})"
    )
    print(
        "SURROGATE MATCH worst rel-err: rate="
        f"{sv['worst_rate_rel_err']:.4f} power={sv['worst_power_rel_err']:.4f}"
    )
    print(f"REPRO HASH: {result['repro_hash']}")
    print(f"ARTIFACT: {path}")
    print(f"BOUNDARY: {result['boundary']}")
    print(
        "NEXT: C3 — bind a pre-committed real LFP+spike dataset; only then are "
        "KILLED_SCOPED/SURVIVED_INITIAL reachable. Clean INADMISSIBLE here is "
        "the designed pre-data success."
    )


if __name__ == "__main__":
    main()
