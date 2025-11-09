"""Fixtures and test data for PR testing scenarios.

This module provides reusable fixtures for testing PR validation,
coverage analysis, and quality gates.
"""
from __future__ import annotations

from typing import Any, Dict, List

import pytest

from tests.utils.pr_testing import PRFileChange, PRTestCoverage


@pytest.fixture
def minimal_pr_changes() -> List[PRFileChange]:
    """Single file change PR."""
    return [
        PRFileChange("src/module.py", "modified", 10, 5),
    ]


@pytest.fixture
def well_tested_pr_changes() -> List[PRFileChange]:
    """PR with source and test changes in good ratio."""
    return [
        PRFileChange("src/module.py", "modified", 100, 20),
        PRFileChange("src/utils.py", "added", 50, 0),
        PRFileChange("tests/test_module.py", "modified", 80, 10),
        PRFileChange("tests/test_utils.py", "added", 40, 0),
    ]


@pytest.fixture
def untested_pr_changes() -> List[PRFileChange]:
    """PR with source changes but no tests."""
    return [
        PRFileChange("src/new_feature.py", "added", 200, 0),
        PRFileChange("src/helper.py", "added", 50, 0),
    ]


@pytest.fixture
def documentation_only_pr_changes() -> List[PRFileChange]:
    """PR with only documentation changes."""
    return [
        PRFileChange("README.md", "modified", 30, 10),
        PRFileChange("docs/guide.md", "added", 100, 0),
        PRFileChange("CHANGELOG.md", "modified", 5, 0),
    ]


@pytest.fixture
def test_only_pr_changes() -> List[PRFileChange]:
    """PR with only test changes."""
    return [
        PRFileChange("tests/test_feature.py", "added", 150, 0),
        PRFileChange("tests/integration/test_workflow.py", "modified", 40, 15),
    ]


@pytest.fixture
def mixed_pr_changes() -> List[PRFileChange]:
    """PR with mixed changes (source, tests, docs)."""
    return [
        PRFileChange("src/core/indicator.py", "modified", 80, 30),
        PRFileChange("tests/test_indicator.py", "modified", 60, 20),
        PRFileChange("docs/indicators.md", "modified", 20, 5),
        PRFileChange("README.md", "modified", 10, 2),
    ]


@pytest.fixture
def excellent_coverage() -> PRTestCoverage:
    """Coverage data meeting high standards."""
    return PRTestCoverage(
        line_coverage=99.5,
        branch_coverage=98.5,
        files_covered=50,
        files_total=50,
        lines_covered=1990,
        lines_total=2000,
    )


@pytest.fixture
def good_coverage() -> PRTestCoverage:
    """Coverage data meeting minimum requirements."""
    return PRTestCoverage(
        line_coverage=97.5,
        branch_coverage=97.0,
        files_covered=45,
        files_total=50,
        lines_covered=1950,
        lines_total=2000,
    )


@pytest.fixture
def marginal_coverage() -> PRTestCoverage:
    """Coverage data just below threshold."""
    return PRTestCoverage(
        line_coverage=96.5,
        branch_coverage=95.0,
        files_covered=40,
        files_total=50,
        lines_covered=1930,
        lines_total=2000,
    )


@pytest.fixture
def poor_coverage() -> PRTestCoverage:
    """Coverage data well below standards."""
    return PRTestCoverage(
        line_coverage=85.0,
        branch_coverage=82.0,
        files_covered=30,
        files_total=50,
        lines_covered=1700,
        lines_total=2000,
    )


@pytest.fixture
def sample_pr_description_good() -> str:
    """Well-formatted PR description."""
    return """
## Summary
This PR implements feature X to improve the trading algorithm's performance
by optimizing the Kuramoto oscillator synchronization calculations.

## Changes
- Refactored `core/indicators/kuramoto.py` for better performance
- Added vectorized operations using NumPy
- Updated tests to cover edge cases
- Added benchmarks to measure performance improvements

## Performance Impact
- Reduced computation time by 35%
- Memory usage decreased by 20%
- Maintained numerical stability

## Testing
- [x] Added unit tests for new vectorized operations
- [x] Updated integration tests
- [x] Ran performance benchmarks
- [x] Verified backward compatibility

## Documentation
- Updated docstrings
- Added performance notes to README

## Checklist
- [x] Tests pass locally
- [x] Code follows style guidelines
- [x] Documentation updated
- [x] No breaking changes
- [x] Coverage threshold met
"""


@pytest.fixture
def sample_pr_description_minimal() -> str:
    """Minimal PR description."""
    return "Fixed bug in module"


@pytest.fixture
def sample_pr_description_empty() -> str:
    """Empty PR description."""
    return ""


