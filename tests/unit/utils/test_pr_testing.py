"""Tests for PR testing utilities.

This test suite validates the PR testing helper functions that analyze
PR changes, test coverage, and quality gates.
"""
from __future__ import annotations

import pytest

from tests.utils.pr_testing import (
    PRFileChange,
    PRTestCoverage,
    analyze_pr_changes,
    check_pr_description_quality,
    get_affected_test_files,
    is_documentation_file,
    is_source_file,
    is_test_file,
    suggest_test_improvements,
    validate_pr_test_requirements,
)


class TestIsTestFile:
    """Tests for is_test_file function."""
    
    def test_detects_test_directory(self) -> None:
        """Test files in tests/ directory are detected."""
        assert is_test_file("tests/unit/test_foo.py")
        assert is_test_file("tests/integration/test_bar.py")
        assert is_test_file("src/tests/test_baz.py")
    
    def test_detects_test_prefix(self) -> None:
        """Files with test_ prefix are detected."""
        assert is_test_file("test_something.py")
        assert is_test_file("src/test_module.py")
    
    def test_detects_test_suffix(self) -> None:
        """Files with _test suffix are detected."""
        assert is_test_file("something_test.py")
        assert is_test_file("module_test.py")
    
    def test_detects_javascript_test_files(self) -> None:
        """JavaScript test files are detected."""
        assert is_test_file("component.test.ts")
        assert is_test_file("component.spec.ts")
        assert is_test_file("module.test.js")
    
    def test_rejects_non_test_files(self) -> None:
        """Non-test files are not detected as tests."""
        assert not is_test_file("src/module.py")
        assert not is_test_file("core/indicator.py")
        assert not is_test_file("README.md")


class TestIsSourceFile:
    """Tests for is_source_file function."""
    
    def test_detects_python_files(self) -> None:
        """Python source files are detected."""
        assert is_source_file("module.py")
        assert is_source_file("src/core/indicator.py")
        assert is_source_file("extension.pyx")
    
    def test_detects_javascript_files(self) -> None:
        """JavaScript source files are detected."""
        assert is_source_file("component.ts")
        assert is_source_file("app.tsx")
        assert is_source_file("module.js")
    
    def test_detects_other_languages(self) -> None:
        """Other language source files are detected."""
        assert is_source_file("service.go")
        assert is_source_file("lib.rs")
        assert is_source_file("Class.java")
    
    def test_rejects_non_source_files(self) -> None:
        """Non-source files are not detected."""
        assert not is_source_file("README.md")
        assert not is_source_file("config.yaml")
        assert not is_source_file("data.json")


class TestIsDocumentationFile:
    """Tests for is_documentation_file function."""
    
    def test_detects_markdown_files(self) -> None:
        """Markdown files are detected as documentation."""
        assert is_documentation_file("README.md")
        assert is_documentation_file("CONTRIBUTING.md")
        assert is_documentation_file("docs/guide.md")
    
    def test_detects_docs_directory(self) -> None:
        """Files in docs/ directory are detected."""
        assert is_documentation_file("docs/architecture.md")
        assert is_documentation_file("docs/api/reference.rst")
    
    def test_detects_common_doc_files(self) -> None:
        """Common documentation files are detected."""
        assert is_documentation_file("LICENSE")
        assert is_documentation_file("CHANGELOG")
        assert is_documentation_file("NOTICE.txt")
    
    def test_rejects_non_documentation(self) -> None:
        """Non-documentation files are not detected."""
        assert not is_documentation_file("src/module.py")
        assert not is_documentation_file("test_something.py")


class TestPRFileChange:
    """Tests for PRFileChange dataclass."""
    
    def test_identifies_test_file(self) -> None:
        """PRFileChange correctly identifies test files."""
        change = PRFileChange("tests/test_foo.py", "added", 10, 0)
        assert change.is_test_file
        assert not change.is_source_file
        assert not change.is_documentation
    
    def test_identifies_source_file(self) -> None:
        """PRFileChange correctly identifies source files."""
        change = PRFileChange("src/module.py", "modified", 5, 2)
        assert change.is_source_file
        assert not change.is_test_file
        assert not change.is_documentation
    
    def test_identifies_documentation(self) -> None:
        """PRFileChange correctly identifies documentation."""
        change = PRFileChange("docs/guide.md", "modified", 20, 5)
        assert change.is_documentation
        assert not change.is_source_file
        assert not change.is_test_file


