#!/usr/bin/env python3
"""Track and visualize historical performance trends.

This script maintains a history of performance benchmarks and generates
trend charts to detect gradual regressions.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class HistoricalDataPoint:
    """Single data point in performance history."""
    
    timestamp: str
    commit_sha: str
    branch: str
    component: str
    p50_ms: float
    p95_ms: float
    p99_ms: float
    mean_ms: float
    std_ms: float


class PerformanceHistory:
    """Manage historical performance data."""
    
    def __init__(self, history_file: Path):
        self.history_file = history_file
        self.data: List[Dict[str, Any]] = []
        self.load()
    
    def load(self) -> None:
        """Load existing history from file."""
        if self.history_file.exists():
            with open(self.history_file) as f:
                self.data = json.load(f)
    
    def save(self) -> None:
        """Save history to file."""
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.history_file, "w") as f:
            json.dump(self.data, f, indent=2)
    
    def add_benchmark(
        self,
        component: str,
        metrics: Dict[str, float],
        commit_sha: str,
        branch: str,
    ) -> None:
        """Add new benchmark result to history."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "commit_sha": commit_sha,
            "branch": branch,
            "component": component,
            **metrics,
        }
        self.data.append(entry)
    
    def get_component_history(
        self,
        component: str,
        limit: Optional[int] = None,
    ) -> List[HistoricalDataPoint]:
        """Get historical data for a component."""
        points = []
        for entry in self.data:
            if entry["component"] == component:
                points.append(HistoricalDataPoint(
                    timestamp=entry["timestamp"],
                    commit_sha=entry["commit_sha"],
                    branch=entry["branch"],
                    component=entry["component"],
                    p50_ms=entry.get("p50_ms", 0),
                    p95_ms=entry.get("p95_ms", 0),
                    p99_ms=entry.get("p99_ms", 0),
                    mean_ms=entry.get("mean_ms", 0),
                    std_ms=entry.get("std_ms", 0),
                ))
        
        # Return most recent first
        points.reverse()
        
        if limit:
            points = points[:limit]
        
        return points
    
    def get_trend_summary(
        self,
        component: str,
        lookback: int = 10,
    ) -> Dict[str, Any]:
        """Get trend summary for a component."""
        history = self.get_component_history(component, limit=lookback)
        
        if len(history) < 2:
            return {
                "component": component,
                "trend": "insufficient_data",
                "data_points": len(history),
            }
        
        # Calculate trend (simple linear regression on p50)
        p50_values = [p.p50_ms for p in reversed(history)]
        n = len(p50_values)
        x_mean = (n - 1) / 2
        y_mean = sum(p50_values) / n
        
        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(p50_values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        
        if denominator == 0:
            slope = 0
        else:
            slope = numerator / denominator
        
        # Determine trend direction
        if abs(slope) < 0.1:
            trend = "stable"
        elif slope > 0:
            trend = "degrading"
        else:
            trend = "improving"
        
        # Calculate percentage change over period
        first_p50 = p50_values[0]
        last_p50 = p50_values[-1]
        pct_change = ((last_p50 - first_p50) / first_p50 * 100) if first_p50 > 0 else 0
        
        return {
            "component": component,
            "trend": trend,
            "slope_ms_per_commit": slope,
            "pct_change": pct_change,
            "data_points": n,
            "current_p50_ms": last_p50,
            "baseline_p50_ms": first_p50,
        }


def update_history(
    benchmark_results: Dict[str, Any],
    history_file: Path,
    commit_sha: str = "unknown",
    branch: str = "unknown",
) -> None:
    """Update performance history with new benchmark results."""
    history = PerformanceHistory(history_file)
    
    for component, result in benchmark_results.items():
        metrics = result["metrics"]
        history.add_benchmark(
            component=component,
            metrics=metrics,
            commit_sha=commit_sha,
            branch=branch,
        )
    
    history.save()
    print(f"Updated history: {history_file}", file=sys.stderr)


def generate_trend_report(
    history_file: Path,
    output_file: Optional[Path] = None,
    lookback: int = 10,
) -> str:
    """Generate markdown trend report."""
    history = PerformanceHistory(history_file)
    
    components = ["order_router", "link_activator", "thermo_validator"]
    
    report_lines = [
        "# Performance Trend Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}",
        f"Lookback: {lookback} data points",
        "",
        "## Component Trends",
        "",
    ]
    
    for component in components:
        summary = history.get_trend_summary(component, lookback)
        
        trend_emoji = {
            "stable": "✓",
            "improving": "📈",
            "degrading": "⚠️",
            "insufficient_data": "❓",
        }.get(summary["trend"], "?")
        
        report_lines.extend([
            f"### {component} {trend_emoji}",
            "",
            f"- **Trend**: {summary['trend']}",
            f"- **Data points**: {summary['data_points']}",
        ])
        
        if summary["data_points"] >= 2:
            report_lines.extend([
                f"- **Current p50**: {summary['current_p50_ms']:.2f}ms",
                f"- **Baseline p50**: {summary['baseline_p50_ms']:.2f}ms",
                f"- **Change**: {summary['pct_change']:+.1f}%",
                f"- **Slope**: {summary['slope_ms_per_commit']:+.3f}ms/commit",
            ])
        
        # Recent history
        recent = history.get_component_history(component, limit=5)
        if recent:
            report_lines.extend([
                "",
                "**Recent history:**",
                "",
                "| Timestamp | Commit | p50 | p95 | p99 |",
                "|-----------|--------|-----|-----|-----|",
            ])
            
            for point in recent:
                report_lines.append(
                    f"| {point.timestamp[:19]} | {point.commit_sha[:7]} | "
                    f"{point.p50_ms:.1f}ms | {point.p95_ms:.1f}ms | {point.p99_ms:.1f}ms |"
                )
        
        report_lines.append("")
    
    report = "\n".join(report_lines)
    
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            f.write(report)
        print(f"Generated trend report: {output_file}", file=sys.stderr)
    
    return report


def main() -> int:
    """Main entry point for trend tracking."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Track historical performance trends")
    parser.add_argument(
        "--history-file",
        type=Path,
        default=Path("reports/performance/history.json"),
        help="Path to history JSON file",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Update command
    update_parser = subparsers.add_parser("update", help="Update history with new results")
    update_parser.add_argument(
        "--benchmark-results",
        type=Path,
        required=True,
        help="Path to benchmark results JSON",
    )
    update_parser.add_argument(
        "--commit-sha",
        default="unknown",
        help="Git commit SHA",
    )
    update_parser.add_argument(
        "--branch",
        default="unknown",
        help="Git branch name",
    )
    
    # Report command
    report_parser = subparsers.add_parser("report", help="Generate trend report")
    report_parser.add_argument(
        "--output",
        type=Path,
        help="Output markdown file",
    )
    report_parser.add_argument(
        "--lookback",
        type=int,
        default=10,
        help="Number of historical points to analyze",
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == "update":
            with open(args.benchmark_results) as f:
                results = json.load(f)
            
            update_history(
                results,
                args.history_file,
                args.commit_sha,
                args.branch,
            )
        
        elif args.command == "report":
            report = generate_trend_report(
                args.history_file,
                args.output,
                args.lookback,
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
