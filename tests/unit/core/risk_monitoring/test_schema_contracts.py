# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Contract tests for schema stability.

These tests verify that serialization formats (to_dict, JSON, etc.)
maintain backward compatibility and schema stability.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from core.risk_monitoring.advanced_risk_manager import (
    LiquidityMetrics,
)
from core.risk_monitoring.compliance import (
    AuditTrailEntry,
    ComplianceViolation,
    RegulationType,
    RegulatoryReport,
)
from core.risk_monitoring.fail_safe import (
    FailSafeAction,
    FailSafeConfig,
    FailSafeLevel,
    FailSafeState,
)


class TestFailSafeStateSchema:
    """Contract tests for FailSafeState serialization."""

    # Schema version: 1.0
    REQUIRED_FIELDS = frozenset({
        "level",
        "active",
        "reason",
        "activated_at",
        "source",
        "position_multiplier",
        "allow_new_orders",
        "force_paper_trading",
        "pending_actions",
        "auto_recover_at",
    })

    def test_schema_has_all_required_fields(self) -> None:
        """Contract: FailSafeState.to_dict includes all required fields."""
        state = FailSafeState(
            level=FailSafeLevel.CAUTION,
            active=True,
            reason="Test",
            activated_at=datetime.now(timezone.utc),
            source="test",
            position_multiplier=0.7,
            allow_new_orders=True,
            force_paper_trading=True,
            pending_actions=(FailSafeAction.REDUCE_POSITIONS,),
            auto_recover_at=datetime.now(timezone.utc),
        )

        d = state.to_dict()

        assert set(d.keys()) == self.REQUIRED_FIELDS

    def test_schema_level_is_string(self) -> None:
        """Contract: level field is serialized as string value."""
        state = FailSafeState(level=FailSafeLevel.HALT)
        d = state.to_dict()

        assert isinstance(d["level"], str)
        assert d["level"] == "halt"

    def test_schema_timestamps_are_iso_format(self) -> None:
        """Contract: Timestamps are ISO 8601 format."""
        now = datetime(2024, 1, 15, 12, 30, 45, tzinfo=timezone.utc)
        state = FailSafeState(
            activated_at=now,
            auto_recover_at=now,
        )
        d = state.to_dict()

        assert d["activated_at"] == "2024-01-15T12:30:45+00:00"
        assert d["auto_recover_at"] == "2024-01-15T12:30:45+00:00"

    def test_schema_pending_actions_are_string_list(self) -> None:
        """Contract: pending_actions is a list of string values."""
        state = FailSafeState(
            pending_actions=(
                FailSafeAction.REDUCE_POSITIONS,
                FailSafeAction.CANCEL_PENDING,
            ),
        )
        d = state.to_dict()

        assert isinstance(d["pending_actions"], list)
        assert all(isinstance(a, str) for a in d["pending_actions"])
        assert "reduce_positions" in d["pending_actions"]
        assert "cancel_pending" in d["pending_actions"]

    def test_schema_is_json_serializable(self) -> None:
        """Contract: to_dict output is JSON serializable."""
        state = FailSafeState(
            level=FailSafeLevel.CAUTION,
            active=True,
            activated_at=datetime.now(timezone.utc),
        )
        d = state.to_dict()

        # Should not raise
        json_str = json.dumps(d)
        assert isinstance(json_str, str)

        # Should be deserializable
        parsed = json.loads(json_str)
        assert parsed == d


class TestFailSafeConfigSchema:
    """Contract tests for FailSafeConfig serialization."""

    REQUIRED_FIELDS = frozenset({
        "caution_position_multiplier",
        "restricted_position_multiplier",
        "auto_recover_delay_minutes",
        "escalation_threshold_seconds",
        "require_manual_recovery_levels",
        "enable_emergency_liquidation",
    })

    def test_schema_has_all_required_fields(self) -> None:
        """Contract: FailSafeConfig.to_dict includes all required fields."""
        config = FailSafeConfig()
        d = config.to_dict()

        assert set(d.keys()) == self.REQUIRED_FIELDS

    def test_schema_require_manual_recovery_levels_is_string_list(self) -> None:
        """Contract: require_manual_recovery_levels is a list of strings."""
        config = FailSafeConfig()
        d = config.to_dict()

        assert isinstance(d["require_manual_recovery_levels"], list)
        assert all(isinstance(level, str) for level in d["require_manual_recovery_levels"])


