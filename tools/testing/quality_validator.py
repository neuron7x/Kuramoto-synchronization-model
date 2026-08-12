# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Test quality validation tool.

Validates test quality metrics including:
- Test documentation completeness
- Test complexity analysis
- Test smell detection
- Test maintainability scores
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TestQualityMetrics:
    """Quality metrics for a single test file."""

    file_path: Path
    total_tests: int = 0
    documented_tests: int = 0
    complex_tests: int = 0  # Tests with high cyclomatic complexity
    test_smells: list[str] = field(default_factory=list)
    avg_test_length: float = 0.0
    has_fixtures: bool = False
    has_parametrize: bool = False

    @property
    def documentation_rate(self) -> float:
        """Calculate documentation coverage rate."""
        if self.total_tests == 0:
            return 0.0
        return self.documented_tests / self.total_tests

    @property
    def quality_score(self) -> float:
        """Calculate overall quality score (0-100)."""
        score = 100.0

        # Deduct for missing documentation
        doc_penalty = (1 - self.documentation_rate) * 20
        score -= doc_penalty

        # Deduct for test smells
        smell_penalty = min(len(self.test_smells) * 5, 30)
        score -= smell_penalty

        # Deduct for overly complex tests
        if self.total_tests > 0:
            complexity_rate = self.complex_tests / self.total_tests
            complexity_penalty = complexity_rate * 15
            score -= complexity_penalty

        # Bonus for using fixtures and parametrization
        if self.has_fixtures:
            score += 5
        if self.has_parametrize:
            score += 5

        return max(0.0, min(100.0, score))


