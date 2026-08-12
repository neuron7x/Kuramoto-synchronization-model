# SPDX-License-Identifier: MIT
"""CTC-FALSIFY-001 orchestrator — emits a schema-valid, hash-bound result.

A clean ``INADMISSIBLE_*`` verdict is the designed pre-data success.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from research.ctc_falsify import config as cfg
from research.ctc_falsify.gates import decide, run_diagnostic


def _repro_hash(payload: dict[str, Any]) -> str:
    """Bind the verdict AND every diagnostic input — not merely a number."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def run() -> dict[str, Any]:
    diag = run_diagnostic()
    verdict = decide(diag, groundtruth_available=True, real_data=False)
    cfg_hash = cfg.config_hash()

    confound = {
        "n1_common_drive_false_positive_rate": diag.null_false_positive_rate["N1_COMMON_DRIVE"],
        "n2_rate_false_positive_rate": diag.null_false_positive_rate["N2_RATE"],
        "n3_snr_false_positive_rate": diag.null_false_positive_rate["N3_SNR"],
        "mean_null_plv": diag.mean_null_plv,
    }
    positive_control = {
        "nplus_recovery_rate": diag.nplus_recovery_rate,
        "nplus_min_required": cfg.NPLUS_MIN_RECOVERY,
        "mean_nplus_plv": diag.mean_nplus_plv,
        "recovered": diag.nplus_recovery_rate >= cfg.NPLUS_MIN_RECOVERY,
    }

    result: dict[str, Any] = {
        "experiment_id": cfg.EXPERIMENT_ID,
        "verdict": verdict,
        "claim": cfg.CLAIM,
        "boundary": cfg.BOUNDARY,
        "generative_groundtruth": "two-population Sakaguchi-Kuramoto, toggleable A->B channel",
        "standard_pipeline": "gamma band-pass -> Hilbert PLV + magnitude-squared coherence",
        "canonical_thresholds": {"plv": cfg.CANON_PLV, "coherence": cfg.CANON_COH},
        "positive_control": positive_control,
        "confound_diagnostic": confound,
        "n_seeds": diag.n_seeds,
        "readout_independent_of_groundtruth": diag.readout_independent_of_groundtruth,
        "real_data_bound": False,
        "config_hash": cfg_hash,
    }
    result["repro_hash"] = _repro_hash(
        {
            "verdict": verdict,
            "config_hash": cfg_hash,
            "confound_diagnostic": confound,
            "positive_control": positive_control,
            "n_seeds": diag.n_seeds,
            "readout_independent_of_groundtruth": diag.readout_independent_of_groundtruth,
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
    cd = result["confound_diagnostic"]
    pc = result["positive_control"]
    print(f"EXPERIMENT: {result['experiment_id']}")
    print(f"VERDICT: {result['verdict']}")
    print(
        "POSITIVE CONTROL N+: recovery="
        f"{pc['nplus_recovery_rate']:.3f} (min {pc['nplus_min_required']}) "
        f"recovered={pc['recovered']}"
    )
    print(
        "CONFOUND FALSE-POSITIVE RATES @ canonical threshold: "
        f"N1={cd['n1_common_drive_false_positive_rate']:.3f} "
        f"N2={cd['n2_rate_false_positive_rate']:.3f} "
        f"N3={cd['n3_snr_false_positive_rate']:.3f}"
    )
    print(f"REPRO HASH: {result['repro_hash']}")
    print(f"ARTIFACT: {path}")
    print(f"BOUNDARY: {result['boundary']}")
    print(
        "NEXT: bind a real LFP+spike dataset (L2) to attempt KILLED_SCOPED; "
        "a clean INADMISSIBLE here is the designed pre-data success"
    )


if __name__ == "__main__":
    main()
