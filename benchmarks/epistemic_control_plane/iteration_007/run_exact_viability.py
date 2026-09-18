#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geosync.epistemic.quorum_viability import (  # noqa: E402
    ViabilityStatus,
    classify_viability,
    exact_quorum_interval,
    load_exact_marginals,
    scan_distinct_model_triplets,
)

SOURCE = ROOT / "benchmarks/epistemic_control_plane/iteration_005/soundnessbench_leaderboard_marginals.json"
OUT = ROOT / "artifacts/epistemic_control_plane/iteration_007/exact_viability_results.json"

FROZEN_IDS = {
    "LLaMA-3.3-70B-Instruct::standard",
    "Claude-Opus-4-6::aggressive",
    "GPT-5.4-Mini::aggressive",
}


def main() -> int:
    rows = load_exact_marginals(SOURCE)
    frozen = tuple(row for row in rows if row.evaluator_id in FROZEN_IDS)
    if len(frozen) != 3:
        raise SystemExit("frozen triplet not found")
    frozen_bounds = exact_quorum_interval(frozen, required_support=2)
    frozen_verdict = classify_viability(frozen_bounds)
    verdicts = scan_distinct_model_triplets(rows)
    counts = Counter(v.status.value for v in verdicts)
    by_support = Counter((v.bounds.required_support, v.status.value) for v in verdicts)
    payload = {
        "schema": "ecp-as-exact-quorum-viability/v1",
        "iteration": "007",
        "source_manifest": str(SOURCE.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "risk_budgets": {"unsafe": "1/10", "false_block": "1/5"},
        "frozen_triplet": frozen_verdict.as_dict(),
        "global_scan": {
            "total": len(verdicts),
            "counts": dict(sorted(counts.items())),
            "by_support": {
                f"{support}-of-3::{status}": count
                for (support, status), count in sorted(by_support.items())
            },
            "impossible_fraction": str(Fraction(counts[ViabilityStatus.IMPOSSIBLE.value], len(verdicts))),
            "unresolved_fraction": str(Fraction(counts[ViabilityStatus.UNRESOLVED.value], len(verdicts))),
        },
        "claim_boundary": (
            "This exact scan uses published aggregate marginals only. IMPOSSIBLE means no compatible dependence "
            "structure can meet the configured budgets; UNRESOLVED still requires aligned per-case joint outputs."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if frozen_verdict.status is not ViabilityStatus.IMPOSSIBLE:
        raise SystemExit("frozen quorum must be classified IMPOSSIBLE")
    if frozen_bounds.unsafe_min != Fraction(129, 500):
        raise SystemExit("unsafe lower bound mismatch")
    if frozen_bounds.false_block_min != Fraction(167, 500):
        raise SystemExit("false-block lower bound mismatch")
    if counts != Counter({"IMPOSSIBLE": 3398, "UNRESOLVED": 122}):
        raise SystemExit(f"global viability counts changed: {counts}")
    print(json.dumps(payload["global_scan"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
