"""Monitoring and metrics export for energy model integration.

This module provides comprehensive monitoring capabilities including:

- Prometheus metrics export for observability
- Real-time alerting based on energy thresholds
- Integration with external monitoring systems
- Structured logging for energy events
- Dashboard-ready metric formatting

These tools enable production-grade monitoring and observability of the
thermodynamic energy model in live trading environments.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence
from enum import Enum
import time
import json

from .energy_model import EnergyMetrics, EnergyValidationResult


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class EnergyAlert:
    """Energy-related alert with context."""
    
    severity: AlertSeverity
    message: str
    timestamp: float
    free_energy: float
    threshold: float
    metrics_snapshot: Mapping[str, float]
    
    def to_dict(self) -> dict:
        """Convert alert to dictionary for serialization."""
        return {
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp,
            "free_energy": self.free_energy,
            "threshold": self.threshold,
            "metrics": dict(self.metrics_snapshot),
        }
    
    def to_json(self) -> str:
        """Convert alert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


@dataclass(slots=True)
class PrometheusMetrics:
    """Prometheus-compatible metrics collector for energy model.
    
    Maintains gauges and counters for key energy metrics that can be exported
    to Prometheus for monitoring and alerting.
    """
    
    prefix: str = "tradepulse_energy"
    _metrics: dict = field(default_factory=dict)
    _labels: dict = field(default_factory=dict)
    
    def __post_init__(self):
        """Initialize metric storage."""
        self._metrics = {
            "free_energy": 0.0,
            "internal_energy": 0.0,
            "entropy": 0.0,
            "validation_total": 0,
            "validation_failures": 0,
            "validation_duration_seconds": 0.0,
        }
        
        # Per-metric penalties
        for metric_name in [
            "latency_p95", "latency_p99", "coherency_drift",
            "cpu_burn", "mem_cost", "queue_depth", "packet_loss"
        ]:
            self._metrics[f"penalty_{metric_name}"] = 0.0
    
    def record_validation(
        self, 
        result: EnergyValidationResult,
        duration_seconds: float,
    ) -> None:
        """Record a validation result in metrics.
        
        Args:
            result: Validation result to record
            duration_seconds: Time taken for validation
        """
        self._metrics["free_energy"] = result.free_energy
        self._metrics["internal_energy"] = result.internal_energy
        self._metrics["entropy"] = result.entropy
        self._metrics["validation_total"] += 1
        self._metrics["validation_duration_seconds"] = duration_seconds
        
        if not result.passed:
            self._metrics["validation_failures"] += 1
        
        # Record individual penalties
        for metric_name, penalty_value in result.penalties.items():
            key = f"penalty_{metric_name}"
            if key in self._metrics:
                self._metrics[key] = penalty_value
    
    def get_metric(self, name: str) -> float:
        """Get current value of a metric.
        
        Args:
            name: Metric name (without prefix)
            
        Returns:
            Current metric value
        """
        return self._metrics.get(name, 0.0)
    
    def format_prometheus(self) -> str:
        """Format metrics in Prometheus text exposition format.
        
        Returns:
            Prometheus-formatted metrics string
        """
        lines = []
        
        # Gauges
        for metric_name, value in self._metrics.items():
            if metric_name == "validation_total" or metric_name == "validation_failures":
                # These are counters
                metric_type = "counter"
            else:
                metric_type = "gauge"
            
            full_name = f"{self.prefix}_{metric_name}"
            lines.append(f"# TYPE {full_name} {metric_type}")
            
            # Add labels if present
            if self._labels:
                label_str = ",".join(f'{k}="{v}"' for k, v in self._labels.items())
                lines.append(f"{full_name}{{{label_str}}} {value}")
            else:
                lines.append(f"{full_name} {value}")
        
        return "\n".join(lines) + "\n"
    
    def set_labels(self, labels: Mapping[str, str]) -> None:
        """Set labels for all metrics.
        
        Args:
            labels: Key-value pairs for metric labels
        """
        self._labels = dict(labels)


