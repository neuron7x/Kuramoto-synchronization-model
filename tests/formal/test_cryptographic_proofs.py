"""Comprehensive tests for formal cryptographic proof verification.

This test module validates the mathematical proofs for cryptographic
security properties, ensuring the formal verification system produces
correct and reproducible results.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from formal.cryptographic_proofs import (
    HAS_Z3,
    CryptographicProofReport,
    CryptographicProver,
    ProofResult,
    ProofStatus,
    SecurityProperty,
    verify_cryptographic_security,
)


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestCryptographicProver:
    """Tests for the CryptographicProver class."""

    @pytest.fixture
    def prover(self) -> CryptographicProver:
        """Create a CryptographicProver instance."""
        return CryptographicProver(timeout_ms=60000, verbose=False)

    def test_prover_initialization(self, prover: CryptographicProver) -> None:
        """Test prover initializes correctly with Z3."""
        assert prover.timeout_ms == 60000
        assert prover.verbose is False
        assert prover._z3 is not None

    def test_hash_collision_resistance_proof(self, prover: CryptographicProver) -> None:
        """Test hash collision resistance proof completes and passes."""
        result = prover.prove_hash_collision_resistance()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "hash_collision_resistance"
        assert result.security_property.category == "hash"
        assert result.security_property.severity == "critical"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True
        assert "UNSAT" in result.certificate
        assert "128-bit" in result.certificate
        assert result.details.get("security_bits") == 128
        assert result.details.get("induction_base_unsat") is True
        assert result.details.get("induction_step_unsat") is True
        assert "merkle" in result.certificate.lower()

    def test_hash_preimage_resistance_proof(self, prover: CryptographicProver) -> None:
        """Test hash preimage resistance proof completes and passes."""
        result = prover.prove_hash_preimage_resistance()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "hash_preimage_resistance"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True
        assert "256-bit" in result.certificate

    def test_hmac_prf_security_proof(self, prover: CryptographicProver) -> None:
        """Test HMAC PRF security proof completes and passes."""
        result = prover.prove_hmac_prf_security()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "hmac_prf_security"
        assert result.security_property.category == "hmac"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True
        assert "PRF" in result.certificate

    def test_hmac_key_binding_proof(self, prover: CryptographicProver) -> None:
        """Test HMAC key binding proof completes and passes."""
        result = prover.prove_hmac_key_binding()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "hmac_key_binding"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True

    def test_key_derivation_entropy_proof(self, prover: CryptographicProver) -> None:
        """Test key derivation entropy preservation proof."""
        result = prover.prove_key_derivation_entropy()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "kdf_entropy_preservation"
        assert result.security_property.category == "kdf"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True

    def test_signature_unforgeability_proof(self, prover: CryptographicProver) -> None:
        """Test digital signature unforgeability proof."""
        result = prover.prove_signature_unforgeability()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "signature_unforgeability"
        assert result.security_property.category == "signature"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True
        assert "EUF-CMA" in result.certificate

    def test_timing_attack_resistance_proof(self, prover: CryptographicProver) -> None:
        """Test timing attack resistance proof."""
        result = prover.prove_timing_attack_resistance()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "timing_attack_resistance"
        assert result.security_property.category == "sidechannel"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True
        assert "zero bits" in result.certificate

    def test_entropy_accumulation_proof(self, prover: CryptographicProver) -> None:
        """Test CSPRNG entropy accumulation proof."""
        result = prover.prove_entropy_accumulation()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "csprng_entropy_accumulation"
        assert result.security_property.category == "random"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True

    def test_checksum_integrity_proof(self, prover: CryptographicProver) -> None:
        """Test checksum integrity soundness proof."""
        result = prover.prove_checksum_integrity()

        assert isinstance(result, ProofResult)
        assert result.security_property.name == "checksum_integrity_soundness"
        assert result.security_property.category == "integrity"
        assert result.status == ProofStatus.PROVED
        assert result.passed is True


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestCryptographicProofReport:
    """Tests for the comprehensive proof report."""

    @pytest.fixture
    def prover(self) -> CryptographicProver:
        """Create a CryptographicProver instance."""
        return CryptographicProver(timeout_ms=60000)

    def test_prove_all_generates_report(self, prover: CryptographicProver) -> None:
        """Test that prove_all generates a complete report."""
        report = prover.prove_all()

        assert isinstance(report, CryptographicProofReport)
        assert len(report.results) == 9  # All proofs ran
        assert report.z3_version != ""
        assert report.total_time_ms > 0
        assert report.timestamp != ""

    def test_all_proofs_pass(self, prover: CryptographicProver) -> None:
        """Test that all proofs pass verification."""
        report = prover.prove_all()

        assert report.all_passed is True
        assert report.passed_count == 9
        assert report.failed_count == 0
        assert len(report.get_failures()) == 0

    def test_report_summary(self, prover: CryptographicProver) -> None:
        """Test report summary generation."""
        report = prover.prove_all()
        summary = report.summary()

        assert "Cryptographic Proof Report" in summary
        assert "Z3 Version" in summary
        assert "9/9 passed" in summary

    def test_get_by_category(self, prover: CryptographicProver) -> None:
        """Test filtering results by category."""
        report = prover.prove_all()

        hash_results = report.get_by_category("hash")
        assert len(hash_results) == 2

        hmac_results = report.get_by_category("hmac")
        assert len(hmac_results) == 2

        signature_results = report.get_by_category("signature")
        assert len(signature_results) == 1

    def test_save_certificate(
        self, prover: CryptographicProver, tmp_path: Path
    ) -> None:
        """Test saving proof certificate to file."""
        cert_path = tmp_path / "CRYPTO_CERT.txt"
        prover.prove_all(output_path=cert_path)

        assert cert_path.exists()
        content = cert_path.read_text(encoding="utf-8")

        assert "CRYPTOGRAPHIC SECURITY PROOF CERTIFICATE" in content
        assert "VERIFICATION RESULTS" in content
        assert "hash_collision_resistance" in content
        assert "SUMMARY" in content
        assert "All Passed: True" in content


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestVerifyCryptographicSecurity:
    """Tests for the verify_cryptographic_security function."""

    def test_verify_returns_report(self) -> None:
        """Test the main verification function returns a report."""
        report = verify_cryptographic_security()

        assert isinstance(report, CryptographicProofReport)
        assert report.all_passed is True

    def test_verify_with_output_path(self, tmp_path: Path) -> None:
        """Test verification with output path saves certificate."""
        cert_path = tmp_path / "cert.txt"
        report = verify_cryptographic_security(output_path=cert_path)

        assert report.all_passed is True
        assert cert_path.exists()


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestSecurityProperty:
    """Tests for SecurityProperty dataclass."""

    def test_security_property_creation(self) -> None:
        """Test creating a SecurityProperty."""
        prop = SecurityProperty(
            name="test_property",
            description="A test security property",
            category="test",
            severity="high",
        )

        assert prop.name == "test_property"
        assert prop.description == "A test security property"
        assert prop.category == "test"
        assert prop.severity == "high"

    def test_security_property_default_severity(self) -> None:
        """Test SecurityProperty defaults to critical severity."""
        prop = SecurityProperty(
            name="test",
            description="test",
            category="test",
        )

        assert prop.severity == "critical"


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestProofResult:
    """Tests for ProofResult dataclass."""

    def test_proof_result_passed(self) -> None:
        """Test ProofResult with passed status."""
        prop = SecurityProperty(
            name="test",
            description="test",
            category="test",
        )
        result = ProofResult(
            security_property=prop,
            status=ProofStatus.PROVED,
            certificate="Test passed",
        )

        assert result.passed is True
        assert result.status == ProofStatus.PROVED

    def test_proof_result_failed(self) -> None:
        """Test ProofResult with failed status."""
        prop = SecurityProperty(
            name="test",
            description="test",
            category="test",
        )
        result = ProofResult(
            security_property=prop,
            status=ProofStatus.REFUTED,
            counterexample={"key": "value"},
        )

        assert result.passed is False
        assert result.counterexample == {"key": "value"}


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestProofStatus:
    """Tests for ProofStatus enum."""

    def test_proof_status_values(self) -> None:
        """Test all ProofStatus enum values."""
        assert ProofStatus.PROVED.value == "proved"
        assert ProofStatus.REFUTED.value == "refuted"
        assert ProofStatus.UNKNOWN.value == "unknown"
        assert ProofStatus.TIMEOUT.value == "timeout"
        assert ProofStatus.ERROR.value == "error"


class TestZ3Availability:
    """Tests for Z3 availability checking."""

    def test_has_z3_constant(self) -> None:
        """Test HAS_Z3 is defined correctly."""
        # HAS_Z3 should be True if we can import z3
        try:
            import z3  # noqa: F401

            assert HAS_Z3 is True
        except ImportError:
            assert HAS_Z3 is False

    @pytest.mark.skipif(HAS_Z3, reason="Test only when Z3 not available")
    def test_prover_raises_without_z3(self) -> None:
        """Test CryptographicProver raises when Z3 not available."""
        with pytest.raises(RuntimeError, match="z3-solver"):
            CryptographicProver()
