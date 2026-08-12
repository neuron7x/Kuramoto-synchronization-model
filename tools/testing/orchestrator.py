# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Enhanced test orchestration and reporting for PR testing workflows.

This module provides comprehensive test orchestration, including:
- Test category execution tracking
- Test quality metrics
- Cross-workflow coordination
- Test performance tracking
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TestCategory:
    """Represents a test category with execution metadata."""

    name: str
    marker: str
    description: str
    executed: bool = False
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class TestOrchestrationReport:
    """Comprehensive report of test execution across all categories."""

    categories: list[TestCategory]
    total_duration: float
    overall_passed: int
    overall_failed: int
    overall_skipped: int
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary format."""
        return {
            "categories": [
                {
                    "name": cat.name,
                    "marker": cat.marker,
                    "description": cat.description,
                    "executed": cat.executed,
                    "passed": cat.passed,
                    "failed": cat.failed,
                    "skipped": cat.skipped,
                    "duration": cat.duration,
                    "errors": cat.errors,
                }
                for cat in self.categories
            ],
            "summary": {
                "total_duration": self.total_duration,
                "overall_passed": self.overall_passed,
                "overall_failed": self.overall_failed,
                "overall_skipped": self.overall_skipped,
            },
            "timestamp": self.timestamp,
        }

    def to_markdown(self) -> str:
        """Generate markdown summary of test execution."""
        lines = ["## Test Orchestration Report", ""]

        # Summary table
        lines.extend(
            [
                "### Summary",
                "",
                "| Metric | Value |",
                "| --- | --- |",
                f"| Total Duration | {self.total_duration:.2f}s |",
                f"| Total Passed | {self.overall_passed} |",
                f"| Total Failed | {self.overall_failed} |",
                f"| Total Skipped | {self.overall_skipped} |",
                "",
            ]
        )

        # Category details
        lines.extend(["### Test Categories", ""])
        lines.extend(
            [
                "| Category | Marker | Executed | Passed | Failed | Skipped | Duration |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )

        for cat in self.categories:
            executed_icon = "✅" if cat.executed else "⏭️"
            lines.append(
                f"| {cat.name} | {cat.marker} | {executed_icon} | "
                f"{cat.passed} | {cat.failed} | {cat.skipped} | {cat.duration:.2f}s |"
            )

        lines.append("")

        # Failed categories
        failed_cats = [cat for cat in self.categories if cat.failed > 0]
        if failed_cats:
            lines.extend(["### Failed Categories", ""])
            for cat in failed_cats:
                lines.append(f"- **{cat.name}**: {cat.failed} failed tests")
                if cat.errors:
                    for error in cat.errors[:3]:  # Show first 3 errors
                        lines.append(f"  - {error}")

        return "\n".join(lines)


class TestOrchestrator:
    """Orchestrates test execution and generates comprehensive reports."""

    # Define test categories with their markers
    TEST_CATEGORIES = [
        TestCategory(
            name="Static Analysis",
            marker="L0",
            description="Static analysis and audit guardrails",
        ),
        TestCategory(
            name="Unit Tests",
            marker="L1",
            description="Hermetic unit tests with no external I/O",
        ),
        TestCategory(
            name="Contract Tests",
            marker="L2",
            description="Schema, OpenAPI, RBAC, and audit-surface validation",
        ),
        TestCategory(
            name="Integration Tests",
            marker="L3",
            description="Integration flows stitching multiple modules",
        ),
        TestCategory(
            name="E2E Tests",
            marker="L4",
            description="End-to-end regression of trading pipeline",
        ),
        TestCategory(
            name="Resilience Tests",
            marker="L5",
            description="Chaos, thermodynamic, and rollout scenarios",
        ),
        TestCategory(
            name="Infrastructure Tests",
            marker="L6",
            description="Infrastructure readiness and conformance",
        ),
        TestCategory(
            name="UI Tests",
            marker="L7",
            description="UI, accessibility, and rendering quality",
        ),
    ]

    def __init__(self, report_dir: Path):
        """Initialize orchestrator with report directory."""
        self.report_dir = report_dir
        self.report_dir.mkdir(parents=True, exist_ok=True)

    def run_test_category(self, category: TestCategory, test_dir: Path) -> TestCategory:
        """Execute tests for a specific category and update metadata."""
        print(f"Running {category.name} (marker: {category.marker})...")

        start_time = time.time()
        result_file = self.report_dir / f"{category.marker}.json"

        # Run pytest with the specific marker
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(test_dir),
            "-m",
            category.marker,
            "--tb=short",
            "-v",
            "--json-report",
            f"--json-report-file={result_file}",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout per category
            )

            category.executed = True
            category.duration = time.time() - start_time

            # Parse pytest-json-report output if available
            if result_file.exists():
                try:
                    with open(result_file, encoding="utf-8") as f:
                        data = json.load(f)
                        summary = data.get("summary", {})
                        category.passed = summary.get("passed", 0)
                        category.failed = summary.get("failed", 0)
                        category.skipped = summary.get("skipped", 0)

                        # Collect error messages
                        tests = data.get("tests", [])
                        for test in tests:
                            if test.get("outcome") == "failed":
                                error_msg = test.get("call", {}).get("longrepr", "Unknown error")
                                if isinstance(error_msg, str):
                                    category.errors.append(error_msg.split("\n")[0][:100])
                except (json.JSONDecodeError, KeyError, IOError) as e:
                    print(f"Warning: Could not parse test results: {e}")

            # Fallback: parse from pytest output
            if category.passed == 0 and category.failed == 0 and category.skipped == 0:
                output = result.stdout + result.stderr
                if "passed" in output:
                    # Simple heuristic parsing
                    for line in output.split("\n"):
                        if "passed" in line.lower():
                            # Try to extract numbers from pytest summary line
                            parts = line.split()
                            for i, part in enumerate(parts):
                                if "passed" in part and i > 0:
                                    try:
                                        category.passed = int(parts[i - 1])
                                    except (ValueError, IndexError):
                                        pass

        except subprocess.TimeoutExpired:
            category.executed = True
            category.duration = time.time() - start_time
            category.errors.append("Test execution timed out")
            print(f"  ⚠️  Timeout for {category.name}")
        except Exception as e:
            category.executed = True
            category.duration = time.time() - start_time
            category.errors.append(f"Execution error: {str(e)}")
            print(f"  ❌ Error running {category.name}: {e}")

        status = "✅" if category.failed == 0 else "❌"
        print(
            f"  {status} {category.name}: "
            f"passed={category.passed}, failed={category.failed}, skipped={category.skipped}, "
            f"duration={category.duration:.2f}s"
        )

        return category

    def orchestrate(
        self, test_dir: Path, categories: list[str] | None = None
    ) -> TestOrchestrationReport:
        """Orchestrate test execution across all or specified categories."""
        start_time = time.time()

        # Filter categories if specified
        categories_to_run = self.TEST_CATEGORIES
        if categories:
            categories_to_run = [cat for cat in self.TEST_CATEGORIES if cat.marker in categories]

        # Execute each category
        executed_categories = []
        for category in categories_to_run:
            executed_cat = self.run_test_category(category, test_dir)
            executed_categories.append(executed_cat)

        # Generate report
        total_duration = time.time() - start_time
        overall_passed = sum(cat.passed for cat in executed_categories)
        overall_failed = sum(cat.failed for cat in executed_categories)
        overall_skipped = sum(cat.skipped for cat in executed_categories)

        report = TestOrchestrationReport(
            categories=executed_categories,
            total_duration=total_duration,
            overall_passed=overall_passed,
            overall_failed=overall_failed,
            overall_skipped=overall_skipped,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Write reports
        json_report = self.report_dir / "orchestration_report.json"
        md_report = self.report_dir / "orchestration_report.md"

        with open(json_report, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        with open(md_report, "w", encoding="utf-8") as f:
            f.write(report.to_markdown())

        print("\n📊 Reports written to:")
        print(f"  - {json_report}")
        print(f"  - {md_report}")

        return report


def main(argv: list[str] | None = None) -> int:
    """Main entry point for test orchestrator."""
    parser = argparse.ArgumentParser(
        description="Orchestrate test execution across all test categories"
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("tests"),
        help="Directory containing tests (default: tests)",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("reports/orchestration"),
        help="Directory for reports (default: reports/orchestration)",
    )
    parser.add_argument(
        "--categories",
        nargs="*",
        help="Specific test categories to run (default: all)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available test categories and exit",
    )

    args = parser.parse_args(argv or sys.argv[1:])

    if args.list:
        print("Available test categories:")
        for cat in TestOrchestrator.TEST_CATEGORIES:
            print(f"  {cat.marker}: {cat.name} - {cat.description}")
        return 0

    orchestrator = TestOrchestrator(report_dir=args.report_dir)
    report = orchestrator.orchestrate(test_dir=args.test_dir, categories=args.categories)

    # Return non-zero if any tests failed
    return 1 if report.overall_failed > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
