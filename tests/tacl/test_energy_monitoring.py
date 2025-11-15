"""Tests for energy monitoring module."""

from __future__ import annotations

import json
import pytest

from tacl.energy_model import EnergyMetrics, EnergyValidationResult
from tacl.energy_monitoring import (
    AlertSeverity,
    EnergyAlert,
    EnergyMonitor,
    EnergyReporter,
    PrometheusMetrics,
)


@pytest.fixture
def sample_result():
    """Create a sample validation result."""
    return EnergyValidationResult(
        passed=True,
        free_energy=1.15,
        internal_energy=1.35,
        entropy=0.33,
        penalties={
            "latency_p95": 0.05,
            "latency_p99": 0.08,
            "coherency_drift": 0.0,
            "cpu_burn": 0.02,
            "mem_cost": 0.0,
            "queue_depth": 0.0,
            "packet_loss": 0.0,
        },
    )


@pytest.fixture
def sample_metrics():
    """Create sample metrics."""
    return EnergyMetrics(
        latency_p95=70.0,
        latency_p99=100.0,
        coherency_drift=0.05,
        cpu_burn=0.6,
        mem_cost=5.0,
        queue_depth=25.0,
        packet_loss=0.003,
    )


def test_energy_alert_creation():
    """Test creation and serialization of energy alerts."""
    alert = EnergyAlert(
        severity=AlertSeverity.WARNING,
        message="Test alert",
        timestamp=1234567890.0,
        free_energy=1.25,
        threshold=1.2,
        metrics_snapshot={"metric1": 100.0, "metric2": 0.5},
    )
    
    assert alert.severity == AlertSeverity.WARNING
    assert alert.message == "Test alert"
    assert alert.free_energy == 1.25
    
    # Test dict conversion
    alert_dict = alert.to_dict()
    assert alert_dict["severity"] == "warning"
    assert alert_dict["free_energy"] == 1.25
    assert "metrics" in alert_dict
    
    # Test JSON conversion
    alert_json = alert.to_json()
    parsed = json.loads(alert_json)
    assert parsed["severity"] == "warning"


def test_prometheus_metrics_recording(sample_result):
    """Test recording validation results in Prometheus metrics."""
    metrics = PrometheusMetrics(prefix="test_energy")
    
    metrics.record_validation(sample_result, duration_seconds=0.123)
    
    assert metrics.get_metric("free_energy") == 1.15
    assert metrics.get_metric("internal_energy") == 1.35
    assert metrics.get_metric("entropy") == 0.33
    assert metrics.get_metric("validation_total") == 1
    assert metrics.get_metric("validation_failures") == 0
    assert metrics.get_metric("validation_duration_seconds") == 0.123


def test_prometheus_metrics_failure_counting(sample_result):
    """Test that failures are counted correctly."""
    metrics = PrometheusMetrics()
    
    # Record passing validation
    metrics.record_validation(sample_result, duration_seconds=0.1)
    
    # Record failing validation
    failed_result = EnergyValidationResult(
        passed=False,
        free_energy=2.0,
        internal_energy=2.2,
        entropy=0.1,
        penalties={},
        reason="Too high",
    )
    metrics.record_validation(failed_result, duration_seconds=0.2)
    
    assert metrics.get_metric("validation_total") == 2
    assert metrics.get_metric("validation_failures") == 1


def test_prometheus_format_output():
    """Test Prometheus text format output."""
    metrics = PrometheusMetrics(prefix="tradepulse_energy")
    
    result = EnergyValidationResult(
        passed=True,
        free_energy=1.0,
        internal_energy=1.2,
        entropy=0.3,
        penalties={
            "latency_p95": 0.1,
            "latency_p99": 0.2,
            "coherency_drift": 0.0,
            "cpu_burn": 0.0,
            "mem_cost": 0.0,
            "queue_depth": 0.0,
            "packet_loss": 0.0,
        },
    )
    metrics.record_validation(result, duration_seconds=0.05)
    
    output = metrics.format_prometheus()
    
    # Check format
    assert "# TYPE tradepulse_energy_free_energy gauge" in output
    assert "tradepulse_energy_free_energy 1.0" in output
    assert "# TYPE tradepulse_energy_validation_total counter" in output
    assert "tradepulse_energy_validation_total 1" in output


def test_prometheus_metrics_with_labels():
    """Test Prometheus metrics with labels."""
    metrics = PrometheusMetrics()
    metrics.set_labels({"environment": "production", "region": "us-east"})
    
    result = EnergyValidationResult(
        passed=True,
        free_energy=1.0,
        internal_energy=1.2,
        entropy=0.3,
        penalties={},
    )
    metrics.record_validation(result, duration_seconds=0.1)
    
    output = metrics.format_prometheus()
    
    # Labels should appear in output
    assert 'environment="production"' in output
    assert 'region="us-east"' in output


def test_energy_monitor_normal_operation(sample_result, sample_metrics):
    """Test energy monitor in normal operation."""
    monitor = EnergyMonitor(
        warning_threshold=1.3,
        critical_threshold=1.4,
    )
    
    # Record normal validation (energy 1.15 < 1.3)
    monitor.record_validation(sample_result, sample_metrics, duration_seconds=0.1)
    
    # Should not generate alerts
    recent_alerts = monitor.get_recent_alerts()
    assert len(recent_alerts) == 0


