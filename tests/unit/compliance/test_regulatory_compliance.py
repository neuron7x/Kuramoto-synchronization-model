import pytest

from core.compliance import ComplianceIssue, RegulatoryComplianceValidator
from core.compliance import regulatory as reg


@pytest.fixture()
def sample_metadata() -> dict[str, object]:
    return {
        "privacy_regulations": ["GDPR", "CCPA"],
        "gdpr_compliant": True,
        "ccpa_compliant": True,
        "iso_certifications": ["ISO27001", "ISO27701"],
        "nist_alignment": ["NIST-CSF"],
        "data_ownership": "TradePulse",
        "confidentiality": "Confidential",
        "retention_policy_days": 365,
        "retention_policy_reference": "policy://retention/market-data",
        "training_restrictions": ["no_personal_data", "approved_sources_only"],
        "license": "TradePulse Proprietary License Agreement (TPLA)",
        "intended_domains": ["quant_research"],
        "user_request_process": "https://intranet.tradepulse/privacy-portal",
        "user_request_sla_hours": 48,
        "consent_logging": True,
        "independent_audit": {"independent": True, "frequency_days": 180},
        "remediation_alignment": {"aligned": True, "reference": "jira://risk-123"},
    }


def _severity(issues: tuple[ComplianceIssue, ...]) -> set[str]:
    return {issue.severity for issue in issues}


def test_helper_normalisation_functions() -> None:
    """Low-level helpers should gracefully normalise heterogeneous inputs."""

    assert reg._normalise_bool(True) is True
    assert reg._normalise_bool(1) is True
    assert reg._normalise_bool(0) is False
    assert reg._normalise_bool("enabled") is True
    assert reg._normalise_bool("non-compliant") is False
    assert reg._normalise_bool("maybe") is None

    assert reg._normalise_positive_int(5) == 5
    assert reg._normalise_positive_int("10") == 10
    assert reg._normalise_positive_int(0) is None
    assert reg._normalise_positive_int("  ") is None
    assert reg._normalise_positive_int("-5") is None
    assert reg._normalise_positive_int("not-a-number") is None
    assert reg._normalise_positive_int(True) is None

    assert reg._normalise_string(" trimmed ") == "trimmed"
    assert reg._normalise_string(123) == "123"
    assert reg._normalise_string("") is None
    assert reg._normalise_string(None) is None


def test_collect_strings_handles_nested_structures() -> None:
    """_collect_strings should flatten tokens across composite structures."""

    payload = {
        "headline": "Alpha; Beta , Gamma",
        "toggles": {"delta": True, "epsilon": False},
        "nested": [{"zeta": "YES"}, "Theta"],
    }

    result = reg._collect_strings(payload)

    assert result == {
        "alpha",
        "beta",
        "gamma",
        "delta",
        "theta",
        "yes",
        "zeta",
    }

    assert reg._collect_strings(None) == set()
    assert reg._collect_strings("   ") == set()
    assert reg._collect_strings(";;") == {";;"}


def test_lookup_value_prefers_first_matching_path() -> None:
    """Paths are evaluated in order, returning the first existing value."""

    metadata = {
        "privacy": {"frameworks": {"gdpr": "yes"}},
        "fallback": "used-second",
    }

    assert (
        reg._lookup_value(
            metadata,
            [
                ("privacy", "frameworks", "gdpr"),
                ("fallback",),
            ],
        )
        == "yes"
    )
    assert reg._lookup_value(metadata, [("missing",), ("fallback",)]) == "used-second"


def test_validator_rejects_non_mapping_metadata() -> None:
    """Validator should guard against accidental non-mapping payloads."""

    validator = RegulatoryComplianceValidator()
    with pytest.raises(TypeError):
        validator.validate(["not", "mapping"])  # type: ignore[arg-type]


