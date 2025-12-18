# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Comprehensive tests for Compliance Manager.

These tests cover:
- Dodd-Frank reporter functionality
- Audit trail management
- Regulatory report generation
- Violation tracking and resolution
- Export functionality
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.risk_monitoring.compliance import (
    AuditTrailEntry,
    ComplianceManager,
    ComplianceViolation,
    DoddFrankReporter,
    RegulationType,
    RegulatoryReport,
)


class TestDoddFrankReporter:
    """Tests for Dodd-Frank compliance reporter."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Test reporter initialization creates storage directory."""
        DoddFrankReporter(
            storage_path=tmp_path / "dodd-frank",
            entity_id="TEST_ENTITY",
        )

        assert (tmp_path / "dodd-frank").exists()

    def test_record_swap_transaction(self, tmp_path: Path) -> None:
        """Test swap transaction recording."""
        reporter = DoddFrankReporter(storage_path=tmp_path)

        exec_time = datetime.now(timezone.utc)
        record = reporter.record_swap_transaction(
            transaction_id="TXN-001",
            counterparty="BANK-ABC",
            asset_class="IR",
            notional=1_000_000.0,
            execution_time=exec_time,
            trade_type="new",
            price=1.5,
            maturity=exec_time + timedelta(days=365),
        )

        assert record["transaction_id"] == "TXN-001"
        assert record["counterparty"] == "BANK-ABC"
        assert record["asset_class"] == "IR"
        assert record["notional"] == 1_000_000.0
        assert record["regulation"] == "dodd_frank"

    def test_record_position(self, tmp_path: Path) -> None:
        """Test position recording."""
        reporter = DoddFrankReporter(storage_path=tmp_path)

        record = reporter.record_position(
            position_id="POS-001",
            asset="BTC/USD",
            position_size=10.0,
            notional_value=500_000.0,
            position_date=datetime.now(timezone.utc),
        )

        assert record["position_id"] == "POS-001"
        assert record["asset"] == "BTC/USD"
        assert record["position_size"] == 10.0

    def test_large_trader_threshold_not_exceeded(self, tmp_path: Path) -> None:
        """Test large trader check when threshold not exceeded."""
        reporter = DoddFrankReporter(storage_path=tmp_path)

        result = reporter.check_large_trader_threshold(
            trader_id="TRADER-001",
            aggregate_position=50_000.0,
            threshold=100_000.0,
            asset_class="Equity",
        )

        assert result is False

    def test_large_trader_threshold_exceeded(self, tmp_path: Path) -> None:
        """Test large trader check when threshold exceeded."""
        reporter = DoddFrankReporter(storage_path=tmp_path)

        result = reporter.check_large_trader_threshold(
            trader_id="TRADER-001",
            aggregate_position=150_000.0,
            threshold=100_000.0,
            asset_class="Equity",
        )

        assert result is True

    def test_flush_to_storage(self, tmp_path: Path) -> None:
        """Test flushing reports to storage."""
        reporter = DoddFrankReporter(storage_path=tmp_path)

        # Add some transactions
        reporter.record_swap_transaction(
            transaction_id="TXN-001",
            counterparty="BANK-ABC",
            asset_class="IR",
            notional=1_000_000.0,
            execution_time=datetime.now(timezone.utc),
            trade_type="new",
            price=1.5,
        )

        reporter.record_position(
            position_id="POS-001",
            asset="BTC/USD",
            position_size=10.0,
            notional_value=500_000.0,
            position_date=datetime.now(timezone.utc),
        )

        # Flush to storage
        output_path = reporter.flush_to_storage()

        assert output_path.exists()

        # Verify content
        content = json.loads(output_path.read_text())
        assert len(content["swap_transactions"]) == 1
        assert len(content["position_reports"]) == 1

        # Verify buffers are cleared
        summary = reporter.generate_summary()
        assert summary["pending_swap_reports"] == 0
        assert summary["pending_position_reports"] == 0

    def test_generate_summary(self, tmp_path: Path) -> None:
        """Test summary generation."""
        reporter = DoddFrankReporter(
            storage_path=tmp_path,
            entity_id="MY_ENTITY",
        )

        # Add transactions
        reporter.record_swap_transaction(
            transaction_id="TXN-001",
            counterparty="BANK-ABC",
            asset_class="IR",
            notional=1_000_000.0,
            execution_time=datetime.now(timezone.utc),
            trade_type="new",
            price=1.5,
        )

        reporter.check_large_trader_threshold(
            trader_id="TRADER-001",
            aggregate_position=150_000.0,
            threshold=100_000.0,
            asset_class="Equity",
        )

        summary = reporter.generate_summary()

        assert summary["entity_id"] == "MY_ENTITY"
        assert summary["pending_swap_reports"] == 1
        assert summary["large_trader_breaches"] == 1