def test_energy_monitor_warning_alert(sample_metrics):
    """Test energy monitor warning alert."""
    monitor = EnergyMonitor(
        warning_threshold=1.2,
        critical_threshold=1.4,
        alert_cooldown=0.0,  # Disable cooldown for testing
    )
    
    high_result = EnergyValidationResult(
        passed=True,
        free_energy=1.25,  # Above warning threshold
        internal_energy=1.45,
        entropy=0.3,
        penalties={},
    )
    
    alert = monitor.check_and_alert(high_result, sample_metrics)
    
    assert alert is not None
    assert alert.severity == AlertSeverity.WARNING
    assert alert.free_energy == 1.25
    assert "Warning" in alert.message


def test_energy_monitor_critical_alert(sample_metrics):
    """Test energy monitor critical alert."""
    monitor = EnergyMonitor(
        warning_threshold=1.2,
        critical_threshold=1.35,
        alert_cooldown=0.0,
    )
    
    critical_result = EnergyValidationResult(
        passed=False,
        free_energy=1.5,  # Above critical threshold
        internal_energy=1.7,
        entropy=0.2,
        penalties={},
    )
    
    alert = monitor.check_and_alert(critical_result, sample_metrics)
    
    assert alert is not None
    assert alert.severity == AlertSeverity.CRITICAL
    assert "Critical" in alert.message


def test_energy_monitor_alert_cooldown(sample_metrics):
    """Test that alert cooldown prevents spam."""
    monitor = EnergyMonitor(
        warning_threshold=1.0,
        critical_threshold=1.5,
        alert_cooldown=60.0,  # 60 seconds
    )
    
    high_result = EnergyValidationResult(
        passed=True,
        free_energy=1.2,
        internal_energy=1.4,
        entropy=0.3,
        penalties={},
    )
    
    # First alert should trigger
    alert1 = monitor.check_and_alert(high_result, sample_metrics)
    assert alert1 is not None
    
    # Immediate second alert should be suppressed
    alert2 = monitor.check_and_alert(high_result, sample_metrics)
    assert alert2 is None


def test_energy_monitor_alert_callback(sample_metrics):
    """Test alert callback mechanism."""
    monitor = EnergyMonitor(
        warning_threshold=1.0,
        alert_cooldown=0.0,
    )
    
    callback_invoked = []
    
    def callback(alert: EnergyAlert):
        callback_invoked.append(alert)
    
    monitor.register_alert_callback(callback)
    
    high_result = EnergyValidationResult(
        passed=True,
        free_energy=1.2,
        internal_energy=1.4,
        entropy=0.3,
        penalties={},
    )
    
    monitor.check_and_alert(high_result, sample_metrics)
    
    assert len(callback_invoked) == 1
    assert callback_invoked[0].free_energy == 1.2


def test_energy_monitor_callback_error_handling(sample_metrics):
    """Test that callback errors don't break monitoring."""
    monitor = EnergyMonitor(warning_threshold=1.0, alert_cooldown=0.0)
    
    def failing_callback(alert: EnergyAlert):
        raise RuntimeError("Callback failed")
    
    monitor.register_alert_callback(failing_callback)
    
    high_result = EnergyValidationResult(
        passed=True,
        free_energy=1.2,
        internal_energy=1.4,
        entropy=0.3,
        penalties={},
    )
    
    # Should not raise exception
    alert = monitor.check_and_alert(high_result, sample_metrics)
    assert alert is not None


def test_energy_reporter_summary():
    """Test generation of summary reports."""
    results = [
        EnergyValidationResult(
            passed=True,
            free_energy=1.0,
            internal_energy=1.2,
            entropy=0.3,
            penalties={},
        ),
        EnergyValidationResult(
            passed=True,
            free_energy=1.1,
            internal_energy=1.3,
            entropy=0.3,
            penalties={},
        ),
        EnergyValidationResult(
            passed=False,
            free_energy=1.5,
            internal_energy=1.7,
            entropy=0.2,
            penalties={},
            reason="Too high",
        ),
    ]
    
    summary = EnergyReporter.format_summary(results, title="Test Report")
    
    assert "Test Report" in summary
    assert "Total Validations: 3" in summary
    assert "Passed: 2" in summary
    assert "Failed: 1" in summary
    assert "Energy Statistics" in summary


def test_energy_reporter_json_export():
    """Test JSON export of results."""
    results = [
        EnergyValidationResult(
            passed=True,
            free_energy=1.0,
            internal_energy=1.2,
            entropy=0.3,
            penalties={"metric1": 0.1},
        ),
        EnergyValidationResult(
            passed=False,
            free_energy=1.5,
            internal_energy=1.7,
            entropy=0.2,
            penalties={"metric1": 0.5},
            reason="Failed",
        ),
    ]
    
    json_output = EnergyReporter.export_json(results, include_penalties=True)
    data = json.loads(json_output)
    
    assert data["total"] == 2
    assert data["passed"] == 1
    assert data["failed"] == 1
    assert len(data["results"]) == 2
    assert "penalties" in data["results"][0]


def test_energy_reporter_json_export_without_penalties():
    """Test JSON export without penalty details."""
    results = [
        EnergyValidationResult(
            passed=True,
            free_energy=1.0,
            internal_energy=1.2,
            entropy=0.3,
            penalties={"metric1": 0.1},
        ),
    ]
    
    json_output = EnergyReporter.export_json(results, include_penalties=False)
    data = json.loads(json_output)
    
    assert "penalties" not in data["results"][0]


def test_monitor_get_prometheus_metrics(sample_result, sample_metrics):
    """Test getting Prometheus metrics from monitor."""
    monitor = EnergyMonitor()
    
    monitor.record_validation(sample_result, sample_metrics, duration_seconds=0.1)
    
    metrics_output = monitor.get_prometheus_metrics()
    
    assert isinstance(metrics_output, str)
    assert "tradepulse_energy" in metrics_output
    assert "free_energy" in metrics_output
