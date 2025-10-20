import pytest

from core.compliance import ComplianceIssue, RegulatoryComplianceValidator


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
        "license": "MIT",
        "intended_domains": ["quant_research"],
        "user_request_process": "https://intranet.tradepulse/privacy-portal",
        "user_request_sla_hours": 48,
        "consent_logging": True,
        "independent_audit": {"independent": True, "frequency_days": 180},
        "remediation_alignment": {"aligned": True, "reference": "jira://risk-123"},
    }


def _severity(issues: tuple[ComplianceIssue, ...]) -> set[str]:
    return {issue.severity for issue in issues}


def test_validator_accepts_compliant_metadata(sample_metadata: dict[str, object]) -> None:
    validator = RegulatoryComplianceValidator()
    report = validator.validate(sample_metadata)
    assert report.compliant
    assert report.issues == ()
    assert report.metadata["license"] == "MIT"
    assert "GDPR" in report.metadata["privacy_regimes"]


def test_validator_flags_missing_privacy_framework(sample_metadata: dict[str, object]) -> None:
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
