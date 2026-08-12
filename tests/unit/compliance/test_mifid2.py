# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for MiFID II compliance module."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from core.compat import UTC, utc_now
from core.compliance.mifid2 import (
    ComplianceSnapshot,
    ExecutionQuality,
    MarketAbuseSignal,
    MiFID2Reporter,
    MiFID2RetentionPolicy,
    OrderAuditTrail,
    TransactionReport,
)


class TestOrderAuditTrail:
    """Tests for OrderAuditTrail dataclass."""

    def test_order_audit_trail_creation(self) -> None:
        """Verify OrderAuditTrail can be created."""
        ts = utc_now()
        trail = OrderAuditTrail(
            order_id="order-123",
            timestamp=ts,
            payload={"action": "submit", "size": 100},
            venue="XNYS",
            actor="trader-1",
        )
        assert trail.order_id == "order-123"
        assert trail.timestamp == ts
        assert trail.payload["action"] == "submit"
        assert trail.venue == "XNYS"
        assert trail.actor == "trader-1"

    def test_order_audit_trail_to_dict(self) -> None:
        """Verify OrderAuditTrail to_dict method."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        trail = OrderAuditTrail(
            order_id="order-123",
            timestamp=ts,
            payload={"action": "submit", "size": 100},
            venue="XNYS",
            actor="trader-1",
        )
        result: dict[str, Any] = cast("dict[str, Any]", trail.to_dict())
        assert result["order_id"] == "order-123"
        assert result["timestamp"] == "2024-01-15T10:30:00+00:00"
        assert result["payload"]["action"] == "submit"
        assert result["venue"] == "XNYS"
        assert result["actor"] == "trader-1"


class TestExecutionQuality:
    """Tests for ExecutionQuality dataclass."""

    def test_execution_quality_creation(self) -> None:
        """Verify ExecutionQuality can be created."""
        quality = ExecutionQuality(
            order_id="order-123",
            venue="XNYS",
            price=100.50,
            benchmark_price=100.00,
            slippage=0.50,
            latency_ms=15.5,
        )
        assert quality.order_id == "order-123"
        assert quality.venue == "XNYS"
        assert quality.price == 100.50
        assert quality.benchmark_price == 100.00
        assert quality.slippage == 0.50
        assert quality.latency_ms == 15.5


class TestTransactionReport:
    """Tests for TransactionReport dataclass."""

    def test_transaction_report_creation(self) -> None:
        """Verify TransactionReport can be created."""
        ts = utc_now()
        report = TransactionReport(
            order_id="order-123",
            instrument="AAPL",
            quantity=100.0,
            price=150.25,
            side="BUY",
            execution_time=ts,
            buyer="buyer-id",
            seller="seller-id",
        )
        assert report.order_id == "order-123"
        assert report.instrument == "AAPL"
        assert report.quantity == 100.0
        assert report.price == 150.25
        assert report.side == "BUY"
        assert report.execution_time == ts
        assert report.buyer == "buyer-id"
        assert report.seller == "seller-id"

    def test_transaction_report_to_dict(self) -> None:
        """Verify TransactionReport to_dict method."""
        ts = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
        report = TransactionReport(
            order_id="order-123",
            instrument="AAPL",
            quantity=100.0,
            price=150.25,
            side="BUY",
            execution_time=ts,
            buyer="buyer-id",
            seller="seller-id",
        )
        result = report.to_dict()
        assert result["order_id"] == "order-123"
        assert result["instrument"] == "AAPL"
        assert result["quantity"] == 100.0
        assert result["price"] == 150.25
        assert result["side"] == "BUY"
        assert result["execution_time"] == "2024-01-15T10:30:00+00:00"
        assert result["buyer"] == "buyer-id"
        assert result["seller"] == "seller-id"


class TestMiFID2RetentionPolicy:
    """Tests for MiFID2RetentionPolicy dataclass."""

    def test_default_retention_policy(self) -> None:
        """Verify default retention is 7 years."""
        policy = MiFID2RetentionPolicy()
        assert policy.retention_years == 7

    def test_custom_retention_policy(self) -> None:
        """Verify custom retention can be set."""
        policy = MiFID2RetentionPolicy(retention_years=10)
        assert policy.retention_years == 10

    def test_retention_delta(self) -> None:
        """Verify retention_delta calculation."""
        policy = MiFID2RetentionPolicy(retention_years=7)
        delta = policy.retention_delta()
        assert delta == timedelta(days=365 * 7)


class TestComplianceSnapshot:
    """Tests for ComplianceSnapshot dataclass."""

    def test_compliance_snapshot_defaults(self) -> None:
        """Verify ComplianceSnapshot defaults."""
        snapshot = ComplianceSnapshot()
        assert snapshot.reports == []
        assert snapshot.audit_trail == []
        assert snapshot.execution_quality == []
        assert snapshot.generated_at is not None

    def test_compliance_snapshot_with_data(self) -> None:
        """Verify ComplianceSnapshot with data."""
        ts = utc_now()
        report = TransactionReport(
            order_id="order-1",
            instrument="AAPL",
            quantity=100.0,
            price=150.0,
            side="BUY",
            execution_time=ts,
            buyer="buyer",
            seller="seller",
        )
        snapshot = ComplianceSnapshot(
            reports=[report],
            audit_trail=[],
            execution_quality=[],
            generated_at=ts,
        )
        assert len(snapshot.reports) == 1
        assert snapshot.generated_at == ts


class TestMarketAbuseSignal:
    """Tests for MarketAbuseSignal dataclass."""

    def test_market_abuse_signal_creation(self) -> None:
        """Verify MarketAbuseSignal can be created."""
        signal = MarketAbuseSignal(
            order_id="order-123",
            actor="trader-1",
            reason="suspicious activity",
        )
        assert signal.order_id == "order-123"
        assert signal.actor == "trader-1"
        assert signal.reason == "suspicious activity"


class TestMiFID2Reporter:
    """Tests for MiFID2Reporter class."""

    @pytest.fixture
    def storage_path(self, tmp_path: Path) -> Path:
        """Create temporary storage path."""
        return tmp_path / "mifid2_storage"

    @pytest.fixture
    def reporter(self, storage_path: Path) -> MiFID2Reporter:
        """Create a test reporter."""
        return MiFID2Reporter(storage_path=storage_path)

    def test_reporter_creation_creates_directory(self, storage_path: Path) -> None:
        """Verify reporter creates storage directory."""
        MiFID2Reporter(storage_path=storage_path)
        assert storage_path.exists()

    def test_reporter_with_custom_retention(self, storage_path: Path) -> None:
        """Verify reporter with custom retention policy."""
        policy = MiFID2RetentionPolicy(retention_years=10)
        reporter = MiFID2Reporter(storage_path=storage_path, retention=policy)
        assert reporter._retention.retention_years == 10

    def test_record_order_adds_to_audit_trail(self, reporter: MiFID2Reporter) -> None:
        """Verify record_order adds entry to audit trail."""
        reporter.record_order(
            order_id="order-1",
            payload={"action": "submit", "size": 100},
            venue="XNYS",
            actor="trader-1",
        )
        assert len(reporter._audit_trail) == 1
        assert reporter._audit_trail[0].order_id == "order-1"

    def test_record_order_detects_market_abuse(self, reporter: MiFID2Reporter) -> None:
        """Verify record_order detects suspicious cancellations."""
        reporter.record_order(
            order_id="order-abuse",
            payload={"action": "cancel", "size": 2_000_000},
            venue="XNYS",
            actor="trader-suspicious",
        )
        signals = reporter.market_abuse_signals()
        assert len(signals) == 1
        assert signals[0].order_id == "order-abuse"
        assert "suspicious" in signals[0].reason.lower()

    def test_record_order_no_abuse_for_small_cancel(self, reporter: MiFID2Reporter) -> None:
        """Verify small cancellations don't trigger abuse signals."""
        reporter.record_order(
            order_id="order-small",
            payload={"action": "cancel", "size": 1000},
            venue="XNYS",
            actor="trader-1",
        )
        signals = reporter.market_abuse_signals()
        assert len(signals) == 0

    def test_record_order_no_abuse_for_non_cancel(self, reporter: MiFID2Reporter) -> None:
        """Verify non-cancel orders don't trigger abuse signals."""
        reporter.record_order(
            order_id="order-submit",
            payload={"action": "submit", "size": 2_000_000},
            venue="XNYS",
            actor="trader-1",
        )
        signals = reporter.market_abuse_signals()
        assert len(signals) == 0

    def test_record_execution_adds_report_and_quality(self, reporter: MiFID2Reporter) -> None:
        """Verify record_execution adds report and quality entries."""
        reporter.record_execution(
            order_id="order-1",
            instrument="AAPL",
            quantity=100.0,
            price=150.50,
            side="BUY",
            buyer="buyer-1",
            seller="seller-1",
            venue="XNYS",
            benchmark_price=150.00,
            latency_ms=10.5,
        )
        assert len(reporter._reports) == 1
        assert len(reporter._execution_quality) == 1
        assert reporter._reports[0].order_id == "order-1"
        assert reporter._execution_quality[0].slippage == 0.50

    def test_synchronise_clock(self, reporter: MiFID2Reporter) -> None:
        """Verify synchronise_clock records timestamp."""
        reporter.synchronise_clock(ntp_offset_ms=15.5)
        assert reporter._synchronised_at is not None

    def test_best_execution_breaches_empty(self, reporter: MiFID2Reporter) -> None:
        """Verify no breaches with no executions."""
        breaches = reporter.best_execution_breaches()
        assert len(breaches) == 0

    def test_best_execution_breaches_detected(self, reporter: MiFID2Reporter) -> None:
        """Verify breaches are detected for high slippage."""
        # Add execution with high slippage
        reporter.record_execution(
            order_id="order-breach",
            instrument="AAPL",
            quantity=100.0,
            price=155.00,  # 5 dollar slippage on $100 benchmark = 50 bps
            side="BUY",
            buyer="buyer-1",
            seller="seller-1",
            venue="XNYS",
            benchmark_price=100.00,
            latency_ms=10.0,
        )
        breaches = reporter.best_execution_breaches(threshold_bps=5.0)
        assert len(breaches) == 1
        assert breaches[0].order_id == "order-breach"

    def test_best_execution_no_breach_within_threshold(self, reporter: MiFID2Reporter) -> None:
        """Verify no breaches when within threshold."""
        reporter.record_execution(
            order_id="order-good",
            instrument="AAPL",
            quantity=100.0,
            price=100.01,  # 1 cent slippage
            side="BUY",
            buyer="buyer-1",
            seller="seller-1",
            venue="XNYS",
            benchmark_price=100.00,
            latency_ms=10.0,
        )
        breaches = reporter.best_execution_breaches(threshold_bps=50.0)
        assert len(breaches) == 0

    def test_position_limit_breaches_detected(self, reporter: MiFID2Reporter) -> None:
        """Verify position limit breaches are detected."""
        positions = {"AAPL": 150.0, "GOOGL": 50.0}
        limits = {"AAPL": 100.0, "GOOGL": 100.0}
        breaches = reporter.position_limit_breaches(positions=positions, limits=limits)
        assert "AAPL" in breaches
        assert "GOOGL" not in breaches
        assert breaches["AAPL"] == 150.0

    def test_position_limit_no_breaches(self, reporter: MiFID2Reporter) -> None:
        """Verify no breaches when within limits."""
        positions = {"AAPL": 50.0}
        limits = {"AAPL": 100.0}
        breaches = reporter.position_limit_breaches(positions=positions, limits=limits)
        assert len(breaches) == 0

    def test_position_limit_ignores_missing_limits(self, reporter: MiFID2Reporter) -> None:
        """Verify positions without limits are ignored."""
        positions = {"AAPL": 150.0}
        limits = {"GOOGL": 100.0}  # No limit for AAPL
        breaches = reporter.position_limit_breaches(positions=positions, limits=limits)
        assert len(breaches) == 0

    def test_health_summary(self, reporter: MiFID2Reporter) -> None:
        """Verify health_summary returns correct counts."""
        reporter.record_order(
            order_id="order-1",
            payload={"action": "submit", "size": 100},
            venue="XNYS",
            actor="trader-1",
        )
        reporter.record_execution(
            order_id="order-1",
            instrument="AAPL",
            quantity=100.0,
            price=150.00,
            side="BUY",
            buyer="buyer-1",
            seller="seller-1",
            venue="XNYS",
            benchmark_price=150.00,
            latency_ms=10.0,
        )
        summary = reporter.health_summary()
        assert summary["reports"] == 1
        assert summary["audit_trail"] == 1
        assert summary["execution_quality"] == 1
        assert summary["synchronised_at"] is None
        assert summary["market_abuse_signals"] == 0

    def test_snapshot(self, reporter: MiFID2Reporter) -> None:
        """Verify snapshot returns ComplianceSnapshot."""
        reporter.record_order(
            order_id="order-1",
            payload={"action": "submit", "size": 100},
            venue="XNYS",
            actor="trader-1",
        )
        snapshot = reporter.snapshot()
        assert isinstance(snapshot, ComplianceSnapshot)
        assert len(snapshot.audit_trail) == 1

    def test_export_creates_file(self, reporter: MiFID2Reporter, storage_path: Path) -> None:
        """Verify export creates JSON file."""
        reporter.record_order(
            order_id="order-1",
            payload={"action": "submit", "size": 100},
            venue="XNYS",
            actor="trader-1",
        )
        reporter.record_execution(
            order_id="order-1",
            instrument="AAPL",
            quantity=100.0,
            price=150.00,
            side="BUY",
            buyer="buyer-1",
            seller="seller-1",
            venue="XNYS",
            benchmark_price=150.00,
            latency_ms=10.0,
        )
        export_path = reporter.export()
        assert export_path.exists()
        assert export_path.suffix == ".json"

        # Verify content
        content = json.loads(export_path.read_text())
        assert "generated_at" in content
        assert "reports" in content
        assert "audit_trail" in content
        assert "execution_quality" in content
        assert len(content["reports"]) == 1
        assert len(content["audit_trail"]) == 1

    def test_export_with_custom_prefix(self, reporter: MiFID2Reporter, storage_path: Path) -> None:
        """Verify export uses custom prefix."""
        export_path = reporter.export(prefix="custom")
        assert export_path.name.startswith("custom-")

    def test_generate_regulatory_report(self, reporter: MiFID2Reporter) -> None:
        """Verify generate_regulatory_report returns complete report."""
        reporter.record_order(
            order_id="order-1",
            payload={"action": "cancel", "size": 2_000_000},
            venue="XNYS",
            actor="suspicious-trader",
        )
        reporter.record_execution(
            order_id="order-breach",
            instrument="AAPL",
            quantity=100.0,
            price=155.00,
            side="BUY",
            buyer="buyer-1",
            seller="seller-1",
            venue="XNYS",
            benchmark_price=100.00,
            latency_ms=10.0,
        )
        report = reporter.generate_regulatory_report()
        assert "health" in report
        assert "best_execution_breaches" in report
        assert "market_abuse_signals" in report
        assert len(cast("list[Any]", report["market_abuse_signals"])) == 1
