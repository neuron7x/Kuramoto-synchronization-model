#!/usr/bin/env python3
"""Demonstration of energy monitoring and observability capabilities.

This script showcases production-grade monitoring features including Prometheus
metrics export, real-time alerting, comprehensive reporting, and integration
patterns for observability systems.
"""

from __future__ import annotations

import sys
from pathlib import Path
import time

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tacl import (
    EnergyMetrics,
    EnergyModel,
    EnergyMonitor,
    EnergyReporter,
    PrometheusMetrics,
    AlertSeverity,
)


def create_metrics_for_load(load_factor: float) -> EnergyMetrics:
    """Create metrics representing system load."""
    base_latency = 60.0 + (load_factor * 60.0)
    
    return EnergyMetrics(
        latency_p95=base_latency,
        latency_p99=base_latency * 1.4,
        coherency_drift=0.03 + (load_factor * 0.05),
        cpu_burn=0.5 + (load_factor * 0.3),
        mem_cost=4.5 + (load_factor * 2.5),
        queue_depth=20.0 + (load_factor * 20.0),
        packet_loss=0.002 + (load_factor * 0.006),
    )


def demo_prometheus_metrics():
    """Demonstrate Prometheus metrics export."""
    print("=" * 70)
    print("PROMETHEUS METRICS EXPORT")
    print("=" * 70)
    print()
    
    # Create Prometheus metrics collector
    prom_metrics = PrometheusMetrics(prefix="tradepulse_energy")
    prom_metrics.set_labels({
        "environment": "production",
        "region": "us-east-1",
        "service": "trading-engine",
    })
    
    model = EnergyModel()
    
    # Simulate multiple validations
    print("Recording validations...")
    for i in range(5):
        load = i * 0.2
        metrics = create_metrics_for_load(load)
        
        start = time.time()
        result = model.evaluate(metrics, max_free_energy=1.4)
        duration = time.time() - start
        
        prom_metrics.record_validation(result, duration)
        
        print(f"  Validation {i+1}: energy={result.free_energy:.6f}, "
              f"passed={result.passed}, duration={duration:.4f}s")
    
    print()
    
    # Export metrics
    print("Prometheus Metrics Export:")
    print("-" * 70)
    output = prom_metrics.format_prometheus()
    print(output)
    print("-" * 70)
    print()
    
    print("These metrics can be scraped by Prometheus at /metrics endpoint")
    print("and visualized in Grafana dashboards.")
    print()


def demo_real_time_alerting():
    """Demonstrate real-time alerting system."""
    print("=" * 70)
    print("REAL-TIME ALERTING SYSTEM")
    print("=" * 70)
    print()
    
    # Create monitor with alert thresholds
    monitor = EnergyMonitor(
        warning_threshold=1.15,
        critical_threshold=1.30,
        alert_cooldown=0.0,  # Disable for demo
    )
    
    # Register alert callback
    alerts_received = []
    
    def alert_handler(alert):
        """Handle energy alerts."""
        alerts_received.append(alert)
        
        severity_emoji = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.CRITICAL: "🚨",
        }
        
        print(f"  {severity_emoji[alert.severity]} ALERT TRIGGERED!")
        print(f"     Severity: {alert.severity.value.upper()}")
        print(f"     Message: {alert.message}")
        print(f"     Energy: {alert.free_energy:.6f}")
        print(f"     Threshold: {alert.threshold:.6f}")
        print()
    
    monitor.register_alert_callback(alert_handler)
    
    model = EnergyModel()
    
    # Simulate escalating load
    scenarios = [
        ("Normal operation", 0.3),
        ("Moderate load", 0.6),
        ("Warning level", 0.8),
        ("Critical level", 1.1),
        ("Recovery", 0.5),
    ]
    
    print("Simulating system load scenarios:")
    print()
    
    for scenario_name, load in scenarios:
        metrics = create_metrics_for_load(load)
        result = model.evaluate(metrics, max_free_energy=1.5)
        
        print(f"{scenario_name}:")
        print(f"  Energy: {result.free_energy:.6f}")
        print(f"  Status: {'PASS' if result.passed else 'FAIL'}")
        
        # Record and check for alerts
        monitor.record_validation(result, metrics, duration_seconds=0.05)
        print()
    
    # Summary
    print("Alert Summary:")
    print(f"  Total alerts generated: {len(alerts_received)}")
    
    by_severity = {}
    for alert in alerts_received:
        severity = alert.severity.value
        by_severity[severity] = by_severity.get(severity, 0) + 1
    
    for severity, count in by_severity.items():
        print(f"  {severity.upper()}: {count}")
    print()


def demo_comprehensive_reporting():
    """Demonstrate comprehensive report generation."""
    print("=" * 70)
    print("COMPREHENSIVE REPORTING")
    print("=" * 70)
    print()
    
    model = EnergyModel()
    
    # Generate validation results
    results = []
    load_factors = [0.2, 0.4, 0.5, 0.7, 0.9, 1.2, 0.6, 0.4, 0.3, 0.5]
    
    for load in load_factors:
        metrics = create_metrics_for_load(load)
        result = model.evaluate(metrics, max_free_energy=1.3)
        results.append(result)
    
    # Generate text summary
    print("TEXT SUMMARY REPORT:")
    print()
    summary = EnergyReporter.format_summary(
        results,
        title="Daily Energy Validation Report"
    )
    print(summary)
    
    # Generate JSON export
    print("\nJSON EXPORT (sample):")
    print("-" * 70)
    json_report = EnergyReporter.export_json(results[:3], include_penalties=True)
    print(json_report)
    print("-" * 70)
    print()


