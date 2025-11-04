from __future__ import annotations

import contextlib

from core.compliance.regulatory import RegulatoryComplianceValidator
from observability.tracing import chaos_span


def test_regulatory_validator_surfaces_black_swan_gaps(monkeypatch):
    captured: dict[str, object] = {}

    def fake_pipeline(stage: str, **attrs):
        captured.setdefault("events", []).append((stage, attrs))
        return contextlib.nullcontext(None)

    monkeypatch.setattr("observability.tracing.pipeline_span", fake_pipeline)

    validator = RegulatoryComplianceValidator(
        required_privacy_regimes=("gdpr", "ccpa"),
        required_iso_controls=("iso27001",),
        required_nist_controls=("nist-csf",),
        minimum_training_restrictions=2,
        maximum_audit_interval_days=90,
    )

    shock_metadata = {
        "privacy_regulations": ["hipaa"],
        "iso_certifications": [],
        "nist_alignment": [],
        "license": "Proprietary",
        "retention_policy_days": 0,
        "training_restrictions": ["market-data"],
        "intended_domains": ["mass_surveillance"],
        "consent_logging": False,
        "independent_audit": {"independent": False, "frequency_days": 400},
    }

    with chaos_span("risk-compliance", disruption="metadata-shock"):
        report = validator.validate(shock_metadata)

    assert report.compliant is False
    errors = {issue.message for issue in report.issues if issue.severity == "error"}
    assert "Missing attestation for GDPR compliance" in errors
    assert "ISO alignment missing required certifications" in errors
    assert "License Proprietary is restricted from use" in errors

    assert captured["events"][0][0] == "chaos.risk-compliance"
    attrs = captured["events"][0][1]
    assert attrs["chaos.experiment"] == "risk-compliance"
    assert attrs["disruption"] == "metadata-shock"
