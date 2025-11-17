#!/usr/bin/env python3
"""
Energy Validation CLI Tool

Command-line tool for validating thermodynamic energy metrics against TACL thresholds.
Used in CI/CD pipelines and operational validation.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List

from runtime.energy_validator import EnergyConfig, EnergyValidator


def load_metrics_from_json(path: Path) -> List[Dict[str, float]]:
    """Load metrics from JSON file.

    Expected format:
    {
        "metrics": [
            {"latency_p95": 75.0, "latency_p99": 95.0, ...},
            {"latency_p95": 76.0, "latency_p99": 96.0, ...}
        ]
    }
    """
    with path.open("r") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif "metrics" in data:
        return data["metrics"]
    else:
        raise ValueError(
            "Invalid JSON format: expected list or dict with 'metrics' key"
        )


def validate_single_metric_set(
    validator: EnergyValidator, metrics: Dict[str, float], verbose: bool = False
) -> bool:
    """Validate a single set of metrics."""
    result = validator.compute_free_energy(metrics)

    if verbose:
        print(f"  Free Energy: {result.free_energy:.6f}")
        print(f"  Internal Energy: {result.internal_energy:.6f}")
        print(f"  Stability: {result.stability:.6f}")
        print(f"  Threshold: {result.threshold:.6f}")
        print(f"  Margin: {result.margin:+.6f}")

        if not result.passed:
            print("  ⚠️  FAILED: Free energy exceeds threshold")
            print("  Violations:")
            for name, penalty in result.penalties.items():
                if penalty > 0:
                    metric_config = validator.config.get_metric(name)
                    metric_value = metrics.get(name, 0)
                    print(
                        f"    - {name}: {metric_value:.3f} > {metric_config.threshold:.3f}"
                    )

    return result.passed


def main():
    parser = argparse.ArgumentParser(
        description="Validate thermodynamic energy metrics against TACL thresholds"
    )

    parser.add_argument(
        "metrics_file",
        type=Path,
        nargs="?",
        help="JSON file containing metrics to validate",
    )

    parser.add_argument(
        "--config", type=Path, help="Custom energy configuration YAML file"
    )

    parser.add_argument(
        "--metric",
        "-m",
        action="append",
        help="Individual metric in format name=value (can be used multiple times)",
    )

    parser.add_argument(
        "--output", "-o", type=Path, help="Output path for validation report JSON"
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit immediately on first validation failure",
    )

    parser.add_argument(
        "--show-config",
        action="store_true",
        help="Display current configuration and exit",
    )

    args = parser.parse_args()

    # Load configuration
    if args.config:
        if args.verbose:
            print(f"Loading configuration from {args.config}")
        from runtime.thermo_config import ThermoConfig

        thermo_config = ThermoConfig.from_yaml(args.config)
        config = EnergyConfig(
            control_temperature=thermo_config.control_temperature,
            max_acceptable_energy=thermo_config.max_acceptable_energy,
        )
    else:
        config = EnergyConfig()

    validator = EnergyValidator(config=config)

    # Show configuration if requested
    if args.show_config:
        print("Energy Validation Configuration:")
        print(f"  Control Temperature: {config.control_temperature}")
        print(f"  Max Acceptable Energy: {config.max_acceptable_energy}")
        print("\nMetric Thresholds:")
        for metric in config.metrics:
            print(
                f"  {metric.name:20s}: {metric.threshold:8.3f} {metric.unit:5s} (weight: {metric.weight:.1f})"
            )
        return 0

    # Collect metrics to validate
    metrics_list: List[Dict[str, float]] = []

    # From command-line arguments
    if args.metric:
        metrics = {}
        for metric_arg in args.metric:
            try:
                name, value = metric_arg.split("=")
                metrics[name.strip()] = float(value.strip())
            except ValueError:
                print(
                    f"Error: Invalid metric format '{metric_arg}'. Expected name=value"
                )
                return 1
        metrics_list.append(metrics)

    # From JSON file
    if args.metrics_file:
        try:
            file_metrics = load_metrics_from_json(args.metrics_file)
            metrics_list.extend(file_metrics)
        except Exception as e:
            print(f"Error loading metrics from {args.metrics_file}: {e}")
            return 1

    if not metrics_list:
        print("Error: No metrics to validate. Use --metric or provide a metrics file.")
        parser.print_help()
        return 1

    # Validate metrics
    if args.verbose:
        print(f"\nValidating {len(metrics_list)} metric set(s)...\n")

    all_passed = True
    failed_count = 0

    for i, metrics in enumerate(metrics_list):
        if args.verbose and len(metrics_list) > 1:
            print(f"Validation {i+1}/{len(metrics_list)}:")

        passed = validate_single_metric_set(validator, metrics, args.verbose)

        if not passed:
            all_passed = False
            failed_count += 1
            if args.fail_fast:
                print("\n❌ Validation failed (fail-fast enabled)")
                break

        if args.verbose and len(metrics_list) > 1:
            status = "✓ PASS" if passed else "✗ FAIL"
            print(f"  Result: {status}\n")

    # Export report if requested
    if args.output:
        validator.export_validation_report(args.output)
        if args.verbose:
            print(f"Validation report exported to {args.output}")

    # Summary
    passed_count = len(validator.validation_history) - failed_count

    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    print(f"Total validations: {len(validator.validation_history)}")
    print(f"Passed: {passed_count} ✓")
    print(f"Failed: {failed_count} ✗")

    if all_passed:
        print("\n✅ All validations PASSED")
        return 0
    else:
        print("\n❌ Some validations FAILED")
        print(f"\nFree energy threshold: {config.max_acceptable_energy:.2f}")
        print("Review the validation report for details.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
