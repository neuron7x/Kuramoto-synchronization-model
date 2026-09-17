import unittest
from epistemic_kernel import *
from epistemic_kernel.scheduler import epistemic_score

class LineageSchedulerTests(unittest.TestCase):
    def test_incomplete_axis_rejected(self):
        c=Claim("c","P","d","s",generator_ancestors=frozenset())
        o=Oracle("o","c","x",OracleIndependence(True,True,True,False),frozenset())
        self.assertFalse(evaluate_oracle_independence(c,o).admissible)
    def test_allowed_shared_ancestor(self):
        c=Claim("c","P","d","s",generator_ancestors=frozenset({"public:data"}))
        o=Oracle("o","c","x",OracleIndependence(True,True,True,True),frozenset({"public:data"}))
        self.assertTrue(evaluate_oracle_independence(c,o,frozenset({"public:data"})).admissible)
    def test_wrong_claim_oracle_rejected(self):
        c=Claim("c","P","d","s")
        o=Oracle("o","x","x",OracleIndependence(True,True,True,True))
        self.assertFalse(evaluate_oracle_independence(c,o).admissible)
    def test_scheduler_prioritizes_discrimination_per_cost(self):
        a=ExperimentCandidate("a",1,0.9,0.9,10)
        b=ExperimentCandidate("b",0.5,0.4,0.3,1)
        ranked=rank_experiments([a,b])
        self.assertEqual(ranked[0].experiment_id,"b")
    def test_zero_cost_rejected(self):
        with self.assertRaises(ValueError): epistemic_score(ExperimentCandidate("x",1,1,1,0))
    def test_scheduler_deterministic_tie_break(self):
        a=ExperimentCandidate("a",1,1,1,1); b=ExperimentCandidate("b",1,1,1,1)
        self.assertEqual([x.experiment_id for x in rank_experiments([b,a])],["a","b"])

if __name__=="__main__": unittest.main()