class TestAuditTrailEntrySchema:
    """Contract tests for AuditTrailEntry serialization."""

    REQUIRED_FIELDS = frozenset({
        "entry_id",
        "timestamp",
        "event_type",
        "actor",
        "action",
        "details",
        "risk_decision",
        "regulation",
        "hash_chain",
    })

    def test_schema_has_all_required_fields(self) -> None:
        """Contract: AuditTrailEntry.to_dict includes all required fields."""
        entry = AuditTrailEntry(
            entry_id="AUD-00000001",
            timestamp=datetime.now(timezone.utc),
            event_type="order",
            actor="trader1",
            action="placed order",
            details={"symbol": "BTC/USD"},
            risk_decision="approved",
            regulation=RegulationType.MIFID_II,
            hash_chain="prev:123",
        )

        d = entry.to_dict()

        assert set(d.keys()) == self.REQUIRED_FIELDS

    def test_schema_regulation_is_string(self) -> None:
        """Contract: regulation field is serialized as string value."""
        entry = AuditTrailEntry(
            entry_id="AUD-00000001",
            timestamp=datetime.now(timezone.utc),
            event_type="test",
            actor="test",
            action="test",
            regulation=RegulationType.DODD_FRANK,
        )
        d = entry.to_dict()

        assert isinstance(d["regulation"], str)
        assert d["regulation"] == "dodd_frank"


class TestComplianceViolationSchema:
    """Contract tests for ComplianceViolation serialization."""

    REQUIRED_FIELDS = frozenset({
        "violation_id",
        "timestamp",
        "regulation",
        "rule",
        "severity",
        "description",
        "remediation",
        "resolved",
    })

    def test_schema_has_all_required_fields(self) -> None:
        """Contract: ComplianceViolation.to_dict includes all required fields."""
        violation = ComplianceViolation(
            violation_id="VIO-000001",
            timestamp=datetime.now(timezone.utc),
            regulation=RegulationType.INTERNAL,
            rule="position_limit",
            severity="warning",
            description="Exceeded limit",
            remediation="Reduced position",
            resolved=True,
        )

        d = violation.to_dict()

        assert set(d.keys()) == self.REQUIRED_FIELDS

    def test_schema_resolved_is_boolean(self) -> None:
        """Contract: resolved field is boolean."""
        violation = ComplianceViolation(
            violation_id="VIO-000001",
            timestamp=datetime.now(timezone.utc),
            regulation=RegulationType.INTERNAL,
            rule="test",
            severity="warning",
            description="test",
            resolved=True,
        )
        d = violation.to_dict()

        assert isinstance(d["resolved"], bool)


class TestRegulatoryReportSchema:
    """Contract tests for RegulatoryReport serialization."""

    REQUIRED_FIELDS = frozenset({
        "report_id",
        "generated_at",
        "regulation",
        "period_start",
        "period_end",
        "audit_entries_count",
        "violations_count",
        "unresolved_violations",
        "risk_metrics",
        "executive_summary",
    })

    def test_schema_has_all_required_fields(self) -> None:
        """Contract: RegulatoryReport.to_dict includes all required fields."""
        report = RegulatoryReport(
            report_id="REP-001",
            generated_at=datetime.now(timezone.utc),
            regulation=RegulationType.MIFID_II,
            period_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            period_end=datetime(2024, 1, 31, tzinfo=timezone.utc),
            audit_entries=[],
            violations=[],
            risk_metrics={"total": 100},
            executive_summary="All clear",
        )

        d = report.to_dict()

        assert set(d.keys()) == self.REQUIRED_FIELDS

    def test_schema_counts_are_integers(self) -> None:
        """Contract: Count fields are integers."""
        report = RegulatoryReport(
            report_id="REP-001",
            generated_at=datetime.now(timezone.utc),
            regulation=RegulationType.INTERNAL,
            period_start=datetime(2024, 1, 1, tzinfo=timezone.utc),
            period_end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        )
        d = report.to_dict()

        assert isinstance(d["audit_entries_count"], int)
        assert isinstance(d["violations_count"], int)
        assert isinstance(d["unresolved_violations"], int)


