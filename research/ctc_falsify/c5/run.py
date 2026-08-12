# SPDX-License-Identifier: MIT
"""C5 orchestrator — decisive verdict on the C4 OPEN."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from research.ctc_falsify.c5 import config_c5 as c5
from research.ctc_falsify.c5.oracle import run_oracle


def _repro_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def decide(auc: float, disjoint: bool) -> str:
    if not disjoint:
        return c5.VERDICT_LEAKAGE
    if auc <= c5.AUC_CHANCE_HI:
        return c5.VERDICT_IDENTIFIABILITY_LIMIT
    if auc >= c5.AUC_SEPARABLE:
        return c5.VERDICT_ESTIMATOR_QUALITY_GAP
    return c5.VERDICT_AMBIGUOUS


def run() -> dict[str, Any]:
    o = run_oracle()
    verdict = decide(o.oos_auc, o.train_test_disjoint)
    cfg_hash = c5.config_hash()
    oracle = {
        "oos_auc": o.oos_auc,
        "n_train": o.n_train,
        "n_test": o.n_test,
        "n_features": o.n_features,
        "train_test_disjoint": o.train_test_disjoint,
    }
    result: dict[str, Any] = {
        "experiment_id": c5.C5_ID,
        "verdict": verdict,
        "claim": c5.CLAIM,
        "boundary": c5.BOUNDARY,
        "oracle": oracle,
        "thresholds": {
            "auc_chance_hi": c5.AUC_CHANCE_HI,
            "auc_separable": c5.AUC_SEPARABLE,
        },
        "config_hash": cfg_hash,
    }
    result["repro_hash"] = _repro_hash(
        {"verdict": verdict, "config_hash": cfg_hash, "oracle": oracle}
    )
    return result


def write_evidence(result: dict[str, Any]) -> str:
    c5.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    c5.RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return str(c5.RESULT_PATH)


def main() -> None:
    result = run()
    path = write_evidence(result)
    o = result["oracle"]
    print(f"EXPERIMENT: {result['experiment_id']}")
    print(f"VERDICT: {result['verdict']}")
    print(
        "ORACLE: OOS AUC="
        f"{o['oos_auc']:.4f} (limit<= {c5.AUC_CHANCE_HI}, "
        f"separable>= {c5.AUC_SEPARABLE}) "
        f"train={o['n_train']} test={o['n_test']} feats={o['n_features']} "
        f"disjoint={o['train_test_disjoint']}"
    )
    print(f"REPRO HASH: {result['repro_hash']}")
    print(f"ARTIFACT: {path}")
    if result["verdict"] == c5.VERDICT_IDENTIFIABILITY_LIMIT:
        print("=> C4 OPEN CLOSED: even a near-oracle cannot separate the")
        print("   channel from confounds here — an IDENTIFIABILITY LIMIT of")
        print("   these observables at this regime (strong boundary result).")
    elif result["verdict"] == c5.VERDICT_ESTIMATOR_QUALITY_GAP:
        print("=> C4 OPEN CLOSED: a sufficient statistic exists — the")
        print("   blindness is an ESTIMATOR-QUALITY gap, not identifiability.")
    elif result["verdict"] == c5.VERDICT_AMBIGUOUS:
        print("=> AMBIGUOUS: AUC between bands. Honest non-decision; the")
        print("   OPEN stays OPEN — needs a richer probe, not a forced call.")
    else:
        print("=> INADMISSIBLE: train/test leakage; verdict withheld.")


if __name__ == "__main__":
    main()
