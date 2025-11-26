"""Regulatory compliance validation covering privacy, licensing and governance."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .models import ComplianceIssue, ComplianceReport


def _to_lower_set(values: Iterable[str]) -> set[str]:
    return {value.strip().lower() for value in values if str(value).strip()}


def _normalise_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 1:
            return True
        if value == 0:
            return False
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "y", "1", "enabled", "compliant", "aligned"}:
            return True
        if lowered in {
            "false",
            "no",
            "n",
            "0",
            "disabled",
            "non-compliant",
            "misaligned",
        }:
            return False
    return None


def _normalise_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        candidate = int(value)
        if candidate > 0:
            return candidate
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            candidate = int(stripped)
        except ValueError:
            return None
        if candidate > 0:
            return candidate
    return None


def _normalise_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _collect_strings(value: Any) -> set[str]:
    collected: set[str] = set()
    if value is None:
        return collected
    if isinstance(value, str):
        tokens = []
        candidate = value.strip()
        if not candidate:
            return collected
        for token in candidate.replace(";", ",").split(","):
            stripped = token.strip()
            if stripped:
                tokens.append(stripped)
        if not tokens:
            tokens.append(candidate)
        for token in tokens:
            collected.add(token.lower())
        return collected
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _normalise_bool(item) is True:
                collected.add(str(key).strip().lower())
            collected.update(_collect_strings(item))
        return collected
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for item in value:
            collected.update(_collect_strings(item))
        return collected
    return collected


def _lookup_value(metadata: Mapping[str, Any], paths: Sequence[Sequence[str]]) -> Any:
    for path in paths:
        current: Any = metadata
        missing = False
        for segment in path:
            if not isinstance(current, Mapping) or segment not in current:
                missing = True
                break
            current = current[segment]
        if not missing:
            return current
    return None


class RegulatoryComplianceValidator:
    """Validate metadata against privacy, governance, and ethical baselines."""

    def __init__(
        self,
        *,
        required_privacy_regimes: Iterable[str] | None = None,
        required_iso_controls: Iterable[str] | None = None,
        required_nist_controls: Iterable[str] | None = None,
        restricted_licenses: Iterable[str] | None = None,
        restricted_domains: Iterable[str] | None = None,
        allowed_confidentiality_levels: Iterable[str] | None = None,
        minimum_training_restrictions: int = 1,
        maximum_audit_interval_days: int = 365,
    ) -> None:
        self._required_privacy = _to_lower_set(
            required_privacy_regimes or {"gdpr", "ccpa"}
        )
        self._required_iso = _to_lower_set(
            required_iso_controls or {"iso27001", "iso27701"}
        )
        self._required_nist = _to_lower_set(
            required_nist_controls or {"nist-csf", "nist-800-53"}
        )
        self._restricted_licenses = _to_lower_set(
            restricted_licenses
            or {"proprietary", "internal use only", "restricted", "unlicensed"}
        )
        self._restricted_domains = _to_lower_set(
            restricted_domains
            or {
                "retail_investment_advice",
                "mass_surveillance",
                "political_profiling",
                "biometric_tracking",
            }
        )
        self._allowed_confidentiality = _to_lower_set(
            allowed_confidentiality_levels
            or {"public", "internal", "confidential", "restricted"}
        )
        self._minimum_training_restrictions = max(1, int(minimum_training_restrictions))
        self._maximum_audit_interval_days = max(1, int(maximum_audit_interval_days))

    def validate(self, metadata: Mapping[str, Any]) -> ComplianceReport:
        if not isinstance(metadata, Mapping):
            raise TypeError("metadata must be a mapping")

        issues: list[ComplianceIssue] = []

        privacy_values = _collect_strings(
            _lookup_value(
                metadata,
                [
                    ("privacy_regulations",),
                    ("privacy", "regulations"),
                    ("privacy", "frameworks"),
                ],
            )
        )
        gdpr_flag = _normalise_bool(
            _lookup_value(
                metadata,
                [
                    ("gdpr_compliant",),
                    ("privacy", "gdpr"),
                    ("privacy", "frameworks", "gdpr"),
                ],
            )
        )
        ccpa_flag = _normalise_bool(
            _lookup_value(
                metadata,
                [
                    ("ccpa_compliant",),
                    ("privacy", "ccpa"),
                    ("privacy", "frameworks", "ccpa"),
                ],
            )
        )

        if gdpr_flag is False:
            issues.append(
                ComplianceIssue(
                    "error",
                    "GDPR compliance explicitly flagged as non-compliant",
                )
            )
        if ccpa_flag is False:
            issues.append(
                ComplianceIssue(
                    "error",
                    "CCPA compliance explicitly flagged as non-compliant",
                )
            )

        for regime in self._required_privacy:
            if regime not in privacy_values:
                if regime == "gdpr" and gdpr_flag is True:
                    continue
                if regime == "ccpa" and ccpa_flag is True:
                    continue
                issues.append(
                    ComplianceIssue(
                        "error",
                        f"Missing attestation for {regime.upper()} compliance",
                    )
                )

        iso_values = _collect_strings(
            _lookup_value(
                metadata,
                [
                    ("iso_certifications",),
                    ("standards", "iso"),
                    ("compliance", "iso"),
                ],
            )
        )
        if not iso_values.intersection(self._required_iso):
            issues.append(
                ComplianceIssue(
                    "error",
                    "ISO alignment missing required certifications",
                )
            )

        nist_values = _collect_strings(
            _lookup_value(
                metadata,
                [
                    ("nist_alignment",),
                    ("standards", "nist"),
                    ("compliance", "nist"),
                ],
            )
        )
        if not nist_values.intersection(self._required_nist):
            issues.append(
                ComplianceIssue(
                    "error",
                    "NIST alignment missing required control frameworks",
                )
            )

        owner = _normalise_string(
            _lookup_value(
                metadata,
                [
                    ("data_ownership",),
                    ("ownership",),
                    ("governance", "ownership"),
                ],
            )
        )
        if not owner:
            issues.append(ComplianceIssue("error", "Data ownership is unspecified"))

        confidentiality = _normalise_string(
            _lookup_value(
                metadata,
                [
                    ("confidentiality",),
                    ("sensitivity",),
                    ("classification",),
                ],
            )
        )
        if not confidentiality:
            issues.append(
                ComplianceIssue("error", "Confidentiality classification missing")
            )
        elif confidentiality.strip().lower() not in self._allowed_confidentiality:
            issues.append(
                ComplianceIssue(
                    "error",
                    f"Confidentiality level '{confidentiality}' is not permitted",
                )
            )

        retention_days = _normalise_positive_int(
            _lookup_value(
                metadata,
                [
                    ("retention_policy_days",),
                    ("retention", "days"),
                    ("retention_policy", "days"),
                ],
            )
        )
        if retention_days is None:
            issues.append(
                ComplianceIssue(
                    "error",
                    "Retention policy does not specify a positive duration",
                )
            )

        retention_basis = _normalise_string(
            _lookup_value(
                metadata,
                [
                    ("retention_policy", "basis"),
                    ("retention", "basis"),
                    ("retention_policy_reference",),
                ],
            )
        )
        if not retention_basis:
            issues.append(
                ComplianceIssue(
                    "warning",
                    "Retention policy lacks documented legal basis or reference",
                )
            )

        training_restrictions = _collect_strings(
            _lookup_value(
                metadata,
                [
                    ("training_restrictions",),
                    ("training", "restrictions"),
                    ("usage", "training_restrictions"),
                ],
            )
        )
        if len(training_restrictions) < self._minimum_training_restrictions:
            issues.append(
                ComplianceIssue(
                    "error",
                    "Training restrictions are incomplete or missing",
                )
            )

        license_name = _normalise_string(
            _lookup_value(
                metadata,
                [
                    ("license",),
                    ("license_name",),
                    ("usage", "license"),
                ],
            )
        )
        if not license_name:
            issues.append(ComplianceIssue("error", "License metadata is missing"))
        elif license_name.strip().lower() in self._restricted_licenses:
            issues.append(
                ComplianceIssue(
                    "error",
                    f"License {license_name} is restricted from use",
                )
            )

        intended_domains = _collect_strings(
            _lookup_value(
                metadata,
                [
                    ("intended_domains",),
                    ("usage", "domains"),
                    ("domains", "allowed"),
                ],
            )
        )
        forbidden_domains = intended_domains.intersection(self._restricted_domains)
        if forbidden_domains:
            issues.append(
                ComplianceIssue(
                    "error",
                    "Intended domains include forbidden areas: "
                    + ", ".join(
                        sorted(domain.replace("_", " ") for domain in forbidden_domains)
                    ),
                )
            )

        user_request_process = _normalise_string(
            _lookup_value(
                metadata,
                [
                    ("user_request_process",),
                    ("user_requests", "process"),
                    ("data_subject_access", "process"),
                ],
            )
        )
        if not user_request_process:
            issues.append(
                ComplianceIssue(
                    "error",
                    "Process for user data requests is undefined",
                )
            )

        user_request_sla = _normalise_positive_int(
            _lookup_value(
                metadata,
                [
                    ("user_request_sla_hours",),
                    ("user_requests", "sla_hours"),
                    ("data_subject_access", "sla_hours"),
                ],
            )
        )
        if user_request_sla is not None and user_request_sla > 168:
            issues.append(
                ComplianceIssue(
                    "warning",
                    "User request SLA exceeds one week; review regulatory commitments",
                )
            )

        consent_logging = _normalise_bool(
            _lookup_value(
                metadata,
                [
                    ("consent_logging",),
                    ("consent", "logging"),
                    ("privacy", "consent_logging"),
                ],
            )
        )
        if consent_logging is not True:
            issues.append(
                ComplianceIssue(
                    "error",
                    "Consent logging must be enabled and verifiable",
                )
            )

        audit_section = _lookup_value(
            metadata,
            [
                ("independent_audit",),
                ("audit",),
                ("audits",),
            ],
        )
        audit_frequency: int | None = None
        audit_independent: bool | None = None
        if isinstance(audit_section, Mapping):
            audit_independent = _normalise_bool(
                audit_section.get("independent") or audit_section.get("enabled")
            )
            audit_frequency = _normalise_positive_int(
                audit_section.get("frequency_days")
                or audit_section.get("interval_days")
            )
        else:
            audit_independent = _normalise_bool(audit_section)

        if audit_independent is not True:
            issues.append(
                ComplianceIssue(
                    "error",
                    "Independent audit coverage is not confirmed",
                )
            )
        if audit_frequency is None:
            issues.append(
                ComplianceIssue(
                    "error",
                    "Audit cadence must specify frequency in days",
                )
            )
        elif audit_frequency > self._maximum_audit_interval_days:
            issues.append(
                ComplianceIssue(
                    "warning",
                    "Audit frequency exceeds configured maximum interval",
                )
            )

        remediation_section = _lookup_value(
            metadata,
            [
                ("remediation_alignment",),
                ("remediation",),
                ("remediation_plan",),
            ],
        )
        remediation_aligned = _normalise_bool(remediation_section)
        remediation_reference: str | None = None
        if isinstance(remediation_section, Mapping):
            remediation_aligned = _normalise_bool(
                remediation_section.get("aligned")
                or remediation_section.get("approved")
            )
            remediation_reference = _normalise_string(
                remediation_section.get("reference") or remediation_section.get("plan")
            )
        elif isinstance(remediation_section, str):
            remediation_reference = remediation_section.strip()

        if remediation_aligned is not True:
            issues.append(
                ComplianceIssue(
                    "error",
                    "Remediation commitments are not aligned with compliance controls",
                )
            )
        if remediation_reference is None:
            issues.append(
                ComplianceIssue(
                    "warning",
                    "Remediation plan reference is missing",
                )
            )

        metadata_view = {
            "privacy_regimes": ", ".join(
                sorted(value.upper() for value in privacy_values)
            ),
            "iso_controls": ", ".join(sorted(value.upper() for value in iso_values)),
            "nist_controls": ", ".join(sorted(value.upper() for value in nist_values)),
            "license": license_name or "unspecified",
            "confidentiality": confidentiality or "unspecified",
            "owner": owner or "unspecified",
            "retention_days": str(retention_days or "unspecified"),
            "training_restrictions": ", ".join(sorted(training_restrictions)),
            "user_request_process": user_request_process or "unspecified",
            "audit_frequency_days": str(audit_frequency or "unspecified"),
        }

        compliant = not any(issue.severity == "error" for issue in issues)
        return ComplianceReport(compliant, tuple(issues), metadata_view)


__all__ = ["RegulatoryComplianceValidator"]