class TestAnalyzePRChanges:
    """Tests for analyze_pr_changes function."""
    
    def test_analyzes_empty_pr(self) -> None:
        """Analysis handles empty PR."""
        result = analyze_pr_changes([])
        assert result["total_files"] == 0
        assert result["test_files"] == 0
        assert result["source_files"] == 0
        assert not result["has_tests"]
    
    def test_analyzes_test_only_pr(self) -> None:
        """Analysis handles PR with only test changes."""
        changes = [
            PRFileChange("tests/test_foo.py", "added", 50, 0),
            PRFileChange("tests/test_bar.py", "modified", 10, 5),
        ]
        result = analyze_pr_changes(changes)
        
        assert result["total_files"] == 2
        assert result["test_files"] == 2
        assert result["source_files"] == 0
        assert result["has_tests"]
        assert not result["requires_new_tests"]
    
    def test_analyzes_source_without_tests(self) -> None:
        """Analysis detects source changes without tests."""
        changes = [
            PRFileChange("src/module.py", "added", 100, 0),
        ]
        result = analyze_pr_changes(changes)
        
        assert result["source_files"] == 1
        assert result["test_files"] == 0
        assert result["requires_new_tests"]
    
    def test_analyzes_documentation_only_pr(self) -> None:
        """Analysis detects documentation-only PRs."""
        changes = [
            PRFileChange("README.md", "modified", 10, 5),
            PRFileChange("docs/guide.md", "added", 50, 0),
        ]
        result = analyze_pr_changes(changes)
        
        assert result["is_documentation_only"]
        assert not result["requires_new_tests"]
    
    def test_calculates_test_to_source_ratio(self) -> None:
        """Analysis calculates test-to-source ratio."""
        changes = [
            PRFileChange("src/foo.py", "added", 100, 0),
            PRFileChange("src/bar.py", "added", 80, 0),
            PRFileChange("tests/test_foo.py", "added", 50, 0),
            PRFileChange("tests/test_bar.py", "added", 40, 0),
        ]
        result = analyze_pr_changes(changes)
        
        assert result["test_files"] == 2
        assert result["source_files"] == 2
        assert result["test_to_source_ratio"] == 1.0


class TestPRTestCoverage:
    """Tests for PRTestCoverage dataclass."""
    
    def test_meets_threshold_when_above(self) -> None:
        """Coverage meets threshold when both line and branch coverage are above."""
        coverage = PRTestCoverage(98.0, 98.0, 10, 10, 980, 1000)
        assert coverage.meets_threshold(97.0)
    
    def test_fails_threshold_when_line_below(self) -> None:
        """Coverage fails threshold when line coverage is below."""
        coverage = PRTestCoverage(96.0, 98.0, 10, 10, 960, 1000)
        assert not coverage.meets_threshold(97.0)
    
    def test_fails_threshold_when_branch_below(self) -> None:
        """Coverage fails threshold when branch coverage is below."""
        coverage = PRTestCoverage(98.0, 96.0, 10, 10, 980, 1000)
        assert not coverage.meets_threshold(97.0)
    
    def test_calculates_coverage_delta(self) -> None:
        """Coverage delta is calculated correctly."""
        coverage = PRTestCoverage(95.5, 94.0, 10, 10, 955, 1000)
        assert coverage.coverage_delta == 6.0  # 100 - 94


