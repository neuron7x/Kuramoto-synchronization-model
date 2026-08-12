# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Performance artifact generation for CI/CD pipelines.

This module generates JSON reports, visualizations, and GitHub issue templates
for performance regression tracking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import matplotlib

    matplotlib.use("Agg")  # Non-interactive backend
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

from .multi_exchange_replay import (
    PerformanceBudget,
    PerformanceMetrics,
    RegressionResult,
    ReplayMetadata,
)


@dataclass(slots=True)
class PerformanceRun:
    """Single performance test run result."""

    name: str
    timestamp: datetime
    metrics: PerformanceMetrics
    metadata: ReplayMetadata | None = None
    budget: PerformanceBudget | None = None
    regression_result: RegressionResult | None = None
    git_commit: str | None = None
    git_branch: str | None = None
    environment: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PerformanceReport:
    """Aggregated performance report for multiple test runs."""

    runs: list[PerformanceRun] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class PerformanceArtifactGenerator:
    """Generate performance artifacts for CI/CD consumption."""

    def __init__(self, output_dir: Path) -> None:
        """Initialize artifact generator.

        Args:
            output_dir: Directory to write artifacts
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_json_report(self, report: PerformanceReport) -> Path:
        """Generate JSON report file.

        Args:
            report: Performance report to serialize

        Returns:
            Path to generated JSON file
        """
        output_path = self.output_dir / "performance_report.json"

        data = {
            "generated_at": report.generated_at.isoformat(),
            "summary": report.summary,
            "runs": [
                {
                    "name": run.name,
                    "timestamp": run.timestamp.isoformat(),
                    "metrics": run.metrics.to_dict(),
                    "metadata": (
                        {
                            "name": run.metadata.name,
                            "exchange": run.metadata.exchange,
                            "symbol": run.metadata.symbol,
                            "tick_count": run.metadata.tick_count,
                        }
                        if run.metadata
                        else None
                    ),
                    "budget": (
                        {
                            "latency_median_ms": run.budget.latency_median_ms,
                            "latency_p95_ms": run.budget.latency_p95_ms,
                            "latency_max_ms": run.budget.latency_max_ms,
                            "throughput_min_tps": run.budget.throughput_min_tps,
                            "slippage_median_bps": run.budget.slippage_median_bps,
                            "slippage_p95_bps": run.budget.slippage_p95_bps,
                        }
                        if run.budget
                        else None
                    ),
                    "regression": (
                        {
                            "passed": run.regression_result.passed,
                            "violations": list(run.regression_result.violations),
                        }
                        if run.regression_result
                        else None
                    ),
                    "git_commit": run.git_commit,
                    "git_branch": run.git_branch,
                    "environment": run.environment,
                }
                for run in report.runs
            ],
        }

        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return output_path

    def generate_markdown_summary(self, report: PerformanceReport) -> Path:
        """Generate markdown summary for GitHub.

        Args:
            report: Performance report to summarize

        Returns:
            Path to generated markdown file
        """
        output_path = self.output_dir / "performance_summary.md"

        lines = ["# Performance Test Results\n"]
        lines.append(f"Generated: {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")

        # Summary statistics
        if report.summary:
            lines.append("\n## Summary\n")
            for key, value in report.summary.items():
                lines.append(f"- **{key}**: {value}\n")

        # Individual runs
        lines.append("\n## Test Runs\n")

        for run in report.runs:
            lines.append(f"\n### {run.name}\n")

            if run.metadata:
                lines.append(f"- **Exchange**: {run.metadata.exchange}\n")
                lines.append(f"- **Symbol**: {run.metadata.symbol}\n")
                lines.append(f"- **Ticks**: {run.metadata.tick_count}\n")

            lines.append("\n#### Metrics\n")
            lines.append("| Metric | Value | Budget | Status |\n")
            lines.append("|--------|-------|--------|--------|\n")

            if run.budget:
                status_lat_med = (
                    "✅" if run.metrics.latency_median_ms <= run.budget.latency_median_ms else "❌"
                )
                status_lat_p95 = (
                    "✅" if run.metrics.latency_p95_ms <= run.budget.latency_p95_ms else "❌"
                )
                status_lat_max = (
                    "✅" if run.metrics.latency_max_ms <= run.budget.latency_max_ms else "❌"
                )
                status_throughput = (
                    "✅" if run.metrics.throughput_tps >= run.budget.throughput_min_tps else "❌"
                )
                status_slip_med = (
                    "✅"
                    if run.metrics.slippage_median_bps <= run.budget.slippage_median_bps
                    else "❌"
                )
                status_slip_p95 = (
                    "✅" if run.metrics.slippage_p95_bps <= run.budget.slippage_p95_bps else "❌"
                )

                lines.append(
                    f"| Latency (median) | {run.metrics.latency_median_ms:.2f}ms | {run.budget.latency_median_ms:.2f}ms | {status_lat_med} |\n"
                )
                lines.append(
                    f"| Latency (p95) | {run.metrics.latency_p95_ms:.2f}ms | {run.budget.latency_p95_ms:.2f}ms | {status_lat_p95} |\n"
                )
                lines.append(
                    f"| Latency (max) | {run.metrics.latency_max_ms:.2f}ms | {run.budget.latency_max_ms:.2f}ms | {status_lat_max} |\n"
                )
                lines.append(
                    f"| Throughput | {run.metrics.throughput_tps:.2f} tps | {run.budget.throughput_min_tps:.2f} tps | {status_throughput} |\n"
                )
                lines.append(
                    f"| Slippage (median) | {run.metrics.slippage_median_bps:.2f}bps | {run.budget.slippage_median_bps:.2f}bps | {status_slip_med} |\n"
                )
                lines.append(
                    f"| Slippage (p95) | {run.metrics.slippage_p95_bps:.2f}bps | {run.budget.slippage_p95_bps:.2f}bps | {status_slip_p95} |\n"
                )
            else:
                lines.append(
                    f"| Latency (median) | {run.metrics.latency_median_ms:.2f}ms | - | - |\n"
                )
                lines.append(f"| Latency (p95) | {run.metrics.latency_p95_ms:.2f}ms | - | - |\n")
                lines.append(f"| Latency (max) | {run.metrics.latency_max_ms:.2f}ms | - | - |\n")
                lines.append(f"| Throughput | {run.metrics.throughput_tps:.2f} tps | - | - |\n")
                lines.append(
                    f"| Slippage (median) | {run.metrics.slippage_median_bps:.2f}bps | - | - |\n"
                )
                lines.append(
                    f"| Slippage (p95) | {run.metrics.slippage_p95_bps:.2f}bps | - | - |\n"
                )

            if run.regression_result and not run.regression_result.passed:
                lines.append("\n#### ⚠️ Regression Violations\n")
                for violation in run.regression_result.violations:
                    lines.append(f"- {violation}\n")

        output_path.write_text("".join(lines), encoding="utf-8")
        return output_path

    def generate_charts(self, report: PerformanceReport) -> list[Path]:
        """Generate performance visualization charts.

        Args:
            report: Performance report to visualize

        Returns:
            List of paths to generated chart files
        """
        if not MATPLOTLIB_AVAILABLE:
            return []

        chart_paths = []

        if not report.runs:
            return chart_paths

        # Latency distribution chart
        latency_chart = self._generate_latency_chart(report)
        if latency_chart:
            chart_paths.append(latency_chart)

        # Throughput comparison chart
        throughput_chart = self._generate_throughput_chart(report)
        if throughput_chart:
            chart_paths.append(throughput_chart)

        # Slippage distribution chart
        slippage_chart = self._generate_slippage_chart(report)
        if slippage_chart:
            chart_paths.append(slippage_chart)

        return chart_paths

    def _generate_latency_chart(self, report: PerformanceReport) -> Path | None:
        """Generate latency distribution chart."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, ax = plt.subplots(figsize=(12, 6))

        run_names = [run.name for run in report.runs]
        medians = [run.metrics.latency_median_ms for run in report.runs]
        p95s = [run.metrics.latency_p95_ms for run in report.runs]
        maxs = [run.metrics.latency_max_ms for run in report.runs]

        x = range(len(run_names))
        width = 0.25

        ax.bar([i - width for i in x], medians, width, label="Median", color="#4CAF50")
        ax.bar(x, p95s, width, label="P95", color="#FFC107")
        ax.bar([i + width for i in x], maxs, width, label="Max", color="#F44336")

        # Add budget lines if available
        if report.runs and report.runs[0].budget:
            budget = report.runs[0].budget
            ax.axhline(
                y=budget.latency_median_ms,
                color="green",
                linestyle="--",
                alpha=0.5,
                label=f"Budget Median ({budget.latency_median_ms}ms)",
            )
            ax.axhline(
                y=budget.latency_p95_ms,
                color="orange",
                linestyle="--",
                alpha=0.5,
                label=f"Budget P95 ({budget.latency_p95_ms}ms)",
            )
            ax.axhline(
                y=budget.latency_max_ms,
                color="red",
                linestyle="--",
                alpha=0.5,
                label=f"Budget Max ({budget.latency_max_ms}ms)",
            )

        ax.set_xlabel("Test Run")
        ax.set_ylabel("Latency (ms)")
        ax.set_title("Latency Distribution by Test Run")
        ax.set_xticks(x)
        ax.set_xticklabels(run_names, rotation=45, ha="right")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        output_path = self.output_dir / "latency_chart.png"
        fig.savefig(output_path, dpi=150)
        plt.close(fig)

        return output_path

    def _generate_throughput_chart(self, report: PerformanceReport) -> Path | None:
        """Generate throughput comparison chart."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, ax = plt.subplots(figsize=(10, 6))

        run_names = [run.name for run in report.runs]
        throughputs = [run.metrics.throughput_tps for run in report.runs]

        bars = ax.bar(run_names, throughputs, color="#2196F3")

        # Add budget line if available
        if report.runs and report.runs[0].budget:
            budget_throughput = report.runs[0].budget.throughput_min_tps
            ax.axhline(
                y=budget_throughput,
                color="red",
                linestyle="--",
                alpha=0.7,
                label=f"Budget ({budget_throughput:.0f} tps)",
            )

            # Color bars based on budget
            for i, (bar, throughput) in enumerate(zip(bars, throughputs)):
                if throughput < budget_throughput:
                    bar.set_color("#F44336")
                else:
                    bar.set_color("#4CAF50")

        ax.set_xlabel("Test Run")
        ax.set_ylabel("Throughput (ticks/second)")
        ax.set_title("Throughput Comparison")
        ax.set_xticklabels(run_names, rotation=45, ha="right")
        ax.legend()
        ax.grid(True, alpha=0.3, axis="y")

        plt.tight_layout()

        output_path = self.output_dir / "throughput_chart.png"
        fig.savefig(output_path, dpi=150)
        plt.close(fig)

        return output_path

    def _generate_slippage_chart(self, report: PerformanceReport) -> Path | None:
        """Generate slippage distribution chart."""
        if not MATPLOTLIB_AVAILABLE:
            return None

        fig, ax = plt.subplots(figsize=(10, 6))

        run_names = [run.name for run in report.runs]
        medians = [run.metrics.slippage_median_bps for run in report.runs]
        p95s = [run.metrics.slippage_p95_bps for run in report.runs]

        x = range(len(run_names))
        width = 0.35

        ax.bar([i - width / 2 for i in x], medians, width, label="Median", color="#00BCD4")
        ax.bar([i + width / 2 for i in x], p95s, width, label="P95", color="#FF9800")

        # Add budget lines if available
        if report.runs and report.runs[0].budget:
            budget = report.runs[0].budget
            ax.axhline(
                y=budget.slippage_median_bps,
                color="cyan",
                linestyle="--",
                alpha=0.5,
                label=f"Budget Median ({budget.slippage_median_bps}bps)",
            )
            ax.axhline(
                y=budget.slippage_p95_bps,
                color="orange",
                linestyle="--",
                alpha=0.5,
                label=f"Budget P95 ({budget.slippage_p95_bps}bps)",
            )

        ax.set_xlabel("Test Run")
        ax.set_ylabel("Slippage (bps)")
        ax.set_title("Slippage Distribution by Test Run")
        ax.set_xticks(x)
        ax.set_xticklabels(run_names, rotation=45, ha="right")
        ax.legend()
        ax.grid(True, alpha=0.3)

        plt.tight_layout()

        output_path = self.output_dir / "slippage_chart.png"
        fig.savefig(output_path, dpi=150)
        plt.close(fig)

        return output_path

    def generate_issue_template(self, run: PerformanceRun, component: str = "performance") -> Path:
        """Generate GitHub issue template for regression.

        Args:
            run: Performance run with regression
            component: Component label for the issue

        Returns:
            Path to issue template file
        """
        output_path = self.output_dir / f"issue_template_{run.name}.md"

        lines = [
            f"# Performance Regression: {run.name}\n\n",
            "## Summary\n\n",
            f"Performance regression detected in {run.name} test run.\n\n",
        ]

        if run.regression_result and run.regression_result.violations:
            lines.append("## Violations\n\n")
            for violation in run.regression_result.violations:
                lines.append(f"- {violation}\n")
            lines.append("\n")

        lines.append("## Metrics\n\n")
        lines.append("| Metric | Value |\n")
        lines.append("|--------|-------|\n")
        lines.append(f"| Latency (median) | {run.metrics.latency_median_ms:.2f}ms |\n")
        lines.append(f"| Latency (p95) | {run.metrics.latency_p95_ms:.2f}ms |\n")
        lines.append(f"| Latency (max) | {run.metrics.latency_max_ms:.2f}ms |\n")
        lines.append(f"| Throughput | {run.metrics.throughput_tps:.2f} tps |\n")
        lines.append(f"| Slippage (median) | {run.metrics.slippage_median_bps:.2f}bps |\n")
        lines.append(f"| Slippage (p95) | {run.metrics.slippage_p95_bps:.2f}bps |\n")
        lines.append("\n")

        if run.git_commit:
            lines.append("## Environment\n\n")
            lines.append(f"- **Commit**: `{run.git_commit}`\n")
            if run.git_branch:
                lines.append(f"- **Branch**: `{run.git_branch}`\n")
            lines.append("\n")

        lines.append("## Labels\n\n")
        lines.append(f"- `{component}`\n")
        lines.append("- `performance-regression`\n")
        lines.append("- `needs-investigation`\n")

        output_path.write_text("".join(lines), encoding="utf-8")
        return output_path


__all__ = [
    "PerformanceRun",
    "PerformanceReport",
    "PerformanceArtifactGenerator",
]
