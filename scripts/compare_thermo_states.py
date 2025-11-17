#!/usr/bin/env python3
"""
Compare Thermodynamic States

Compares two thermodynamic state snapshots (e.g., pre/post maintenance)
to identify changes and verify system stability.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


def load_state(path: Path) -> Dict[str, Any]:
    """Load state from JSON file."""
    with path.open('r') as f:
        return json.load(f)


def compare_free_energy(state1: Dict[str, Any], state2: Dict[str, Any]) -> Dict[str, Any]:
    """Compare free energy between states."""
    F1 = state1.get('current_F', 0)
    F2 = state2.get('current_F', 0)

    delta_F = F2 - F1
    percent_change = (delta_F / F1 * 100) if F1 != 0 else 0

    status = "improved" if delta_F < 0 else "degraded" if delta_F > 0 else "unchanged"

    return {
        "F_before": F1,
        "F_after": F2,
        "delta_F": delta_F,
        "percent_change": percent_change,
        "status": status,
    }


def compare_derivatives(state1: Dict[str, Any], state2: Dict[str, Any]) -> Dict[str, Any]:
    """Compare energy derivatives."""
    dFdt1 = state1.get('dF_dt', 0)
    dFdt2 = state2.get('dF_dt', 0)

    return {
        "dF_dt_before": dFdt1,
        "dF_dt_after": dFdt2,
        "delta_dF_dt": dFdt2 - dFdt1,
    }


def compare_violations(state1: Dict[str, Any], state2: Dict[str, Any]) -> Dict[str, Any]:
    """Compare violation counts."""
    v1 = state1.get('violations_total', 0)
    v2 = state2.get('violations_total', 0)

    return {
        "violations_before": v1,
        "violations_after": v2,
        "new_violations": max(0, v2 - v1),
    }


def compare_circuit_breaker(state1: Dict[str, Any], state2: Dict[str, Any]) -> Dict[str, Any]:
    """Compare circuit breaker states."""
    cb1 = state1.get('crisis_mode', 'normal')
    cb2 = state2.get('crisis_mode', 'normal')

    status_changed = cb1 != cb2

    return {
        "mode_before": cb1,
        "mode_after": cb2,
        "status_changed": status_changed,
        "severity": "critical" if "CRITICAL" in cb2 else "warning" if cb2 != "normal" else "ok",
    }


def generate_comparison_report(
    comparison: Dict[str, Any],
    state1_path: Path,
    state2_path: Path
) -> None:
    """Generate comparison report."""
    print("\n" + "=" * 70)
    print("THERMODYNAMIC STATE COMPARISON")
    print("=" * 70)
    print(f"\nBefore: {state1_path.name}")
    print(f"After:  {state2_path.name}")

    # Free Energy
    fe_comp = comparison.get('free_energy', {})
    print("\n## Free Energy")
    print(f"  Before:        {fe_comp['F_before']:.6f}")
    print(f"  After:         {fe_comp['F_after']:.6f}")
    print(f"  Change:        {fe_comp['delta_F']:+.6f} ({fe_comp['percent_change']:+.2f}%)")
    print(f"  Status:        {fe_comp['status'].upper()}")

    # Derivative
    deriv_comp = comparison.get('derivative', {})
    print("\n## Energy Derivative")
    print(f"  Before:        {deriv_comp['dF_dt_before']:+.6f}")
    print(f"  After:         {deriv_comp['dF_dt_after']:+.6f}")
    print(f"  Change:        {deriv_comp['delta_dF_dt']:+.6f}")

    # Violations
    viol_comp = comparison.get('violations', {})
    print("\n## Violations")
    print(f"  Before:        {viol_comp['violations_before']}")
    print(f"  After:         {viol_comp['violations_after']}")
    print(f"  New Violations: {viol_comp['new_violations']}")

    # Circuit Breaker
    cb_comp = comparison.get('circuit_breaker', {})
    print("\n## System Mode")
    print(f"  Before:        {cb_comp['mode_before']}")
    print(f"  After:         {cb_comp['mode_after']}")
    print(f"  Changed:       {'YES' if cb_comp['status_changed'] else 'NO'}")
    print(f"  Severity:      {cb_comp['severity'].upper()}")

    # Overall Assessment
    print("\n## Overall Assessment")

    issues = []
    if fe_comp['status'] == 'degraded' and abs(fe_comp['percent_change']) > 10:
        issues.append(f"⚠️  Free energy increased by {fe_comp['percent_change']:.1f}%")

    if viol_comp['new_violations'] > 0:
        issues.append(f"⚠️  {viol_comp['new_violations']} new violations detected")

    if cb_comp['severity'] == 'critical':
        issues.append("⚠️  System in CRITICAL mode")

    if fe_comp['F_after'] > 1.35:
        issues.append(f"❌ Free energy ({fe_comp['F_after']:.4f}) exceeds threshold (1.35)")

    if issues:
        print("  Status: ⚠️  ISSUES DETECTED")
        for issue in issues:
            print(f"    {issue}")
    else:
        print("  Status: ✓ STABLE")
        if fe_comp['status'] == 'improved':
            print(f"    ✓ Free energy improved by {abs(fe_comp['percent_change']):.1f}%")
        print("    ✓ No new violations")
        print("    ✓ System stable")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Compare two thermodynamic state snapshots"
    )

    parser.add_argument(
        "state1",
        type=Path,
        help="First state file (baseline/before)"
    )

    parser.add_argument(
        "state2",
        type=Path,
        help="Second state file (current/after)"
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Output path for JSON comparison report"
    )

    args = parser.parse_args()

    # Load states
    try:
        state1 = load_state(args.state1)
        state2 = load_state(args.state2)
    except Exception as e:
        print(f"Error loading states: {e}")
        return 1

    # Perform comparison
    comparison = {
        "free_energy": compare_free_energy(state1, state2),
        "derivative": compare_derivatives(state1, state2),
        "violations": compare_violations(state1, state2),
        "circuit_breaker": compare_circuit_breaker(state1, state2),
    }

    # Generate report
    generate_comparison_report(comparison, args.state1, args.state2)

    # Export if requested
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('w') as f:
            json.dump(comparison, f, indent=2)
        print(f"\nComparison exported to: {args.output}")

    # Return exit code based on status
    fe_status = comparison['free_energy']['status']
    cb_severity = comparison['circuit_breaker']['severity']

    if cb_severity == 'critical' or fe_status == 'degraded':
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
