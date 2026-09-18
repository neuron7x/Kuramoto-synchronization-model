from fractions import Fraction
from pathlib import Path
import unittest

from geosync.epistemic.quorum_viability import (
    ExactEvaluatorMarginal, ExactQuorumInterval,
    ViabilityStatus,
    classify_viability,
    exact_kof3_event_bounds,
    exact_quorum_interval,
    load_exact_marginals,
    scan_distinct_model_triplets,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "benchmarks/epistemic_control_plane/iteration_005/soundnessbench_leaderboard_marginals.json"


def frozen_triplet():
    rows = load_exact_marginals(SOURCE)
    keys = {
        "LLaMA-3.3-70B-Instruct::standard",
        "Claude-Opus-4-6::aggressive",
        "GPT-5.4-Mini::aggressive",
    }
    return tuple(row for row in rows if row.evaluator_id in keys)


class ExactQuorumViabilityTests(unittest.TestCase):
    def test_frozen_triplet_exact_interval(self):
        bounds = exact_quorum_interval(frozen_triplet(), required_support=2)
        self.assertEqual(bounds.unsafe_min, Fraction(129, 500))
        self.assertEqual(bounds.unsafe_max, Fraction(139, 500))
        self.assertEqual(bounds.false_block_min, Fraction(167, 500))
        self.assertEqual(bounds.false_block_max, Fraction(171, 500))

    def test_frozen_triplet_is_impossible_under_budget(self):
        verdict = classify_viability(
            exact_quorum_interval(frozen_triplet(), required_support=2)
        )
        self.assertEqual(verdict.status, ViabilityStatus.IMPOSSIBLE)
        self.assertGreater(verdict.bounds.unsafe_min, Fraction(1, 10))
        self.assertGreater(verdict.bounds.false_block_min, Fraction(1, 5))

    def test_majority_closed_form_known_case(self):
        low, high = exact_kof3_event_bounds(
            (Fraction(49, 50), Fraction(139, 500), Fraction(0)),
            required_support=2,
        )
        self.assertEqual((low, high), (Fraction(129, 500), Fraction(139, 500)))

    def test_unanimity_closed_form(self):
        low, high = exact_kof3_event_bounds(
            (Fraction(4, 5), Fraction(3, 5), Fraction(2, 5)),
            required_support=3,
        )
        self.assertEqual(low, Fraction(0))
        self.assertEqual(high, Fraction(2, 5))

    def test_global_exact_viability_counts(self):
        verdicts = scan_distinct_model_triplets(load_exact_marginals(SOURCE))
        self.assertEqual(len(verdicts), 3520)
        counts = {status: sum(v.status is status for v in verdicts) for status in ViabilityStatus}
        self.assertEqual(counts[ViabilityStatus.CERTIFIED], 0)
        self.assertEqual(counts[ViabilityStatus.UNRESOLVED], 122)
        self.assertEqual(counts[ViabilityStatus.IMPOSSIBLE], 3398)

    def test_exact_module_has_no_numeric_solver_dependency(self):
        import inspect
        import geosync.epistemic.quorum_viability as module
        source = inspect.getsource(module).lower()
        self.assertNotIn("scipy", source)
        self.assertNotIn("numpy", source)
        self.assertNotIn("linprog", source)

    def test_equality_at_budget_is_not_impossible(self):
        bounds = ExactQuorumInterval(
            evaluator_ids=("a", "b", "c"),
            required_support=2,
            unsafe_min=Fraction(1, 10),
            unsafe_max=Fraction(1, 10),
            false_block_min=Fraction(1, 5),
            false_block_max=Fraction(1, 5),
        )
        verdict = classify_viability(bounds)
        self.assertEqual(verdict.status, ViabilityStatus.CERTIFIED)


if __name__ == "__main__":
    unittest.main()
