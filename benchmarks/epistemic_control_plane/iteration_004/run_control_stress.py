#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geosync.epistemic.soundness_stress import load_soundness_slice, run_stress_suite  # noqa: E402

MANIFEST = ROOT / "benchmarks/epistemic_control_plane/iteration_004/soundnessbench_label_slice.json"
OUT = ROOT / "artifacts/epistemic_control_plane/iteration_004/control_stress_results.json"


def main() -> int:
    cases = load_soundness_slice(MANIFEST)
    payload = run_stress_suite(cases)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    optimistic = payload["profiles"]["optimistic_correlated"]
    ecp = optimistic["ecp_as_lineage_quorum"]
    raw = optimistic["raw_majority"]
    hidden = payload["profiles"]["hidden_common_cause"]["ecp_as_lineage_quorum"]
    if not ecp["unsafe_promotion_rate"] < raw["unsafe_promotion_rate"]:
        raise SystemExit("lineage quorum did not reduce unsafe promotion")
    if ecp["false_block_rate"] > 0.10:
        raise SystemExit("lineage quorum false-block rate exceeds declared bound")
    if hidden["unsafe_promotion_rate"] <= 0.10:
        raise SystemExit("hidden-common-cause boundary probe failed to expose residual risk")
    print(json.dumps({"optimistic": {"raw": raw, "ecp": ecp}, "hidden_ecp": hidden}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
