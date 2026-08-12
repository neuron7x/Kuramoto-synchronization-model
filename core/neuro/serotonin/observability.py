# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""SRE Observability utilities for Serotonin Controller.

This module provides SLI/SLO definitions, metrics collection,
and monitoring utilities following SRE best practices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class AlertSeverity(Enum):
    """Alert severity levels following SRE practices."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class SLI:
    """Service Level Indicator definition."""

    name: str
    description: str
    unit: str
    good_event_condition: str  # Human-readable condition for "good" events

    def __str__(self) -> str:
        return f"SLI({self.name}): {self.description} [{self.unit}]"


@dataclass(frozen=True)
class SLO:
    """Service Level Objective with error budget."""

    sli: SLI
    target: float  # Target percentage (e.g., 99.5 for 99.5%)
    window: str  # Time window (e.g., "30d", "7d")

    @property
    def error_budget(self) -> float:
        """Calculate error budget percentage."""
        return 100.0 - self.target

    def is_met(self, actual: float) -> bool:
        """Check if actual performance meets SLO."""
        return actual >= self.target

    def budget_consumed(self, actual: float) -> float:
        """Calculate percentage of error budget consumed.

        Returns:
            0.0 = no budget consumed (perfect)
            1.0 = entire budget consumed (at SLO threshold)
            > 1.0 = over budget (SLO violation)
        """
        if actual >= self.target:
            return 0.0

        error_rate = 100.0 - actual
        budget = self.error_budget

        if budget <= 0:
            return float("inf")

        return error_rate / budget

    def __str__(self) -> str:
        return f"SLO({self.sli.name}): {self.target}% over {self.window}"


# Define SLIs for Serotonin Controller
SEROTONIN_SLIS = {
    "step_latency_p95": SLI(
        name="step_latency_p95",
        description="95th percentile step() execution time",
        unit="microseconds",
        good_event_condition="latency < 500μs",
    ),
    "step_latency_p99": SLI(
        name="step_latency_p99",
        description="99th percentile step() execution time",
        unit="microseconds",
        good_event_condition="latency < 1000μs",
    ),
    "hold_decision_accuracy": SLI(
        name="hold_decision_accuracy",
        description="Percentage of correct hold/release decisions",
        unit="percentage",
        good_event_condition="decision prevents trading loss",
    ),
    "state_validation_success": SLI(
        name="state_validation_success",
        description="Percentage of state validation checks passing",
        unit="percentage",
        good_event_condition="validate_state() returns True",
    ),
    "config_load_success": SLI(
        name="config_load_success",
        description="Percentage of successful config loads",
        unit="percentage",
        good_event_condition="config loaded without errors",
    ),
}


# Define SLOs with error budgets
SEROTONIN_SLOS = {
    "step_latency_p95": SLO(
        sli=SEROTONIN_SLIS["step_latency_p95"],
        target=99.9,  # 99.9% of steps < 500μs
        window="30d",
    ),
    "step_latency_p99": SLO(
        sli=SEROTONIN_SLIS["step_latency_p99"],
        target=99.5,  # 99.5% of steps < 1000μs
        window="30d",
    ),
    "hold_decision_accuracy": SLO(
        sli=SEROTONIN_SLIS["hold_decision_accuracy"],
        target=99.5,  # 99.5% correct decisions
        window="7d",
    ),
    "state_validation_success": SLO(
        sli=SEROTONIN_SLIS["state_validation_success"],
        target=99.99,  # 99.99% validation success
        window="30d",
    ),
    "config_load_success": SLO(
        sli=SEROTONIN_SLIS["config_load_success"],
        target=99.9,  # 99.9% successful loads
        window="30d",
    ),
}


@dataclass(frozen=True)
class Alert:
    """Alert definition for monitoring."""

    name: str
    description: str
    severity: AlertSeverity
    condition: str
    remediation: str

    def __str__(self) -> str:
        return f"Alert[{self.severity.value}]({self.name}): {self.condition}"


# Define alerts based on SLOs and operational concerns
SEROTONIN_ALERTS = {
    "high_stress_level": Alert(
        name="serotonin_high_stress_level",
        description="Serotonin level elevated above warning threshold",
        severity=AlertSeverity.WARNING,
        condition="level > 1.2 for 5 consecutive minutes",
        remediation=(
            "Review recent market events and trading activity. "
            "Consider manual intervention if level approaches 1.4."
        ),
    ),
    "extended_hold_state": Alert(
        name="serotonin_extended_hold_state",
        description="Controller in hold state for extended period",
        severity=AlertSeverity.WARNING,
        condition="hold_state = True for > 30 minutes",
        remediation=(
            "Investigate market conditions. Verify stress inputs are accurate. "
            "May indicate market crisis or data issue."
        ),
    ),
    "state_validation_failure": Alert(
        name="serotonin_state_validation_failure",
        description="State validation check failed",
        severity=AlertSeverity.CRITICAL,
        condition="validate_state() returns False",
        remediation=(
            "IMMEDIATE: Stop trading. Investigate state corruption. "
            "Review recent inputs and config changes. Restart controller with reset()."
        ),
    ),
    "slo_violation_latency": Alert(
        name="serotonin_slo_violation_latency",
        description="Step latency SLO violation",
        severity=AlertSeverity.WARNING,
        condition="P95 latency > 500μs over 30-day window",
        remediation=(
            "Profile step() execution. Check for performance regressions. "
            "Consider optimization or infrastructure upgrade."
        ),
    ),
    "error_budget_critical": Alert(
        name="serotonin_error_budget_critical",
        description="Error budget critically depleted",
        severity=AlertSeverity.CRITICAL,
        condition="Error budget consumption > 80%",
        remediation=(
            "FREEZE: Stop non-critical changes. Focus on stability. "
            "Conduct incident review. Defer feature work until budget recovers."
        ),
    ),
    "desensitization_excessive": Alert(
        name="serotonin_desensitization_excessive",
        description="Desensitization level near maximum",
        severity=AlertSeverity.WARNING,
        condition="desensitization > 0.7 (approaching max_desensitization)",
        remediation=(
            "Extended high-stress period detected. Review market conditions "
            "and risk exposure. Consider manual stress assessment."
        ),
    ),
}


class SerotoninMonitor:
    """Monitoring and alerting for SerotoninController.

    Provides SRE-style observability including:
    - SLI/SLO tracking
    - Error budget calculation
    - Alert evaluation
    - Anomaly detection
    """

    def __init__(
        self,
        alert_callback: Optional[Callable[[Alert, float], None]] = None,
    ) -> None:
        """Initialize monitor.

        Args:
            alert_callback: Optional callback for alert notifications.
                            Called with (alert, current_value).
        """
        self._alert_callback = alert_callback or (lambda alert, value: None)

        # Tracking state
        self._high_stress_ticks = 0
        self._hold_state_ticks = 0
        self._last_hold_state = False

    def check_alerts(
        self,
        level: float,
        hold: bool,
        desensitization: float,
        validation_ok: bool,
    ) -> list[Alert]:
        """Evaluate alert conditions and return triggered alerts.

        Args:
            level: Current serotonin level
            hold: Current hold state
            desensitization: Current desensitization level
            validation_ok: Result of validate_state()

        Returns:
            List of triggered alerts
        """
        triggered = []

        # Track consecutive ticks
        if level > 1.2:
            self._high_stress_ticks += 1
        else:
            self._high_stress_ticks = 0

        if hold:
            self._hold_state_ticks += 1
        else:
            self._hold_state_ticks = 0

        self._last_hold_state = hold

        # Evaluate alert conditions
        if self._high_stress_ticks >= 300:  # 5 minutes at 1 tick/second
            alert = SEROTONIN_ALERTS["high_stress_level"]
            triggered.append(alert)
            self._alert_callback(alert, level)

        if self._hold_state_ticks >= 1800:  # 30 minutes
            alert = SEROTONIN_ALERTS["extended_hold_state"]
            triggered.append(alert)
            self._alert_callback(alert, float(self._hold_state_ticks))

        if not validation_ok:
            alert = SEROTONIN_ALERTS["state_validation_failure"]
            triggered.append(alert)
            self._alert_callback(alert, 0.0)

        if desensitization > 0.7:
            alert = SEROTONIN_ALERTS["desensitization_excessive"]
            triggered.append(alert)
            self._alert_callback(alert, desensitization)

        return triggered

    def reset_tracking(self) -> None:
        """Reset internal tracking counters."""
        self._high_stress_ticks = 0
        self._hold_state_ticks = 0
        self._last_hold_state = False

    @staticmethod
    def format_slo_report(slo_name: str, actual: float) -> str:
        """Format SLO status report.

        Args:
            slo_name: Name of SLO to report on
            actual: Actual measured value (percentage)

        Returns:
            Formatted report string
        """
        if slo_name not in SEROTONIN_SLOS:
            return f"Unknown SLO: {slo_name}"

        slo = SEROTONIN_SLOS[slo_name]
        budget_consumed = slo.budget_consumed(actual)
        is_met = slo.is_met(actual)

        status = "✓ PASS" if is_met else "✗ FAIL"

        report = [
            f"SLO Report: {slo.sli.name}",
            f"Status: {status}",
            f"Target: {slo.target}% over {slo.window}",
            f"Actual: {actual:.2f}%",
            f"Error Budget: {slo.error_budget:.2f}%",
            f"Budget Consumed: {budget_consumed * 100:.1f}%",
        ]

        if budget_consumed > 0.8:
            report.append("⚠️  WARNING: Error budget critically depleted!")
        elif budget_consumed > 0.5:
            report.append("⚠️  CAUTION: Error budget > 50% consumed")

        return "\n".join(report)


def create_prometheus_metrics() -> str:
    """Generate Prometheus metrics exposition format.

    Returns example metrics that should be exposed by the controller.
    This is a reference implementation - actual integration would
    use prometheus_client library.

    Returns:
        Prometheus metrics format string (for documentation/reference)
    """
    metrics = """
