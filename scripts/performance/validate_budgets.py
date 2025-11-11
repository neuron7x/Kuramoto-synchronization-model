#!/usr/bin/env python3
"""Validate performance budgets against benchmark results.

This script loads performance budgets from YAML configuration and validates
them against actual benchmark measurements. It checks percentile latencies,
throughput, stability metrics, and generates violation reports.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import yaml


@dataclass(slots=True)
class ComponentBudget:
    """Performance budget for a single component."""

    name: str
    description: str
    latency_p50_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_max_ms: float
    throughput_min_tps: float
    stability_coefficient_max: float
    error_rate_max_percent: float
    observed_p50_ms: float | None = None
    observed_p95_ms: float | None = None
    observed_p99_ms: float | None = None


@dataclass(slots=True)
class BenchmarkResult:
    """Benchmark measurement results for a component."""

    name: str
    latencies_ms: list[float]
    throughput_tps: float
    error_count: int
    total_count: int
    duration_s: float

    @property
    def latency_p50_ms(self) -> float:
        """Median latency."""
        return float(np.percentile(self.latencies_ms, 50)) if self.latencies_ms else 0.0

    @property
    def latency_p95_ms(self) -> float:
        """95th percentile latency."""
        return float(np.percentile(self.latencies_ms, 95)) if self.latencies_ms else 0.0

    @property
    def latency_p99_ms(self) -> float:
        """99th percentile latency."""
        return float(np.percentile(self.latencies_ms, 99)) if self.latencies_ms else 0.0

    @property
    def latency_max_ms(self) -> float:
        """Maximum latency."""
        return float(max(self.latencies_ms)) if self.latencies_ms else 0.0

    @property
    def stability_coefficient(self) -> float:
        """Coefficient of variation (std/mean)."""
        if not self.latencies_ms:
            return 0.0
        mean = np.mean(self.latencies_ms)
        if mean == 0:
            return 0.0
        std = np.std(self.latencies_ms)
        return float(std / mean)

    @property
    def error_rate_percent(self) -> float:
        """Error rate as percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.error_count / self.total_count) * 100.0


@dataclass(slots=True)
class BudgetViolation:
    """Record of a budget violation."""

    component: str
    metric: str
    budget_value: float
    actual_value: float
    difference_percent: float
    severity: str  # "critical", "high", "medium"


@dataclass(slots=True)
class ValidationResult:
    """Complete validation result."""

    passed: bool
    violations: list[BudgetViolation] = field(default_factory=list)
    components_checked: int = 0
    components_passed: int = 0
    timestamp: str = ""


def load_budgets(config_path: Path) -> dict[str, ComponentBudget]:
    """Load component budgets from YAML configuration."""
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    budgets = {}
    components = config.get("components", {})
    
    for name, component_config in components.items():
        budgets[name] = ComponentBudget(
            name=name,
            description=component_config.get("description", ""),
            latency_p50_ms=float(component_config.get("latency_p50_ms", 100.0)),
            latency_p95_ms=float(component_config.get("latency_p95_ms", 200.0)),
            latency_p99_ms=float(component_config.get("latency_p99_ms", 300.0)),
            latency_max_ms=float(component_config.get("latency_max_ms", 500.0)),
            throughput_min_tps=float(component_config.get("throughput_min_tps", 10.0)),
            stability_coefficient_max=float(
                component_config.get("stability_coefficient_max", 0.2)
            ),
            error_rate_max_percent=float(
                component_config.get("error_rate_max_percent", 1.0)
            ),
            observed_p50_ms=component_config.get("observed_p50_ms"),
            observed_p95_ms=component_config.get("observed_p95_ms"),
            observed_p99_ms=component_config.get("observed_p99_ms"),
        )

    return budgets


