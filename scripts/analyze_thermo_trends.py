#!/usr/bin/env python3
"""
Thermodynamics Trend Analysis Tool

Analyzes historical thermodynamic metrics to identify trends and anomalies.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


def load_audit_log(log_path: Path, period_days: int = 7) -> List[Dict[str, Any]]:
    """Load audit log entries from the specified period."""
    cutoff_time = datetime.now().timestamp() - (period_days * 86400)
    entries = []

    if not log_path.exists():
        print(f"Warning: Audit log not found at {log_path}")
        return entries

    with log_path.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                if entry.get("ts", 0) >= cutoff_time:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    return entries


def analyze_free_energy_trend(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze free energy trends."""
    if not entries:
        return {"status": "no_data"}

    F_values = [e.get("F_new", 0) for e in entries]
    timestamps = [e.get("ts", 0) for e in entries]

    if not F_values:
        return {"status": "no_data"}

    # Basic statistics
    mean_F = np.mean(F_values)
    std_F = np.std(F_values)
    min_F = np.min(F_values)
    max_F = np.max(F_values)

    # Trend analysis (simple linear regression)
    if len(F_values) > 2:
        coeffs = np.polyfit(timestamps, F_values, 1)
        trend_slope = coeffs[0]
        trend_direction = "increasing" if trend_slope > 0 else "decreasing"
    else:
        trend_slope = 0
        trend_direction = "stable"

    # Count violations
    violations = sum(1 for F in F_values if F > 1.35)
    warning_count = sum(1 for F in F_values if 1.20 < F <= 1.35)

    return {
        "status": "ok",
        "mean": mean_F,
        "std": std_F,
        "min": min_F,
        "max": max_F,
        "trend_slope": trend_slope,
        "trend_direction": trend_direction,
        "violations": violations,
        "warnings": warning_count,
        "total_samples": len(F_values),
    }


def analyze_circuit_breaker_events(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze circuit breaker activations."""
    cb_active_count = sum(1 for e in entries if e.get("circuit_breaker_active", False))
    manual_overrides = sum(1 for e in entries if e.get("manual_override", False))

    return {
        "circuit_breaker_activations": cb_active_count,
        "manual_overrides": manual_overrides,
        "activation_rate": cb_active_count / len(entries) if entries else 0,
    }


def analyze_topology_changes(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze topology change patterns."""
    total_changes = 0
    bond_type_changes = {}

    for entry in entries:
        changes = entry.get("topology_changes", [])
        total_changes += len(changes)

        for change in changes:
            old_type = change.get("old", "unknown")
            new_type = change.get("new", "unknown")
            transition = f"{old_type}->{new_type}"
            bond_type_changes[transition] = bond_type_changes.get(transition, 0) + 1

    return {
        "total_changes": total_changes,
        "changes_per_hour": (total_changes / len(entries) * 3600) if entries else 0,
        "top_transitions": sorted(
            bond_type_changes.items(), key=lambda x: x[1], reverse=True
        )[:5],
    }


def generate_report(analysis: Dict[str, Any], output_path: Path = None) -> None:
    """Generate and display analysis report."""
    print("\n" + "=" * 70)
    print("THERMODYNAMICS TREND ANALYSIS REPORT")
    print("=" * 70)

    # Free Energy Trends
    fe_analysis = analysis.get("free_energy", {})
    if fe_analysis.get("status") == "ok":
        print("\n## Free Energy Analysis")
        print(f"  Mean F:       {fe_analysis['mean']:.6f}")
        print(f"  Std Dev:      {fe_analysis['std']:.6f}")
        print(f"  Min F:        {fe_analysis['min']:.6f}")
        print(f"  Max F:        {fe_analysis['max']:.6f}")
        print(
            f"  Trend:        {fe_analysis['trend_direction']} (slope: {fe_analysis['trend_slope']:.2e})"
        )
        print(f"  Violations:   {fe_analysis['violations']} (F > 1.35)")
        print(f"  Warnings:     {fe_analysis['warnings']} (1.20 < F ≤ 1.35)")
        print(f"  Total Samples: {fe_analysis['total_samples']}")
    else:
        print("\n## Free Energy Analysis: NO DATA")

    # Circuit Breaker
    cb_analysis = analysis.get("circuit_breaker", {})
    print("\n## Circuit Breaker Events")
    print(f"  Activations:     {cb_analysis.get('circuit_breaker_activations', 0)}")
    print(f"  Manual Overrides: {cb_analysis.get('manual_overrides', 0)}")
    print(f"  Activation Rate:  {cb_analysis.get('activation_rate', 0):.2%}")

    # Topology Changes
    topo_analysis = analysis.get("topology", {})
    print("\n## Topology Changes")
    print(f"  Total Changes:    {topo_analysis.get('total_changes', 0)}")
    print(f"  Changes/Hour:     {topo_analysis.get('changes_per_hour', 0):.2f}")

    top_transitions = topo_analysis.get("top_transitions", [])
    if top_transitions:
        print("\n  Top Bond Transitions:")
        for transition, count in top_transitions:
            print(f"    {transition:20s}: {count:4d}")

    print("\n" + "=" * 70)

    # Export if requested
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w") as f:
            json.dump(analysis, f, indent=2)
        print(f"\nFull analysis exported to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze thermodynamic trends from audit logs"
    )

    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path("/var/log/tradepulse/thermo_audit.jsonl"),
        help="Path to audit log file",
    )

    parser.add_argument(
        "--period", type=str, default="7d", help="Analysis period (e.g., 7d, 24h, 30d)"
    )

    parser.add_argument("--output", "-o", type=Path, help="Output path for JSON report")

    args = parser.parse_args()

    # Parse period
    period_str = args.period.lower()
    if period_str.endswith("d"):
        period_days = int(period_str[:-1])
    elif period_str.endswith("h"):
        period_days = int(period_str[:-1]) / 24
    else:
        print(
            f"Error: Invalid period format '{args.period}'. Use format like '7d' or '24h'"
        )
        return 1

    print(f"Loading audit log from: {args.log_path}")
    print(f"Analysis period: {period_days} days")

    entries = load_audit_log(args.log_path, int(period_days))

    if not entries:
        print("\nNo audit log entries found for the specified period.")
        return 1

    print(f"Loaded {len(entries)} entries")

    # Perform analysis
    analysis = {
        "generated_at": datetime.now().isoformat(),
        "period_days": period_days,
        "entry_count": len(entries),
        "free_energy": analyze_free_energy_trend(entries),
        "circuit_breaker": analyze_circuit_breaker_events(entries),
        "topology": analyze_topology_changes(entries),
    }

    # Generate report
    generate_report(analysis, args.output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