class TestComplianceManager:
    """Tests for unified Compliance Manager."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Test manager initialization."""
        manager = ComplianceManager(
            storage_path=tmp_path,
            entity_id="TEST_ENTITY",
        )

        assert manager.dodd_frank is not None
        assert tmp_path.exists()

    def test_record_audit_entry(self, tmp_path: Path) -> None:
        """Test audit entry recording."""
        manager = ComplianceManager(storage_path=tmp_path)

        entry = manager.record_audit_entry(
            event_type="order",
            actor="trader1",
            action="placed buy order",
            details={"symbol": "BTC/USD", "quantity": 1.0},
            regulation=RegulationType.INTERNAL,
        )

        assert entry.entry_id.startswith("AUD-")
        assert entry.event_type == "order"
        assert entry.actor == "trader1"
        assert entry.timestamp is not None

    def test_audit_entry_with_risk_decision(self, tmp_path: Path) -> None:
        """Test audit entry with risk decision."""
        manager = ComplianceManager(storage_path=tmp_path)

        entry = manager.record_audit_entry(
            event_type="risk_check",
            actor="system",
            action="evaluated position size",
            risk_decision="approved",
            regulation=RegulationType.MIFID_II,
        )

        assert entry.risk_decision == "approved"
        assert entry.regulation == RegulationType.MIFID_II

    def test_record_violation(self, tmp_path: Path) -> None:
        """Test violation recording."""
        manager = ComplianceManager(storage_path=tmp_path)

        violation = manager.record_violation(
            regulation=RegulationType.DODD_FRANK,
            rule="Position limit",
            severity="warning",
            description="Position exceeded soft limit",
        )

        assert violation.violation_id.startswith("VIO-")
        assert violation.regulation == RegulationType.DODD_FRANK
        assert violation.resolved is False

    def test_resolve_violation(self, tmp_path: Path) -> None:
        """Test violation resolution."""
        manager = ComplianceManager(storage_path=tmp_path)

        violation = manager.record_violation(
            regulation=RegulationType.INTERNAL,
            rule="Max trades per day",
            severity="error",
            description="Exceeded daily trade limit",
        )

        success = manager.resolve_violation(
            violation.violation_id,
            "Trade limit increased after review"
        )

        assert success is True
        assert violation.resolved is True
        assert "Trade limit increased" in violation.remediation

    def test_resolve_nonexistent_violation(self, tmp_path: Path) -> None:
        """Test resolving non-existent violation returns False."""
        manager = ComplianceManager(storage_path=tmp_path)

        success = manager.resolve_violation(
            "VIO-999999",
            "This should not work"
        )

        assert success is False

    def test_generate_report(self, tmp_path: Path) -> None:
        """Test regulatory report generation."""
        manager = ComplianceManager(storage_path=tmp_path, entity_id="TEST")

        # Add some entries and violations
        start = datetime.now(timezone.utc) - timedelta(hours=1)
        end = datetime.now(timezone.utc) + timedelta(hours=1)

        manager.record_audit_entry(
            event_type="order",
            actor="trader1",
            action="placed order",
            regulation=RegulationType.MIFID_II,
        )

        manager.record_violation(
            regulation=RegulationType.MIFID_II,
            rule="Best execution",
            severity="warning",
            description="Execution quality below threshold",
        )

        report = manager.generate_report(
            regulation=RegulationType.MIFID_II,
            period_start=start,
            period_end=end,
        )

        assert report.report_id.startswith("REP-mifid_ii-")
        assert report.regulation == RegulationType.MIFID_II
        assert len(report.audit_entries) >= 1
        assert len(report.violations) >= 1
        assert "MIFID_II" in report.executive_summary

    def test_export_audit_trail(self, tmp_path: Path) -> None:
        """Test audit trail export."""
        manager = ComplianceManager(storage_path=tmp_path)

        # Add entries
        manager.record_audit_entry(
            event_type="order",
            actor="trader1",
            action="placed order",
        )
        manager.record_audit_entry(
            event_type="execution",
            actor="system",
            action="executed order",
        )

        export_path = manager.export_audit_trail()

        assert export_path.exists()

        content = json.loads(export_path.read_text())
        assert len(content["entries"]) == 2

    def test_export_audit_trail_with_date_filter(self, tmp_path: Path) -> None:
        """Test audit trail export with date filtering."""
        manager = ComplianceManager(storage_path=tmp_path)

        # Add entries
        manager.record_audit_entry(
            event_type="order",
            actor="trader1",
            action="placed order",
        )

        # Export with future date filter (should return no entries)
        future_start = datetime.now(timezone.utc) + timedelta(hours=1)
        export_path = manager.export_audit_trail(period_start=future_start)

        content = json.loads(export_path.read_text())
        assert len(content["entries"]) == 0

    def test_get_compliance_status(self, tmp_path: Path) -> None:
        """Test compliance status retrieval."""
        manager = ComplianceManager(storage_path=tmp_path, entity_id="TEST")

        # Add entries and violations
        manager.record_audit_entry(
            event_type="order",
            actor="trader1",
            action="placed order",
        )

        manager.record_violation(
            regulation=RegulationType.INTERNAL,
            rule="Risk limit",
            severity="critical",
            description="Critical risk limit exceeded",
        )

        manager.record_violation(
            regulation=RegulationType.INTERNAL,
            rule="Trade limit",
            severity="warning",
            description="Soft limit exceeded",
        )

        status = manager.get_compliance_status()

        assert status["entity_id"] == "TEST"
        assert status["total_audit_entries"] >= 1
        assert status["total_violations"] == 2
        assert status["unresolved_violations"] == 2
        assert status["unresolved_by_severity"]["critical"] == 1
        assert status["unresolved_by_severity"]["warning"] == 1