class TestLiquidityMetricsSchema:
    """Contract tests for LiquidityMetrics serialization."""

    REQUIRED_FIELDS = frozenset({
        "bid_depth_value",
        "ask_depth_value",
        "imbalance_ratio",
        "spread_bps",
        "market_impact_estimate",
        "liquidity_score",
        "depth_levels_analyzed",
        "timestamp",
    })

    def test_schema_has_all_required_fields(self) -> None:
        """Contract: LiquidityMetrics.to_dict includes all required fields."""
        metrics = LiquidityMetrics(
            bid_depth_value=100000.0,
            ask_depth_value=120000.0,
            imbalance_ratio=-0.1,
            spread_bps=5.0,
            market_impact_estimate=0.01,
            liquidity_score=0.8,
            depth_levels_analyzed=5,
            timestamp=datetime.now(timezone.utc),
        )

        d = metrics.to_dict()

        assert set(d.keys()) == self.REQUIRED_FIELDS

    def test_schema_numeric_fields_are_numbers(self) -> None:
        """Contract: Numeric fields are floats or ints."""
        metrics = LiquidityMetrics()
        d = metrics.to_dict()

        assert isinstance(d["bid_depth_value"], (int, float))
        assert isinstance(d["ask_depth_value"], (int, float))
        assert isinstance(d["imbalance_ratio"], (int, float))
        assert isinstance(d["spread_bps"], (int, float))
        assert isinstance(d["depth_levels_analyzed"], int)


class TestSchemaJSONRoundtrip:
    """Tests for JSON roundtrip compatibility."""

    def test_fail_safe_state_json_roundtrip(self) -> None:
        """Test FailSafeState survives JSON roundtrip."""
        state = FailSafeState(
            level=FailSafeLevel.RESTRICTED,
            active=True,
            reason="Market stress",
            activated_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            source="stress_detector",
            position_multiplier=0.3,
            allow_new_orders=False,
            force_paper_trading=True,
            pending_actions=(FailSafeAction.REDUCE_POSITIONS, FailSafeAction.CANCEL_PENDING),
            auto_recover_at=datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc),
        )

        original = state.to_dict()
        json_str = json.dumps(original)
        parsed = json.loads(json_str)

        assert parsed == original

    def test_compliance_violation_json_roundtrip(self) -> None:
        """Test ComplianceViolation survives JSON roundtrip."""
        violation = ComplianceViolation(
            violation_id="VIO-000001",
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
            regulation=RegulationType.MIFID_II,
            rule="Best execution",
            severity="warning",
            description="Execution quality below threshold",
            remediation="Improved routing logic",
            resolved=True,
        )

        original = violation.to_dict()
        json_str = json.dumps(original)
        parsed = json.loads(json_str)

        assert parsed == original

    def test_liquidity_metrics_json_roundtrip(self) -> None:
        """Test LiquidityMetrics survives JSON roundtrip."""
        metrics = LiquidityMetrics(
            bid_depth_value=500000.0,
            ask_depth_value=600000.0,
            imbalance_ratio=-0.09,
            spread_bps=3.5,
            market_impact_estimate=0.005,
            liquidity_score=0.92,
            depth_levels_analyzed=10,
            timestamp=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

        original = metrics.to_dict()
        json_str = json.dumps(original)
        parsed = json.loads(json_str)

        assert parsed == original