def load_benchmark_results(benchmarks_path: Path) -> dict[str, BenchmarkResult]:
    """Load benchmark results from JSON files."""
    results = {}
    
    # Look for benchmark JSON files
    if benchmarks_path.is_dir():
        for json_file in benchmarks_path.glob("*_bench.json"):
            component_name = json_file.stem.replace("_bench", "")
            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                    
                # Extract benchmark data (pytest-benchmark format)
                benchmarks = data.get("benchmarks", [])
                if not benchmarks:
                    continue
                    
                # Aggregate latencies from all benchmarks
                all_latencies = []
                total_errors = 0
                total_samples = 0
                total_duration = 0.0
                
                for bench in benchmarks:
                    stats = bench.get("stats", {})
                    # Convert seconds to milliseconds
                    if "data" in stats:
                        all_latencies.extend([t * 1000 for t in stats["data"]])
                    iterations = bench.get("stats", {}).get("iterations", 1)
                    total_samples += iterations
                    total_duration += stats.get("total", 0.0)
                
                if all_latencies:
                    throughput = total_samples / total_duration if total_duration > 0 else 0.0
                    results[component_name] = BenchmarkResult(
                        name=component_name,
                        latencies_ms=all_latencies,
                        throughput_tps=throughput,
                        error_count=total_errors,
                        total_count=total_samples,
                        duration_s=total_duration,
                    )
            except Exception as e:
                print(f"Warning: Failed to load benchmark {json_file}: {e}", file=sys.stderr)
                continue
    
    return results


def validate_component(
    budget: ComponentBudget, result: BenchmarkResult, strict: bool = False
) -> list[BudgetViolation]:
    """Validate a component's performance against its budget."""
    violations = []

    # Check p50 latency
    if result.latency_p50_ms > budget.latency_p50_ms:
        diff_pct = ((result.latency_p50_ms - budget.latency_p50_ms) / budget.latency_p50_ms) * 100
        violations.append(
            BudgetViolation(
                component=budget.name,
                metric="latency_p50_ms",
                budget_value=budget.latency_p50_ms,
                actual_value=result.latency_p50_ms,
                difference_percent=diff_pct,
                severity="high" if diff_pct > 20 else "medium",
            )
        )

    # Check p95 latency
    if result.latency_p95_ms > budget.latency_p95_ms:
        diff_pct = ((result.latency_p95_ms - budget.latency_p95_ms) / budget.latency_p95_ms) * 100
        violations.append(
            BudgetViolation(
                component=budget.name,
                metric="latency_p95_ms",
                budget_value=budget.latency_p95_ms,
                actual_value=result.latency_p95_ms,
                difference_percent=diff_pct,
                severity="critical" if diff_pct > 30 else "high",
            )
        )

    # Check p99 latency
    if result.latency_p99_ms > budget.latency_p99_ms:
        diff_pct = ((result.latency_p99_ms - budget.latency_p99_ms) / budget.latency_p99_ms) * 100
        violations.append(
            BudgetViolation(
                component=budget.name,
                metric="latency_p99_ms",
                budget_value=budget.latency_p99_ms,
                actual_value=result.latency_p99_ms,
                difference_percent=diff_pct,
                severity="critical" if diff_pct > 30 else "high",
            )
        )

    # Check max latency
    if result.latency_max_ms > budget.latency_max_ms:
        diff_pct = ((result.latency_max_ms - budget.latency_max_ms) / budget.latency_max_ms) * 100
        violations.append(
            BudgetViolation(
                component=budget.name,
                metric="latency_max_ms",
                budget_value=budget.latency_max_ms,
                actual_value=result.latency_max_ms,
                difference_percent=diff_pct,
                severity="high",
            )
        )

    # Check throughput
    if result.throughput_tps < budget.throughput_min_tps:
        diff_pct = ((budget.throughput_min_tps - result.throughput_tps) / budget.throughput_min_tps) * 100
        violations.append(
            BudgetViolation(
                component=budget.name,
                metric="throughput_min_tps",
                budget_value=budget.throughput_min_tps,
                actual_value=result.throughput_tps,
                difference_percent=diff_pct,
                severity="high" if diff_pct > 20 else "medium",
            )
        )

    # Check stability coefficient
    if result.stability_coefficient > budget.stability_coefficient_max:
        diff_pct = (
            (result.stability_coefficient - budget.stability_coefficient_max)
            / budget.stability_coefficient_max
        ) * 100
        violations.append(
            BudgetViolation(
                component=budget.name,
                metric="stability_coefficient",
                budget_value=budget.stability_coefficient_max,
                actual_value=result.stability_coefficient,
                difference_percent=diff_pct,
                severity="medium",
            )
        )

    # Check error rate
    if result.error_rate_percent > budget.error_rate_max_percent:
        diff_pct = (
            (result.error_rate_percent - budget.error_rate_max_percent)
            / max(budget.error_rate_max_percent, 0.01)
        ) * 100
        violations.append(
            BudgetViolation(
                component=budget.name,
                metric="error_rate_percent",
                budget_value=budget.error_rate_max_percent,
                actual_value=result.error_rate_percent,
                difference_percent=diff_pct,
                severity="critical",
            )
        )

    return violations


