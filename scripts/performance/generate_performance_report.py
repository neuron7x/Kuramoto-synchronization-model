#!/usr/bin/env python3
"""Generate comprehensive performance report for PR comments.

This script creates a concise, well-formatted report summarizing benchmark
results, violations, trends, and flamegraph links for GitHub PR comments.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def format_metric(value: float, unit: str = "ms") -> str:
    """Format metric value with appropriate precision."""
    if value >= 100:
        return f"{value:.1f}{unit}"
    elif value >= 10:
        return f"{value:.2f}{unit}"
    else:
        return f"{value:.3f}{unit}"


def generate_summary_table(results: Dict[str, Any]) -> List[str]:
    """Generate summary table of benchmark results."""
    lines = [
        "| Component | p50 | p95 | p99 | Budget p50 | Budget p95 | Budget p99 | Status |",
        "|-----------|-----|-----|-----|------------|------------|------------|--------|",
    ]
    
    for component, result in results.items():
        metrics = result["metrics"]
        budgets = result["budgets"]
        passed = result["passed"]
        
        p50 = format_metric(metrics["p50_ms"])
        p95 = format_metric(metrics["p95_ms"])
        p99 = format_metric(metrics["p99_ms"])
        
        budget_p50 = format_metric(budgets["p50_ms"])
        budget_p95 = format_metric(budgets["p95_ms"])
        budget_p99 = format_metric(budgets["p99_ms"])
        
        status = "✅ PASS" if passed else "❌ FAIL"
        
        lines.append(
            f"| `{component}` | {p50} | {p95} | {p99} | "
            f"{budget_p50} | {budget_p95} | {budget_p99} | {status} |"
        )
    
    return lines


def generate_violations_section(results: Dict[str, Any]) -> List[str]:
    """Generate violations section if any exist."""
    lines = []
    has_violations = False
    
    for component, result in results.items():
        if result["violations"]:
            if not has_violations:
                lines.extend([
                    "",
                    "## ⚠️ Performance Budget Violations",
                    "",
                ])
                has_violations = True
            
            lines.append(f"### {component}")
            lines.append("")
            for violation in result["violations"]:
                lines.append(f"- {violation}")
            lines.append("")
    
    return lines


def generate_stability_section(results: Dict[str, Any]) -> List[str]:
    """Generate stability metrics section."""
    lines = [
        "",
        "## 📊 Stability Metrics",
        "",
        "| Component | Mean | Std Dev | CoV | Min | Max | Samples |",
        "|-----------|------|---------|-----|-----|-----|---------|",
    ]
    
    for component, result in results.items():
        metrics = result["metrics"]
        mean = format_metric(metrics["mean_ms"])
        std = format_metric(metrics["std_ms"])
        cov = metrics["std_ms"] / metrics["mean_ms"] if metrics["mean_ms"] > 0 else 0
        min_val = format_metric(metrics["min_ms"])
        max_val = format_metric(metrics["max_ms"])
        samples = metrics["samples"]
        
        lines.append(
            f"| `{component}` | {mean} | {std} | {cov:.3f} | "
            f"{min_val} | {max_val} | {samples} |"
        )
    
    return lines


def generate_trend_section(trend_report_path: Optional[Path]) -> List[str]:
    """Generate trend section from trend report."""
    if not trend_report_path or not trend_report_path.exists():
        return []
    
    with open(trend_report_path) as f:
        trend_content = f.read()
    
    # Extract just the component trends section
    lines = [
        "",
        "## 📈 Historical Trends",
        "",
    ]
    
    # Parse trend report and extract key info
    in_trends = False
    for line in trend_content.split("\n"):
        if "## Component Trends" in line:
            in_trends = True
            continue
        if in_trends:
            lines.append(line)
    
    return lines


def generate_artifacts_section(
    flamegraph_dir: Optional[Path],
    artifacts_url: Optional[str],
) -> List[str]:
    """Generate artifacts section."""
    lines = [
        "",
        "## 📁 Artifacts",
        "",
    ]
    
    if flamegraph_dir and flamegraph_dir.exists():
        flamegraphs = list(flamegraph_dir.glob("*_flamegraph.svg"))
        if flamegraphs:
            lines.append("### Flamegraphs")
            lines.append("")
            for fg in sorted(flamegraphs):
                component = fg.stem.replace("_flamegraph", "")
                lines.append(f"- `{component}`: {fg.name}")
            lines.append("")
    
    if artifacts_url:
        lines.append(f"📦 [Download all artifacts]({artifacts_url})")
        lines.append("")
    
    return lines


def generate_performance_report(
    benchmark_results_path: Path,
    output_path: Optional[Path] = None,
    trend_report_path: Optional[Path] = None,
    flamegraph_dir: Optional[Path] = None,
    artifacts_url: Optional[str] = None,
) -> str:
    """Generate complete performance report."""
    with open(benchmark_results_path) as f:
        results = json.load(f)
    
    # Determine overall status
    all_passed = all(result["passed"] for result in results.values())
    
    header_emoji = "✅" if all_passed else "❌"
    header_status = "All Checks Passed" if all_passed else "Performance Violations Detected"
    
    lines = [
        f"# {header_emoji} Performance Benchmark Report",
        "",
        f"**Status**: {header_status}",
        "",
        "## 📋 Summary",
        "",
    ]
    
    # Add summary table
    lines.extend(generate_summary_table(results))
    
    # Add violations if any
    lines.extend(generate_violations_section(results))
    
    # Add stability metrics
    lines.extend(generate_stability_section(results))
    
    # Add trend analysis
    lines.extend(generate_trend_section(trend_report_path))
    
    # Add artifacts section
    lines.extend(generate_artifacts_section(flamegraph_dir, artifacts_url))
    
    # Footer
    lines.extend([
        "",
        "---",
        "",
        "💡 **Performance budgets** are defined in `configs/perf_budgets.yaml`",
        "",
        "⚙️ **Benchmark details**: Run `python scripts/performance/benchmark_components.py --help`",
        "",
    ])
    
    report = "\n".join(lines)
    
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report)
        print(f"Generated report: {output_path}", file=sys.stderr)
    
    return report


def main() -> int:
    """Generate performance report."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate comprehensive performance report"
    )
    parser.add_argument(
        "--benchmark-results",
        type=Path,
        required=True,
        help="Path to benchmark results JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output markdown file",
    )
    parser.add_argument(
        "--trend-report",
        type=Path,
        help="Path to trend report markdown",
    )
    parser.add_argument(
        "--flamegraph-dir",
        type=Path,
        help="Directory containing flamegraphs",
    )
    parser.add_argument(
        "--artifacts-url",
        help="URL to GitHub Actions artifacts",
    )
    
    args = parser.parse_args()
    
    try:
        report = generate_performance_report(
            args.benchmark_results,
            args.output,
            args.trend_report,
            args.flamegraph_dir,
            args.artifacts_url,
        )
        
        if not args.output:
            print(report)
        
        return 0
    
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
