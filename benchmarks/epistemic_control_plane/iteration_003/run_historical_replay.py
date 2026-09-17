#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geosync.epistemic.historical_replay import (  # noqa: E402
    default_historical_policies,
    load_historical_cases,
    run_historical_policy,
)

MANIFEST = ROOT / "benchmarks/epistemic_control_plane/iteration_003/historical_cases.json"
OUT = ROOT / "artifacts/epistemic_control_plane/iteration_003/historical_replay_results.json"


def main() -> int:
    cases = load_historical_cases(MANIFEST)
    payload = {
        "schema": "ecp-as-historical-replay-results/v1",
        "iteration": "003",
        "case_count": len(cases),
        "policies": {},
        "case_decisions": {},
    }
    for policy in default_historical_policies():
        metrics, decisions = run_historical_policy(policy, cases)
        payload["policies"][policy.name] = metrics.as_dict()
        payload["case_decisions"][policy.name] = [
            {
                "case_id": d.case_id,
                "action": d.action.value,
                "predicted_state": d.predicted_state.value,
                "reason": d.reason,
            }
            for d in decisions
        ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    ecp = payload["policies"]["ecp_as_external_adjudication"]
    if ecp["transition_conformance"] != len(cases):
        raise SystemExit("ECP-AS historical replay transition-conformance gate failed")
    if ecp["false_degradations"] or ecp["missed_degradations"] or ecp["false_falsifications"]:
        raise SystemExit("ECP-AS historical replay safety gate failed")
    print(json.dumps(ecp, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
