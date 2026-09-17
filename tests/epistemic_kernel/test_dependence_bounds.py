from pathlib import Path
import json
import unittest

from geosync.epistemic.dependence_bounds import (
    EvaluatorMarginal,
    RiskCertifiedLineageQuorumPolicy,
    certify_quorum,
    quorum_risk_bounds,
    search_triplet_quorums,
)
from geosync.epistemic.evaluator_control import EvaluatorObservation, LineageQuorumPolicy
from geosync.epistemic.models import Claim, Oracle, OracleIndependence

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "benchmarks/epistemic_control_plane/iteration_005/soundnessbench_leaderboard_marginals.json"
FULL = OracleIndependence(True, True, True, True)


def load_rows():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return tuple(
        EvaluatorMarginal(
            evaluator_id=f"{item['model']}::{item['mode']}",
            model=item["model"],
            mode=item["mode"],
            fp_rate=float(item["fp_rate"]),
            fn_rate=float(item["fn_rate"]),
            source_ref=payload["source"]["project_url"],
        )
        for item in payload["evaluators"]
    )


class DependenceBoundsTests(unittest.TestCase):
    def test_symmetric_three_way_quorum_bound(self):
        rows = tuple(
            EvaluatorMarginal(f"e{i}", f"m{i}", "standard", 0.10, 0.10)
            for i in range(3)
        )
        bounds = quorum_risk_bounds(rows, required_support=2)
        self.assertAlmostEqual(bounds.unsafe_max, 0.15, places=9)
        self.assertAlmostEqual(bounds.unsafe_min, 0.0, places=9)
        self.assertAlmostEqual(bounds.unsafe_independence, 0.028, places=9)

    def test_marginal_only_certificate_fails_when_worst_case_is_large(self):
        rows = (
            EvaluatorMarginal("a", "a", "standard", 0.05, 0.10),
            EvaluatorMarginal("b", "b", "standard", 0.05, 0.10),
            EvaluatorMarginal("c", "c", "standard", 0.05, 0.10),
        )
        cert = certify_quorum(
            rows,
            required_support=2,
            max_unsafe=0.05,
            max_false_block=0.20,
        )
        self.assertFalse(cert.certified)
        self.assertIn("unsafe_max", cert.reason)

    def test_public_leaderboard_manifest_has_24_configurations(self):
        rows = load_rows()
        self.assertEqual(len(rows), 24)
        self.assertEqual(len({row.evaluator_id for row in rows}), 24)

    def test_no_distinct_model_triplet_is_robustly_certified(self):
        certs = search_triplet_quorums(
            load_rows(), max_unsafe=0.10, max_false_block=0.20, distinct_models=True
        )
        self.assertGreater(len(certs), 0)
        self.assertFalse(any(cert.certified for cert in certs))

    def test_best_minimax_candidate_remains_high_risk(self):
        certs = search_triplet_quorums(
            load_rows(), max_unsafe=0.10, max_false_block=0.20, distinct_models=True
        )
        best = certs[0]
        self.assertEqual(best.bounds.required_support, 2)
        self.assertAlmostEqual(best.bounds.unsafe_max, 0.278, places=9)
        self.assertAlmostEqual(best.bounds.false_block_max, 0.342, places=9)
        self.assertGreater(best.bounds.minimax_error, 0.30)

    def test_independence_assumption_is_not_used_as_robust_bound(self):
        rows = tuple(
            EvaluatorMarginal(f"e{i}", f"m{i}", "standard", 0.10, 0.10)
            for i in range(3)
        )
        bounds = quorum_risk_bounds(rows, required_support=2)
        self.assertGreater(bounds.unsafe_max, bounds.unsafe_independence)

    def test_risk_certificate_can_block_live_lineage_quorum(self):
        rows = tuple(
            EvaluatorMarginal(f"e{i}", f"m{i}", "standard", 0.10, 0.10)
            for i in range(3)
        )
        cert = certify_quorum(
            rows,
            required_support=2,
            max_unsafe=0.05,
            max_false_block=0.20,
        )
        base = LineageQuorumPolicy(min_admissible=3, required_support=2)
        policy = RiskCertifiedLineageQuorumPolicy(cert, base_policy=base)
        claim = Claim(
            "c", "p", "benchmark", "proposal", generator_ancestors=frozenset({"research"})
        )
        observations = tuple(
            EvaluatorObservation(
                Oracle(f"o{i}", "c", f"d{i}", FULL, frozenset({f"ext:{i}"})),
                True,
            )
            for i in range(3)
        )
        decision = policy.decide(claim, observations)
        self.assertFalse(decision.promoted)
        self.assertTrue(any("distributionally robust" in item for item in decision.blockers))

    def test_certified_low_risk_certificate_does_not_override_live_dissent(self):
        rows = (
            EvaluatorMarginal("a", "a", "standard", 0.0, 0.0),
            EvaluatorMarginal("b", "b", "standard", 0.0, 0.0),
            EvaluatorMarginal("c", "c", "standard", 0.0, 0.0),
        )
        cert = certify_quorum(
            rows,
            required_support=2,
            max_unsafe=0.01,
            max_false_block=0.01,
        )
        self.assertTrue(cert.certified)
        policy = RiskCertifiedLineageQuorumPolicy(cert)
        claim = Claim(
            "c", "p", "benchmark", "proposal", generator_ancestors=frozenset({"research"})
        )
        observations = (
            EvaluatorObservation(Oracle("a", "c", "a", FULL, frozenset({"ext:a"})), True),
            EvaluatorObservation(Oracle("b", "c", "b", FULL, frozenset({"ext:b"})), False),
            EvaluatorObservation(Oracle("c", "c", "c", FULL, frozenset({"ext:c"})), False),
        )
        self.assertFalse(policy.decide(claim, observations).promoted)


if __name__ == "__main__":
    unittest.main()
