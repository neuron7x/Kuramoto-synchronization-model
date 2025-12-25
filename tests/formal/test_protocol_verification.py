"""Tests for formal protocol verification.

This test module validates the protocol verification system for
TLS 1.3 and HMAC-based protocols.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from formal.protocol_verification import (
    HAS_Z3,
    HMACProtocolVerifier,
    ProtocolProofResult,
    ProtocolProperty,
    ProtocolVerificationReport,
    TLSProtocolVerifier,
    verify_protocol_security,
)


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestTLSProtocolVerifier:
    """Tests for TLS 1.3 protocol verification."""

    @pytest.fixture
    def verifier(self) -> TLSProtocolVerifier:
        """Create a TLSProtocolVerifier instance."""
        return TLSProtocolVerifier(timeout_ms=60000)

    def test_verifier_initialization(self, verifier: TLSProtocolVerifier) -> None:
        """Test verifier initializes correctly."""
        assert verifier.timeout_ms == 60000
        assert verifier._z3 is not None

    def test_key_exchange_security(self, verifier: TLSProtocolVerifier) -> None:
        """Test key exchange security verification."""
        result = verifier.verify_key_exchange_security()

        assert isinstance(result, ProtocolProofResult)
        assert result.property == ProtocolProperty.CONFIDENTIALITY
        assert result.holds is True
        assert "ECDHE" in result.certificate

    def test_forward_secrecy(self, verifier: TLSProtocolVerifier) -> None:
        """Test forward secrecy verification."""
        result = verifier.verify_forward_secrecy()

        assert isinstance(result, ProtocolProofResult)
        assert result.property == ProtocolProperty.FORWARD_SECRECY
        assert result.holds is True
        assert "forward secrecy" in result.certificate.lower()

    def test_authentication(self, verifier: TLSProtocolVerifier) -> None:
        """Test server authentication verification."""
        result = verifier.verify_authentication()

        assert isinstance(result, ProtocolProofResult)
        assert result.property == ProtocolProperty.AUTHENTICATION
        assert result.holds is True

    def test_replay_resistance(self, verifier: TLSProtocolVerifier) -> None:
        """Test replay attack resistance verification."""
        result = verifier.verify_replay_resistance()

        assert isinstance(result, ProtocolProofResult)
        assert result.property == ProtocolProperty.REPLAY_RESISTANCE
        assert result.holds is True
        assert "nonce" in result.certificate.lower()
        assert "inductive" in result.certificate.lower()

    def test_session_binding(self, verifier: TLSProtocolVerifier) -> None:
        """Test session binding verification."""
        result = verifier.verify_session_binding()

        assert isinstance(result, ProtocolProofResult)
        assert result.property == ProtocolProperty.SESSION_BINDING
        assert result.holds is True


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestProtocolVerificationReport:
    """Tests for protocol verification report."""

    @pytest.fixture
    def verifier(self) -> TLSProtocolVerifier:
        """Create a TLSProtocolVerifier instance."""
        return TLSProtocolVerifier(timeout_ms=60000)

    def test_verify_all_generates_report(self, verifier: TLSProtocolVerifier) -> None:
        """Test verify_all generates complete report."""
        report = verifier.verify_all()

        assert isinstance(report, ProtocolVerificationReport)
        assert report.protocol_name == "TLS 1.3"
        assert len(report.results) == 5
        assert report.total_time_ms > 0

    def test_all_properties_verified(self, verifier: TLSProtocolVerifier) -> None:
        """Test all protocol properties are verified."""
        report = verifier.verify_all()

        assert report.all_secure is True

        properties_verified = {r.property for r in report.results}
        expected_properties = {
            ProtocolProperty.CONFIDENTIALITY,
            ProtocolProperty.FORWARD_SECRECY,
            ProtocolProperty.AUTHENTICATION,
            ProtocolProperty.REPLAY_RESISTANCE,
            ProtocolProperty.SESSION_BINDING,
        }
        assert properties_verified == expected_properties

    def test_save_certificate(
        self, verifier: TLSProtocolVerifier, tmp_path: Path
    ) -> None:
        """Test saving protocol verification certificate."""
        cert_path = tmp_path / "PROTOCOL_CERT.txt"
        verifier.verify_all(output_path=cert_path)

        assert cert_path.exists()
        content = cert_path.read_text(encoding="utf-8")

        assert "PROTOCOL VERIFICATION CERTIFICATE" in content
        assert "TLS 1.3" in content
        assert "All Secure: True" in content


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestHMACProtocolVerifier:
    """Tests for HMAC protocol verification."""

    @pytest.fixture
    def verifier(self) -> HMACProtocolVerifier:
        """Create an HMACProtocolVerifier instance."""
        return HMACProtocolVerifier(timeout_ms=60000)

    def test_verifier_initialization(self, verifier: HMACProtocolVerifier) -> None:
        """Test verifier initializes correctly."""
        assert verifier.timeout_ms == 60000

    def test_message_authentication(self, verifier: HMACProtocolVerifier) -> None:
        """Test message authentication verification."""
        result = verifier.verify_message_authentication()

        assert isinstance(result, ProtocolProofResult)
        assert result.property == ProtocolProperty.AUTHENTICATION
        assert result.holds is True
        assert "HMAC-SHA256" in result.certificate

    def test_key_freshness(self, verifier: HMACProtocolVerifier) -> None:
        """Test key freshness verification."""
        result = verifier.verify_key_freshness()

        assert isinstance(result, ProtocolProofResult)
        assert result.property == ProtocolProperty.KEY_FRESHNESS
        assert result.holds is True
        assert "HKDF" in result.certificate


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestVerifyProtocolSecurity:
    """Tests for the verify_protocol_security function."""

    def test_verify_returns_report(self) -> None:
        """Test main verification function returns report."""
        report = verify_protocol_security()

        assert isinstance(report, ProtocolVerificationReport)
        assert report.all_secure is True

    def test_verify_with_output_path(self, tmp_path: Path) -> None:
        """Test verification with output path."""
        cert_path = tmp_path / "cert.txt"
        report = verify_protocol_security(output_path=cert_path)

        assert report.all_secure is True
        assert cert_path.exists()


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestProtocolProperty:
    """Tests for ProtocolProperty enum."""

    def test_all_properties_defined(self) -> None:
        """Test all protocol properties are defined."""
        properties = [
            ProtocolProperty.CONFIDENTIALITY,
            ProtocolProperty.AUTHENTICATION,
            ProtocolProperty.INTEGRITY,
            ProtocolProperty.FORWARD_SECRECY,
            ProtocolProperty.REPLAY_RESISTANCE,
            ProtocolProperty.KEY_FRESHNESS,
            ProtocolProperty.SESSION_BINDING,
        ]

        assert len(properties) == 7
        for prop in properties:
            assert prop.value != ""


@pytest.mark.skipif(not HAS_Z3, reason="z3-solver dependency is not installed")
class TestProtocolProofResult:
    """Tests for ProtocolProofResult dataclass."""

    def test_result_holds(self) -> None:
        """Test result with holds=True."""
        result = ProtocolProofResult(
            property=ProtocolProperty.CONFIDENTIALITY,
            holds=True,
            certificate="Property verified",
        )

        assert result.holds is True
        assert result.attack_trace is None

    def test_result_not_holds(self) -> None:
        """Test result with holds=False."""
        result = ProtocolProofResult(
            property=ProtocolProperty.CONFIDENTIALITY,
            holds=False,
            certificate="Property violated",
        )

        assert result.holds is False


class TestZ3AvailabilityProtocol:
    """Tests for Z3 availability in protocol verification."""

    def test_has_z3_constant(self) -> None:
        """Test HAS_Z3 is defined correctly."""
        try:
            import z3  # noqa: F401

            assert HAS_Z3 is True
        except ImportError:
            assert HAS_Z3 is False

    @pytest.mark.skipif(HAS_Z3, reason="Test only when Z3 not available")
    def test_verifier_raises_without_z3(self) -> None:
        """Test TLSProtocolVerifier raises when Z3 not available."""
        with pytest.raises(RuntimeError, match="Z3"):
            TLSProtocolVerifier()
