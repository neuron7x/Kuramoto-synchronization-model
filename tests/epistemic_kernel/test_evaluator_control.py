from pathlib import Path
import unittest

from geosync.epistemic.evaluator_control import (
    EvaluatorObservation,
    LineageQuorumPolicy,
    QuorumAction,
    synthesize_quorum_oracle,
)
from geosync.epistemic.models import Claim, Oracle, OracleIndependence
from geosync.epistemic.soundness_stress import (
    default_profiles,
    evaluate_profile,
    load_soundness_slice,
    run_stress_suite,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "benchmarks/epistemic_control_plane/iteration_004/soundnessbench_label_slice.json"
FULL = OracleIndependence(True, True, True, True)


def oracle(oid, claim_id, ancestors):
    return Oracle(oid, claim_id, f"digest:{oid}", FULL, frozenset(ancestors))


class EvaluatorControlTests(unittest.TestCase):
    def setUp(self):
        self.claim = Claim(
            "c", "p", "benchmark", "proposal", generator_ancestors=frozenset({"research:family"})
        )
        self.policy = LineageQuorumPolicy(min_admissible=3, required_support=2)

    def test_research_plane_clones_cannot_authorize(self):
        obs = [
            EvaluatorObservation(oracle("self", "c", {"research:family"}), True),
            EvaluatorObservation(oracle("sibling", "c", {"research:family"}), True),
            EvaluatorObservation(oracle("ext-a", "c", {"ext:a"}), True),
            EvaluatorObservation(oracle("ext-b", "c", {"ext:b"}), False),
            EvaluatorObservation(oracle("ext-c", "c", {"ext:c"}), False),
        ]
        decision = self.policy.decide(self.claim, obs)
        self.assertEqual(decision.action, QuorumAction.HOLD)
        self.assertIn("self", decision.excluded_oracle_ids)
        self.assertIn("sibling", decision.excluded_oracle_ids)

    def test_two_of_three_independent_supports_promote(self):
        obs = [
            EvaluatorObservation(oracle("a", "c", {"ext:a"}), True),
            EvaluatorObservation(oracle("b", "c", {"ext:b"}), True),
            EvaluatorObservation(oracle("c", "c", {"ext:c"}), False),
        ]
        decision = self.policy.decide(self.claim, obs)
        self.assertTrue(decision.promoted)
        self.assertEqual(decision.support_count, 2)
        self.assertEqual(decision.admissible_count, 3)

    def test_successful_quorum_emits_admission_compatible_aggregate_oracle(self):
        obs = [
            EvaluatorObservation(oracle("a", "c", {"ext:a"}), True),
            EvaluatorObservation(oracle("b", "c", {"ext:b"}), True),
            EvaluatorObservation(oracle("c", "c", {"ext:c"}), False),
        ]
        decision = self.policy.decide(self.claim, obs)
        aggregate = synthesize_quorum_oracle(self.claim, obs, decision)
        self.assertEqual(aggregate.claim_id, "c")
        self.assertEqual(aggregate.ancestors, frozenset({"ext:a", "ext:b", "ext:c"}))
        self.assertTrue(aggregate.independence.fully_independent)

    def test_hold_cannot_emit_aggregate_oracle(self):
        obs = [
            EvaluatorObservation(oracle("a", "c", {"ext:a"}), True),
            EvaluatorObservation(oracle("b", "c", {"ext:b"}), False),
            EvaluatorObservation(oracle("c", "c", {"ext:c"}), False),
        ]
        decision = self.policy.decide(self.claim, obs)
        with self.assertRaises(ValueError):
            synthesize_quorum_oracle(self.claim, obs, decision)

    def test_pairwise_shared_lineage_is_collapsed(self):
        obs = [
            EvaluatorObservation(oracle("a1", "c", {"ext:a", "shared:model"}), True),
            EvaluatorObservation(oracle("a2", "c", {"ext:b", "shared:model"}), True),
            EvaluatorObservation(oracle("c", "c", {"ext:c"}), True),
        ]
        decision = self.policy.decide(self.claim, obs)
        self.assertFalse(decision.promoted)
        self.assertEqual(decision.admissible_count, 2)

    def test_missing_lineage_is_fail_closed(self):
        obs = [
            EvaluatorObservation(oracle("a", "c", set()), True),
            EvaluatorObservation(oracle("b", "c", {"ext:b"}), True),
            EvaluatorObservation(oracle("c", "c", {"ext:c"}), True),
        ]
        decision = self.policy.decide(self.claim, obs)
        self.assertFalse(decision.promoted)
        self.assertIn("a", decision.excluded_oracle_ids)

    def test_label_slice_is_external_and_balanced_enough(self):
        cases = load_soundness_slice(MANIFEST)
        self.assertEqual(len(cases), 39)
        self.assertEqual(sum(not row.sound for row in cases), 19)
        self.assertEqual(sum(row.sound for row in cases), 20)

    def test_gate_decision_does_not_receive_ground_truth_label(self):
        # Same observations -> same gate output regardless of how a benchmark later scores the case.
        obs = [
            EvaluatorObservation(oracle("a", "c", {"ext:a"}), True),
            EvaluatorObservation(oracle("b", "c", {"ext:b"}), True),
            EvaluatorObservation(oracle("c", "c", {"ext:c"}), False),
        ]
        first = self.policy.decide(self.claim, obs)
        second = self.policy.decide(self.claim, obs)
        self.assertEqual(first, second)

    def test_optimistic_profile_improves_unsafe_rate_with_bounded_false_blocks(self):
        cases = load_soundness_slice(MANIFEST)
        profile = next(p for p in default_profiles() if p.name == "optimistic_correlated")
        metrics = {m.policy: m for m in evaluate_profile(cases, profile)}
        self.assertLess(
            metrics["ecp_as_lineage_quorum"].unsafe_promotion_rate,
            metrics["raw_majority"].unsafe_promotion_rate,
        )
        self.assertLess(metrics["ecp_as_lineage_quorum"].false_block_rate, 0.10)

    def test_hidden_common_cause_remains_a_real_failure_boundary(self):
        cases = load_soundness_slice(MANIFEST)
        result = run_stress_suite(cases)
        rate = result["profiles"]["hidden_common_cause"]["ecp_as_lineage_quorum"][
            "unsafe_promotion_rate"
        ]
        self.assertGreater(rate, 0.10)


if __name__ == "__main__":
    unittest.main()
