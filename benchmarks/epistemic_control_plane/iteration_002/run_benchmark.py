#!/usr/bin/env python3
"""Run ECP-AS Iteration 002 adversarial claim-promotion benchmark."""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from geosync.epistemic.benchmark import (
    build_core_scenarios,
    build_repository_negative_probes,
    default_policies,
    run_benchmark,
)


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_json_gz(path: Path, obj) -> None:
    payload = (json.dumps(obj, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))


def _scenario_record(s):
    return {
        "scenario_id": s.scenario_id,
        "current_state": s.claim.state.value,
        "target_state": s.target.value,
        "safe_to_promote": s.safe_to_promote,
        "failure_class": s.failure_class,
        "rationale": s.rationale,
        "source_ref": s.source_ref,
        "falsifier_executed": s.falsifier_executed,
        "evidence_kinds": [e.kind.value for e in s.evidence],
        "negative_evidence": [n.kind.value for n in s.negative_evidence],
        "oracle_count": len(s.oracles),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--out", default="artifacts/epistemic_control_plane/iteration_002")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)

    core = build_core_scenarios()
    repo_probes = build_repository_negative_probes(root)
    scenarios = core + repo_probes
    policies = default_policies()
    metrics = run_benchmark(scenarios, policies)

    decision_matrix = []
    for scenario in scenarios:
        decisions = {}
        for policy in policies:
            decision = policy.decide(scenario)
            decisions[policy.name] = {
                "allowed": decision.allowed,
                "reason": decision.reason,
            }
        decision_matrix.append(
            {
                "scenario_id": scenario.scenario_id,
                "safe_to_promote": scenario.safe_to_promote,
                "failure_class": scenario.failure_class,
                "decisions": decisions,
            }
        )

    manifest = [_scenario_record(s) for s in scenarios]
    _write_json_gz(out / "scenario_manifest.json.gz", manifest)
    failure_breakdown = {}
    for policy in policies:
        by_class = {}
        for scenario in scenarios:
            if scenario.safe_to_promote:
                continue
            decision = policy.decide(scenario)
            row = by_class.setdefault(
                scenario.failure_class,
                {"cases": 0, "unsafe_promotions": 0},
            )
            row["cases"] += 1
            if decision.allowed:
                row["unsafe_promotions"] += 1
        failure_breakdown[policy.name] = by_class

    result = {
        "benchmark": "ECP-AS Iteration 002 adversarial promotion benchmark",
        "scope": "synthetic adversarial policy benchmark plus repository-grounded negative-evidence probes",
        "scenario_count": len(scenarios),
        "core_synthetic_scenarios": len(core),
        "repository_negative_probes": len(repo_probes),
        "metrics": [m.as_dict() for m in metrics],
        "primary_claim_boundary": (
            "The benchmark measures policy behavior under declared adversarial cases. "
            "It does not establish real-world scientific truth or external workload generalization."
        ),
    }
    _write_json(out / "benchmark_results.json", result)
    _write_json_gz(out / "decision_matrix.json.gz", decision_matrix)
    _write_json_gz(out / "failure_class_breakdown.json.gz", failure_breakdown)

    ecp = next(m for m in metrics if m.policy == "ecp_as")
    strongest_baseline = next(m for m in metrics if m.policy == "artifact_chain_no_lineage")
    summary = {
        "ecp_as_unsafe_promotion_rate": ecp.unsafe_promotion_rate,
        "ecp_as_false_block_rate": ecp.false_block_rate,
        "artifact_chain_unsafe_promotion_rate": strongest_baseline.unsafe_promotion_rate,
        "absolute_unsafe_promotion_reduction_vs_artifact_chain": strongest_baseline.unsafe_promotion_rate - ecp.unsafe_promotion_rate,
        "ecp_as_correct": ecp.correct,
        "total": ecp.total,
    }
    _write_json(out / "primary_summary.json", summary)

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if ecp.unsafe_promotions == 0 and ecp.false_blocks == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
