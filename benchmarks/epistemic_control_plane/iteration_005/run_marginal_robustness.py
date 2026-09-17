#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geosync.epistemic.dependence_bounds import (  # noqa: E402
    EvaluatorMarginal,
    search_triplet_quorums,
)

MANIFEST = ROOT / "benchmarks/epistemic_control_plane/iteration_005/soundnessbench_leaderboard_marginals.json"
OUT = ROOT / "artifacts/epistemic_control_plane/iteration_005/marginal_robustness_results.json"

MAX_UNSAFE = 0.10
MAX_FALSE_BLOCK = 0.20


def load_rows():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows = []
    for item in payload["evaluators"]:
        mode = item["mode"]
        model = item["model"]
        rows.append(
            EvaluatorMarginal(
                evaluator_id=f"{model}::{mode}",
                model=model,
                mode=mode,
                fp_rate=float(item["fp_rate"]),
                fn_rate=float(item["fn_rate"]),
                source_ref=payload["source"]["project_url"],
            )
        )
    return tuple(rows), payload["source"]


def main() -> int:
    rows, source = load_rows()
    certificates = search_triplet_quorums(
        rows,
        max_unsafe=MAX_UNSAFE,
        max_false_block=MAX_FALSE_BLOCK,
        distinct_models=True,
    )
    certified = tuple(cert for cert in certificates if cert.certified)
    best = certificates[0]
    payload = {
        "schema": "ecp-as-marginal-robustness/v1",
        "iteration": "005",
        "source": source,
        "evaluator_config_count": len(rows),
        "candidate_triplet_quorum_count": len(certificates),
        "risk_limits": {
            "max_unsafe": MAX_UNSAFE,
            "max_false_block": MAX_FALSE_BLOCK,
        },
        "certified_count": len(certified),
        "best_minimax_candidate": best.as_dict(),
        "top_10": [cert.as_dict() for cert in certificates[:10]],
        "claim_boundary": (
            "Bounds optimize over every joint Bernoulli distribution compatible with the published "
            "marginal FP/FN rates. They do not estimate actual cross-model dependence."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if len(certified) != 0:
        raise SystemExit("unexpected marginal-only robust certificate")
    if best.bounds.minimax_error < 0.30:
        raise SystemExit("best worst-case risk unexpectedly below declared falsification threshold")
    print(json.dumps(payload["best_minimax_candidate"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
