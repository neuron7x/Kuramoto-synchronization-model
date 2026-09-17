import unittest
from geosync.epistemic import *

def ev(cid,kind,n="x"):
    return Evidence(n,kind,"d"+n,"unit","1",cid)

def oracle(cid, ancestors=frozenset(), independent=True):
    ind=OracleIndependence(independent,independent,independent,independent)
    return Oracle("o",cid,"od",ind,ancestors)

class AdmissionTests(unittest.TestCase):
    def setUp(self): self.c=AdmissionController()
    def claim(self,state=ClaimState.UNOBSERVED,anc=frozenset()):
        return Claim("c","P","science","scope",state,generator_ancestors=anc)
    def test_conjecture_requires_no_evidence(self):
        c,d=self.c.promote(self.claim(),ClaimState.CONJECTURE,())
        self.assertTrue(d.allowed); self.assertEqual(c.state,ClaimState.CONJECTURE)
    def test_state_skipping_fails_closed(self):
        with self.assertRaises(ValueError): self.c.evaluate(self.claim(),ClaimState.TESTABLE,())
    def test_testable_requires_operational_definition_and_falsifier(self):
        c=self.claim(ClaimState.CONJECTURE)
        d=self.c.evaluate(c,ClaimState.TESTABLE,[ev("c",EvidenceKind.OPERATIONAL_DEFINITION)])
        self.assertFalse(d.allowed); self.assertIn("FALSIFIER_DEFINED"," ".join(d.blockers))
    def test_instrumented_requires_provenance(self):
        c=self.claim(ClaimState.TESTABLE)
        d=self.c.evaluate(c,ClaimState.INSTRUMENTED,[ev("c",EvidenceKind.INSTRUMENT)])
        self.assertFalse(d.allowed)
    def test_observed_requires_executed_falsifier(self):
        c=self.claim(ClaimState.INSTRUMENTED)
        evidence=[ev("c",EvidenceKind.OBSERVATION),ev("c",EvidenceKind.PROVENANCE)]
        self.assertFalse(self.c.evaluate(c,ClaimState.OBSERVED,evidence).allowed)
        self.assertTrue(self.c.evaluate(c,ClaimState.OBSERVED,evidence,falsifier_executed=True).allowed)
    def test_replication_rejects_self_verifying_oracle(self):
        c=self.claim(ClaimState.OBSERVED,frozenset({"model:A"}))
        evidence=[ev("c",EvidenceKind.REPLICATION),ev("c",EvidenceKind.REPLAY),ev("c",EvidenceKind.PROVENANCE)]
        o=oracle("c",frozenset({"model:A"}))
        d=self.c.evaluate(c,ClaimState.REPLICATED,evidence,oracles=[o],falsifier_executed=True)
        self.assertFalse(d.allowed); self.assertIn("independent oracle"," ".join(d.blockers))
    def test_replication_accepts_independent_oracle(self):
        c=self.claim(ClaimState.OBSERVED,frozenset({"model:A"}))
        evidence=[ev("c",EvidenceKind.REPLICATION),ev("c",EvidenceKind.REPLAY),ev("c",EvidenceKind.PROVENANCE)]
        o=oracle("c",frozenset({"model:B"}))
        d=self.c.evaluate(c,ClaimState.REPLICATED,evidence,oracles=[o],falsifier_executed=True)
        self.assertTrue(d.allowed); self.assertIsNotNone(d.certificate)
    def test_bounded_blocks_unresolved_negative_evidence(self):
        c=self.claim(ClaimState.REPLICATED)
        ks=[EvidenceKind.NULL_COMPARISON,EvidenceKind.BASELINE_COMPARISON,EvidenceKind.BOUNDARY,EvidenceKind.REPLAY,EvidenceKind.PROVENANCE]
        evidence=[ev("c",k,str(i)) for i,k in enumerate(ks)]
        n=NegativeEvidence("n",NegativeEvidenceKind.REPLAY_MISMATCH,"nd","c",True,False)
        d=self.c.evaluate(c,ClaimState.BOUNDED,evidence,[n],[oracle("c")],falsifier_executed=True)
        self.assertFalse(d.allowed); self.assertIn("negative evidence"," ".join(d.blockers))
    def test_cross_claim_evidence_rejected(self):
        c=self.claim(ClaimState.CONJECTURE)
        evidence=[ev("other",EvidenceKind.OPERATIONAL_DEFINITION),ev("c",EvidenceKind.FALSIFIER_DEFINED)]
        d=self.c.evaluate(c,ClaimState.TESTABLE,evidence)
        self.assertFalse(d.allowed); self.assertIn("cross-claim"," ".join(d.blockers))
    def test_certificate_is_deterministic(self):
        c=self.claim(ClaimState.OBSERVED)
        evidence=[ev("c",EvidenceKind.REPLICATION),ev("c",EvidenceKind.REPLAY),ev("c",EvidenceKind.PROVENANCE)]
        o=oracle("c")
        a=self.c.evaluate(c,ClaimState.REPLICATED,evidence,oracles=[o],falsifier_executed=True).certificate
        b=self.c.evaluate(c,ClaimState.REPLICATED,evidence,oracles=[o],falsifier_executed=True).certificate
        self.assertEqual(a,b)

if __name__=="__main__": unittest.main()
