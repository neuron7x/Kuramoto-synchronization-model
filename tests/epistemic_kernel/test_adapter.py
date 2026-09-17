import unittest
from epistemic_kernel.geosync_adapter import map_legacy_state
from epistemic_kernel.models import ClaimState

class AdapterTests(unittest.TestCase):
    def test_bounded_legacy_maps_bounded(self): self.assertEqual(map_legacy_state("BOUNDED_CLAIM_ALLOWED"),ClaimState.BOUNDED)
    def test_unknown_legacy_fails(self):
        with self.assertRaises(ValueError): map_legacy_state("MAGIC")

if __name__=="__main__": unittest.main()
