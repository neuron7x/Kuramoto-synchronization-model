"""Automated compliance checks for alternative data sources."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable, Mapping

from core.compliance import ComplianceIssue, ComplianceReport


class AltDataComplianceChecker:
    """Perform static licence and usage checks for alternative datasets."""

    def __init__(
        self,
        *,
        allowed_licenses: Iterable[str] | None = None,
        restricted_licenses: Iterable[str] | None = None,
        restricted_regions: Iterable[str] | None = None,
        allowed_usage: Iterable[str] | None = None,
    ) -> None:
        self._allowed = {
            license.lower()
            for license in (allowed_licenses or {"mit", "cc-by", "cc-by-4.0"})
        }
        self._restricted = {
            license.lower()
            for license in (restricted_licenses or {"proprietary", "internal"})
        }
        self._restricted_regions = {
            region.lower() for region in (restricted_regions or set())
        }
        self._allowed_usage = {
            usage.lower()
            for usage in (allowed_usage or {"research", "backtesting", "internal"})
        }

    def _parse_date(self, raw: object) -> datetime | None:
        if raw is None:
            return None
        if isinstance(raw, datetime):
            return raw
        try:
            return datetime.fromisoformat(str(raw))
        except ValueError:
            return None

    def check(self, metadata: Mapping[str, object]) -> ComplianceReport:
        """Return a compliance report for ``metadata``."""

        issues: list[ComplianceIssue] = []
        license_name = str(
            metadata.get("license") or metadata.get("license_name") or ""
        ).strip()
        usage = str(
            metadata.get("permitted_usage") or metadata.get("usage") or ""
        ).strip()
        region = str(
            metadata.get("region") or metadata.get("jurisdiction") or ""
        ).strip()
        expires_at = self._parse_date(metadata.get("expires_at"))

        if not license_name:
            issues.append(ComplianceIssue("error", "License metadata missing"))
        else:
            lowered = license_name.lower()
            if lowered in self._restricted:
                issues.append(
                    ComplianceIssue(
                        "error", f"License {license_name} is explicitly restricted"
                    )
                )
            elif self._allowed and lowered not in self._allowed:
                issues.append(
                    ComplianceIssue(
                        "warning", f"License {license_name} not in approved allow-list"
                    )
                )

        if usage:
            if usage.lower() not in self._allowed_usage:
                issues.append(
                    ComplianceIssue("error", f"Usage '{usage}' not permitted")
                )
        else:
            issues.append(ComplianceIssue("warning", "Usage terms unspecified"))

        if region and region.lower() in self._restricted_regions:
            issues.append(
                ComplianceIssue("error", f"Region {region} restricted for this dataset")
            )

        if expires_at is not None and expires_at < datetime.now(UTC):
            issues.append(ComplianceIssue("error", "License has expired"))

        metadata_view = {
            "license": license_name or "unknown",
            "usage": usage or "unspecified",
            "region": region or "global",
            "expires_at": expires_at.isoformat() if expires_at else "perpetual",
        }
        compliant = not any(issue.severity == "error" for issue in issues)
        return ComplianceReport(compliant, tuple(issues), metadata_view)


__all__ = ["AltDataComplianceChecker", "ComplianceIssue", "ComplianceReport"]