class TestAuditTrailEntry:
    """Tests for AuditTrailEntry dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        entry = AuditTrailEntry(
            entry_id="AUD-00000001",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            event_type="order",
            actor="trader1",
            action="placed order",
            details={"symbol": "BTC/USD"},
            risk_decision="approved",
            regulation=RegulationType.MIFID_II,
            hash_chain="prev:123",
        )

        d = entry.to_dict()

        assert d["entry_id"] == "AUD-00000001"
        assert d["event_type"] == "order"
        assert d["actor"] == "trader1"
        assert d["regulation"] == "mifid_ii"
        assert d["hash_chain"] == "prev:123"


class TestComplianceViolation:
    """Tests for ComplianceViolation dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        violation = ComplianceViolation(
            violation_id="VIO-000001",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            regulation=RegulationType.DODD_FRANK,
            rule="Position limit",
            severity="warning",
            description="Position exceeded limit",
            remediation="Reduced position",
            resolved=True,
        )

        d = violation.to_dict()

        assert d["violation_id"] == "VIO-000001"
        assert d["regulation"] == "dodd_frank"
        assert d["resolved"] is True


class TestRegulatoryReport:
    """Tests for RegulatoryReport dataclass."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        report = RegulatoryReport(
            report_id="REP-001",
            generated_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            regulation=RegulationType.MIFID_II,
            period_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            period_end=datetime(2024, 1, 31, tzinfo=timezone.utc),
            audit_entries=[],
            violations=[],
            risk_metrics={"total_events": 100},
            executive_summary="All clear",
        )

        d = report.to_dict()

        assert d["report_id"] == "REP-001"
        assert d["regulation"] == "mifid_ii"
        assert d["audit_entries_count"] == 0
        assert d["violations_count"] == 0
        assert d["risk_metrics"]["total_events"] == 100
