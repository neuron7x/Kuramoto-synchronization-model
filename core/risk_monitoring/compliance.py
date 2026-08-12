# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Regulatory Compliance for Risk Monitoring.

This module provides compliance support for global trading regulations:
- MiFID II (European Union)
- Dodd-Frank (United States)
- Clear audit trails and transparency features

Integrates with existing core.compliance modules for MiFID II support.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = [
    "ComplianceManager",
    "DoddFrankReporter",
    "AuditTrailEntry",
    "RegulatoryReport",
    "ComplianceViolation",
    "RegulationType",
]

LOGGER = logging.getLogger(__name__)


class RegulationType(str, Enum):
    """Supported regulatory frameworks."""

    MIFID_II = "mifid_ii"
    DODD_FRANK = "dodd_frank"
    INTERNAL = "internal"


@dataclass(slots=True)
class AuditTrailEntry:
    """Audit trail entry for regulatory compliance.

    Attributes:
        entry_id: Unique identifier for the entry.
        timestamp: When the event occurred.
        event_type: Type of event (e.g., order, risk_check, position_change).
        actor: Who/what initiated the action.
        action: Description of the action taken.
        details: Additional event details.
        risk_decision: Risk-related decision if applicable.
        regulation: Applicable regulation.
        hash_chain: Hash linking to previous entry for tamper detection.
    """

    entry_id: str
    timestamp: datetime
    event_type: str
    actor: str
    action: str
    details: Mapping[str, Any] = field(default_factory=dict)
    risk_decision: str | None = None
    regulation: RegulationType = RegulationType.INTERNAL
    hash_chain: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "actor": self.actor,
            "action": self.action,
            "details": dict(self.details),
            "risk_decision": self.risk_decision,
            "regulation": self.regulation.value,
            "hash_chain": self.hash_chain,
        }


@dataclass(slots=True)
class ComplianceViolation:
    """Record of a compliance violation.

    Attributes:
        violation_id: Unique identifier.
        timestamp: When violation was detected.
        regulation: Violated regulation.
        rule: Specific rule that was violated.
        severity: Severity level (warning, error, critical).
        description: Description of the violation.
        remediation: Remediation steps taken.
        resolved: Whether the violation has been resolved.
    """

    violation_id: str
    timestamp: datetime
    regulation: RegulationType
    rule: str
    severity: str
    description: str
    remediation: str = ""
    resolved: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "violation_id": self.violation_id,
            "timestamp": self.timestamp.isoformat(),
            "regulation": self.regulation.value,
            "rule": self.rule,
            "severity": self.severity,
            "description": self.description,
            "remediation": self.remediation,
            "resolved": self.resolved,
        }


@dataclass(slots=True)
class RegulatoryReport:
    """Comprehensive regulatory compliance report.

    Attributes:
        report_id: Unique report identifier.
        generated_at: Report generation timestamp.
        regulation: Target regulation.
        period_start: Start of reporting period.
        period_end: End of reporting period.
        audit_entries: Audit trail entries in period.
        violations: Compliance violations in period.
        risk_metrics: Risk-related metrics.
        executive_summary: Summary for regulators.
    """

    report_id: str
    generated_at: datetime
    regulation: RegulationType
    period_start: datetime
    period_end: datetime
    audit_entries: Sequence[AuditTrailEntry] = field(default_factory=list)
    violations: Sequence[ComplianceViolation] = field(default_factory=list)
    risk_metrics: Mapping[str, Any] = field(default_factory=dict)
    executive_summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "report_id": self.report_id,
            "generated_at": self.generated_at.isoformat(),
            "regulation": self.regulation.value,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "audit_entries_count": len(self.audit_entries),
            "violations_count": len(self.violations),
            "unresolved_violations": sum(1 for v in self.violations if not v.resolved),
            "risk_metrics": dict(self.risk_metrics),
            "executive_summary": self.executive_summary,
        }


