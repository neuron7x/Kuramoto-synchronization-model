import json, tempfile, unittest
from pathlib import Path
from epistemic_kernel import *

def ev(cid,kind,n): return Evidence(n,kind,"digest-"+n,"unit","1",cid)
def indep_oracle(cid): return Oracle("o",cid,"od",OracleIndependence(True,True,True,True),frozenset({"external:B"}))

class RuntimeLedgerTests(unittest.TestCase):
    def runtime(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup)
        return EpistemicRuntime(Path(td.name)/"ledger.jsonl")
    def test_pre_promoted_claim_rejected(self):
        rt=self.runtime()
        with self.assertRaises(ValueError): rt.register_claim(Claim("c","P","d","s",ClaimState.REPLICATED))
    def test_authoritative_state_reconstructed_from_ledger(self):
        rt=self.runtime(); rt.register_claim(Claim("c","P","d","s"))
        self.assertTrue(rt.promote("c",ClaimState.CONJECTURE).allowed)
        self.assertEqual(rt.claim("c").state,ClaimState.CONJECTURE)
    def test_blocked_attempt_does_not_mutate_state(self):
        rt=self.runtime(); rt.register_claim(Claim("c","P","d","s")); rt.promote("c",ClaimState.CONJECTURE)
        d=rt.promote("c",ClaimState.TESTABLE)
        self.assertFalse(d.allowed); self.assertEqual(rt.claim("c").state,ClaimState.CONJECTURE)
    def test_full_chain_to_replicated_requires_independent_oracle(self):
        rt=self.runtime(); rt.register_claim(Claim("c","P","d","s",generator_ancestors=frozenset({"model:A"})))
        self.assertTrue(rt.promote("c",ClaimState.CONJECTURE).allowed)
        rt.add_evidence(ev("c",EvidenceKind.OPERATIONAL_DEFINITION,"op")); rt.add_evidence(ev("c",EvidenceKind.FALSIFIER_DEFINED,"fd"))
        self.assertTrue(rt.promote("c",ClaimState.TESTABLE).allowed)
        rt.add_evidence(ev("c",EvidenceKind.INSTRUMENT,"ins")); rt.add_evidence(ev("c",EvidenceKind.PROVENANCE,"prov"))
        self.assertTrue(rt.promote("c",ClaimState.INSTRUMENTED).allowed)
        rt.add_evidence(ev("c",EvidenceKind.OBSERVATION,"obs"))
        self.assertTrue(rt.promote("c",ClaimState.OBSERVED,falsifier_executed=True).allowed)
        rt.add_evidence(ev("c",EvidenceKind.REPLICATION,"rep")); rt.add_evidence(ev("c",EvidenceKind.REPLAY,"replay"))
        self.assertFalse(rt.promote("c",ClaimState.REPLICATED,falsifier_executed=True).allowed)
        rt.add_oracle(indep_oracle("c"))
        self.assertTrue(rt.promote("c",ClaimState.REPLICATED,falsifier_executed=True).allowed)
        self.assertEqual(rt.claim("c").state,ClaimState.REPLICATED)
    def test_degradation_blocks_further_promotion(self):
        rt=self.runtime(); rt.register_claim(Claim("c","P","d","s")); rt.promote("c",ClaimState.CONJECTURE)
        rt.degrade("c",ClaimState.FALSIFIED,"counterexample","artifact:1")
        self.assertEqual(rt.claim("c").state,ClaimState.FALSIFIED)
        with self.assertRaises(ValueError): rt.promote("c",ClaimState.TESTABLE)
    def test_tamper_is_detected_on_reopen(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); path=Path(td.name)/"l.jsonl"
        rt=EpistemicRuntime(path); rt.register_claim(Claim("c","P","d","s"))
        rows=path.read_text().splitlines(); raw=json.loads(rows[0]); raw["payload"]["proposition"]="tampered"; rows[0]=json.dumps(raw)
        path.write_text("\n".join(rows)+"\n")
        with self.assertRaises(ValueError): EpistemicRuntime(path)
    def test_runtime_survives_reopen(self):
        td=tempfile.TemporaryDirectory(); self.addCleanup(td.cleanup); path=Path(td.name)/"l.jsonl"
        rt=EpistemicRuntime(path); rt.register_claim(Claim("c","P","d","s")); rt.promote("c",ClaimState.CONJECTURE)
        rt2=EpistemicRuntime(path); self.assertEqual(rt2.claim("c").state,ClaimState.CONJECTURE)

    def test_negative_evidence_resolution_is_append_only(self):
        rt=self.runtime(); rt.register_claim(Claim("c","P","d","s"))
        n=NegativeEvidence("n1",NegativeEvidenceKind.CALIBRATION_MISS,"nd","c",True,False)
        rt.add_negative_evidence(n); self.assertFalse(rt.negative_evidence("c")[0].resolved)
        rt.resolve_negative_evidence("c","n1","artifact:resolution")
        self.assertTrue(rt.negative_evidence("c")[0].resolved)
        types=[e.event_type for e in rt.ledger.for_claim("c")]
        self.assertIn("NEGATIVE_EVIDENCE_ADDED",types); self.assertIn("NEGATIVE_EVIDENCE_RESOLVED",types)
    def test_duplicate_negative_id_rejected(self):
        rt=self.runtime(); rt.register_claim(Claim("c","P","d","s"))
        n=NegativeEvidence("n1",NegativeEvidenceKind.INVALID_INPUT,"nd","c",True,False)
        rt.add_negative_evidence(n)
        with self.assertRaises(ValueError): rt.add_negative_evidence(n)

if __name__=="__main__": unittest.main()