@dataclass(slots=True)
class EnergyMonitor:
    """Real-time monitoring and alerting for energy model.
    
    Tracks energy levels and triggers alerts when thresholds are exceeded.
    Integrates with Prometheus and other monitoring systems.
    """
    
    warning_threshold: float = 1.2
    critical_threshold: float = 1.35
    alert_cooldown: float = 60.0  # seconds
    
    _prometheus: PrometheusMetrics = field(default_factory=PrometheusMetrics)
    _alerts: list[EnergyAlert] = field(default_factory=list)
    _last_alert_time: float = 0.0
    _alert_callbacks: list[Callable[[EnergyAlert], None]] = field(default_factory=list)
    
    def register_alert_callback(
        self, 
        callback: Callable[[EnergyAlert], None]
    ) -> None:
        """Register a callback to be invoked when alerts are generated.
        
        Args:
            callback: Function to call with EnergyAlert objects
        """
        self._alert_callbacks.append(callback)
    
    def check_and_alert(
        self,
        result: EnergyValidationResult,
        metrics: EnergyMetrics,
    ) -> EnergyAlert | None:
        """Check energy level and generate alert if needed.
        
        Args:
            result: Validation result to check
            metrics: Metrics that produced the result
            
        Returns:
            EnergyAlert if threshold exceeded, None otherwise
        """
        current_time = time.time()
        
        # Apply cooldown to avoid alert spam
        if current_time - self._last_alert_time < self.alert_cooldown:
            return None
        
        alert = None
        energy = result.free_energy
        
        if energy >= self.critical_threshold:
            alert = EnergyAlert(
                severity=AlertSeverity.CRITICAL,
                message=f"Critical: Free energy {energy:.3f} exceeds critical threshold {self.critical_threshold:.3f}",
                timestamp=current_time,
                free_energy=energy,
                threshold=self.critical_threshold,
                metrics_snapshot=metrics.as_dict(),
            )
        elif energy >= self.warning_threshold:
            alert = EnergyAlert(
                severity=AlertSeverity.WARNING,
                message=f"Warning: Free energy {energy:.3f} exceeds warning threshold {self.warning_threshold:.3f}",
                timestamp=current_time,
                free_energy=energy,
                threshold=self.warning_threshold,
                metrics_snapshot=metrics.as_dict(),
            )
        
        if alert:
            self._alerts.append(alert)
            self._last_alert_time = current_time
            
            # Invoke callbacks
            for callback in self._alert_callbacks:
                try:
                    callback(alert)
                except Exception:
                    # Don't let callback errors break monitoring
                    pass
        
        return alert
    
    def record_validation(
        self,
        result: EnergyValidationResult,
        metrics: EnergyMetrics,
        duration_seconds: float,
    ) -> None:
        """Record a validation and update monitoring state.
        
        Args:
            result: Validation result
            metrics: Metrics that were validated
            duration_seconds: Time taken for validation
        """
        self._prometheus.record_validation(result, duration_seconds)
        self.check_and_alert(result, metrics)
    
    def get_prometheus_metrics(self) -> str:
        """Get Prometheus-formatted metrics string.
        
        Returns:
            Metrics in Prometheus text format
        """
        return self._prometheus.format_prometheus()
    
    def get_recent_alerts(self, limit: int = 100) -> Sequence[EnergyAlert]:
        """Get recent alerts.
        
        Args:
            limit: Maximum number of alerts to return
            
        Returns:
            List of recent alerts
        """
        return self._alerts[-limit:]
    
    def clear_alerts(self) -> None:
        """Clear alert history."""
        self._alerts.clear()


class EnergyReporter:
    """Generate comprehensive reports for energy validation results."""
    
    @staticmethod
    def format_summary(
        results: Sequence[EnergyValidationResult],
        *,
        title: str = "Energy Validation Summary",
    ) -> str:
        """Generate a formatted summary report.
        
        Args:
            results: Validation results to summarize
            title: Report title
            
        Returns:
            Formatted text report
        """
        lines = [
            "=" * 70,
            title.center(70),
            "=" * 70,
            "",
            f"Total Validations: {len(results)}",
        ]
        
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        
        lines.extend([
            f"Passed: {passed} ({100 * passed / len(results):.1f}%)",
            f"Failed: {failed} ({100 * failed / len(results):.1f}%)",
            "",
        ])
        
        if results:
            energies = [r.free_energy for r in results]
            lines.extend([
                "Energy Statistics:",
                f"  Mean: {sum(energies) / len(energies):.6f}",
                f"  Min:  {min(energies):.6f}",
                f"  Max:  {max(energies):.6f}",
                "",
            ])
        
        # Failed validations detail
        if failed > 0:
            lines.append("Failed Validations:")
            for i, result in enumerate(results):
                if not result.passed:
                    lines.append(f"  [{i}] Energy: {result.free_energy:.6f}")
                    if result.reason:
                        lines.append(f"      Reason: {result.reason}")
            lines.append("")
        
        lines.append("=" * 70)
        return "\n".join(lines)
    
    @staticmethod
    def export_json(
        results: Sequence[EnergyValidationResult],
        *,
        include_penalties: bool = True,
    ) -> str:
        """Export results as JSON.
        
        Args:
            results: Validation results to export
            include_penalties: Whether to include penalty details
            
        Returns:
            JSON string
        """
        data = {
            "total": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "results": [],
        }
        
        for result in results:
            entry = {
                "passed": result.passed,
                "free_energy": result.free_energy,
                "internal_energy": result.internal_energy,
                "entropy": result.entropy,
            }
            
            if include_penalties:
                entry["penalties"] = dict(result.penalties)
            
            if result.reason:
                entry["reason"] = result.reason
            
            data["results"].append(entry)
        
        return json.dumps(data, indent=2)


__all__ = [
    "AlertSeverity",
    "EnergyAlert",
    "EnergyMonitor",
    "EnergyReporter",
    "PrometheusMetrics",
]