@pytest.fixture
def sample_coverage_data() -> Dict[str, Any]:
    """Sample coverage data in standard format."""
    return {
        "files": {
            "src/module.py": {
                "covered_lines": 95,
                "num_statements": 100,
                "missing_lines": [15, 23, 45, 67, 89],
            },
            "src/utils.py": {
                "covered_lines": 48,
                "num_statements": 50,
                "missing_lines": [12, 34],
            },
            "tests/test_module.py": {
                "covered_lines": 100,
                "num_statements": 100,
                "missing_lines": [],
            },
        },
        "totals": {
            "covered_lines": 243,
            "num_statements": 250,
            "percent_covered": 97.2,
        },
    }


@pytest.fixture
def github_workflow_context() -> Dict[str, Any]:
    """Simulated GitHub Actions workflow context."""
    return {
        "event_name": "pull_request",
        "repository": "neuron7x/TradePulse",
        "ref": "refs/pull/123/merge",
        "sha": "abc123def456",
        "actor": "developer",
        "pull_request": {
            "number": 123,
            "title": "feat: Add new indicator",
            "base": {
                "ref": "main",
                "sha": "base123",
            },
            "head": {
                "ref": "feature-branch",
                "sha": "head456",
            },
        },
    }


@pytest.fixture
def pr_labels_test_needed() -> List[str]:
    """PR labels indicating tests are needed."""
    return ["test-needed", "missing-coverage"]


@pytest.fixture
def pr_labels_ready() -> List[str]:
    """PR labels indicating PR is ready."""
    return ["ready-for-review", "approved"]


@pytest.fixture
def pr_files_with_tests() -> List[Dict[str, Any]]:
    """GitHub API response for PR files with tests."""
    return [
        {
            "filename": "src/core/indicator.py",
            "status": "modified",
            "additions": 50,
            "deletions": 20,
            "changes": 70,
        },
        {
            "filename": "tests/test_indicator.py",
            "status": "modified",
            "additions": 40,
            "deletions": 5,
            "changes": 45,
        },
    ]


@pytest.fixture
def pr_files_without_tests() -> List[Dict[str, Any]]:
    """GitHub API response for PR files without tests."""
    return [
        {
            "filename": "src/new_feature.py",
            "status": "added",
            "additions": 150,
            "deletions": 0,
            "changes": 150,
        },
        {
            "filename": "src/helper.py",
            "status": "added",
            "additions": 80,
            "deletions": 0,
            "changes": 80,
        },
    ]


@pytest.fixture
def workflow_test_matrix() -> Dict[str, List[str]]:
    """Test matrix configuration for CI workflows."""
    return {
        "python-version": ["3.11", "3.12"],
        "os": ["ubuntu-latest", "windows-latest", "macos-latest"],
        "test-suite": ["unit", "integration", "e2e"],
    }


@pytest.fixture
def coverage_report_xml() -> str:
    """Sample coverage.xml content."""
    return """<?xml version="1.0" ?>
<coverage version="7.3.0" timestamp="1699564800000" lines-valid="1000" lines-covered="970" line-rate="0.97" branches-valid="200" branches-covered="194" branch-rate="0.97" complexity="0">
    <packages>
        <package name="core" line-rate="0.98" branch-rate="0.97" complexity="0">
            <classes>
                <class name="indicator.py" filename="core/indicator.py" line-rate="0.98" branch-rate="0.97" complexity="0">
                    <methods/>
                    <lines>
                        <line number="1" hits="1"/>
                        <line number="2" hits="1"/>
                        <line number="3" hits="0"/>
                    </lines>
                </class>
            </classes>
        </package>
    </packages>
</coverage>
"""


@pytest.fixture
def pytest_junit_xml() -> str:
    """Sample pytest JUnit XML output."""
    return """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
    <testsuite name="pytest" errors="0" failures="0" skipped="0" tests="100" time="45.234">
        <testcase classname="tests.test_module" name="test_feature" time="0.001"/>
        <testcase classname="tests.test_module" name="test_edge_case" time="0.002"/>
        <testcase classname="tests.test_integration" name="test_workflow" time="1.234"/>
    </testsuite>
</testsuites>
"""


@pytest.fixture
def flaky_test_report() -> Dict[str, Any]:
    """Sample flaky test report."""
    return {
        "flaky_tests": [
            {
                "nodeid": "tests/test_network.py::test_api_call",
                "location": {
                    "path": "tests/test_network.py",
                    "line": 45,
                    "name": "test_api_call",
                },
                "attempts": 3,
                "reruns": 2,
                "outcome": "passed",
                "first_failure": "ConnectionError: Failed to connect",
            },
        ],
        "total_flaky": 1,
        "pass_rate": 0.67,
    }