def test_validator_detects_broad_failures() -> None:
    """An incomplete metadata payload surfaces comprehensive diagnostics."""

    validator = RegulatoryComplianceValidator()
    report = validator.validate(
        {
            "privacy_regulations": [],
            "gdpr_compliant": False,
            "ccpa_compliant": "no",
            "iso_certifications": [],
            "nist_alignment": [],
            "confidentiality": "Top Secret",
            "retention_policy_days": 0,
            "training_restrictions": [],
            "license": "Proprietary",
            "intended_domains": ["mass_surveillance"],
            "user_request_sla_hours": 200,
            "consent_logging": "disabled",
            "independent_audit": {"independent": False, "frequency_days": 720},
            "remediation_alignment": {"aligned": False},
        }
    )

    assert not report.compliant
    messages = {issue.message for issue in report.issues}

    assert "GDPR compliance explicitly flagged as non-compliant" in messages
    assert "CCPA compliance explicitly flagged as non-compliant" in messages
    assert any("Missing attestation" in message for message in messages)
    assert "ISO alignment missing required certifications" in messages
    assert "NIST alignment missing required control frameworks" in messages
    assert "Data ownership is unspecified" in messages
    assert "Confidentiality level 'Top Secret' is not permitted" in messages
    assert "Retention policy does not specify a positive duration" in messages
    assert any("Retention policy lacks" in message for message in messages)
    assert "Training restrictions are incomplete or missing" in messages
    assert any("License Proprietary" in message for message in messages)
    assert any("forbidden areas" in message for message in messages)
    assert "Process for user data requests is undefined" in messages
    assert any("User request SLA exceeds one week" in message for message in messages)
    assert any("Consent logging must be enabled" in message for message in messages)
    assert "Independent audit coverage is not confirmed" in messages
    assert "Audit frequency exceeds configured maximum interval" in messages
    assert any(
        "Remediation commitments are not aligned" in message for message in messages
    )
    assert "Remediation plan reference is missing" in messages


def test_validator_requires_audit_frequency(sample_metadata: dict[str, object]) -> None:
    """Audit declarations must specify a cadence when marked as independent."""

    sample_metadata["independent_audit"] = {"independent": True}
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)

    assert not report.compliant
    assert any("Audit cadence" in issue.message for issue in report.issues)


def test_validator_accepts_string_remediation_reference(
    sample_metadata: dict[str, object],
) -> None:
    """Plain string remediation notes should count as both alignment and reference."""

    sample_metadata["remediation_alignment"] = " aligned "
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)

    assert report.compliant
    assert report.metadata["user_request_process"].startswith("https://")


def test_validator_skips_attested_privacy_requirements(
    sample_metadata: dict[str, object],
) -> None:
    """Explicit GDPR/CCPA flags should satisfy the regulatory checklist."""

    sample_metadata["privacy_regulations"] = []
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)

    assert report.compliant


def test_validator_flags_missing_confidentiality_and_license(
    sample_metadata: dict[str, object],
) -> None:
    """Absence of key metadata should yield direct validation errors."""

    sample_metadata.pop("confidentiality", None)
    sample_metadata.pop("license", None)
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)

    assert not report.compliant
    messages = {issue.message for issue in report.issues}
    assert "Confidentiality classification missing" in messages
    assert "License metadata is missing" in messages


def test_validator_accepts_scalar_audit_toggle(
    sample_metadata: dict[str, object],
) -> None:
    """Scalar audit indicators should be normalised just like mappings."""

    sample_metadata["independent_audit"] = "yes"
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)

    assert not report.compliant
    assert any("Audit cadence" in issue.message for issue in report.issues)


def test_validator_accepts_compliant_metadata(
    sample_metadata: dict[str, object],
) -> None:
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)
    assert report.compliant
    assert report.issues == ()
    assert (
        report.metadata["license"] == "TradePulse Proprietary License Agreement (TPLA)"
    )
    assert "GDPR" in report.metadata["privacy_regimes"]


def test_validator_flags_missing_privacy_framework(
    sample_metadata: dict[str, object],
) -> None:
    sample_metadata.pop("ccpa_compliant", None)
    sample_metadata["privacy_regulations"] = ["GDPR"]
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)
    assert not report.compliant
    assert any("CCPA" in issue.message for issue in report.issues)


def test_validator_blocks_restricted_domain(sample_metadata: dict[str, object]) -> None:
    sample_metadata["intended_domains"] = ["retail_investment_advice", "quant_research"]
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)
    assert not report.compliant
    assert any("forbidden" in issue.message for issue in report.issues)


def test_validator_requires_consent_logging(sample_metadata: dict[str, object]) -> None:
    sample_metadata["consent_logging"] = False
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)
    assert not report.compliant
    severities = _severity(report.issues)
    assert "error" in severities
    assert any("Consent" in issue.message for issue in report.issues)
