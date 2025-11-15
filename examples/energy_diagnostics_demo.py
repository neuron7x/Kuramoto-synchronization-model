#!/usr/bin/env python3
"""Demonstration of advanced energy diagnostics capabilities.

This script showcases the comprehensive diagnostic tools available in the
enhanced energy model, including trend analysis, anomaly detection, energy
breakdowns, budget tracking, and entropy decomposition.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tacl import (
    EnergyMetrics,
    EnergyModel,
    EnergyDiagnostics,
    EnergyBudget,
    EntropyDecomposition,
    DEFAULT_WEIGHTS,
    DEFAULT_THRESHOLDS,
)


def create_sample_metrics(base_latency: float) -> EnergyMetrics:
    """Create sample metrics with varying latency."""
    return EnergyMetrics(
        latency_p95=base_latency,
        latency_p99=base_latency * 1.4,
        coherency_drift=0.03 + (base_latency / 1000.0),
        cpu_burn=0.5 + (base_latency / 200.0),
        mem_cost=4.5 + (base_latency / 50.0),
        queue_depth=20.0 + (base_latency / 10.0),
        packet_loss=0.002 + (base_latency / 50000.0),
    )


def demo_trend_analysis():
    """Demonstrate energy trend analysis."""
    print("=" * 70)
    print("TREND ANALYSIS DEMONSTRATION")
    print("=" * 70)
    print()
    
    # Create model and diagnostics
    model = EnergyModel(track_history=True)
    diagnostics = EnergyDiagnostics(enable_forecasting=True)
    
    # Simulate increasing latency over time
    results = []
    latencies = [60, 65, 70, 75, 80, 85, 90, 95, 100, 105]
    
    for latency in latencies:
        metrics = create_sample_metrics(latency)
        free_energy, internal, entropy, penalties = model.free_energy(metrics)
        result = model.evaluate(metrics, max_free_energy=1.5)
        results.append(result)
    
    # Analyze trend
    trend = diagnostics.analyze_trend(results)
    
    print(f"Energy Statistics:")
    print(f"  Mean:     {trend.mean:.6f}")
    print(f"  Std Dev:  {trend.std:.6f}")
    print(f"  Min:      {trend.min:.6f}")
    print(f"  Max:      {trend.max:.6f}")
    print()
    
    print(f"Trend Analysis:")
    print(f"  Slope:    {trend.trend_slope:.6f}")
    print(f"  P-value:  {trend.trend_pvalue:.6f}")
    print(f"  Direction: {'INCREASING' if trend.is_increasing else 'DECREASING'}")
    print(f"  Statistically Significant: {trend.is_statistically_significant()}")
    print()
    
    if trend.forecast_next is not None:
        print(f"Forecast:")
        print(f"  Next value: {trend.forecast_next:.6f}")
    print()
    
    # Model statistics
    stats = model.get_statistics()
    print(f"Model Statistics:")
    print(f"  Validations: {int(stats['validation_count'])}")
    print(f"  History size: {int(stats['history_size'])}")
    if 'mean_energy' in stats:
        print(f"  Historical mean: {stats['mean_energy']:.6f}")
    print()


def demo_anomaly_detection():
    """Demonstrate anomaly detection."""
    print("=" * 70)
    print("ANOMALY DETECTION DEMONSTRATION")
    print("=" * 70)
    print()
    
    model = EnergyModel()
    diagnostics = EnergyDiagnostics()
    
    # Create normal results with one anomaly
    results = []
    latencies = [65, 70, 68, 72, 71, 150, 69, 73, 70, 71]  # 150 is anomaly
    
    for i, latency in enumerate(latencies):
        metrics = create_sample_metrics(latency)
        result = model.evaluate(metrics, max_free_energy=2.0)
        results.append(result)
        print(f"  Sample {i}: latency={latency:.0f}ms, energy={result.free_energy:.6f}")
    
    print()
    
    # Detect anomalies
    report = diagnostics.detect_anomalies(results, threshold=2.5)
    
    print(f"Anomaly Detection Results:")
    print(f"  Threshold: {report.threshold:.1f} std deviations")
    print(f"  Anomalies found: {report.anomaly_count}")
    print(f"  Anomaly rate: {report.anomaly_rate:.1%}")
    print()
    
    if report.has_anomalies():
        print(f"  Anomalous indices: {report.anomaly_indices}")
        print(f"  Z-scores at anomalies:")
        for idx in report.anomaly_indices:
            print(f"    Sample {idx}: z-score = {report.z_scores[idx]:.2f}")
    else:
        print("  No anomalies detected")
    print()


def demo_energy_breakdown():
    """Demonstrate detailed energy breakdown."""
    print("=" * 70)
    print("ENERGY BREAKDOWN DEMONSTRATION")
    print("=" * 70)
    print()
    
    model = EnergyModel()
    diagnostics = EnergyDiagnostics()
    
    # Create metrics with some violations
    metrics = EnergyMetrics(
        latency_p95=95.0,   # Over threshold
        latency_p99=140.0,  # Over threshold
        coherency_drift=0.06,
        cpu_burn=0.7,
        mem_cost=6.8,       # Over threshold
        queue_depth=28.0,
        packet_loss=0.004,
    )
    
    result = model.evaluate(metrics, max_free_energy=1.5)
    breakdown = diagnostics.create_breakdown(result, temperature=0.6)
    
    print(f"Energy Components:")
    print(f"  Total Free Energy:      {breakdown.total_free_energy:.6f}")
    print(f"  Internal Energy:        {breakdown.internal_energy:.6f}")
    print(f"  Entropy Contribution:   {breakdown.entropy_contribution:.6f}")
    print(f"  Temperature:            {breakdown.temperature:.6f}")
    print()
    
    print(f"Penalty Contributions (sorted by magnitude):")
    for metric, penalty in breakdown.get_sorted_penalties():
        if penalty > 0.001:
            indicator = "⚠️ " if penalty > 0.05 else "  "
            print(f"  {indicator}{metric:20s}: {penalty:.6f}")
    print()
    
    if breakdown.dominant_penalty:
        print(f"Dominant Penalty:")
        print(f"  Metric: {breakdown.dominant_penalty}")
        print(f"  Value:  {breakdown.dominant_penalty_value:.6f}")
    print()


def demo_budget_tracking():
    """Demonstrate energy budget tracking."""
    print("=" * 70)
    print("ENERGY BUDGET TRACKING DEMONSTRATION")
    print("=" * 70)
    print()
    
    budget = EnergyBudget(
        budget_limit=1.4,
        warning_threshold=0.8,
        critical_threshold=0.95,
    )
    
    model = EnergyModel()
    
    # Simulate increasing energy usage
    latencies = [60, 75, 85, 95, 105]
    
    print(f"Budget Configuration:")
    print(f"  Limit:              {budget.budget_limit:.2f}")
    print(f"  Warning threshold:  {budget.warning_threshold:.0%}")
    print(f"  Critical threshold: {budget.critical_threshold:.0%}")
    print()
    
    print("Simulating energy evolution:")
    for i, latency in enumerate(latencies):
        metrics = create_sample_metrics(latency)
        free_energy, _, _, _ = model.free_energy(metrics)
        budget.update(free_energy)
        
        status = "✓" if budget.alert_level() == "NORMAL" else "⚠️" if budget.alert_level() == "WARNING" else "🚨"
        print(f"  Step {i+1}: {status} Energy={free_energy:.6f}, "
              f"Utilization={budget.utilization():.1%}, "
              f"Alert={budget.alert_level()}, "
              f"Remaining={budget.remaining_budget():.6f}")
    
    print()


def demo_entropy_decomposition():
    """Demonstrate entropy decomposition."""
    print("=" * 70)
    print("ENTROPY DECOMPOSITION DEMONSTRATION")
    print("=" * 70)
    print()
    
    decomp = EntropyDecomposition(DEFAULT_WEIGHTS, DEFAULT_THRESHOLDS)
    
    # Create two scenarios: healthy and stressed
    scenarios = {
        "Healthy System": EnergyMetrics(
            latency_p95=55.0,
            latency_p99=75.0,
            coherency_drift=0.02,
            cpu_burn=0.45,
            mem_cost=4.0,
            queue_depth=15.0,
            packet_loss=0.001,
        ),
        "Stressed System": EnergyMetrics(
            latency_p95=95.0,
            latency_p99=130.0,
            coherency_drift=0.09,
            cpu_burn=0.82,
            mem_cost=7.2,
            queue_depth=38.0,
            packet_loss=0.008,
        ),
    }
    
    for scenario_name, metrics in scenarios.items():
        print(f"{scenario_name}:")
        print(f"  Stability Ranking:")
        
        ranking = decomp.get_stability_ranking(metrics)
        for metric, contribution in ranking[:5]:  # Top 5
            bar_length = int(contribution * 50)
            bar = "█" * bar_length
            print(f"    {metric:20s}: {contribution:.6f} {bar}")
        
        print()


def main():
    """Run all demonstrations."""
    print()
    print("╔" + "═" * 68 + "╗")
    print("║" + " ENERGY MODEL DIAGNOSTICS DEMONSTRATION ".center(68) + "║")
    print("╚" + "═" * 68 + "╝")
    print()
    
    demo_trend_analysis()
    demo_anomaly_detection()
    demo_energy_breakdown()
    demo_budget_tracking()
    demo_entropy_decomposition()
    
    print("=" * 70)
    print("DEMONSTRATION COMPLETE")
    print("=" * 70)
    print()
    print("The energy diagnostics module provides comprehensive tools for")
    print("understanding and managing system thermodynamic behavior.")
    print()


if __name__ == "__main__":
    main()