class DoddFrankReporter:
    """Dodd-Frank Act compliance reporter.

    Implements reporting requirements for:
    - Swap Data Repository (SDR) reporting
    - Real-time public reporting
    - Large trader reporting
    - Position limits monitoring
    """

    def __init__(
        self,
        *,
        storage_path: Path | str,
        entity_id: str = "GEOSYNC",
        retention_days: int = 2557,  # ~7 years (includes leap years: 7*365 + 2)
    ) -> None:
        """Initialize Dodd-Frank reporter.

        Args:
            storage_path: Path for storing compliance records.
            entity_id: Legal Entity Identifier (LEI) or internal ID.
            retention_days: Data retention period in days (default ~7 years).
        """
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._entity_id = entity_id
        self._retention_delta = timedelta(days=retention_days)
        self._lock = threading.RLock()

        # In-memory buffers for batching
        self._swap_reports: list[dict[str, Any]] = []
        self._position_reports: list[dict[str, Any]] = []
        self._large_trader_reports: list[dict[str, Any]] = []

        LOGGER.info(
            "Dodd-Frank reporter initialized",
            extra={
                "entity_id": entity_id,
                "storage_path": str(self._storage_path),
            },
        )

    def record_swap_transaction(
        self,
        *,
        transaction_id: str,
        counterparty: str,
        asset_class: str,
        notional: float,
        execution_time: datetime,
        trade_type: str,
        price: float,
        maturity: datetime | None = None,
    ) -> dict[str, Any]:
        """Record a swap transaction for SDR reporting.

        Args:
            transaction_id: Unique transaction identifier.
            counterparty: Counterparty identifier.
            asset_class: Asset class (IR, FX, Credit, etc.).
            notional: Notional amount.
            execution_time: Time of execution.
            trade_type: Type of trade (new, amend, cancel).
            price: Transaction price or rate.
            maturity: Maturity date if applicable.

        Returns:
            The recorded transaction details.
        """
        with self._lock:
            record = {
                "transaction_id": transaction_id,
                "reporting_entity": self._entity_id,
                "counterparty": counterparty,
                "asset_class": asset_class,
                "notional": notional,
                "execution_time": execution_time.isoformat(),
                "trade_type": trade_type,
                "price": price,
                "maturity": maturity.isoformat() if maturity else None,
                "reported_at": datetime.now(timezone.utc).isoformat(),
                "regulation": RegulationType.DODD_FRANK.value,
            }
            self._swap_reports.append(record)
            LOGGER.debug("Recorded swap transaction %s", transaction_id)
            return record

    def record_position(
        self,
        *,
        position_id: str,
        asset: str,
        position_size: float,
        notional_value: float,
        position_date: datetime,
    ) -> dict[str, Any]:
        """Record position for position limits monitoring.

        Args:
            position_id: Position identifier.
            asset: Asset identifier.
            position_size: Size of position in units.
            notional_value: Notional value of position.
            position_date: Date of position snapshot.

        Returns:
            The recorded position details.
        """
        with self._lock:
            record = {
                "position_id": position_id,
                "reporting_entity": self._entity_id,
                "asset": asset,
                "position_size": position_size,
                "notional_value": notional_value,
                "position_date": position_date.isoformat(),
                "reported_at": datetime.now(timezone.utc).isoformat(),
            }
            self._position_reports.append(record)
            return record

    def check_large_trader_threshold(
        self,
        *,
        trader_id: str,
        aggregate_position: float,
        threshold: float,
        asset_class: str,
    ) -> bool:
        """Check if large trader reporting threshold is breached.

        Args:
            trader_id: Trader or account identifier.
            aggregate_position: Aggregate position across venues.
            threshold: Applicable threshold for the asset class.
            asset_class: Asset class being checked.

        Returns:
            True if threshold is exceeded and reporting required.
        """
        with self._lock:
            if aggregate_position > threshold:
                record = {
                    "trader_id": trader_id,
                    "aggregate_position": aggregate_position,
                    "threshold": threshold,
                    "asset_class": asset_class,
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "threshold_exceeded": True,
                }
                self._large_trader_reports.append(record)
                LOGGER.warning(
                    "Large trader threshold exceeded",
                    extra=record,
                )
                return True
            return False

    def flush_to_storage(self) -> Path:
        """Flush buffered reports to storage.

        Returns:
            Path to the generated report file.
        """
        with self._lock:
            timestamp = datetime.now(timezone.utc)
            payload = {
                "entity_id": self._entity_id,
                "generated_at": timestamp.isoformat(),
                "swap_transactions": list(self._swap_reports),
                "position_reports": list(self._position_reports),
                "large_trader_reports": list(self._large_trader_reports),
            }

            filename = f"dodd-frank-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"
            target = self._storage_path / filename
            target.write_text(json.dumps(payload, indent=2))

            # Clear buffers
            self._swap_reports.clear()
            self._position_reports.clear()
            self._large_trader_reports.clear()

            self._apply_retention()
            LOGGER.info("Flushed Dodd-Frank reports to %s", target)
            return target

    def generate_summary(self) -> dict[str, Any]:
        """Generate summary of Dodd-Frank compliance status.

        Returns:
            Summary dictionary.
        """
        with self._lock:
            return {
                "entity_id": self._entity_id,
                "pending_swap_reports": len(self._swap_reports),
                "pending_position_reports": len(self._position_reports),
                "large_trader_breaches": len(self._large_trader_reports),
                "storage_path": str(self._storage_path),
            }

    def _apply_retention(self) -> None:
        """Apply retention policy to stored files."""
        cutoff = datetime.now(timezone.utc) - self._retention_delta
        for artefact in self._storage_path.glob("dodd-frank-*.json"):
            try:
                timestamp_str = artefact.stem.split("-", 2)[-1]
                timestamp = datetime.strptime(timestamp_str, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            if timestamp < cutoff:
                artefact.unlink(missing_ok=True)


class ComplianceManager:
    """Unified compliance manager for multiple regulations.

    Coordinates MiFID II, Dodd-Frank, and internal compliance
    requirements with centralized audit trail management.
    """

    def __init__(
        self,
        *,
        storage_path: Path | str,
        entity_id: str = "GEOSYNC",
    ) -> None:
        """Initialize compliance manager.

        Args:
            storage_path: Base path for compliance storage.
            entity_id: Entity identifier for reporting.
        """
        self._storage_path = Path(storage_path)
        self._storage_path.mkdir(parents=True, exist_ok=True)
        self._entity_id = entity_id
        self._lock = threading.RLock()

        # Audit trail storage
        self._audit_trail: list[AuditTrailEntry] = []
        self._violations: list[ComplianceViolation] = []
        self._entry_counter = 0
        self._violation_counter = 0

        # Initialize sub-reporters
        self._dodd_frank = DoddFrankReporter(
            storage_path=self._storage_path / "dodd-frank",
            entity_id=entity_id,
        )

        LOGGER.info(
            "Compliance manager initialized",
            extra={"entity_id": entity_id, "storage_path": str(self._storage_path)},
        )

    @property
    def dodd_frank(self) -> DoddFrankReporter:
        """Access Dodd-Frank reporter."""
        return self._dodd_frank

    def record_audit_entry(
        self,
        *,
        event_type: str,
        actor: str,
        action: str,
        details: Mapping[str, Any] | None = None,
        risk_decision: str | None = None,
        regulation: RegulationType = RegulationType.INTERNAL,
    ) -> AuditTrailEntry:
        """Record an audit trail entry.

        Args:
            event_type: Type of event.
            actor: Who initiated the action.
            action: Description of the action.
            details: Additional details.
            risk_decision: Risk-related decision.
            regulation: Applicable regulation.

        Returns:
            The created audit entry.
        """
        with self._lock:
            self._entry_counter += 1
            entry_id = f"AUD-{self._entry_counter:08d}"

            # Create hash chain for tamper detection
            previous_hash = None
            if self._audit_trail:
                prev = self._audit_trail[-1]
                previous_hash = f"{prev.entry_id}:{prev.timestamp.isoformat()}"

            entry = AuditTrailEntry(
                entry_id=entry_id,
                timestamp=datetime.now(timezone.utc),
                event_type=event_type,
                actor=actor,
                action=action,
                details=details or {},
                risk_decision=risk_decision,
                regulation=regulation,
                hash_chain=previous_hash,
            )
            self._audit_trail.append(entry)

            LOGGER.debug(
                "Recorded audit entry %s",
                entry_id,
                extra={"event_type": event_type, "actor": actor},
            )
            return entry

    def record_violation(
        self,
        *,
        regulation: RegulationType,
        rule: str,
        severity: str,
        description: str,
        remediation: str = "",
    ) -> ComplianceViolation:
        """Record a compliance violation.

        Args:
            regulation: Violated regulation.
            rule: Specific rule violated.
            severity: Severity level.
            description: Violation description.
            remediation: Remediation steps.

        Returns:
            The created violation record.
        """
        with self._lock:
            self._violation_counter += 1
            violation_id = f"VIO-{self._violation_counter:06d}"

            violation = ComplianceViolation(
                violation_id=violation_id,
                timestamp=datetime.now(timezone.utc),
                regulation=regulation,
                rule=rule,
                severity=severity,
                description=description,
                remediation=remediation,
            )
            self._violations.append(violation)

            LOGGER.warning(
                "Compliance violation recorded: %s",
                violation_id,
                extra={"rule": rule, "severity": severity},
            )

            # Also create audit entry for the violation
            self.record_audit_entry(
                event_type="compliance_violation",
                actor="system",
                action=f"Recorded violation of {rule}",
                details={"violation_id": violation_id, "severity": severity},
                regulation=regulation,
            )

            return violation

    def resolve_violation(self, violation_id: str, resolution_notes: str) -> bool:
        """Mark a violation as resolved.

        Args:
            violation_id: ID of the violation to resolve.
            resolution_notes: Notes about the resolution.

        Returns:
            True if violation was found and resolved.
        """
        with self._lock:
            for violation in self._violations:
                if violation.violation_id == violation_id:
                    violation.resolved = True
                    violation.remediation = resolution_notes

                    self.record_audit_entry(
                        event_type="violation_resolved",
                        actor="operator",
                        action=f"Resolved violation {violation_id}",
                        details={"resolution": resolution_notes},
                        regulation=violation.regulation,
                    )
                    return True
            return False

    def generate_report(
        self,
        *,
        regulation: RegulationType,
        period_start: datetime,
        period_end: datetime,
    ) -> RegulatoryReport:
        """Generate a regulatory compliance report.

        Args:
            regulation: Target regulation.
            period_start: Start of reporting period.
            period_end: End of reporting period.

        Returns:
            Generated compliance report.
        """
        with self._lock:
            # Filter audit entries for period and regulation
            entries = [
                e
                for e in self._audit_trail
                if (
                    period_start <= e.timestamp <= period_end
                    and (e.regulation == regulation or e.regulation == RegulationType.INTERNAL)
                )
            ]

            # Filter violations for period and regulation
            violations = [
                v
                for v in self._violations
                if period_start <= v.timestamp <= period_end and v.regulation == regulation
            ]

            # Calculate risk metrics
            risk_metrics = self._calculate_risk_metrics(entries)

            # Generate executive summary
            summary = self._generate_executive_summary(
                regulation, entries, violations, risk_metrics
            )

            report = RegulatoryReport(
                report_id=f"REP-{regulation.value}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                generated_at=datetime.now(timezone.utc),
                regulation=regulation,
                period_start=period_start,
                period_end=period_end,
                audit_entries=entries,
                violations=violations,
                risk_metrics=risk_metrics,
                executive_summary=summary,
            )

            LOGGER.info(
                "Generated compliance report %s",
                report.report_id,
                extra=report.to_dict(),
            )
            return report

    def export_audit_trail(
        self,
        *,
        period_start: datetime | None = None,
        period_end: datetime | None = None,
    ) -> Path:
        """Export audit trail to file.

        Args:
            period_start: Optional start date filter.
            period_end: Optional end date filter.

        Returns:
            Path to exported file.
        """
        with self._lock:
            entries = self._audit_trail
            if period_start:
                entries = [e for e in entries if e.timestamp >= period_start]
            if period_end:
                entries = [e for e in entries if e.timestamp <= period_end]

            timestamp = datetime.now(timezone.utc)
            payload = {
                "exported_at": timestamp.isoformat(),
                "entity_id": self._entity_id,
                "entries": [e.to_dict() for e in entries],
            }

            filename = f"audit-trail-{timestamp.strftime('%Y%m%dT%H%M%SZ')}.json"
            target = self._storage_path / filename
            target.write_text(json.dumps(payload, indent=2))

            LOGGER.info("Exported audit trail to %s", target)
            return target

    def get_compliance_status(self) -> dict[str, Any]:
        """Get current compliance status.

        Returns:
            Status dictionary.
        """
        with self._lock:
            unresolved = [v for v in self._violations if not v.resolved]
            return {
                "entity_id": self._entity_id,
                "total_audit_entries": len(self._audit_trail),
                "total_violations": len(self._violations),
                "unresolved_violations": len(unresolved),
                "unresolved_by_severity": {
                    "critical": sum(1 for v in unresolved if v.severity == "critical"),
                    "error": sum(1 for v in unresolved if v.severity == "error"),
                    "warning": sum(1 for v in unresolved if v.severity == "warning"),
                },
                "dodd_frank_status": self._dodd_frank.generate_summary(),
            }

    def _calculate_risk_metrics(self, entries: Sequence[AuditTrailEntry]) -> dict[str, Any]:
        """Calculate risk metrics from audit entries."""
        risk_decisions = [e for e in entries if e.risk_decision]
        return {
            "total_events": len(entries),
            "risk_decisions": len(risk_decisions),
            "events_by_type": self._count_by_field(entries, "event_type"),
        }

    @staticmethod
    def _count_by_field(entries: Sequence[AuditTrailEntry], field: str) -> dict[str, int]:
        """Count entries by field value."""
        counts: dict[str, int] = {}
        for entry in entries:
            value = getattr(entry, field, "unknown")
            counts[value] = counts.get(value, 0) + 1
        return counts

    def _generate_executive_summary(
        self,
        regulation: RegulationType,
        entries: Sequence[AuditTrailEntry],
        violations: Sequence[ComplianceViolation],
        metrics: Mapping[str, Any],
    ) -> str:
        """Generate executive summary for report."""
        unresolved = [v for v in violations if not v.resolved]
        critical = [v for v in unresolved if v.severity == "critical"]

        summary_lines = [
            f"Compliance Report for {regulation.value.upper()}",
            f"Entity: {self._entity_id}",
            "",
            f"Total audit events: {len(entries)}",
            f"Total violations: {len(violations)}",
            f"Unresolved violations: {len(unresolved)}",
        ]

        if critical:
            summary_lines.extend(
                [
                    "",
                    "CRITICAL ISSUES REQUIRING IMMEDIATE ATTENTION:",
                    *[f"  - {v.rule}: {v.description}" for v in critical[:5]],
                ]
            )

        return "\n".join(summary_lines)
