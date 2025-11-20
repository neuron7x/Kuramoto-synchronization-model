"""Tests for serotonin controller observability module."""

from __future__ import annotations

from src.tradepulse.core.neuro.serotonin.observability import (
    SEROTONIN_ALERTS,
    SEROTONIN_SLOS,
    SLI,
    SLO,
    Alert,
    AlertSeverity,
    SerotoninMonitor,
    create_grafana_dashboard_json,
    create_prometheus_metrics,
)


def test_sli_creation():
    """Test SLI dataclass creation."""
    sli = SLI(
        name="test_metric",
        description="Test metric",
        unit="seconds",
        good_event_condition="value < 1.0",
    )
    assert sli.name == "test_metric"
    assert "Test metric" in str(sli)


def test_slo_error_budget():
    """Test SLO error budget calculation."""
    sli = SLI("test", "desc", "unit", "condition")
    slo = SLO(sli=sli, target=99.9, window="30d")

    # Error budget should be 0.1%
    assert abs(slo.error_budget - 0.1) < 0.001

    # At target, should meet SLO
    assert slo.is_met(99.9)
    assert slo.is_met(100.0)

    # Below target, should fail
    assert not slo.is_met(99.8)


def test_slo_budget_consumed():
    """Test error budget consumption calculation."""
    sli = SLI("test", "desc", "unit", "condition")
    slo = SLO(sli=sli, target=99.9, window="30d")

    # Perfect performance = 0% budget consumed
    assert slo.budget_consumed(100.0) == 0.0
    assert slo.budget_consumed(99.9) == 0.0

    # At 99.85%, half the error budget is consumed
    # Error = 0.15%, Budget = 0.1%, Consumed = 150%
    consumed = slo.budget_consumed(99.85)
    assert abs(consumed - 1.5) < 0.01


def test_predefined_slos():
    """Test that predefined SLOs are properly configured."""
    # Check all expected SLOs exist
    expected_slos = {
        "step_latency_p95",
        "step_latency_p99",
        "hold_decision_accuracy",
        "state_validation_success",
        "config_load_success",
    }
    assert set(SEROTONIN_SLOS.keys()) == expected_slos

    # Verify latency SLO targets
    assert SEROTONIN_SLOS["step_latency_p95"].target == 99.9
    assert SEROTONIN_SLOS["step_latency_p99"].target == 99.5


def test_predefined_alerts():
    """Test that predefined alerts are properly configured."""
    expected_alerts = {
        "high_stress_level",
        "extended_hold_state",
        "state_validation_failure",
        "slo_violation_latency",
        "error_budget_critical",
        "desensitization_excessive",
    }
    assert set(SEROTONIN_ALERTS.keys()) == expected_alerts

    # Check critical alerts have correct severity
    assert (
        SEROTONIN_ALERTS["state_validation_failure"].severity == AlertSeverity.CRITICAL
    )
    assert SEROTONIN_ALERTS["error_budget_critical"].severity == AlertSeverity.CRITICAL

    # Check warning alerts
    assert SEROTONIN_ALERTS["high_stress_level"].severity == AlertSeverity.WARNING


def test_monitor_initialization():
    """Test SerotoninMonitor initialization."""
    monitor = SerotoninMonitor()
    assert monitor._high_stress_ticks == 0
    assert monitor._hold_state_ticks == 0
    assert not monitor._last_hold_state


def test_monitor_no_alerts():
    """Test monitor with normal conditions triggers no alerts."""
    monitor = SerotoninMonitor()

    alerts = monitor.check_alerts(
        level=0.5,
        hold=False,
        desensitization=0.3,
        validation_ok=True,
    )

    assert len(alerts) == 0


def test_monitor_validation_failure_alert():
    """Test that validation failure triggers critical alert."""
    monitor = SerotoninMonitor()

    alerts = monitor.check_alerts(
        level=0.5,
        hold=False,
        desensitization=0.3,
        validation_ok=False,
    )

    assert len(alerts) == 1
    assert alerts[0].name == "serotonin_state_validation_failure"
    assert alerts[0].severity == AlertSeverity.CRITICAL