class TestValidatePRTestRequirements:
    """Tests for validate_pr_test_requirements function."""
    
    def test_validates_pr_with_tests_and_coverage(self) -> None:
        """PR with tests and good coverage is valid."""
        changes = [
            PRFileChange("src/module.py", "added", 100, 0),
            PRFileChange("tests/test_module.py", "added", 50, 0),
        ]
        coverage = PRTestCoverage(98.0, 98.0, 1, 1, 980, 1000)
        
        result = validate_pr_test_requirements(changes, coverage)
        
        assert result["valid"]
        assert len(result["issues"]) == 0
    
    def test_fails_pr_without_tests(self) -> None:
        """PR with source changes but no tests is invalid."""
        changes = [
            PRFileChange("src/module.py", "added", 100, 0),
        ]
        
        result = validate_pr_test_requirements(changes)
        
        assert not result["valid"]
        assert any("without accompanying tests" in issue for issue in result["issues"])
    
    def test_fails_pr_with_low_coverage(self) -> None:
        """PR with coverage below threshold is invalid."""
        changes = [
            PRFileChange("src/module.py", "added", 100, 0),
            PRFileChange("tests/test_module.py", "added", 20, 0),
        ]
        coverage = PRTestCoverage(85.0, 85.0, 1, 1, 850, 1000)
        
        result = validate_pr_test_requirements(changes, coverage, min_coverage=90.0)
        
        assert not result["valid"]
        assert any("below threshold" in issue for issue in result["issues"])
    
    def test_warns_on_low_test_ratio(self) -> None:
        """PR with low test-to-source ratio gets warning."""
        changes = [
            PRFileChange("src/module.py", "added", 200, 0),
            PRFileChange("tests/test_module.py", "added", 20, 0),
        ]
        coverage = PRTestCoverage(98.0, 98.0, 1, 1, 980, 1000)
        
        result = validate_pr_test_requirements(changes, coverage)
        
        assert result["valid"]  # Still valid
        assert len(result["warnings"]) > 0
        assert any("test-to-source ratio" in warning for warning in result["warnings"])


class TestCheckPRDescriptionQuality:
    """Tests for check_pr_description_quality function."""
    
    def test_validates_good_description(self) -> None:
        """Well-formed PR description passes validation."""
        description = """
        ## Summary
        This PR adds new feature X to improve performance.
        
        ## Changes
        - Added new module
        - Updated tests
        
        ## Testing
        - Added unit tests
        - Verified manually
        
        ## Checklist
        - [x] Tests added
        - [x] Documentation updated
        """
        
        result = check_pr_description_quality(description)
        
        assert result["has_description"]
        assert result["word_count"] > 20
        assert len(result["issues"]) == 0
        assert result["quality_score"] > 80
    
    def test_fails_empty_description(self) -> None:
        """Empty PR description fails validation."""
        result = check_pr_description_quality("")
        
        assert not result["has_description"]
        assert len(result["issues"]) > 0
        assert "too short" in result["issues"][0]
    
    def test_warns_on_missing_sections(self) -> None:
        """PR description missing sections gets warnings."""
        description = "Just a quick fix"
        
        result = check_pr_description_quality(description)
        
        assert len(result["warnings"]) > 0
        assert len(result["missing_sections"]) > 0
    
    def test_warns_on_brief_description(self) -> None:
        """Brief PR description gets warning."""
        description = "Fixed bug in module"
        
        result = check_pr_description_quality(description)
        
        assert result["has_description"]
        assert any("brief" in warning.lower() for warning in result["warnings"])


class TestSuggestTestImprovements:
    """Tests for suggest_test_improvements function."""
    
    def test_suggests_tests_for_source_changes(self) -> None:
        """Suggestions include adding tests when source changed without tests."""
        analysis = {
            "requires_new_tests": True,
            "has_source_changes": True,
            "has_tests": False,
            "test_to_source_ratio": 0.0,
        }
        
        suggestions = suggest_test_improvements(analysis)
        
        assert len(suggestions) > 0
        assert any("unit tests" in s.lower() for s in suggestions)
        assert any("integration tests" in s.lower() for s in suggestions)
    
    def test_suggests_more_coverage_for_low_ratio(self) -> None:
        """Suggestions include more coverage when ratio is low."""
        analysis = {
            "requires_new_tests": False,
            "has_source_changes": True,
            "has_tests": True,
            "test_to_source_ratio": 0.2,
        }
        
        suggestions = suggest_test_improvements(analysis)
        
        assert len(suggestions) > 0
        assert any("more test coverage" in s.lower() for s in suggestions)
    
    def test_no_suggestions_for_good_coverage(self) -> None:
        """No suggestions when coverage is good."""
        analysis = {
            "requires_new_tests": False,
            "has_source_changes": True,
            "has_tests": True,
            "test_to_source_ratio": 1.0,
        }
        
        suggestions = suggest_test_improvements(analysis)
        
        # Should have minimal or no suggestions
        assert len(suggestions) <= 1