def demo_production_integration():
    """Demonstrate production integration patterns."""
    print("=" * 70)
    print("PRODUCTION INTEGRATION PATTERNS")
    print("=" * 70)
    print()
    
    print("Example 1: FastAPI Metrics Endpoint")
    print("-" * 70)
    print("""
from fastapi import FastAPI
from tacl import EnergyMonitor

app = FastAPI()
monitor = EnergyMonitor()

@app.get("/metrics")
async def metrics():
    '''Prometheus metrics endpoint'''
    return monitor.get_prometheus_metrics()

@app.get("/health")
async def health():
    '''Health check with energy status'''
    recent_alerts = monitor.get_recent_alerts(limit=1)
    
    if recent_alerts and recent_alerts[0].severity == AlertSeverity.CRITICAL:
        return {"status": "unhealthy", "reason": "critical energy level"}
    
    return {"status": "healthy"}

@app.get("/alerts")
async def get_alerts():
    '''Get recent energy alerts'''
    alerts = monitor.get_recent_alerts(limit=10)
    return {"alerts": [a.to_dict() for a in alerts]}
    """)
    print("-" * 70)
    print()
    
    print("Example 2: CI/CD Integration")
    print("-" * 70)
    print("""
# .github/workflows/energy-validation.yml

- name: Enhanced Energy Validation
  run: |
    python -c "
    from tacl import EnergyValidator, EnergyMonitor, EnergyReporter
    from tacl import load_scenarios
    
    scenarios = load_scenarios()
    validator = EnergyValidator(max_free_energy=1.35)
    monitor = EnergyMonitor(critical_threshold=1.35)
    
    results = []
    for name, metrics in scenarios.items():
        result = validator.evaluate(metrics)
        monitor.record_validation(result, metrics, duration_seconds=0.1)
        results.append(result)
    
    # Generate reports
    print(EnergyReporter.format_summary(results))
    
    # Save artifacts
    with open('.ci_artifacts/metrics.txt', 'w') as f:
        f.write(monitor.get_prometheus_metrics())
    
    # Fail if critical alerts
    if any(a.severity == AlertSeverity.CRITICAL 
           for a in monitor.get_recent_alerts()):
        exit(1)
    "
    """)
    print("-" * 70)
    print()
    
    print("Example 3: Grafana Dashboard Query")
    print("-" * 70)
    print("""
# Panel 1: Free Energy Gauge
tradepulse_energy_free_energy{environment="production"}

# Panel 2: Validation Failure Rate
rate(tradepulse_energy_validation_failures[5m])

# Panel 3: Energy Trend
avg_over_time(tradepulse_energy_free_energy[1h])

# Alert Rule: High Energy
tradepulse_energy_free_energy > 1.3
    """)
    print("-" * 70)
    print()


def demo_monitoring_lifecycle():
    """Demonstrate complete monitoring lifecycle."""
    print("=" * 70)
    print("MONITORING LIFECYCLE DEMONSTRATION")
    print("=" * 70)
    print()
    
    # Initialize monitoring
    monitor = EnergyMonitor(
        warning_threshold=1.2,
        critical_threshold=1.35,
    )
    
    model = EnergyModel(track_history=True)
    
    print("Phase 1: System Startup")
    for i in range(3):
        metrics = create_metrics_for_load(0.2)
        result = model.evaluate(metrics, max_free_energy=1.4)
        monitor.record_validation(result, metrics, duration_seconds=0.05)
    
    print(f"  Recorded {len(monitor._prometheus._metrics)} metric types")
    print()
    
    print("Phase 2: Normal Operation")
    for i in range(5):
        metrics = create_metrics_for_load(0.4 + i * 0.1)
        result = model.evaluate(metrics, max_free_energy=1.4)
        monitor.record_validation(result, metrics, duration_seconds=0.05)
    
    alerts = monitor.get_recent_alerts()
    print(f"  Alerts generated: {len(alerts)}")
    print()
    
    print("Phase 3: Export Metrics")
    output = monitor.get_prometheus_metrics()
    lines = output.strip().split('\n')
    print(f"  Exported {len(lines)} lines of metrics")
    print(f"  Sample metrics:")
    for line in lines[:5]:
        if not line.startswith('#'):
            print(f"    {line}")
    print()
    
    print("Phase 4: Generate Report")
    # Get model statistics
    stats = model.get_statistics()
    print(f"  Total validations: {int(stats['validation_count'])}")
    if 'mean_energy' in stats:
        print(f"  Mean energy: {stats['mean_energy']:.6f}")
        print(f"  Energy range: [{stats['min_energy']:.6f}, {stats['max_energy']:.6f}]")
    print()
    
    print("Phase 5: Cleanup")
    monitor.clear_alerts()
    model.clear_cache()
    model.reset_history()
    print("  Monitoring state reset")
    print()


def main():
    """Run all demonstrations."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " ENERGY MONITORING & OBSERVABILITY DEMONSTRATION ".center(68) + "║")
    print("╚" + "═" * 68 + "╝")
    print()
    
    demo_prometheus_metrics()
    demo_real_time_alerting()
    demo_comprehensive_reporting()
    demo_production_integration()
    demo_monitoring_lifecycle()
    
    print("=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()
    print("The energy monitoring module provides production-grade observability")
    print("with Prometheus integration, real-time alerting, and comprehensive")
    print("reporting for thermodynamic system management.")
    print()


if __name__ == "__main__":
    main()
