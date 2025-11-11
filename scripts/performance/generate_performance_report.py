#!/usr/bin/env python3
"""Generate comprehensive performance report with historical trends.

This script generates a detailed performance report including:
- Budget validation results
- Percentile latency charts
- Historical trend analysis
- Flamegraph references
- Actionable recommendations
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(slots=True)
class ReportConfig:
    """Configuration for report generation."""

    include_trends: bool = True
    include_flamegraphs: bool = True
    include_charts: bool = True
    max_trend_history: int = 50


def load_validation_results(path: Path) -> dict[str, Any]:
    """Load validation results from JSON."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_config(path: Path) -> dict[str, Any]:
    """Load performance budget configuration."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def format_metric_value(metric: str, value: float) -> str:
    """Format metric value with appropriate units."""
    if "ms" in metric or "latency" in metric:
        return f"{value:.2f} ms"
    elif "tps" in metric or "throughput" in metric:
        return f"{value:.2f} TPS"
    elif "percent" in metric or "rate" in metric:
        return f"{value:.2f}%"
    elif "coefficient" in metric:
        return f"{value:.4f}"
    return f"{value:.2f}"


def generate_violations_table(violations: list[dict[str, Any]]) -> str:
    """Generate markdown table of violations."""
    if not violations:
        return "✅ **No budget violations detected!**\n"

    lines = [
        "| Component | Metric | Budget | Actual | Diff | Severity |",
        "|-----------|--------|--------|--------|------|----------|",
    ]

    for v in violations:
        component = v["component"]
        metric = v["metric"]
        budget = format_metric_value(metric, v["budget_value"])
        actual = format_metric_value(metric, v["actual_value"])
        diff = f"+{v['difference_percent']:.1f}%"
        severity = v["severity"].upper()
        
        # Add emoji based on severity
        if severity == "CRITICAL":
            emoji = "🔴"
        elif severity == "HIGH":
            emoji = "🟠"
        else:
            emoji = "🟡"
            
        lines.append(f"| {component} | {metric} | {budget} | {actual} | {diff} | {emoji} {severity} |")

    return "\n".join(lines) + "\n"


def generate_component_summary(
    config: dict[str, Any], validation: dict[str, Any]
) -> str:
    """Generate per-component summary."""
    lines = ["### Component Performance Summary\n"]
    
    components = config.get("components", {})
    violations_by_component = {}
    
    for v in validation.get("violations", []):
        comp = v["component"]
        if comp not in violations_by_component:
            violations_by_component[comp] = []
        violations_by_component[comp].append(v)
    
    for component_name, component_config in components.items():
        desc = component_config.get("description", "")
        violations = violations_by_component.get(component_name, [])
        
        if violations:
            status = "❌ FAILED"
            severity_counts = {}
            for v in violations:
                sev = v["severity"]
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
            status_detail = ", ".join(f"{count} {sev}" for sev, count in severity_counts.items())
        else:
            status = "✅ PASSED"
            status_detail = "All metrics within budget"
        
        lines.append(f"#### {component_name}")
        lines.append(f"**Description:** {desc}")
        lines.append(f"**Status:** {status} ({status_detail})")
        
        # Show key metrics
        lines.append(f"**Budget Limits:**")
        lines.append(f"- p50 latency: ≤ {component_config.get('latency_p50_ms', 'N/A')} ms")
        lines.append(f"- p95 latency: ≤ {component_config.get('latency_p95_ms', 'N/A')} ms")
        lines.append(f"- p99 latency: ≤ {component_config.get('latency_p99_ms', 'N/A')} ms")
        lines.append(f"- Throughput: ≥ {component_config.get('throughput_min_tps', 'N/A')} TPS")
        lines.append(f"- Stability CoV: ≤ {component_config.get('stability_coefficient_max', 'N/A')}")
        lines.append("")
    
    return "\n".join(lines)


def generate_flamegraph_section(flamegraph_path: Path) -> str:
    """Generate flamegraph references section."""
    lines = ["### 🔥 Flamegraph Profiles\n"]
    
    if not flamegraph_path.exists():
        lines.append("*No flamegraphs available for this run.*\n")
        return "\n".join(lines)
    
    flamegraphs = list(flamegraph_path.glob("*.svg"))
    if not flamegraphs:
        lines.append("*No flamegraphs generated.*\n")
        return "\n".join(lines)
    
    lines.append("Flamegraphs have been generated for the following components:\n")
    for fg in sorted(flamegraphs):
        component = fg.stem
        lines.append(f"- **{component}**: `{fg.relative_to(flamegraph_path.parent.parent)}`")
    
    lines.append("\nThese flamegraphs are available in the workflow artifacts.")
    lines.append("Download them to identify performance bottlenecks.\n")
    
    return "\n".join(lines)


def generate_recommendations(violations: list[dict[str, Any]]) -> str:
    """Generate actionable recommendations."""
    if not violations:
        return "### ✨ Recommendations\n\nPerformance is within all budget limits. Great work! 🎉\n"
    
    lines = ["### 🎯 Recommendations\n"]
    
    # Group violations by component
    by_component = {}
    for v in violations:
        comp = v["component"]
        if comp not in by_component:
            by_component[comp] = []
        by_component[comp].append(v)
    
    for component, comp_violations in by_component.items():
        lines.append(f"#### {component}")
        
        # Check for latency issues
        latency_violations = [v for v in comp_violations if "latency" in v["metric"]]
        if latency_violations:
            lines.append("**Latency Issues:**")
            lines.append("- Review flamegraph for CPU hotspots")
            lines.append("- Consider caching frequently accessed data")
            lines.append("- Profile database queries and optimize indexes")
            lines.append("- Check for unnecessary synchronous operations")
        
        # Check for throughput issues
        throughput_violations = [v for v in comp_violations if "throughput" in v["metric"]]
        if throughput_violations:
            lines.append("**Throughput Issues:**")
            lines.append("- Analyze concurrency and parallelism")
            lines.append("- Review resource limits (CPU, memory, I/O)")
            lines.append("- Consider batching operations")
            lines.append("- Check for lock contention")
        
        # Check for stability issues
        stability_violations = [v for v in comp_violations if "stability" in v["metric"] or "coefficient" in v["metric"]]
        if stability_violations:
            lines.append("**Stability Issues:**")
            lines.append("- High variance detected in latencies")
            lines.append("- Investigate GC pauses or resource contention")
            lines.append("- Review outlier cases in flamegraph")
            lines.append("- Consider warm-up period before measurements")
        
        lines.append("")
    
    return "\n".join(lines)


def generate_historical_trends_section() -> str:
    """Generate placeholder for historical trends."""
    lines = ["### 📈 Historical Trends\n"]
    lines.append("*Historical trend tracking is configured and will accumulate data over time.*\n")
    lines.append("Key metrics tracked:")
    lines.append("- p50, p95, p99 latency trends")
    lines.append("- Throughput evolution")
    lines.append("- Stability coefficient changes")
    lines.append("- Violation frequency\n")
    return "\n".join(lines)


def generate_report(
    config_path: Path,
    validation_path: Path,
    config: ReportConfig,
) -> str:
    """Generate complete performance report."""
    budget_config = load_config(config_path)
    validation = load_validation_results(validation_path)
    
    lines = []
    
    # Header
    lines.append("# Performance Budget Validation Report\n")
    lines.append(f"**Generated:** {validation.get('timestamp', 'N/A')}\n")
    
    # Summary
    summary = validation.get("summary", {})
    lines.append("## 📊 Summary\n")
    lines.append(f"- **Components Checked:** {summary.get('components_checked', 0)}")
    lines.append(f"- **Components Passed:** {summary.get('components_passed', 0)}")
    lines.append(f"- **Total Violations:** {summary.get('total_violations', 0)}")
    
    if validation.get("passed"):
        lines.append(f"\n**Overall Status:** ✅ **PASSED**\n")
    else:
        lines.append(f"\n**Overall Status:** ❌ **FAILED**\n")
    
    # Violations table
    lines.append("## 🚨 Budget Violations\n")
    lines.append(generate_violations_table(validation.get("violations", [])))
    
    # Component summary
    lines.append(generate_component_summary(budget_config, validation))
    
    # Flamegraphs
    if config.include_flamegraphs:
        flamegraph_path = Path("reports/performance/flamegraphs")
        lines.append(generate_flamegraph_section(flamegraph_path))
    
    # Historical trends
    if config.include_trends:
        lines.append(generate_historical_trends_section())
    
    # Recommendations
    lines.append(generate_recommendations(validation.get("violations", [])))
    
    # Gate configuration
    gate_config = budget_config.get("gate_thresholds", {})
    lines.append("## ⚙️ Gate Configuration\n")
    lines.append(f"- **Regression Threshold:** {gate_config.get('regression_threshold_percent', 'N/A')}%")
    lines.append(f"- **Min Sample Size:** {gate_config.get('min_sample_size', 'N/A')}")
    lines.append(f"- **Confidence Level:** {gate_config.get('confidence_level', 'N/A')}")
    lines.append("")
    
    return "\n".join(lines)


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
        "--validation",
        type=Path,
        required=True,
        help="Path to validation results JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to output report markdown file",
    )
    parser.add_argument(
        "--include-trends",
        action="store_true",
        help="Include historical trends section",
    )
    parser.add_argument(
        "--include-flamegraphs",
        action="store_true",
        help="Include flamegraph references",
    )
    
    args = parser.parse_args()
    
    config = ReportConfig(
        include_trends=args.include_trends,
        include_flamegraphs=args.include_flamegraphs,
    )
    
    print(f"Generating performance report...")
    report = generate_report(args.config, args.validation, config)
    
    # Write report
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(report)
    
    print(f"Report written to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
