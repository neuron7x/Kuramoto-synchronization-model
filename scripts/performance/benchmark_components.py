#!/usr/bin/env python3
"""Component performance benchmarking runner.

Benchmarks critical components (order_router, link_activator, thermo_validator)
and validates against performance budgets with percentile tracking.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml


@dataclass
class PercentileMetrics:
    """Performance metrics with percentile analysis."""
    
    p50: float
    p95: float
    p99: float
    mean: float
    std: float
    min: float
    max: float
    samples: int
    
    @classmethod
    def from_timings(cls, timings: List[float]) -> PercentileMetrics:
        """Calculate percentile metrics from raw timing samples."""
        if not timings:
            raise ValueError("Cannot calculate metrics from empty timings")
        
        sorted_timings = sorted(timings)
        n = len(sorted_timings)
        
        def percentile(data: List[float], p: float) -> float:
            """Calculate percentile using linear interpolation."""
            idx = (n - 1) * p
            lower = int(idx)
            upper = lower + 1
            weight = idx - lower
            
            if upper >= n:
                return data[-1]
            return data[lower] * (1 - weight) + data[upper] * weight
        
        return cls(
            p50=percentile(sorted_timings, 0.50),
            p95=percentile(sorted_timings, 0.95),
            p99=percentile(sorted_timings, 0.99),
            mean=statistics.mean(timings),
            std=statistics.stdev(timings) if n > 1 else 0.0,
            min=min(timings),
            max=max(timings),
            samples=n,
        )


@dataclass
class BenchmarkResult:
    """Result of component benchmark."""
    
    component: str
    metrics: PercentileMetrics
    budget_p50: float
    budget_p95: float
    budget_p99: float
    passed: bool
    violations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "component": self.component,
            "metrics": {
                "p50_ms": self.metrics.p50 * 1000,
                "p95_ms": self.metrics.p95 * 1000,
                "p99_ms": self.metrics.p99 * 1000,
                "mean_ms": self.metrics.mean * 1000,
                "std_ms": self.metrics.std * 1000,
                "min_ms": self.metrics.min * 1000,
                "max_ms": self.metrics.max * 1000,
                "samples": self.metrics.samples,
            },
            "budgets": {
                "p50_ms": self.budget_p50,
                "p95_ms": self.budget_p95,
                "p99_ms": self.budget_p99,
            },
            "passed": self.passed,
            "violations": self.violations,
        }


def load_budgets(config_path: Path) -> Dict[str, Any]:
    """Load performance budgets from YAML configuration."""
    with open(config_path) as f:
        config = yaml.safe_load(f)
    return config.get("components", {})


def benchmark_function(
    func: Callable[[], Any],
    iterations: int = 100,
    warmup: int = 10,
) -> List[float]:
    """Benchmark a function with warmup and return timing samples."""
    # Warmup
    for _ in range(warmup):
        func()
    
    # Actual benchmarking
    timings = []
    for _ in range(iterations):
        start = time.perf_counter()
        func()
        end = time.perf_counter()
        timings.append(end - start)
    
    return timings


def benchmark_order_router() -> List[float]:
    """Benchmark order_router component."""
    # Import locally to avoid startup overhead
    from execution.router import SlippageModel, OrderStateNormalizer
    from domain import Order, OrderSide, OrderType
    
    def workload():
        """Representative workload for order router."""
        order = Order(
            symbol="BTC-USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            price=50000.0,
        )
        
        slippage = SlippageModel(max_slippage_bps=5.0, limit_buffer_bps=10.0)
        adjusted = slippage.apply(order)
        
        normalizer = OrderStateNormalizer()
        _ = normalizer.normalize(adjusted)
    
    return benchmark_function(workload, iterations=100, warmup=10)


def benchmark_link_activator() -> List[float]:
    """Benchmark link_activator component."""
    from runtime.link_activator import LinkActivator
    
    activator = LinkActivator(enable_rdma=True, enable_crdt=True)
    
    bond_types = ["metallic", "ionic", "covalent", "hydrogen", "vdw"]
    
    def workload():
        """Representative workload for link activator."""
        for bond_type in bond_types:
            activator.apply(
                bond_type=bond_type,
                src="node_a",
                dst="node_b",
                metadata={"test": True},
            )
    
    return benchmark_function(workload, iterations=100, warmup=10)


def benchmark_thermo_validator() -> List[float]:
    """Benchmark thermo_validator component."""
    from core.energy import bond_internal_energy, delta_free_energy, BondType
    
    def workload():
        """Representative workload for thermodynamic validation."""
        # Simulate bond energy calculations
        for bond_type in ["covalent", "ionic", "metallic"]:
            _ = bond_internal_energy(bond_type, strength=0.5)
        
        # Simulate free energy delta
        _ = delta_free_energy(
            bond_counts_before={"covalent": 10, "ionic": 5},
            bond_counts_after={"covalent": 9, "ionic": 6},
        )
    
    return benchmark_function(workload, iterations=100, warmup=10)


def validate_against_budget(
    component: str,
    metrics: PercentileMetrics,
    budget: Dict[str, Any],
) -> BenchmarkResult:
    """Validate metrics against budget and return result."""
    percentiles = budget.get("percentiles", {})
    stability = budget.get("stability", {})
    
    budget_p50 = percentiles.get("p50_ms", float("inf"))
    budget_p95 = percentiles.get("p95_ms", float("inf"))
    budget_p99 = percentiles.get("p99_ms", float("inf"))
    
    violations = []
    
    # Check percentiles (convert to ms)
    p50_ms = metrics.p50 * 1000
    p95_ms = metrics.p95 * 1000
    p99_ms = metrics.p99 * 1000
    
    if p50_ms > budget_p50:
        violations.append(
            f"p50: {p50_ms:.2f}ms exceeds budget {budget_p50:.2f}ms "
            f"(+{(p50_ms - budget_p50):.2f}ms, {((p50_ms / budget_p50 - 1) * 100):.1f}%)"
        )
    
    if p95_ms > budget_p95:
        violations.append(
            f"p95: {p95_ms:.2f}ms exceeds budget {budget_p95:.2f}ms "
            f"(+{(p95_ms - budget_p95):.2f}ms, {((p95_ms / budget_p95 - 1) * 100):.1f}%)"
        )
    
    if p99_ms > budget_p99:
        violations.append(
            f"p99: {p99_ms:.2f}ms exceeds budget {budget_p99:.2f}ms "
            f"(+{(p99_ms - budget_p99):.2f}ms, {((p99_ms / budget_p99 - 1) * 100):.1f}%)"
        )
    
    # Check stability
    max_variance = stability.get("max_variance", 1.0)
    if metrics.samples > 1:
        coefficient_of_variation = metrics.std / metrics.mean if metrics.mean > 0 else 0
        if coefficient_of_variation > max_variance:
            violations.append(
                f"Stability: coefficient of variation {coefficient_of_variation:.3f} "
                f"exceeds threshold {max_variance:.3f}"
            )
    
    return BenchmarkResult(
        component=component,
        metrics=metrics,
        budget_p50=budget_p50,
        budget_p95=budget_p95,
        budget_p99=budget_p99,
        passed=len(violations) == 0,
        violations=violations,
    )


def run_benchmarks(
    config_path: Path,
    output_path: Optional[Path] = None,
) -> Dict[str, BenchmarkResult]:
    """Run all component benchmarks and validate against budgets."""
    budgets = load_budgets(config_path)
    
    benchmarks = {
        "order_router": benchmark_order_router,
        "link_activator": benchmark_link_activator,
        "thermo_validator": benchmark_thermo_validator,
    }
    
    results = {}
    
    for component, benchmark_func in benchmarks.items():
        print(f"Benchmarking {component}...", file=sys.stderr)
        
        try:
            timings = benchmark_func()
            metrics = PercentileMetrics.from_timings(timings)
            
            budget = budgets.get(component, {})
            result = validate_against_budget(component, metrics, budget)
            results[component] = result
            
            print(f"  ✓ {component}: p50={metrics.p50*1000:.2f}ms p95={metrics.p95*1000:.2f}ms p99={metrics.p99*1000:.2f}ms", file=sys.stderr)
        except Exception as e:
            print(f"  ✗ {component}: {e}", file=sys.stderr)
            raise
    
    if output_path:
        output_data = {
            comp: result.to_dict() for comp, result in results.items()
        }
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
    
    return results


def main() -> int:
    """Run benchmarks and report results."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Benchmark critical components")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/perf_budgets.yaml"),
        help="Path to performance budgets config",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Path to output JSON results",
    )
    parser.add_argument(
        "--fail-on-violation",
        action="store_true",
        help="Exit with non-zero code if any budget is violated",
    )
    
    args = parser.parse_args()
    
    try:
        results = run_benchmarks(args.config, args.output)
        
        # Print summary
        print("\n" + "=" * 70)
        print("PERFORMANCE BENCHMARK SUMMARY")
        print("=" * 70)
        
        all_passed = True
        for component, result in results.items():
            status = "✓ PASS" if result.passed else "✗ FAIL"
            print(f"\n{component}: {status}")
            print(f"  p50: {result.metrics.p50*1000:.2f}ms (budget: {result.budget_p50:.2f}ms)")
            print(f"  p95: {result.metrics.p95*1000:.2f}ms (budget: {result.budget_p95:.2f}ms)")
            print(f"  p99: {result.metrics.p99*1000:.2f}ms (budget: {result.budget_p99:.2f}ms)")
            
            if result.violations:
                all_passed = False
                print("\n  Violations:")
                for violation in result.violations:
                    print(f"    • {violation}")
        
        print("\n" + "=" * 70)
        
        if args.fail_on_violation and not all_passed:
            print("ERROR: Performance budget violations detected", file=sys.stderr)
            return 1
        
        return 0
    
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