def validate_all(
    budgets: dict[str, ComponentBudget],
    results: dict[str, BenchmarkResult],
    strict: bool = False,
) -> ValidationResult:
    """Validate all components."""
    all_violations = []
    components_checked = 0
    components_passed = 0
    
    for component_name, budget in budgets.items():
        if component_name not in results:
            print(f"Warning: No benchmark results for {component_name}", file=sys.stderr)
            continue
            
        components_checked += 1
        result = results[component_name]
        violations = validate_component(budget, result, strict)
        
        if not violations:
            components_passed += 1
        else:
            all_violations.extend(violations)

    from datetime import datetime, timezone
    
    return ValidationResult(
        passed=len(all_violations) == 0,
        violations=all_violations,
        components_checked=components_checked,
        components_passed=components_passed,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


def export_validation(result: ValidationResult, output_path: Path) -> None:
    """Export validation results to JSON."""
    data = {
        "passed": result.passed,
        "timestamp": result.timestamp,
        "summary": {
            "components_checked": result.components_checked,
            "components_passed": result.components_passed,
            "total_violations": len(result.violations),
        },
        "violations": [
            {
                "component": v.component,
                "metric": v.metric,
                "budget_value": v.budget_value,
                "actual_value": v.actual_value,
                "difference_percent": v.difference_percent,
                "severity": v.severity,
            }
            for v in result.violations
        ],
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        required=True,
        help="Path to performance budgets YAML configuration",
    )
    parser.add_argument(
        "--benchmarks",
        type=Path,
        required=True,
        help="Path to directory containing benchmark JSON files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to output validation results JSON",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Enable strict validation mode",
    )
    
    args = parser.parse_args()
    
    # Load budgets and results
    print(f"Loading budgets from {args.config}")
    budgets = load_budgets(args.config)
    print(f"Loaded {len(budgets)} component budgets")
    
    print(f"Loading benchmark results from {args.benchmarks}")
    results = load_benchmark_results(args.benchmarks)
    print(f"Loaded {len(results)} benchmark results")
    
    # Validate
    print("Validating performance budgets...")
    validation = validate_all(budgets, results, args.strict)
    
    # Export results
    export_validation(validation, args.output)
    print(f"Validation results written to {args.output}")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"Validation Summary")
    print(f"{'='*60}")
    print(f"Components checked: {validation.components_checked}")
    print(f"Components passed:  {validation.components_passed}")
    print(f"Total violations:   {len(validation.violations)}")
    
    if validation.violations:
        print(f"\nViolations by severity:")
        critical = sum(1 for v in validation.violations if v.severity == "critical")
        high = sum(1 for v in validation.violations if v.severity == "high")
        medium = sum(1 for v in validation.violations if v.severity == "medium")
        print(f"  Critical: {critical}")
        print(f"  High:     {high}")
        print(f"  Medium:   {medium}")
    
    return 0 if validation.passed else 1


if __name__ == "__main__":
    sys.exit(main())
