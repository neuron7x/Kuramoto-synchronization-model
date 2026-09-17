import itertools
import unittest

from geosync.epistemic.benchmark import ECPASPolicy, PromotionScenario
from geosync.epistemic.models import (
    Claim,
    ClaimState,
    Evidence,
    EvidenceKind,
    NegativeEvidence,
    NegativeEvidenceKind,
    Oracle,
    OracleIndependence,
)


class ReplicationTruthTableTests(unittest.TestCase):
    def test_exhaustive_replication_gate_truth_table(self):
        policy = ECPASPolicy()
        states_checked = 0
        for (
            evidence_complete,
            falsifier_executed,
            active_negative,
            oracle_present,
            axes_complete,
            shared_lineage,
            oracle_admissible,
        ) in itertools.product((False, True), repeat=7):
            claim_id = f"matrix-{states_checked}"
            claim = Claim(
                claim_id,
                "P",
                "benchmark",
                "replication-truth-table",
                ClaimState.OBSERVED,
                generator_ancestors=frozenset({"model:generator"}),
            )
            kinds = [EvidenceKind.REPLICATION, EvidenceKind.REPLAY, EvidenceKind.PROVENANCE]
            if not evidence_complete:
                kinds = kinds[:-1]
            evidence = tuple(
                Evidence(
                    f"e:{i}",
                    kind,
                    f"digest:{i}",
                    "truth-table",
                    "1",
                    claim_id,
                )
                for i, kind in enumerate(kinds)
            )
            negatives = ()
            if active_negative:
                negatives = (
                    NegativeEvidence(
                        "n:1",
                        NegativeEvidenceKind.REPLAY_MISMATCH,
                        "neg-digest",
                        claim_id,
                        blocking=True,
                        resolved=False,
                    ),
                )
            oracles = ()
            if oracle_present:
                axes = (True, True, True, True) if axes_complete else (True, True, True, False)
                ancestor = "model:generator" if shared_lineage else "model:external"
                oracles = (
                    Oracle(
                        "o:1",
                        claim_id,
                        "oracle-digest",
                        OracleIndependence(*axes),
                        frozenset({ancestor}),
                        admissible=oracle_admissible,
                    ),
                )
            expected = (
                evidence_complete
                and falsifier_executed
                and not active_negative
                and oracle_present
                and axes_complete
                and not shared_lineage
                and oracle_admissible
            )
            scenario = PromotionScenario(
                scenario_id=claim_id,
                claim=claim,
                target=ClaimState.REPLICATED,
                evidence=evidence,
                negative_evidence=negatives,
                oracles=oracles,
                falsifier_executed=falsifier_executed,
                safe_to_promote=expected,
                failure_class="truth_table",
                rationale="Independent model-based truth-table state.",
            )
            with self.subTest(
                evidence_complete=evidence_complete,
                falsifier_executed=falsifier_executed,
                active_negative=active_negative,
                oracle_present=oracle_present,
                axes_complete=axes_complete,
                shared_lineage=shared_lineage,
                oracle_admissible=oracle_admissible,
            ):
                self.assertEqual(policy.decide(scenario).allowed, expected)
            states_checked += 1
        self.assertEqual(states_checked, 128)


if __name__ == "__main__":
    unittest.main()