def test_monitor_high_stress_alert():
    """Test that sustained high stress triggers alert."""
    monitor = SerotoninMonitor()

    # Simulate 300 ticks (5 minutes) of high stress
    for _ in range(299):
        alerts = monitor.check_alerts(
            level=1.3,
            hold=False,
            desensitization=0.3,
            validation_ok=True,
        )
        # Should not trigger yet
        assert len([a for a in alerts if a.name == "serotonin_high_stress_level"]) == 0

    # 300th tick should trigger
    alerts = monitor.check_alerts(
        level=1.3,
        hold=False,
        desensitization=0.3,
        validation_ok=True,
    )
    assert any(a.name == "serotonin_high_stress_level" for a in alerts)


def test_monitor_extended_hold_alert():
    """Test that extended hold state triggers alert."""
    monitor = SerotoninMonitor()

    # Simulate 1800 ticks (30 minutes) of hold
    for _ in range(1799):
        alerts = monitor.check_alerts(
            level=0.8,
            hold=True,
            desensitization=0.3,
            validation_ok=True,
        )
        # Should not trigger yet
        assert (
            len([a for a in alerts if a.name == "serotonin_extended_hold_state"]) == 0
        )

    # 1800th tick should trigger
    alerts = monitor.check_alerts(
        level=0.8,
        hold=True,
        desensitization=0.3,
        validation_ok=True,
    )
    assert any(a.name == "serotonin_extended_hold_state" for a in alerts)


def test_monitor_desensitization_alert():
    """Test that excessive desensitization triggers alert."""
    monitor = SerotoninMonitor()

    alerts = monitor.check_alerts(
        level=0.8,
        hold=False,
        desensitization=0.75,  # > 0.7 threshold
        validation_ok=True,
    )

    assert any(a.name == "serotonin_desensitization_excessive" for a in alerts)


def test_monitor_reset():
    """Test that monitor reset clears tracking state."""
    monitor = SerotoninMonitor()

    # Build up some state
    for _ in range(10):
        monitor.check_alerts(
            level=1.3,
            hold=True,
            desensitization=0.3,
            validation_ok=True,
        )

    assert monitor._high_stress_ticks > 0
    assert monitor._hold_state_ticks > 0

    # Reset should clear
    monitor.reset_tracking()
    assert monitor._high_stress_ticks == 0
    assert monitor._hold_state_ticks == 0
    assert not monitor._last_hold_state


def test_alert_callback():
    """Test that alert callback is invoked."""
    triggered_alerts = []

    def callback(alert: Alert, value: float):
        triggered_alerts.append((alert.name, value))

    monitor = SerotoninMonitor(alert_callback=callback)

    # Trigger validation failure
    monitor.check_alerts(
        level=0.5,
        hold=False,
        desensitization=0.3,
        validation_ok=False,
    )

    assert len(triggered_alerts) == 1
    assert triggered_alerts[0][0] == "serotonin_state_validation_failure"


def test_slo_report_formatting():
    """Test SLO report generation."""
    report = SerotoninMonitor.format_slo_report("step_latency_p95", 99.85)

    assert "step_latency_p95" in report
    assert "99.85" in report
    assert "99.9" in report  # Target
    assert "150" in report  # Budget consumed percentage


def test_prometheus_metrics_format():
    """Test Prometheus metrics format generation."""
    metrics = create_prometheus_metrics()

    # Check for key metrics
    assert "serotonin_level" in metrics
    assert "serotonin_hold_state" in metrics
    assert "serotonin_step_duration_seconds" in metrics
    assert "TYPE" in metrics
    assert "HELP" in metrics


def test_grafana_dashboard_structure():
    """Test Grafana dashboard JSON structure."""
    dashboard = create_grafana_dashboard_json()

    assert "dashboard" in dashboard
    assert "title" in dashboard["dashboard"]
    assert "panels" in dashboard["dashboard"]
    assert len(dashboard["dashboard"]["panels"]) > 0


if __name__ == "__main__":
    # Run basic smoke tests
    test_sli_creation()
    test_slo_error_budget()
    test_predefined_slos()
    test_predefined_alerts()
    test_monitor_initialization()
    test_monitor_no_alerts()
    test_monitor_validation_failure_alert()
    test_monitor_desensitization_alert()
    test_monitor_reset()
    test_alert_callback()
    test_slo_report_formatting()
    test_prometheus_metrics_format()
    test_grafana_dashboard_structure()

    print("✓ All observability tests passed!")
