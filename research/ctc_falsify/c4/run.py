# SPDX-License-Identifier: MIT
"""C4 orchestrator — schema-valid, hash-bound self-audit verdict."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from research.ctc_falsify.c4 import config_c4 as c4
from research.ctc_falsify.c4.audit import decide, run_audit


def _repro_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run() -> dict[str, Any]:
    a = run_audit()
    verdict = decide(a)
    cfg_hash = c4.config_hash()
    audit = {
        "cohens_d": a.cohens_d,
        "decision_boundary": a.decision_boundary,
        "confound_false_positive_rate": a.confound_false_positive_rate,
        "signflip_pass_fraction": a.signflip_pass_fraction,
        "sweep_false_positive_count": a.sweep_false_positive_count,
        "sweep_total": a.sweep_total,
        "g1_separable": a.g1_separable,
        "g2_confounds_rejected": a.g2_confounds_rejected,
        "g3_signflip_ok": a.g3_signflip_ok,
        "g4_sweep_clean": a.g4_sweep_clean,
    }
    result: dict[str, Any] = {
        "experiment_id": c4.C4_ID,
        "verdict": verdict,
        "claim": c4.CLAIM,
        "boundary": c4.BOUNDARY,
        "audited_estimator": "mean gamma-band phase offset (the C3 boundary probe)",
        "audit": audit,
        "thresholds": {
            "d_min": c4.D_MIN,
            "fp_max": c4.FP_MAX,
            "sign_frac": c4.SIGN_FRAC,
        },
        "config_hash": cfg_hash,
    }
    result["repro_hash"] = _repro_hash(
        {"verdict": verdict, "config_hash": cfg_hash, "audit": audit}
    )
    return result


def write_evidence(result: dict[str, Any]) -> str:
    c4.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    c4.RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return str(c4.RESULT_PATH)


def main() -> None:
    result = run()
    path = write_evidence(result)
    au = result["audit"]
    print(f"EXPERIMENT: {result['experiment_id']}")
    print(f"VERDICT: {result['verdict']}")
    print(
        "AUDIT: d="
        f"{au['cohens_d']:.3f} (min {c4.D_MIN}) "
        f"fp={au['confound_false_positive_rate']:.3f} (max {c4.FP_MAX}) "
        f"signflip={au['signflip_pass_fraction']:.3f} (min {c4.SIGN_FRAC}) "
        f"sweep_fp={au['sweep_false_positive_count']}/{au['sweep_total']}"
    )
    print(
        "GATES: G1="
        f"{au['g1_separable']} G2={au['g2_confounds_rejected']} "
        f"G3={au['g3_signflip_ok']} G4={au['g4_sweep_clean']}"
    )
    print(f"REPRO HASH: {result['repro_hash']}")
    print(f"ARTIFACT: {path}")
    if result["verdict"] == c4.VERDICT_BOUNDARY_HARDENED:
        print("=> C3 in-silico negative HARDENS: the boundary probe is vetted.")
    else:
        print("=> C3 'recoverable in principle' is SCOPED/RETRACTED, not the")
        print("   standard-estimand blindness. The instrument caught its own lie.")


if __name__ == "__main__":
    main()