# HELP serotonin_level Current serotonin stress level
# TYPE serotonin_level gauge
serotonin_level{component="serotonin_controller"} 0.0

# HELP serotonin_hold_state Hold state (1=hold, 0=active)
# TYPE serotonin_hold_state gauge
serotonin_hold_state{component="serotonin_controller"} 0

# HELP serotonin_cooldown_ticks Remaining cooldown ticks
# TYPE serotonin_cooldown_ticks gauge
serotonin_cooldown_ticks{component="serotonin_controller"} 0

# HELP serotonin_desensitization Current desensitization level
# TYPE serotonin_desensitization gauge
serotonin_desensitization{component="serotonin_controller"} 0.0

# HELP serotonin_temperature_floor Current temperature floor
# TYPE serotonin_temperature_floor gauge
serotonin_temperature_floor{component="serotonin_controller"} 0.0

# HELP serotonin_step_duration_seconds Step execution duration
# TYPE serotonin_step_duration_seconds histogram
serotonin_step_duration_seconds_bucket{le="0.0001"} 0
serotonin_step_duration_seconds_bucket{le="0.0005"} 0
serotonin_step_duration_seconds_bucket{le="0.001"} 0
serotonin_step_duration_seconds_bucket{le="+Inf"} 0
serotonin_step_duration_seconds_sum 0.0
serotonin_step_duration_seconds_count 0

