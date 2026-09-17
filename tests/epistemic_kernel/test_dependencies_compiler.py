import unittest
from geosync.epistemic import *

class DependencyCompilerTests(unittest.TestCase):
    def test_scoped_transitive_invalidation(self):
        g=DependencyGraph(); g.add("evidence:A","claim:B",DependencyKind.DATA); g.add("claim:B","claim:C",DependencyKind.LOGICAL); g.add("evidence:X","claim:Y",DependencyKind.DATA)
        self.assertEqual(g.impacted("evidence:A"),frozenset({"claim:B","claim:C"}))
    def test_cycle_rejected(self):
        g=DependencyGraph(); g.add("a","b",DependencyKind.LOGICAL)
        with self.assertRaises(ValueError): g.add("b","a",DependencyKind.LOGICAL)
    def test_structured_compiler_accepts_explicit_contract(self):
        spec=compile_structured_claim(proposition="P",population_or_domain="D",operational_definition="measure M",null_hypothesis="not P",alternative_hypotheses=("Q",),effect_criterion="M > 1",falsification_criterion="M <= 0",required_oracle="external")
        self.assertEqual(spec.proposition,"P")
    def test_structured_compiler_rejects_missing_alternative(self):
        with self.assertRaises(ValueError): compile_structured_claim(proposition="P",population_or_domain="D",operational_definition="M",null_hypothesis="N",alternative_hypotheses=(),effect_criterion="E",falsification_criterion="F",required_oracle="O")
    def test_effect_and_falsifier_must_be_distinct(self):
        with self.assertRaises(ValueError): compile_structured_claim(proposition="P",population_or_domain="D",operational_definition="M",null_hypothesis="N",alternative_hypotheses=("A",),effect_criterion="same",falsification_criterion="same",required_oracle="O")

if __name__=="__main__": unittest.main()
