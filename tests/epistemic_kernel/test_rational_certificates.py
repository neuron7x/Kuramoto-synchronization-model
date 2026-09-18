from dataclasses import replace
from fractions import Fraction
import unittest

from geosync.epistemic.rational_certificates import (
    iteration_006_certificates,
    verify_rational_certificate,
)


class RationalCertificateTests(unittest.TestCase):
    def test_iteration_006_certificates_verify_exactly(self):
        for cert in iteration_006_certificates():
            result = verify_rational_certificate(cert)
            self.assertTrue(result.valid, result.reason)
            self.assertTrue(result.primal_valid)
            self.assertTrue(result.dual_valid)
            self.assertTrue(result.strong_duality)

    def test_unsafe_optimum_is_exact_0278(self):
        unsafe, _ = iteration_006_certificates()
        self.assertEqual(Fraction(unsafe.optimum), Fraction(139, 500))
        result = verify_rational_certificate(unsafe)
        self.assertEqual(Fraction(result.primal_objective), Fraction(139, 500))

    def test_false_block_optimum_is_exact_0342(self):
        _, false_block = iteration_006_certificates()
        self.assertEqual(Fraction(false_block.optimum), Fraction(171, 500))
        result = verify_rational_certificate(false_block)
        self.assertEqual(Fraction(result.dual_objective), Fraction(171, 500))

    def test_tampered_primal_witness_fails(self):
        unsafe, _ = iteration_006_certificates()
        tampered = replace(unsafe, joint_mass={"000": "1/50", "100": "350/500", "110": "140/500"})
        self.assertFalse(verify_rational_certificate(tampered).valid)

    def test_tampered_dual_fails(self):
        unsafe, _ = iteration_006_certificates()
        tampered = replace(unsafe, dual_coefficients=("0", "0", "1"))
        result = verify_rational_certificate(tampered)
        self.assertFalse(result.valid)
        self.assertFalse(result.dual_valid)

    def test_certificate_verifier_uses_no_solver(self):
        # Regression invariant: exact verification module has no scipy/numpy dependency.
        import inspect
        import geosync.epistemic.rational_certificates as module
        source = inspect.getsource(module)
        self.assertNotIn("scipy", source)
        self.assertNotIn("numpy", source)


if __name__ == "__main__":
    unittest.main()
