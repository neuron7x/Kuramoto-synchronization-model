# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Energy Validation Example

Demonstrates how to use the EnergyValidator to validate system metrics
against TACL thermodynamic thresholds.
"""

from pathlib import Path

from runtime.energy_validator import EnergyConfig, EnergyValidator


def example_basic_validation():
    """Basic energy validation with default configuration."""
    print("=" * 80)
    print("Example 1: Basic Energy Validation")
    print("=" * 80)

    # Create validator with default configuration
    validator = EnergyValidator()

    # Example metrics (all below threshold - should pass)
    metrics_good = {
        "latency_p95": 75.0,  # Threshold: 85.0 ms
        "latency_p99": 100.0,  # Threshold: 120.0 ms
        "coherency_drift": 0.05,  # Threshold: 0.08
        "cpu_burn": 0.65,  # Threshold: 0.75
        "mem_cost": 5.5,  # Threshold: 6.5 GiB
        "queue_depth": 25.0,  # Threshold: 32.0
        "packet_loss": 0.003,  # Threshold: 0.005
    }

    result = validator.compute_free_energy(metrics_good)

    print("\nMetrics (all below threshold):")
    for name, value in metrics_good.items():
        metric_config = validator.config.get_metric(name)
        print(f"  {name:20s}: {value:8.3f} (threshold: {metric_config.threshold:.3f})")

    print("\nEnergy Computation:")
    print(f"  Internal Energy (U): {result.internal_energy:.6f}")
    print(f"  Stability (S):       {result.stability:.6f}")
    print(f"  Temperature (T):     {result.temperature:.6f}")
    print(f"  Free Energy (F):     {result.free_energy:.6f}")
    print(f"  Threshold:           {result.threshold:.6f}")
    print(f"  Margin:              {result.margin:.6f}")
    print(f"  Status:              {'PASS ✓' if result.passed else 'FAIL ✗'}")
    print()


def example_threshold_violation():
    """Example with metrics exceeding thresholds."""
    print("=" * 80)
    print("Example 2: Threshold Violation Detection")
    print("=" * 80)

    validator = EnergyValidator()

    # Metrics with violations (should fail)
    metrics_bad = {
        "latency_p95": 95.0,  # ABOVE threshold (85.0)
        "latency_p99": 130.0,  # ABOVE threshold (120.0)
        "coherency_drift": 0.05,  # Below threshold (OK)
        "cpu_burn": 0.80,  # ABOVE threshold (0.75)
        "mem_cost": 5.0,  # Below threshold (OK)
        "queue_depth": 35.0,  # ABOVE threshold (32.0)
        "packet_loss": 0.007,  # ABOVE threshold (0.005)
    }

    result = validator.compute_free_energy(metrics_bad)

    print("\nMetrics (some above threshold):")
    for name, value in metrics_bad.items():
        metric_config = validator.config.get_metric(name)
        threshold = metric_config.threshold
        status = "✗ VIOLATION" if value > threshold else "✓ OK"
        print(f"  {name:20s}: {value:8.3f} (threshold: {threshold:.3f}) {status}")

    print("\nPenalties:")
    for name, penalty in result.penalties.items():
        if penalty > 0:
            print(f"  {name:20s}: {penalty:.6f}")

    print("\nEnergy Computation:")
    print(f"  Internal Energy (U): {result.internal_energy:.6f}")
    print(f"  Stability (S):       {result.stability:.6f}")
    print(f"  Free Energy (F):     {result.free_energy:.6f}")
    print(f"  Threshold:           {result.threshold:.6f}")
    print(f"  Margin:              {result.margin:.6f}")
    print(f"  Status:              {'PASS ✓' if result.passed else 'FAIL ✗'}")
    print()


def example_time_series_validation():
    """Validate a time series of metrics."""
    print("=" * 80)
    print("Example 3: Time Series Validation")
    print("=" * 80)

    validator = EnergyValidator()

    # Simulate metrics getting progressively worse
    time_series = [
        {"latency_p95": 70.0, "latency_p99": 90.0, "cpu_burn": 0.60},
        {"latency_p95": 75.0, "latency_p99": 95.0, "cpu_burn": 0.65},
        {"latency_p95": 80.0, "latency_p99": 105.0, "cpu_burn": 0.70},
        {"latency_p95": 85.0, "latency_p99": 115.0, "cpu_burn": 0.75},
        {"latency_p95": 90.0, "latency_p99": 125.0, "cpu_burn": 0.80},
    ]

    print(f"\nValidating {len(time_series)} time steps:\n")
    print(f"{'Step':<6} {'F':<10} {'U':<10} {'S':<10} {'Status':<10}")
    print("-" * 50)

    for i, metrics in enumerate(time_series):
        # Fill in missing metrics with safe defaults
        full_metrics = {
            "latency_p95": metrics.get("latency_p95", 70.0),
            "latency_p99": metrics.get("latency_p99", 90.0),
            "coherency_drift": 0.05,
            "cpu_burn": metrics.get("cpu_burn", 0.60),
            "mem_cost": 5.0,
            "queue_depth": 20.0,
            "packet_loss": 0.002,
        }

        result = validator.compute_free_energy(full_metrics)
        status = "PASS ✓" if result.passed else "FAIL ✗"

        print(
            f"{i + 1:<6} {result.free_energy:<10.6f} {result.internal_energy:<10.6f} "
            f"{result.stability:<10.6f} {status:<10}"
        )

    print("\nSummary:")
    print(f"  Total validations: {len(validator.validation_history)}")
    passed = sum(1 for r in validator.validation_history if r.passed)
    failed = len(validator.validation_history) - passed
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print()


def example_export_report():
    """Export validation report to JSON."""
    print("=" * 80)
    print("Example 4: Export Validation Report")
    print("=" * 80)

    validator = EnergyValidator()

    # Run several validations
    test_cases = [
        {"name": "normal", "latency_p95": 70.0, "cpu_burn": 0.60},
        {"name": "elevated", "latency_p95": 85.0, "cpu_burn": 0.75},
        {"name": "critical", "latency_p95": 100.0, "cpu_burn": 0.85},
    ]

    for case in test_cases:
        metrics = {
            "latency_p95": case["latency_p95"],
            "latency_p99": case["latency_p95"] * 1.3,
            "coherency_drift": 0.05,
            "cpu_burn": case["cpu_burn"],
            "mem_cost": 5.0,
            "queue_depth": 20.0,
            "packet_loss": 0.002,
        }
        validator.compute_free_energy(metrics)
        print(f"  Validated scenario: {case['name']}")

    # Export report
    output_path = Path("/tmp/energy_validation_report.json")
    validator.export_validation_report(output_path)

    print(f"\nValidation report exported to: {output_path}")
    print(f"Report contains {len(validator.validation_history)} validation results")

    # Show report summary
    latest = validator.get_latest_result()
    if latest:
        print("\nLatest validation:")
        print(f"  Free Energy: {latest.free_energy:.6f}")
        print(f"  Status: {'PASS ✓' if latest.passed else 'FAIL ✗'}")
    print()


def example_custom_configuration():
    """Example with custom energy configuration."""
    print("=" * 80)
    print("Example 5: Custom Configuration")
    print("=" * 80)

    # Create custom configuration with stricter thresholds
    from runtime.energy_validator import MetricThreshold

    custom_config = EnergyConfig(
        control_temperature=0.70,  # Higher temperature
        max_acceptable_energy=1.20,  # Stricter threshold
        metrics=(
            MetricThreshold("latency_p95", "95th percentile latency", 75.0, 1.8, "ms"),
            MetricThreshold("latency_p99", "99th percentile latency", 110.0, 2.0, "ms"),
            MetricThreshold("cpu_burn", "CPU utilization", 0.70, 1.0, ""),
        ),
    )

    validator = EnergyValidator(config=custom_config)

    print("Custom Configuration:")
    print(f"  Control Temperature: {custom_config.control_temperature}")
    print(f"  Max Energy: {custom_config.max_acceptable_energy}")
    print(f"  Metrics: {len(custom_config.metrics)}")

    metrics = {
        "latency_p95": 72.0,
        "latency_p99": 105.0,
        "cpu_burn": 0.68,
    }

    result = validator.compute_free_energy(metrics)

    print("\nValidation Result:")
    print(f"  Free Energy: {result.free_energy:.6f}")
    print(f"  Threshold: {result.threshold:.6f}")
    print(f"  Status: {'PASS ✓' if result.passed else 'FAIL ✗'}")
    print()


def main():
    """Run all examples."""
    print("\n" + "=" * 80)
    print("TACL Energy Validation Examples")
    print("=" * 80 + "\n")

    example_basic_validation()
    example_threshold_violation()
    example_time_series_validation()
    example_export_report()
    example_custom_configuration()

    print("=" * 80)
    print("All examples completed successfully!")
    print("=" * 80)


if __name__ == "__main__":
    main()
