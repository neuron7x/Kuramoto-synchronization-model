# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Test performance tracking and analysis.

Tracks test execution times and identifies performance regressions.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class TestPerformanceRecord:
    """Performance record for a single test."""

    test_id: str
    duration: float
    status: str
    timestamp: str


@dataclass
class PerformanceComparison:
    """Comparison between current and baseline performance."""

    test_id: str
    current_duration: float
    baseline_duration: float
    delta_seconds: float
    delta_percentage: float
    is_regression: bool


class TestPerformanceTracker:
    """Tracks and analyzes test performance metrics."""

    def __init__(self, baseline_file: Path | None = None):
        """Initialize tracker with optional baseline."""
        self.baseline_file = baseline_file
        self.baseline: dict[str, float] = {}
        if baseline_file and baseline_file.exists():
            self._load_baseline()

    def _load_baseline(self) -> None:
        """Load baseline performance data."""
        if not self.baseline_file or not self.baseline_file.exists():
            return

        try:
            with open(self.baseline_file, encoding="utf-8") as f:
                data = json.load(f)
                self.baseline = {
                    record["test_id"]: record["duration"] for record in data.get("records", [])
                }
            print(f"Loaded baseline with {len(self.baseline)} test records")
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"Warning: Could not load baseline: {e}")

    def load_current_results(self, results_file: Path) -> list[TestPerformanceRecord]:
        """Load current test results from pytest-json-report."""
        records = []

        try:
            with open(results_file, encoding="utf-8") as f:
                data = json.load(f)

            for test in data.get("tests", []):
                test_id = test.get("nodeid", "unknown")
                duration = test.get("duration", 0.0)
                status = test.get("outcome", "unknown")
                timestamp = data.get("created", "")

                records.append(
                    TestPerformanceRecord(
                        test_id=test_id,
                        duration=duration,
                        status=status,
                        timestamp=timestamp,
                    )
                )

        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"Error loading test results: {e}")

        return records

    def compare_with_baseline(
        self, current_records: list[TestPerformanceRecord], threshold: float = 1.2
    ) -> list[PerformanceComparison]:
        """Compare current results with baseline and identify regressions."""
        comparisons = []

        for record in current_records:
            if record.test_id not in self.baseline:
                continue

            baseline_duration = self.baseline[record.test_id]
            current_duration = record.duration
            delta_seconds = current_duration - baseline_duration
            delta_percentage = (
                (delta_seconds / baseline_duration * 100) if baseline_duration > 0 else 0
            )

            is_regression = current_duration > baseline_duration * threshold

            comparisons.append(
                PerformanceComparison(
                    test_id=record.test_id,
                    current_duration=current_duration,
                    baseline_duration=baseline_duration,
                    delta_seconds=delta_seconds,
                    delta_percentage=delta_percentage,
                    is_regression=is_regression,
                )
            )

        return comparisons

    def identify_slow_tests(
        self, records: list[TestPerformanceRecord], threshold: float = 1.0
    ) -> list[TestPerformanceRecord]:
        """Identify tests that are slower than threshold."""
        return sorted(
            [r for r in records if r.duration >= threshold],
            key=lambda x: x.duration,
            reverse=True,
        )

    def save_as_baseline(self, records: list[TestPerformanceRecord], output_file: Path) -> None:
        """Save current results as new baseline."""
        data = {
            "records": [
                {
                    "test_id": r.test_id,
                    "duration": r.duration,
                    "status": r.status,
                    "timestamp": r.timestamp,
                }
                for r in records
            ]
        }

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        print(f"Saved baseline with {len(records)} test records to {output_file}")

    def generate_report(
        self,
        current_records: list[TestPerformanceRecord],
        comparisons: list[PerformanceComparison] | None = None,
    ) -> dict[str, Any]:
        """Generate comprehensive performance report."""
        # Calculate statistics
        total_tests = len(current_records)
        total_duration = sum(r.duration for r in current_records)
        avg_duration = total_duration / total_tests if total_tests > 0 else 0

        # Identify slow tests
        slow_tests = self.identify_slow_tests(current_records, threshold=1.0)

        # Regression analysis
        regressions = []
        if comparisons:
            regressions = [c for c in comparisons if c.is_regression]

        report = {
            "summary": {
                "total_tests": total_tests,
                "total_duration": total_duration,
                "average_duration": avg_duration,
                "slow_tests_count": len(slow_tests),
                "regressions_count": len(regressions),
            },
            "slow_tests": [
                {
                    "test_id": r.test_id,
                    "duration": r.duration,
                    "status": r.status,
                }
                for r in slow_tests[:20]  # Top 20 slowest
            ],
            "regressions": [
                {
                    "test_id": c.test_id,
                    "current_duration": c.current_duration,
                    "baseline_duration": c.baseline_duration,
                    "delta_seconds": c.delta_seconds,
                    "delta_percentage": c.delta_percentage,
                }
                for c in sorted(regressions, key=lambda x: x.delta_percentage, reverse=True)[
                    :20
                ]  # Top 20 worst
            ],
        }

        return report

    def print_report(self, report: dict[str, Any]) -> None:
        """Print performance report to console."""
        summary = report["summary"]

        print("\n" + "=" * 70)
        print("TEST PERFORMANCE ANALYSIS")
        print("=" * 70)
        print(f"\nTotal Tests: {summary['total_tests']}")
        print(f"Total Duration: {summary['total_duration']:.2f}s")
        print(f"Average Duration: {summary['average_duration']:.3f}s")
        print(f"Slow Tests (>1s): {summary['slow_tests_count']}")

        if report["slow_tests"]:
            print("\n⏱️  Slowest Tests:")
            for test in report["slow_tests"][:10]:
                print(f"  - {test['test_id']}: {test['duration']:.2f}s")

        if summary["regressions_count"] > 0:
            print(f"\n⚠️  Performance Regressions: {summary['regressions_count']}")
            for reg in report["regressions"][:10]:
                print(
                    f"  - {reg['test_id']}: {reg['current_duration']:.2f}s "
                    f"(+{reg['delta_percentage']:.1f}% from {reg['baseline_duration']:.2f}s)"
                )
        else:
            print("\n✅ No performance regressions detected")


def main(argv: list[str] | None = None) -> int:
    """Main entry point for test performance tracker."""
    parser = argparse.ArgumentParser(description="Track and analyze test performance metrics")
    parser.add_argument(
        "--results",
        type=Path,
        required=True,
        help="Path to pytest-json-report results file",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        help="Path to baseline performance file",
    )
    parser.add_argument(
        "--save-baseline",
        type=Path,
        help="Save current results as new baseline",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Output JSON report file",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=1.2,
        help="Regression threshold multiplier (default: 1.2)",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with error if performance regressions detected",
    )

    args = parser.parse_args(argv or sys.argv[1:])

    # Initialize tracker
    tracker = TestPerformanceTracker(baseline_file=args.baseline)

    # Load current results
    current_records = tracker.load_current_results(args.results)
    if not current_records:
        print("No test results found")
        return 2

    # Compare with baseline if available
    comparisons = None
    if tracker.baseline:
        comparisons = tracker.compare_with_baseline(current_records, args.threshold)

    # Generate report
    report = tracker.generate_report(current_records, comparisons)
    tracker.print_report(report)

    # Save report if requested
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\n📄 Report written to {args.report}")

    # Save as baseline if requested
    if args.save_baseline:
        tracker.save_as_baseline(current_records, args.save_baseline)

    # Check for regressions
    if args.fail_on_regression and report["summary"]["regressions_count"] > 0:
        print(f"\n❌ {report['summary']['regressions_count']} performance regression(s) detected")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
