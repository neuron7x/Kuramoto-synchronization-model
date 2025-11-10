# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for MiFID II compliance reporting functionality."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.compliance.mifid2 import (
    ComplianceSnapshot,
    ExecutionQuality,
    MarketAbuseSignal,
    MiFID2Reporter,
    MiFID2RetentionPolicy,
    OrderAuditTrail,
    TransactionReport,
)


def test_order_audit_trail_to_dict() -> None:
    """OrderAuditTrail should serialize to dictionary."""
    timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
    trail = OrderAuditTrail(
        order_id="ORD-123",
        timestamp=timestamp,
        payload={"quantity": 100, "price": 50.25},
        venue="NYSE",
        actor="trader@example.com",
    )
    
    result = trail.to_dict()
    
    assert result["order_id"] == "ORD-123"
    assert result["timestamp"] == timestamp.isoformat()
    assert result["payload"] == {"quantity": 100, "price": 50.25}
    assert result["venue"] == "NYSE"
    assert result["actor"] == "trader@example.com"


def test_transaction_report_to_dict() -> None:
    """TransactionReport should serialize to dictionary."""
    exec_time = datetime(2024, 1, 15, 10, 30, 0, tzinfo=UTC)
    report = TransactionReport(
        order_id="ORD-456",
        instrument="AAPL",
        quantity=50.0,
        price=175.50,
        side="BUY",
        execution_time=exec_time,
        buyer="client-a",
        seller="client-b",
    )
    
    result = report.to_dict()
    
    assert result["order_id"] == "ORD-456"
    assert result["instrument"] == "AAPL"
    assert result["quantity"] == 50.0
    assert result["price"] == 175.50
    assert result["side"] == "BUY"
    assert result["execution_time"] == exec_time.isoformat()
    assert result["buyer"] == "client-a"
    assert result["seller"] == "client-b"


def test_retention_policy_default_seven_years() -> None:
    """Default retention policy should be 7 years."""
    policy = MiFID2RetentionPolicy()
    
    assert policy.retention_years == 7
    delta = policy.retention_delta()
    
    # Should be approximately 7 years in days
    assert delta == timedelta(days=365 * 7)


def test_retention_policy_custom_duration() -> None:
    """Retention policy should support custom durations."""
    policy = MiFID2RetentionPolicy(retention_years=10)
    
    assert policy.retention_years == 10
    delta = policy.retention_delta()
    
    assert delta == timedelta(days=3650)


def test_compliance_snapshot_initialization() -> None:
    """ComplianceSnapshot should initialize with empty lists."""
    snapshot = ComplianceSnapshot()
    
    assert snapshot.reports == []
    assert snapshot.audit_trail == []
    assert snapshot.execution_quality == []
    assert isinstance(snapshot.generated_at, datetime)


def test_mifid2_reporter_initialization(tmp_path: Path) -> None:
    """MiFID2Reporter should initialize with storage path."""
    storage_path = tmp_path / "compliance"
    reporter = MiFID2Reporter(storage_path=storage_path)
    
    # Storage path should be created
    assert storage_path.exists()
    assert storage_path.is_dir()


def test_record_order_creates_audit_trail(tmp_path: Path) -> None:
    """Recording an order should create an audit trail entry."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    reporter.record_order(
        order_id="ORD-001",
        payload={"quantity": 100, "symbol": "MSFT"},
        venue="NASDAQ",
        actor="trader1",
    )
    
    snapshot = reporter.snapshot()
    assert len(snapshot.audit_trail) == 1
    
    entry = snapshot.audit_trail[0]
    assert entry.order_id == "ORD-001"
    assert entry.venue == "NASDAQ"
    assert entry.actor == "trader1"
    assert entry.payload == {"quantity": 100, "symbol": "MSFT"}


def test_record_execution_creates_reports(tmp_path: Path) -> None:
    """Recording an execution should create transaction report and quality metrics."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    reporter.record_execution(
        order_id="ORD-002",
        instrument="TSLA",
        quantity=25.0,
        price=250.75,
        side="SELL",
        buyer="buyer-1",
        seller="seller-1",
        venue="NASDAQ",
        benchmark_price=250.50,
        latency_ms=15.5,
    )
    
    snapshot = reporter.snapshot()
    assert len(snapshot.reports) == 1
    assert len(snapshot.execution_quality) == 1
    
    report = snapshot.reports[0]
    assert report.order_id == "ORD-002"
    assert report.instrument == "TSLA"
    assert report.quantity == 25.0
    assert report.price == 250.75
    assert report.side == "SELL"
    
    quality = snapshot.execution_quality[0]
    assert quality.order_id == "ORD-002"
    assert quality.venue == "NASDAQ"
    assert quality.price == 250.75
    assert quality.benchmark_price == 250.50
    assert quality.slippage == 0.25
    assert quality.latency_ms == 15.5


