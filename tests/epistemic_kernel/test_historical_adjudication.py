from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from geosync.epistemic import Claim, ClaimState, EpistemicRuntime
from geosync.epistemic.adjudication import (
    AdjudicationAction,
    AdjudicationKind,
    AuthorityClass,
    DefectClass,
    ExternalAdjudicationEvent,
    ExternalAdjudicationPolicy,
    IndependenceLevel,
)
from geosync.epistemic.historical_replay import (
    ECPASHistoricalPolicy,
    RetractionEqualsFalsificationBaseline,
    default_historical_policies,
    load_historical_cases,
    run_historical_policy,
)

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "benchmarks/epistemic_control_plane/iteration_003/historical_cases.json"


class HistoricalAdjudicationTests(unittest.TestCase):
    def setUp(self):
        self.cases = load_historical_cases(MANIFEST)

    def test_manifest_size_and_labels(self):
        self.assertEqual(len(self.cases), 14)
        self.assertEqual(sum(c.expected_action is AdjudicationAction.DEGRADE for c in self.cases), 9)
        self.assertEqual(sum(c.expected_action is AdjudicationAction.PRESERVE for c in self.cases), 5)

    def test_ecp_as_exact_transitions(self):
        metrics, _ = run_historical_policy(ECPASHistoricalPolicy(), self.cases)
        self.assertEqual(metrics.transition_conformance, 14)
        self.assertEqual(metrics.correct_actions, 14)
        self.assertEqual(metrics.false_degradations, 0)
        self.assertEqual(metrics.missed_degradations, 0)
        self.assertEqual(metrics.false_falsifications, 0)

    def test_naive_retraction_policy_over_falsifies(self):
        metrics, _ = run_historical_policy(RetractionEqualsFalsificationBaseline(), self.cases)
        self.assertGreater(metrics.false_falsifications, 0)
        self.assertLess(metrics.transition_conformance, 14)

    def test_unverified_source_requires_review(self):
        event = ExternalAdjudicationEvent(
            event_id="unverified",
            claim_id="c",
            kind=AdjudicationKind.EDITORIAL_RETRACTION,
            authority=AuthorityClass.PUBLISHER_EDITORIAL,
            source_url="https://example.invalid/unverified",
            source_title="Unverified",
            source_date="2026-09-17",
            source_digest="d",
            defects=frozenset({DefectClass.DATA_PROVENANCE_INVALID}),
            source_authenticity_verified=False,
            independence_level=IndependenceLevel.UNKNOWN,
        )
        decision = ExternalAdjudicationPolicy().evaluate(event)
        self.assertEqual(decision.action, AdjudicationAction.REVIEW_REQUIRED)
        self.assertIsNone(decision.target_state)

    def test_validation_falsification_requires_verified_independence(self):
        event = ExternalAdjudicationEvent(
            event_id="partial-validation",
            claim_id="c",
            kind=AdjudicationKind.EDITORIAL_RETRACTION,
            authority=AuthorityClass.PUBLISHER_EDITORIAL,
            source_url="https://example.invalid/partial",
            source_title="Partial",
            source_date="2026-09-17",
            source_digest="d",
            defects=frozenset({DefectClass.VALIDATION_METHODOLOGY_INVALID}),
            source_authenticity_verified=True,
            independence_level=IndependenceLevel.PARTIAL,
            explicit_conclusions_unsupported=True,
        )
        decision = ExternalAdjudicationPolicy().evaluate(event)
        self.assertEqual(decision.target_state, ClaimState.INCONCLUSIVE)

    def test_runtime_records_negative_evidence_and_degrades(self):
        case = next(c for c in self.cases if c.policy_expected_state is ClaimState.CONFLICTED)
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EpistemicRuntime(Path(tmp) / "ledger.jsonl")
            runtime.register_claim(Claim(case.event.claim_id, "p", "historical", "external-replay"))
            decision = runtime.apply_external_adjudication(case.event)
            self.assertEqual(decision.action, AdjudicationAction.DEGRADE)
            self.assertEqual(runtime.claim(case.event.claim_id).state, ClaimState.CONFLICTED)
            negatives = runtime.negative_evidence(case.event.claim_id)
            self.assertEqual(len(negatives), 1)
            self.assertTrue(negatives[0].blocking)
            with self.assertRaises(ValueError):
                runtime.apply_external_adjudication(case.event)

    def test_benign_correction_is_ledgered_without_degradation(self):
        case = next(c for c in self.cases if c.case_id == "control-ai-news-author-name")
        with tempfile.TemporaryDirectory() as tmp:
            runtime = EpistemicRuntime(Path(tmp) / "ledger.jsonl")
            runtime.register_claim(Claim(case.event.claim_id, "p", "historical", "external-replay"))
            decision = runtime.apply_external_adjudication(case.event)
            self.assertEqual(decision.action, AdjudicationAction.PRESERVE)
            self.assertEqual(runtime.claim(case.event.claim_id).state, ClaimState.UNOBSERVED)
            types = [e.event_type for e in runtime.ledger.for_claim(case.event.claim_id)]
            self.assertIn("EXTERNAL_ADJUDICATION_PRESERVED", types)
            self.assertNotIn("CLAIM_DEGRADED", types)


    def test_source_manifest_digests_are_deterministic(self):
        raw = json.loads(MANIFEST.read_text(encoding="utf-8"))
        seen = set()
        for item in raw["cases"]:
            canonical = "|".join([
                item["source_url"], item["source_title"], item["source_date"], item["reason_summary"]
            ])
            digest = hashlib.sha256(canonical.encode()).hexdigest()
            self.assertEqual(item["source_digest"], digest)
            self.assertTrue(item["source_url"].startswith("https://www.nature.com/"))
            self.assertNotIn(item["case_id"], seen)
            seen.add(item["case_id"])

    def test_falsified_is_reserved_for_strong_validation_failure(self):
        policy = ECPASHistoricalPolicy()
        decisions = [policy.decide(c) for c in self.cases]
        falsified = [d.case_id for d in decisions if d.predicted_state is ClaimState.FALSIFIED]
        self.assertEqual(falsified, ["hist-earthquake-la-validation"])

    def test_default_policies_are_distinct(self):
        names = [p.name for p in default_historical_policies()]
        self.assertEqual(len(names), len(set(names)))
        self.assertIn("ecp_as_external_adjudication", names)


if __name__ == "__main__":
    unittest.main()