# HELP serotonin_state_validation_total State validation checks
# TYPE serotonin_state_validation_total counter
serotonin_state_validation_total{result="success"} 0
serotonin_state_validation_total{result="failure"} 0

# HELP serotonin_hold_transitions_total Hold state transitions
# TYPE serotonin_hold_transitions_total counter
serotonin_hold_transitions_total{transition="enter"} 0
serotonin_hold_transitions_total{transition="exit"} 0
"""
    return metrics.strip()


def create_grafana_dashboard_json() -> dict:
    """Generate Grafana dashboard configuration.

    Returns:
        Dashboard JSON structure (simplified reference)
    """
    return {
        "dashboard": {
            "title": "Serotonin Controller - SRE Dashboard",
            "tags": ["serotonin", "neuromodulator", "sre"],
            "panels": [
                {
                    "title": "Serotonin Level",
                    "type": "graph",
                    "targets": [
                        {"expr": "serotonin_level"},
                    ],
                    "alert": {
                        "name": "High Stress Level",
                        "conditions": [
                            {"query": "avg() OF serotonin_level > 1.2 FOR 5m"},
                        ],
                    },
                },
                {
                    "title": "Hold State",
                    "type": "stat",
                    "targets": [
                        {"expr": "serotonin_hold_state"},
                    ],
                },
                {
                    "title": "SLO Compliance",
                    "type": "table",
                    "targets": [
                        {"expr": "histogram_quantile(0.95, serotonin_step_duration_seconds)"},
                        {"expr": "rate(serotonin_state_validation_total{result='failure'}[30d])"},
                    ],
                },
                {
                    "title": "Error Budget Burn Rate",
                    "type": "graph",
                    "targets": [
                        {"expr": "rate(serotonin_slo_violations_total[1h])"},
                    ],
                },
            ],
        },
    }


__all__ = [
    "Alert",
    "AlertSeverity",
    "SLI",
    "SLO",
    "SEROTONIN_ALERTS",
    "SEROTONIN_SLIS",
    "SEROTONIN_SLOS",
    "SerotoninMonitor",
    "create_grafana_dashboard_json",
    "create_prometheus_metrics",
]
