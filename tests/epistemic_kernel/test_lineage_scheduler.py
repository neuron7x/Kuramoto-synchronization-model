"""Oracle lineage and falsifier-first scheduling regression controls."""

import unittest

from geosync.epistemic import *
from geosync.epistemic.scheduler import epistemic_score


class LineageSchedulerTests(unittest.TestCase):
    def test_incomplete_axis_rejected(self):
        c = Claim("c", "P", "d", "s", generator_ancestors=frozenset())
        o = Oracle("o", "c", "x", OracleIndependence(True, True, True, False), frozenset())
        self.assertFalse(evaluate_oracle_independence(c, o).admissible)

    def test_allowed_shared_ancestor(self):
        c = Claim("c", "P", "d", "s", generator_ancestors=frozenset({"public:data"}))
        o = Oracle(
            "o",
            "c",
            "x",
            OracleIndependence(True, True, True, True),
            frozenset({"public:data"}),
        )
        self.assertTrue(
            evaluate_oracle_independence(c, o, frozenset({"public:data"})).admissible
        )

    def test_wrong_claim_oracle_rejected(self):
        c = Claim("c", "P", "d", "s")
        o = Oracle("o", "x", "x", OracleIndependence(True, True, True, True))
        self.assertFalse(evaluate_oracle_independence(c, o).admissible)

    def test_scheduler_prioritizes_discrimination_per_cost(self):
        a = ExperimentCandidate("a", 1, 0.9, 0.9, 10)
        b = ExperimentCandidate("b", 0.5, 0.4, 0.3, 1)
        ranked = rank_experiments([a, b])
        self.assertEqual(ranked[0].experiment_id, "b")

    def test_zero_cost_rejected(self):
        with self.assertRaises(ValueError):
            epistemic_score(ExperimentCandidate("x", 1, 1, 1, 0))

    def test_scheduler_deterministic_tie_break(self):
        a = ExperimentCandidate("a", 1, 1, 1, 1)
        b = ExperimentCandidate("b", 1, 1, 1, 1)
        self.assertEqual(
            [x.experiment_id for x in rank_experiments([b, a])], ["a", "b"]
        )

    def test_scheduler_exact_weighted_score(self):
        candidate = ExperimentCandidate("weighted", 2.0, 0.5, 1.5, 2.0)
        self.assertAlmostEqual(epistemic_score(candidate), 2.0)
        self.assertAlmostEqual(
            epistemic_score(
                candidate, falsification_weight=3.0, independence_weight=4.0
            ),
            4.75,
        )

    def test_scheduler_rejects_each_negative_term_and_negative_cost(self):
        for values in (
            (-0.1, 1, 1, 1),
            (1, -0.1, 1, 1),
            (1, 1, -0.1, 1),
            (1, 1, 1, -1),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                epistemic_score(ExperimentCandidate("invalid", *values))

    def test_scheduler_ranking_responds_to_independent_weights(self):
        falsifiable = ExperimentCandidate("falsifiable", 0.2, 0.9, 0.1, 1)
        independent = ExperimentCandidate("independent", 0.2, 0.1, 0.9, 1)
        options = [independent, falsifiable]
        self.assertEqual(
            rank_experiments(
                options, falsification_weight=5.0, independence_weight=0.0
            )[0].experiment_id,
            "falsifiable",
        )
        self.assertEqual(
            rank_experiments(
                options, falsification_weight=0.0, independence_weight=5.0
            )[0].experiment_id,
            "independent",
        )


if __name__ == "__main__":
    unittest.main()
