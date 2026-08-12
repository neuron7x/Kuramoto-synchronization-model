# SPDX-License-Identifier: MIT
"""C3 orchestrator — v2 time-reversed-surrogate estimator self-validation.

Reuses the L2 verdict logic (`decide_l2`) and the SAME admissibility bar.
Only the estimator changed (v1 phase-randomization -> v2 directed PSI with a
time-reversed surrogate). Honest outcome is reported with no threshold
tuning: if v2 is still blind -> INADMISSIBLE_NPLUS_INSITU_BLIND; if it
clears the bar -> INADMISSIBLE_NO_PAIRED_DATA (estimator admissible, real
data still unbound — C3-data is the next cycle).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from research.ctc_falsify import config as l1
from research.ctc_falsify.generative import draw_n_plus, draw_null
from research.ctc_falsify.l2 import config_l2 as cfg
from research.ctc_falsify.l2.estimator_v2 import directed_residual_v2
from research.ctc_falsify.l2.gates_l2 import L2SelfValidation, decide_l2


def run_self_validation_v2() -> L2SelfValidation:
    seeds = [l1.SEED + i for i in range(cfg.N_VALIDATION_SEEDS)]
    nplus_z = [directed_residual_v2(draw_n_plus(s), s).residual_z for s in seeds]
    confound_z: list[float] = []
    for fam in l1.NULL_FAMILIES:
        confound_z += [directed_residual_v2(draw_null(s, fam), s).residual_z for s in seeds]

    mean_nplus = float(sum(nplus_z) / len(nplus_z))
    max_conf = max(confound_z)
    return L2SelfValidation(
        surrogate_all_matched=True,  # time reversal preserves spectrum exactly
        mean_nplus_residual_z=mean_nplus,
        max_confound_residual_z=max_conf,
        nplus_recovered=mean_nplus >= cfg.NPLUS_RESIDUAL_MIN_Z,
        confounds_not_flagged=max_conf <= cfg.CONFOUND_RESIDUAL_MAX_Z,
        n_validation_seeds=len(seeds),
        worst_rate_rel_err=0.0,
        worst_power_rel_err=0.0,
    )


def _repro_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run() -> dict[str, Any]:
    v = run_self_validation_v2()
    verdict = decide_l2(v, real_dataset_bound=False)
    cfg_hash = cfg.config_hash()
    sv = {
        "estimator_version": cfg.ESTIMATOR_VERSION,
        "mean_nplus_residual_z": v.mean_nplus_residual_z,
        "max_confound_residual_z": v.max_confound_residual_z,
        "nplus_recovered": v.nplus_recovered,
        "confounds_not_flagged": v.confounds_not_flagged,
        "n_validation_seeds": v.n_validation_seeds,
    }
    result: dict[str, Any] = {
        "experiment_id": "CTC-FALSIFY-001-L2V2",
        "verdict": verdict,
        "estimator": "time-reversed-surrogate directed Phase-Slope Index (Nolte 2008)",
        "claim": cfg.CLAIM,
        "boundary": cfg.BOUNDARY,
        "self_validation": sv,
        "thresholds": {
            "nplus_residual_min_z": cfg.NPLUS_RESIDUAL_MIN_Z,
            "confound_residual_max_z": cfg.CONFOUND_RESIDUAL_MAX_Z,
        },
        "real_dataset_bound": False,
        "config_hash": cfg_hash,
    }
    result["repro_hash"] = _repro_hash(
        {"verdict": verdict, "config_hash": cfg_hash, "self_validation": sv}
    )
    return result


def write_evidence(result: dict[str, Any]) -> str:
    cfg.V2_RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    cfg.V2_RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return str(cfg.V2_RESULT_PATH)


def main() -> None:
    result = run()
    path = write_evidence(result)
    sv = result["self_validation"]
    print(f"EXPERIMENT: {result['experiment_id']}  ESTIMATOR: {sv['estimator_version']}")
    print(f"VERDICT: {result['verdict']}")
    print(
        "SELF-VALIDATION: nplus_z="
        f"{sv['mean_nplus_residual_z']:.3f} (min {cfg.NPLUS_RESIDUAL_MIN_Z}) "
        f"max_confound_z={sv['max_confound_residual_z']:.3f} "
        f"(max {cfg.CONFOUND_RESIDUAL_MAX_Z}) "
        f"recovered={sv['nplus_recovered']} clean={sv['confounds_not_flagged']}"
    )
    print(f"REPRO HASH: {result['repro_hash']}")
    print(f"ARTIFACT: {path}")
    print(
        "NEXT: if recovered -> C4 bind pre-committed real LFP+spike dataset; "
        "if still blind -> next estimator family. No threshold tuning."
    )


if __name__ == "__main__":
    main()
