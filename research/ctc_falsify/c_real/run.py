# SPDX-License-Identifier: MIT
"""C-real orchestrator — pre-data: emits the designed fail-closed
INADMISSIBLE_NO_PAIRED_DATA, schema-valid and hash-bound. No data touched.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from research.ctc_falsify.c_real import config_c_real as cr
from research.ctc_falsify.c_real.gate import decide


def _repro_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def run() -> dict[str, Any]:
    verdict = decide(dataset_bound=False)  # pre-data, by construction
    cfg_hash = cr.config_hash()
    result: dict[str, Any] = {
        "experiment_id": cr.C_REAL_ID,
        "verdict": verdict,
        "claim": cr.CLAIM,
        "boundary": cr.BOUNDARY,
        "estimator": cr.ESTIMATOR,
        "primary_endpoint": cr.PRIMARY_ENDPOINT,
        "dataset_selection_rule": {
            "inclusion": list(cr.DATASET_INCLUSION),
            "source_order": list(cr.DATASET_SOURCE_ORDER),
        },
        "thresholds": {
            "auc_support_min": cr.AUC_SUPPORT_MIN,
            "auc_chance_hi": cr.AUC_CHANCE_HI,
            "mde_auc": cr.MDE_AUC,
            "min_sessions": cr.MIN_SESSIONS,
            "holm_alpha": cr.HOLM_ALPHA,
        },
        "dataset_bound": False,
        "config_hash": cfg_hash,
    }
    result["repro_hash"] = _repro_hash(
        {"verdict": verdict, "config_hash": cfg_hash, "dataset_bound": False}
    )
    return result


def write_evidence(result: dict[str, Any]) -> str:
    cr.EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    cr.RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return str(cr.RESULT_PATH)


def main() -> None:
    result = run()
    path = write_evidence(result)
    print(f"EXPERIMENT: {result['experiment_id']}")
    print(f"VERDICT: {result['verdict']}")
    print(f"ESTIMATOR (pre-committed): {result['estimator']}")
    print(f"REPRO HASH: {result['repro_hash']}")
    print(f"ARTIFACT: {path}")
    print(f"BOUNDARY: {result['boundary']}")
    print(
        "NEXT: C-real-data binds the FIRST dataset satisfying the frozen "
        "selection rule under its A-gate; only then are KILLED_SCOPED / "
        "SURVIVED_INITIAL reachable. A clean INADMISSIBLE here is the "
        "designed pre-data success."
    )


if __name__ == "__main__":
    main()