def test_synchronise_clock(tmp_path: Path) -> None:
    """Clock synchronization should record timestamp and offset."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    reporter.synchronise_clock(ntp_offset_ms=1.234)
    
    health = reporter.health_summary()
    assert health["synchronised_at"] is not None


def test_best_execution_breaches_detection(tmp_path: Path) -> None:
    """Best execution breaches should be detected based on slippage threshold."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    # Record execution with acceptable slippage (< 5 bps)
    reporter.record_execution(
        order_id="ORD-GOOD",
        instrument="AAPL",
        quantity=100.0,
        price=150.00,
        side="BUY",
        buyer="client-a",
        seller="market",
        venue="NYSE",
        benchmark_price=150.00,  # No slippage
        latency_ms=10.0,
    )
    
    # Record execution with unacceptable slippage (> 5 bps)
    reporter.record_execution(
        order_id="ORD-BAD",
        instrument="GOOGL",
        quantity=50.0,
        price=2800.00,
        side="BUY",
        buyer="client-b",
        seller="market",
        venue="NASDAQ",
        benchmark_price=2798.00,  # 2.00 slippage on 2798 base ~= 7.15 bps
        latency_ms=25.0,
    )
    
    breaches = reporter.best_execution_breaches(threshold_bps=5.0)
    
    # Should detect one breach
    assert len(breaches) == 1
    assert breaches[0].order_id == "ORD-BAD"


def test_position_limit_breaches(tmp_path: Path) -> None:
    """Position limit breaches should be detected and reported."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    positions = {
        "AAPL": 1000.0,
        "TSLA": 500.0,
        "MSFT": -800.0,
    }
    
    limits = {
        "AAPL": 1500.0,  # Within limit
        "TSLA": 400.0,   # Breach (500 > 400)
        "MSFT": 750.0,   # Breach (|-800| > 750)
    }
    
    breaches = reporter.position_limit_breaches(positions=positions, limits=limits)
    
    assert len(breaches) == 2
    assert "TSLA" in breaches
    assert "MSFT" in breaches
    assert breaches["TSLA"] == 500.0
    assert breaches["MSFT"] == -800.0


def test_position_limit_no_breaches(tmp_path: Path) -> None:
    """When positions are within limits, no breaches should be detected."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    positions = {
        "AAPL": 100.0,
        "TSLA": 50.0,
    }
    
    limits = {
        "AAPL": 1000.0,
        "TSLA": 500.0,
    }
    
    breaches = reporter.position_limit_breaches(positions=positions, limits=limits)
    
    assert breaches == {}


def test_position_limit_missing_instrument_limits(tmp_path: Path) -> None:
    """Instruments without defined limits should be ignored."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    positions = {
        "AAPL": 100.0,
        "UNKNOWN": 999.0,  # No limit defined
    }
    
    limits = {
        "AAPL": 1000.0,
    }
    
    breaches = reporter.position_limit_breaches(positions=positions, limits=limits)
    
    # UNKNOWN should not be flagged as a breach since no limit is set
    assert breaches == {}


def test_health_summary(tmp_path: Path) -> None:
    """Health summary should report correct counts."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    reporter.record_order(
        order_id="ORD-001",
        payload={},
        venue="NYSE",
        actor="trader1",
    )
    
    reporter.record_execution(
        order_id="ORD-002",
        instrument="AAPL",
        quantity=100.0,
        price=150.0,
        side="BUY",
        buyer="client",
        seller="market",
        venue="NYSE",
        benchmark_price=150.0,
        latency_ms=10.0,
    )
    
    reporter.synchronise_clock(0.5)
    
    health = reporter.health_summary()
    
    assert health["reports"] == 1
    assert health["audit_trail"] == 1
    assert health["execution_quality"] == 1
    assert health["synchronised_at"] is not None
    assert "market_abuse_signals" in health


def test_snapshot_returns_current_state(tmp_path: Path) -> None:
    """Snapshot should return current state of all recorded data."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    # Record some data
    reporter.record_order(order_id="O1", payload={}, venue="V1", actor="A1")
    reporter.record_order(order_id="O2", payload={}, venue="V2", actor="A2")
    
    snapshot = reporter.snapshot()
    
    assert len(snapshot.audit_trail) == 2
    assert isinstance(snapshot.generated_at, datetime)
    assert snapshot.reports == []  # No executions recorded
    assert snapshot.execution_quality == []


def test_market_abuse_signals(tmp_path: Path) -> None:
    """Market abuse signals should be retrievable."""
    reporter = MiFID2Reporter(storage_path=tmp_path)
    
    # Initially empty
    signals = reporter.market_abuse_signals()
    assert signals == []


def test_execution_quality_dataclass() -> None:
    """ExecutionQuality should store all required fields."""
    quality = ExecutionQuality(
        order_id="ORD-X",
        venue="NASDAQ",
        price=100.50,
        benchmark_price=100.25,
        slippage=0.25,
        latency_ms=12.5,
    )
    
    assert quality.order_id == "ORD-X"
    assert quality.venue == "NASDAQ"
    assert quality.price == 100.50
    assert quality.benchmark_price == 100.25
    assert quality.slippage == 0.25
    assert quality.latency_ms == 12.5


def test_market_abuse_signal_dataclass() -> None:
    """MarketAbuseSignal should store required fields."""
    signal = MarketAbuseSignal(
        order_id="ORD-Y",
        actor="trader@example.com",
        reason="Suspected wash trading",
    )
    
    assert signal.order_id == "ORD-Y"
    assert signal.actor == "trader@example.com"
    assert signal.reason == "Suspected wash trading"


def test_custom_retention_policy(tmp_path: Path) -> None:
    """Reporter should accept custom retention policy."""
    policy = MiFID2RetentionPolicy(retention_years=10)
    reporter = MiFID2Reporter(storage_path=tmp_path, retention=policy)
    
    # Policy should be used internally
    assert reporter._retention.retention_years == 10
