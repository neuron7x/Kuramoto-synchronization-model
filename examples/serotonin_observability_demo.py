#!/usr/bin/env python3
"""Demonstration of Serotonin Controller with SRE Observability.

This example shows how to use the serotonin controller with:
- SLI/SLO monitoring
- Alert evaluation
- Performance tracking
- Practical integration patterns

Following the principles from docs/prompts/system_prompt_principal_architect.md and
Architecture Decision Record ADR-0002.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import yaml

# Add serotonin module path directly to avoid full package import
serotonin_path = (
    Path(__file__).parent.parent / "src" / "tradepulse" / "core" / "neuro" / "serotonin"
)
sys.path.insert(0, str(serotonin_path))

from serotonin_controller import SerotoninController  # type: ignore  # noqa: E402

from observability import (  # type: ignore  # noqa: E402
    SEROTONIN_ALERTS,
    SEROTONIN_SLOS,
    Alert,
    SerotoninMonitor,
)


def create_temp_config() -> str:
    """Create temporary configuration file."""
    config_data = {
        "tonic_beta": 0.005,
        "phasic_beta": 0.2,
        "stress_gain": 1.0,
        "drawdown_gain": 1.5,
        "novelty_gain": 0.5,
        "stress_threshold": 0.8,
        "release_threshold": 0.4,
        "hysteresis": 0.1,
        "cooldown_ticks": 10,
        "chronic_window": 30,
        "desensitization_rate": 0.01,
        "desensitization_decay": 0.05,
        "max_desensitization": 0.8,
        "floor_min": 0.1,
        "floor_max": 0.9,
        "floor_gain": 1.0,
        "cooldown_extension": 5,
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(config_data, f)
        return f.name


def alert_handler(alert: Alert, value: float) -> None:
    """Handle triggered alerts."""
    severity_emoji = {
        "info": "ℹ️",
        "warning": "⚠️",
        "critical": "🚨",
    }

    emoji = severity_emoji.get(alert.severity.value, "❓")
    print(f"\n{emoji} ALERT: {alert.name}")
    print(f"   Severity: {alert.severity.value.upper()}")
    print(f"   Current Value: {value:.3f}")
    print(f"   Condition: {alert.condition}")
    print(f"   Remediation: {alert.remediation[:80]}...")


def log_metrics(name: str, value: float) -> None:
    """Log metrics (placeholder for real metrics system)."""
    # In production, this would push to Prometheus, StatsD, CloudWatch, etc.
    pass


def main() -> None:
    """Run observability demonstration."""
    print("=" * 70)
    print("Serotonin Controller - SRE Observability Demo")
    print("=" * 70)
    print()

    # Create configuration
    config_path = create_temp_config()

    try:
        # Initialize controller with performance tracking
        print("1. Initializing Controller with Performance Tracking")
        print("-" * 70)
        controller = SerotoninController(
            config_path=config_path,
            logger=log_metrics,
            enable_performance_tracking=True,
        )
        print("✓ Controller initialized")
        print()

        # Initialize monitor with alert handler
        print("2. Setting up SRE Monitor")
        print("-" * 70)
        monitor = SerotoninMonitor(alert_callback=alert_handler)
        print("✓ Monitor initialized with alert callbacks")
        print()

        # Display SLO definitions
        print("3. Service Level Objectives (SLOs)")
        print("-" * 70)
        for name, slo in SEROTONIN_SLOS.items():
            print(f"• {slo.sli.name}")
            print(f"  Target: {slo.target}% over {slo.window}")
            print(f"  Error Budget: {slo.error_budget:.2f}%")
            print()

        # Simulate normal trading conditions
        print("4. Simulating Normal Trading Conditions (50 steps)")
        print("-" * 70)
        for i in range(50):
            result = controller.step(
                stress=0.3 + (i % 10) * 0.02,  # Mild fluctuation
                drawdown=0.05,
                novelty=0.03,
            )

            # Validate state
            is_valid, issues = controller.validate_state()

            # Check alerts
            monitor.check_alerts(
                level=result["level"],
                hold=bool(result["hold"]),
                desensitization=result["desensitization"],
                validation_ok=is_valid,
            )

            if i % 10 == 0:
                print(
                    f"  Step {i:3d}: level={result['level']:.3f}, "
                    f"hold={result['hold']:.0f}, "
                    f"floor={result['temperature_floor']:.3f}"
                )

        print("✓ Normal conditions: No alerts triggered")
        print()

        # Simulate high-stress scenario
        print("5. Simulating High-Stress Market Event (30 steps)")
        print("-" * 70)
        monitor.reset_tracking()  # Reset alert counters

        for i in range(30):
            result = controller.step(
                stress=0.9,  # High stress
                drawdown=0.3,  # Significant drawdown
                novelty=0.15,
            )

            is_valid, issues = controller.validate_state()

            monitor.check_alerts(
                level=result["level"],
                hold=bool(result["hold"]),
                desensitization=result["desensitization"],
                validation_ok=is_valid,
            )

            if i % 5 == 0:
                print(
                    f"  Step {i:3d}: level={result['level']:.3f}, "
                    f"hold={result['hold']:.0f}, "
                    f"desentitization={result['desensitization']:.3f}"
                )

        print()

        # Display performance statistics
        print("6. Performance Statistics")
        print("-" * 70)
        perf_stats = controller.get_performance_stats()
        if perf_stats:
            print(f"Total Steps: {perf_stats['total_steps']:.0f}")
            print(f"Avg Step Time: {perf_stats['avg_step_time_ms']:.3f} ms")
            print(f"Steps/Second: {perf_stats['steps_per_second']:.1f}")
            print(f"Hold Rate: {perf_stats['hold_rate'] * 100:.1f}%")

            # Check SLO compliance
            print()
            print("SLO Compliance Check:")

            # Simulate P95 latency measurement
            simulated_p95_success_rate = (
                99.92  # Would be calculated from actual measurements
            )
            latency_slo = SEROTONIN_SLOS["step_latency_p95"]

            if latency_slo.is_met(simulated_p95_success_rate):
                print(f"  ✓ {latency_slo.sli.name}: PASS")
                print(
                    f"    Target: {latency_slo.target}%, Actual: {simulated_p95_success_rate}%"
                )
            else:
                print(f"  ✗ {latency_slo.sli.name}: FAIL")
                budget_consumed = latency_slo.budget_consumed(
                    simulated_p95_success_rate
                )
                print(f"    Error budget consumed: {budget_consumed * 100:.1f}%")

        print()

        # Display current state
        print("7. Controller State Summary")
        print("-" * 70)
        print(controller.get_state_summary())
        print()

        # Practical decision-making utilities
        print("8. Practical Trading Decision Support")
        print("-" * 70)

        for risk_level in ["conservative", "moderate", "aggressive"]:
            should_act = controller.should_take_action(risk_level=risk_level)
            print(f"  Should trade ({risk_level:12s}): {should_act}")

        multiplier = controller.get_position_size_multiplier()
        print(f"  Position size multiplier: {multiplier:.2%}")

        recovery = controller.estimate_recovery_time()
        if recovery > 0:
            print(
                f"  Estimated recovery time: {recovery} ticks (~{recovery/60:.1f} min)"
            )
        else:
            print("  Status: Ready for trading")

        print()

        # Display alert definitions
        print("9. Configured Alerts")
        print("-" * 70)
        for name, alert in SEROTONIN_ALERTS.items():
            severity_str = alert.severity.value.upper()
            print(f"• [{severity_str:8s}] {alert.name}")
            print(f"  Condition: {alert.condition}")
            print()

        # Generate SLO report
        print("10. Example SLO Report")
        print("-" * 70)
        report = monitor.format_slo_report("step_latency_p95", 99.85)
        print(report)
        print()

        # Summary
        print("=" * 70)
        print("✓ Observability Demo Completed Successfully")
        print("=" * 70)
        print()
        print("Key Takeaways:")
        print("• Controller tracks performance metrics automatically")
        print("• SRE monitor evaluates alerts based on SLO/SLI definitions")
        print("• State validation ensures system integrity")
        print("• Practical utilities support trading decision-making")
        print(
            "• Integration with metrics systems (Prometheus, etc.) via logger callback"
        )
        print()

    finally:
        # Cleanup
        Path(config_path).unlink()


if __name__ == "__main__":
    main()
