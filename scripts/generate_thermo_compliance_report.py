#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Generate Thermodynamics Compliance Report

Generates compliance reports for audit and regulatory purposes.
Analyzes audit logs and produces formatted reports.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


def load_audit_entries(
    log_path: Path, start_date: datetime, end_date: datetime
) -> List[Dict[str, Any]]:
    """Load audit log entries for the specified date range."""
    start_ts = start_date.timestamp()
    end_ts = end_date.timestamp()

    entries = []

    if not log_path.exists():
        print(f"Warning: Audit log not found at {log_path}")
        return entries

    with log_path.open("r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                ts = entry.get("ts", 0)
                if start_ts <= ts <= end_ts:
                    entries.append(entry)
            except json.JSONDecodeError:
                continue

    return entries


def analyze_compliance(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze entries for compliance metrics."""
    if not entries:
        return {
            "total_decisions": 0,
            "monotonic_violations": 0,
            "circuit_breaker_activations": 0,
            "manual_overrides": 0,
            "topology_mutations": 0,
            "avg_free_energy": 0,
            "max_free_energy": 0,
        }

    F_values = [e.get("F_new", 0) for e in entries]

    return {
        "total_decisions": len(entries),
        "monotonic_violations": sum(1 for e in entries if e.get("action") == "rejected"),
        "circuit_breaker_activations": sum(
            1 for e in entries if e.get("circuit_breaker_active", False)
        ),
        "manual_overrides": sum(1 for e in entries if e.get("manual_override", False)),
        "topology_mutations": sum(1 for e in entries if e.get("topology_changes", [])),
        "avg_free_energy": sum(F_values) / len(F_values) if F_values else 0,
        "max_free_energy": max(F_values) if F_values else 0,
        "energy_threshold_breaches": sum(1 for F in F_values if F > 1.35),
    }


def generate_text_report(
    analysis: Dict[str, Any],
    start_date: datetime,
    end_date: datetime,
    output_path: Path,
) -> None:
    """Generate text-based compliance report."""

    report_lines = [
        "=" * 70,
        "THERMODYNAMICS COMPLIANCE REPORT",
        "=" * 70,
        "",
        f"Report Period: {start_date.date()} to {end_date.date()}",
        f"Generated:     {datetime.now().isoformat()}",
        "",
        "=" * 70,
        "SYSTEM METRICS",
        "=" * 70,
        "",
        f"Total Control Decisions:        {analysis['total_decisions']:,}",
        f"Average Free Energy:            {analysis['avg_free_energy']:.6f}",
        f"Maximum Free Energy:            {analysis['max_free_energy']:.6f}",
        f"Energy Threshold (1.35):        {'COMPLIANT' if analysis['max_free_energy'] <= 1.35 else 'NON-COMPLIANT'}",
        "",
        "=" * 70,
        "SAFETY EVENTS",
        "=" * 70,
        "",
        f"Monotonic Violations:           {analysis['monotonic_violations']}",
        f"Circuit Breaker Activations:    {analysis['circuit_breaker_activations']}",
        f"Energy Threshold Breaches:      {analysis['energy_threshold_breaches']}",
        f"Manual Overrides:               {analysis['manual_overrides']}",
        "",
        "=" * 70,
        "TOPOLOGY CHANGES",
        "=" * 70,
        "",
        f"Total Topology Mutations:       {analysis['topology_mutations']}",
        "",
        "=" * 70,
        "COMPLIANCE STATUS",
        "=" * 70,
        "",
    ]

    # Determine compliance status
    compliance_issues = []

    if analysis["max_free_energy"] > 1.35:
        compliance_issues.append(
            f"❌ Maximum free energy ({analysis['max_free_energy']:.4f}) exceeded threshold (1.35)"
        )

    if analysis["energy_threshold_breaches"] > 0:
        compliance_issues.append(
            f"⚠️  {analysis['energy_threshold_breaches']} energy threshold breaches detected"
        )

    if analysis["monotonic_violations"] > len(entries) * 0.01:  # More than 1% violations
        compliance_issues.append(
            f"⚠️  High violation rate: {analysis['monotonic_violations']} violations"
        )

    if compliance_issues:
        report_lines.append("Status: ⚠️  NON-COMPLIANT\n")
        report_lines.append("Issues:")
        for issue in compliance_issues:
            report_lines.append(f"  {issue}")
    else:
        report_lines.append("Status: ✓ COMPLIANT\n")
        report_lines.append("All compliance criteria met:")
        report_lines.append(
            f"  ✓ Free energy within threshold (max: {analysis['max_free_energy']:.6f})"
        )
        report_lines.append(
            f"  ✓ Violation rate acceptable ({analysis['monotonic_violations']} violations)"
        )
        report_lines.append("  ✓ System operated within safety parameters")

    report_lines.extend(
        [
            "",
            "=" * 70,
            "AUDIT TRAIL",
            "=" * 70,
            "",
            "Complete audit trail available at:",
            "  /var/log/geosync/thermo_audit.jsonl",
            "",
            "Retention: 7 years (regulatory requirement)",
            "",
            "=" * 70,
        ]
    )

    report_text = "\n".join(report_lines)

    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        f.write(report_text)

    print(report_text)


def main():
    parser = argparse.ArgumentParser(description="Generate thermodynamics compliance report")

    parser.add_argument("--start", type=str, required=True, help="Start date (YYYY-MM-DD)")

    parser.add_argument("--end", type=str, required=True, help="End date (YYYY-MM-DD)")

    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path("/var/log/geosync/thermo_audit.jsonl"),
        help="Path to audit log file",
    )

    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        required=True,
        help="Output file path (.txt or .pdf)",
    )

    args = parser.parse_args()

    # Parse dates
    try:
        start_date = datetime.fromisoformat(args.start)
        end_date = datetime.fromisoformat(args.end)
    except ValueError as e:
        print(f"Error parsing dates: {e}")
        print("Use format: YYYY-MM-DD")
        return 1

    # Load audit entries
    print(f"Loading audit entries from {start_date.date()} to {end_date.date()}...")
    global entries
    entries = load_audit_entries(args.log_path, start_date, end_date)

    if not entries:
        print("No audit entries found for the specified period.")
        return 1

    print(f"Loaded {len(entries)} audit entries")

    # Analyze compliance
    analysis = analyze_compliance(entries)

    # Generate report
    if args.output.suffix == ".txt":
        generate_text_report(analysis, start_date, end_date, args.output)
        print(f"\nCompliance report generated: {args.output}")
    elif args.output.suffix == ".pdf":
        # For PDF, first generate text then note that PDF requires additional library
        txt_path = args.output.with_suffix(".txt")
        generate_text_report(analysis, start_date, end_date, txt_path)
        print(f"\nText report generated: {txt_path}")
        print("\nNote: PDF generation requires reportlab library.")
        print("Install with: pip install reportlab")
        print("For now, use the .txt report or convert manually.")
    else:
        print(f"Error: Unsupported output format '{args.output.suffix}'. Use .txt or .pdf")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
