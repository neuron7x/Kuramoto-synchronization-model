"""Self-audit compliance automation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from research.audit.kernel_purity import audit_determinism


@dataclass(frozen=True)
class AuditReport:
    invariants_checked: int
    invariants_passed: int
    determinism_verified: bool
    timestamp_utc: str


class SelfAuditingModule:
    def audit(self) -> AuditReport:
        purity = audit_determinism()
        checked = len(purity.checks)
        passed = sum(1 for c in purity.checks if c.passed)
        return AuditReport(
            invariants_checked=checked,
            invariants_passed=passed,
            determinism_verified=purity.all_passed,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )

    @property
    def compliance_certificate(self) -> dict:
        report = self.audit()
        return {
            "module": self.__class__.__name__,
            "invariants_checked": report.invariants_checked,
            "invariants_passed": report.invariants_passed,
            "determinism_verified": report.determinism_verified,
            "timestamp_utc": report.timestamp_utc,
        }
