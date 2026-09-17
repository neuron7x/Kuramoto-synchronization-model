import unittest
from geosync.epistemic.benchmark import (
    ArtifactChainBaseline,
    ECPASPolicy,
    MultiAgentVoteBaseline,
    build_core_scenarios,
    run_policy,
)


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.scenarios = build_core_scenarios()

    def test_scenarios_have_unique_ids_and_both_classes(self):
        ids = [s.scenario_id for s in self.scenarios]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(s.safe_to_promote for s in self.scenarios))
        self.assertTrue(any(not s.safe_to_promote for s in self.scenarios))

    def test_ecp_as_has_no_unsafe_promotions_on_core_suite(self):
        metrics = run_policy(ECPASPolicy(), self.scenarios)
        self.assertEqual(metrics.unsafe_promotions, 0)
        self.assertEqual(metrics.false_blocks, 0)

    def test_lineage_gate_adds_value_over_artifact_chain(self):
        ecp = run_policy(ECPASPolicy(), self.scenarios)
        artifact = run_policy(ArtifactChainBaseline(), self.scenarios)
        self.assertGreater(artifact.unsafe_promotions, ecp.unsafe_promotions)

    def test_correlated_vote_baseline_is_falsified(self):
        metrics = run_policy(MultiAgentVoteBaseline(), self.scenarios)
        self.assertGreater(metrics.unsafe_promotions, 0)

    def test_shared_lineage_case_is_blocked_by_ecp(self):
        scenario = next(s for s in self.scenarios if s.scenario_id == "unsafe-two-correlated-verifiers")
        self.assertFalse(ECPASPolicy().decide(scenario).allowed)
        self.assertTrue(MultiAgentVoteBaseline().decide(scenario).allowed)

    def test_unresolved_negative_blocks_replicated(self):
        scenario = next(s for s in self.scenarios if s.scenario_id == "unsafe-active-negative-0")
        decision = ECPASPolicy().decide(scenario)
        self.assertFalse(decision.allowed)
        self.assertIn("negative evidence", decision.reason)


if __name__ == "__main__":
    unittest.main()