class TestQualityAnalyzer(ast.NodeVisitor):
    """AST visitor for analyzing test quality."""

    def __init__(self):
        """Initialize analyzer."""
        self.metrics = TestQualityMetrics(file_path=Path())
        self.current_function: ast.FunctionDef | None = None

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definition to analyze tests."""
        self.current_function = node

        # Check if it's a test function
        if node.name.startswith("test_"):
            self.metrics.total_tests += 1

            # Check for docstring
            docstring = ast.get_docstring(node)
            if docstring and len(docstring.strip()) > 10:
                self.metrics.documented_tests += 1

            # Calculate test complexity (simple heuristic: number of statements)
            num_statements = sum(1 for _ in ast.walk(node) if isinstance(_, ast.stmt))
            if num_statements > 50:  # Arbitrary threshold
                self.metrics.complex_tests += 1

            # Detect test smells
            self._detect_test_smells(node)

        # Check for fixture usage
        if any(
            dec.id == "pytest.fixture" for dec in node.decorator_list if isinstance(dec, ast.Name)
        ):
            self.metrics.has_fixtures = True

        # Check for parametrize usage
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Attribute):
                    if decorator.func.attr == "parametrize":
                        self.metrics.has_parametrize = True

        self.generic_visit(node)

    def _detect_test_smells(self, node: ast.FunctionDef) -> None:
        """Detect common test smells in a test function."""
        # Smell 1: Too many assertions (indicates test doing too much)
        assertions = [n for n in ast.walk(node) if isinstance(n, ast.Assert)]
        if len(assertions) > 10:
            self.metrics.test_smells.append(f"{node.name}: Too many assertions ({len(assertions)})")

        # Smell 2: No assertions at all
        if len(assertions) == 0:
            # Check if it's not using pytest.raises or similar
            has_pytest_raises = any(isinstance(n, ast.With) for n in ast.walk(node))
            if not has_pytest_raises:
                self.metrics.test_smells.append(f"{node.name}: No assertions found")

        # Smell 3: Test contains print statements (debugging left in)
        prints = [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "print"
        ]
        if prints:
            self.metrics.test_smells.append(
                f"{node.name}: Contains print statements ({len(prints)})"
            )

        # Smell 4: Sleep calls (makes tests slow)
        sleeps = [
            n
            for n in ast.walk(node)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "sleep"
        ]
        if sleeps:
            self.metrics.test_smells.append(f"{node.name}: Contains sleep calls ({len(sleeps)})")

        # Smell 5: Hardcoded values that should be parametrized
        # Check for similar test names (indication that tests should be parametrized)
        if "_1" in node.name or "_2" in node.name or "_test1" in node.name:
            self.metrics.test_smells.append(f"{node.name}: Might benefit from parametrization")


class TestQualityValidator:
    """Validates test quality across the test suite."""

    def __init__(self, test_dir: Path):
        """Initialize validator with test directory."""
        self.test_dir = test_dir
        self.file_metrics: list[TestQualityMetrics] = []

    def analyze_file(self, file_path: Path) -> TestQualityMetrics:
        """Analyze a single test file."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            tree = ast.parse(content, filename=str(file_path))
            analyzer = TestQualityAnalyzer()
            analyzer.metrics.file_path = file_path
            analyzer.visit(tree)

            return analyzer.metrics
        except SyntaxError as e:
            print(f"⚠️  Syntax error in {file_path}: {e}")
            return TestQualityMetrics(file_path=file_path)
        except Exception as e:
            print(f"⚠️  Error analyzing {file_path}: {e}")
            return TestQualityMetrics(file_path=file_path)

    def validate_suite(self) -> dict[str, Any]:
        """Validate the entire test suite."""
        print(f"Analyzing test suite in {self.test_dir}...")

        # Find all test files
        test_files = list(self.test_dir.rglob("test_*.py"))
        print(f"Found {len(test_files)} test files\n")

        # Analyze each file
        for test_file in test_files:
            metrics = self.analyze_file(test_file)
            if metrics.total_tests > 0:  # Only include files with tests
                self.file_metrics.append(metrics)

        # Calculate aggregate metrics
        total_tests = sum(m.total_tests for m in self.file_metrics)
        total_documented = sum(m.documented_tests for m in self.file_metrics)
        total_smells = sum(len(m.test_smells) for m in self.file_metrics)
        avg_quality_score = (
            sum(m.quality_score for m in self.file_metrics) / len(self.file_metrics)
            if self.file_metrics
            else 0.0
        )

        # Find problematic files
        low_quality_files = [m for m in self.file_metrics if m.quality_score < 60]
        undocumented_files = [m for m in self.file_metrics if m.documentation_rate < 0.5]

        report = {
            "summary": {
                "total_test_files": len(self.file_metrics),
                "total_tests": total_tests,
                "documented_tests": total_documented,
                "documentation_rate": (total_documented / total_tests if total_tests > 0 else 0),
                "total_smells": total_smells,
                "avg_quality_score": avg_quality_score,
            },
            "problematic_files": {
                "low_quality": [
                    {
                        "path": str(m.file_path.relative_to(self.test_dir)),
                        "quality_score": m.quality_score,
                        "tests": m.total_tests,
                        "smells": len(m.test_smells),
                    }
                    for m in low_quality_files[:10]  # Top 10 worst
                ],
                "poorly_documented": [
                    {
                        "path": str(m.file_path.relative_to(self.test_dir)),
                        "documentation_rate": m.documentation_rate,
                        "tests": m.total_tests,
                        "documented": m.documented_tests,
                    }
                    for m in undocumented_files[:10]  # Top 10 worst
                ],
            },
            "details": [
                {
                    "file": str(m.file_path.relative_to(self.test_dir)),
                    "total_tests": m.total_tests,
                    "documented_tests": m.documented_tests,
                    "documentation_rate": m.documentation_rate,
                    "quality_score": m.quality_score,
                    "smells": m.test_smells,
                }
                for m in self.file_metrics
            ],
        }

        return report

    def print_summary(self, report: dict[str, Any]) -> None:
        """Print a summary of the validation results."""
        summary = report["summary"]

        print("\n" + "=" * 70)
        print("TEST QUALITY VALIDATION SUMMARY")
        print("=" * 70)
        print(f"\nTotal Test Files: {summary['total_test_files']}")
        print(f"Total Tests: {summary['total_tests']}")
        print(
            f"Documented Tests: {summary['documented_tests']} ({summary['documentation_rate']:.1%})"
        )
        print(f"Total Test Smells: {summary['total_smells']}")
        print(f"Average Quality Score: {summary['avg_quality_score']:.1f}/100")

        # Quality assessment
        if summary["avg_quality_score"] >= 80:
            print("\n✅ EXCELLENT - Test suite has high quality")
        elif summary["avg_quality_score"] >= 60:
            print("\n⚠️  GOOD - Test suite quality is acceptable but can be improved")
        else:
            print("\n❌ NEEDS IMPROVEMENT - Test suite quality is below acceptable standards")

        # Show problematic files
        if report["problematic_files"]["low_quality"]:
            print("\n📉 Files with Low Quality Score:")
            for file_info in report["problematic_files"]["low_quality"][:5]:
                print(
                    f"  - {file_info['path']}: Score {file_info['quality_score']:.1f}, "
                    f"{file_info['smells']} smells"
                )

        if report["problematic_files"]["poorly_documented"]:
            print("\n📝 Poorly Documented Files:")
            for file_info in report["problematic_files"]["poorly_documented"][:5]:
                print(
                    f"  - {file_info['path']}: {file_info['documentation_rate']:.1%} documented "
                    f"({file_info['documented']}/{file_info['tests']})"
                )


def main(argv: list[str] | None = None) -> int:
    """Main entry point for test quality validator."""
    parser = argparse.ArgumentParser(
        description="Validate test quality metrics across the test suite"
    )
    parser.add_argument(
        "--test-dir",
        type=Path,
        default=Path("tests"),
        help="Directory containing tests (default: tests)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Output JSON report file",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=70.0,
        help="Minimum acceptable quality score (default: 70.0)",
    )
    parser.add_argument(
        "--fail-under",
        action="store_true",
        help="Exit with error if quality score is below threshold",
    )

    args = parser.parse_args(argv or sys.argv[1:])

    validator = TestQualityValidator(test_dir=args.test_dir)
    report = validator.validate_suite()
    validator.print_summary(report)

    # Write report if requested
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"\n📄 Report written to {args.report}")

    # Check threshold
    avg_score = report["summary"]["avg_quality_score"]
    if args.fail_under and avg_score < args.threshold:
        print(f"\n❌ Quality score {avg_score:.1f} is below threshold {args.threshold:.1f}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
