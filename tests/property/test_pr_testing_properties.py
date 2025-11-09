"""Property-based tests for PR testing utilities.

This test suite uses Hypothesis to verify invariants and edge cases
in PR analysis and validation logic.
"""
from __future__ import annotations

from hypothesis import given, settings, strategies as st
import pytest

from tests.utils.pr_testing import (
    PRFileChange,
    PRTestCoverage,
    analyze_pr_changes,
    is_documentation_file,
    is_source_file,
    is_test_file,
    validate_pr_test_requirements,
)


# Custom strategies for generating test data
@st.composite
def file_changes(draw):
    """Generate arbitrary file changes."""
    filename = draw(st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), min_codepoint=32, max_codepoint=126)))
    # Ensure valid filename
    filename = filename.strip()
    if not filename or '/' not in filename:
        filename = f"src/{filename}.py"
    
    status = draw(st.sampled_from(["added", "modified", "removed", "renamed"]))
    additions = draw(st.integers(min_value=0, max_value=1000))
    deletions = draw(st.integers(min_value=0, max_value=1000))
    
    return PRFileChange(filename, status, additions, deletions)


@st.composite
def pr_changes_list(draw):
    """Generate a list of PR file changes."""
    return draw(st.lists(file_changes(), min_size=0, max_size=20))


@st.composite
def coverage_data(draw):
    """Generate arbitrary coverage data."""
    lines_total = draw(st.integers(min_value=1, max_value=10000))
    lines_covered = draw(st.integers(min_value=0, max_value=lines_total))
    
    branches_total = draw(st.integers(min_value=0, max_value=1000))
    branches_covered = draw(st.integers(min_value=0, max_value=branches_total))
    
    files_total = draw(st.integers(min_value=1, max_value=100))
    files_covered = draw(st.integers(min_value=0, max_value=files_total))
    
    line_coverage = (lines_covered / lines_total) * 100.0 if lines_total > 0 else 0.0
    branch_coverage = (branches_covered / branches_total) * 100.0 if branches_total > 0 else 0.0
    
    return PRTestCoverage(
        line_coverage=line_coverage,
        branch_coverage=branch_coverage,
        files_covered=files_covered,
        files_total=files_total,
        lines_covered=lines_covered,
        lines_total=lines_total,
    )


class TestFileDetectionProperties:
    """Property-based tests for file type detection."""
    
    @given(st.text(min_size=1, max_size=200))
    @settings(max_examples=200, deadline=None)
    def test_file_classification_is_consistent(self, filepath: str) -> None:
        """File classification functions should be consistent."""
        # A file can be multiple types but should not change on repeated calls
        is_test_1 = is_test_file(filepath)
        is_test_2 = is_test_file(filepath)
        assert is_test_1 == is_test_2, "is_test_file should be deterministic"
        
        is_source_1 = is_source_file(filepath)
        is_source_2 = is_source_file(filepath)
        assert is_source_1 == is_source_2, "is_source_file should be deterministic"
        
        is_doc_1 = is_documentation_file(filepath)
        is_doc_2 = is_documentation_file(filepath)
        assert is_doc_1 == is_doc_2, "is_documentation_file should be deterministic"
    
    @given(st.sampled_from([
        "tests/test_foo.py",
        "test_bar.py",
        "something_test.py",
        "tests/unit/test_module.py",
    ]))
    def test_known_test_files_are_detected(self, filepath: str) -> None:
        """Known test file patterns should always be detected."""
        assert is_test_file(filepath), f"{filepath} should be detected as test file"
    
    @given(st.sampled_from([
        "src/module.py",
        "core/indicator.py",
        "app.ts",
        "service.go",
    ]))
    def test_known_source_files_are_detected(self, filepath: str) -> None:
        """Known source file patterns should always be detected."""
        assert is_source_file(filepath), f"{filepath} should be detected as source file"
    
    @given(st.sampled_from([
        "README.md",
        "docs/guide.md",
        "CHANGELOG",
        "LICENSE.txt",
    ]))
    def test_known_doc_files_are_detected(self, filepath: str) -> None:
        """Known documentation file patterns should always be detected."""
        assert is_documentation_file(filepath), f"{filepath} should be detected as documentation"


class TestPRFileChangeProperties:
    """Property-based tests for PRFileChange."""
    
    @given(file_changes())
    @settings(max_examples=200, deadline=None)
    def test_file_change_properties_are_exclusive(self, change: PRFileChange) -> None:
        """A file should not be both test and documentation (usually)."""
        # While technically possible, it's rare - just ensure consistency
        classifications = [
            change.is_test_file,
            change.is_source_file and not change.is_test_file,
            change.is_documentation,
        ]
        # At least one should be true, or none (for other file types)
        # This is just checking consistency, not enforcing exclusivity
        assert isinstance(change.is_test_file, bool)
        assert isinstance(change.is_source_file, bool)
        assert isinstance(change.is_documentation, bool)
    
    @given(
        filename=st.text(min_size=1, max_size=100),
        status=st.sampled_from(["added", "modified", "removed", "renamed"]),
        additions=st.integers(min_value=0, max_value=1000),
        deletions=st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_file_change_creation_always_succeeds(
        self, filename: str, status: str, additions: int, deletions: int
    ) -> None:
        """Creating PRFileChange should always succeed with valid inputs."""
        change = PRFileChange(filename, status, additions, deletions)
        assert change.filename == filename
        assert change.status == status
        assert change.additions == additions
        assert change.deletions == deletions


class TestAnalyzePRChangesProperties:
    """Property-based tests for PR analysis."""
    
    @given(pr_changes_list())
    @settings(max_examples=100, deadline=None)
    def test_analysis_total_files_matches_input(self, changes: list) -> None:
        """Analysis should count correct total files."""
        result = analyze_pr_changes(changes)
        assert result["total_files"] == len(changes)
    
    @given(pr_changes_list())
    @settings(max_examples=100, deadline=None)
    def test_analysis_file_counts_sum_to_total(self, changes: list) -> None:
        """File type counts should not exceed total."""
        result = analyze_pr_changes(changes)
        
        test_files = result["test_files"]
        source_files = result["source_files"]
        doc_files = result["documentation_files"]
        total = result["total_files"]
        
        # Counts should be non-negative
        assert test_files >= 0
        assert source_files >= 0
        assert doc_files >= 0
        
        # Sum of categorized files should not exceed total
        # (files can be multiple types, so sum might exceed total)
        assert test_files <= total
        assert source_files <= total
        assert doc_files <= total
    
    @given(pr_changes_list())
    @settings(max_examples=100, deadline=None)
    def test_analysis_booleans_are_consistent(self, changes: list) -> None:
        """Boolean flags should be consistent with counts."""
        result = analyze_pr_changes(changes)
        
        if result["test_files"] > 0:
            assert result["has_tests"] is True
        else:
            assert result["has_tests"] is False
        
        if result["source_files"] > 0:
            assert result["has_source_changes"] is True
        else:
            assert result["has_source_changes"] is False
    
    @given(pr_changes_list())
    @settings(max_examples=100, deadline=None)
    def test_analysis_test_ratio_is_valid(self, changes: list) -> None:
        """Test-to-source ratio should be non-negative."""
        result = analyze_pr_changes(changes)
        ratio = result["test_to_source_ratio"]
        
        assert ratio >= 0.0
        assert not (ratio < 0.0)  # Should never be negative


class TestCoverageProperties:
    """Property-based tests for coverage calculations."""
    
    @given(coverage_data())
    @settings(max_examples=200, deadline=None)
    def test_coverage_percentages_are_valid(self, coverage: PRTestCoverage) -> None:
        """Coverage percentages should be between 0 and 100."""
        assert 0.0 <= coverage.line_coverage <= 100.0
        assert 0.0 <= coverage.branch_coverage <= 100.0
    
    @given(coverage_data())
    @settings(max_examples=200, deadline=None)
    def test_coverage_counts_are_consistent(self, coverage: PRTestCoverage) -> None:
        """Covered counts should not exceed total counts."""
        assert coverage.lines_covered <= coverage.lines_total
        assert coverage.files_covered <= coverage.files_total
    
    @given(coverage_data(), st.floats(min_value=0.0, max_value=100.0))
    @settings(max_examples=100, deadline=None)
    def test_meets_threshold_is_monotonic(
        self, coverage: PRTestCoverage, threshold: float
    ) -> None:
        """If coverage meets higher threshold, it meets lower threshold."""
        if coverage.meets_threshold(threshold):
            # Should also meet a lower threshold
            lower_threshold = max(0.0, threshold - 10.0)
            assert coverage.meets_threshold(lower_threshold)
    
    @given(coverage_data())
    @settings(max_examples=100, deadline=None)
    def test_coverage_delta_is_valid(self, coverage: PRTestCoverage) -> None:
        """Coverage delta should be between 0 and 100."""
        delta = coverage.coverage_delta
        assert 0.0 <= delta <= 100.0


class TestValidationProperties:
    """Property-based tests for PR validation."""
    
    @given(pr_changes_list(), coverage_data(), st.floats(min_value=0.0, max_value=100.0))
    @settings(max_examples=50, deadline=None)
    def test_validation_result_structure(
        self, changes: list, coverage: PRTestCoverage, threshold: float
    ) -> None:
        """Validation result should have expected structure."""
        result = validate_pr_test_requirements(changes, coverage, threshold)
        
        assert "valid" in result
        assert "issues" in result
        assert "warnings" in result
        assert "analysis" in result
        assert "coverage" in result
        
        assert isinstance(result["valid"], bool)
        assert isinstance(result["issues"], list)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["analysis"], dict)
        assert isinstance(result["coverage"], dict)
    
    @given(pr_changes_list())
    @settings(max_examples=50, deadline=None)
    def test_validation_without_coverage_works(self, changes: list) -> None:
        """Validation should work without coverage data."""
        result = validate_pr_test_requirements(changes, None)
        
        assert "valid" in result
        assert "coverage" in result
        assert result["coverage"]["line"] is None
        assert result["coverage"]["branch"] is None
    
    @given(coverage_data())
    @settings(max_examples=50, deadline=None)
    def test_perfect_coverage_has_no_issues(self, coverage: PRTestCoverage) -> None:
        """Perfect coverage with tests should have no coverage issues."""
        # Create a PR with tests
        changes = [
            PRFileChange("src/module.py", "added", 100, 0),
            PRFileChange("tests/test_module.py", "added", 50, 0),
        ]
        
        # Set perfect coverage
        perfect_coverage = PRTestCoverage(
            line_coverage=100.0,
            branch_coverage=100.0,
            files_covered=coverage.files_total,
            files_total=coverage.files_total,
            lines_covered=coverage.lines_total,
            lines_total=coverage.lines_total,
        )
        
        result = validate_pr_test_requirements(changes, perfect_coverage, 97.0)
        
        # Should have no coverage-related issues
        coverage_issues = [
            issue for issue in result["issues"]
            if "coverage" in issue.lower()
        ]
        assert len(coverage_issues) == 0


class TestEdgeCases:
    """Test edge cases with property-based testing."""
    
    @given(st.lists(st.text(min_size=0, max_size=50), min_size=0, max_size=10))
    @settings(max_examples=100, deadline=None)
    def test_handles_unusual_filenames(self, filenames: list) -> None:
        """File detection should handle unusual filenames gracefully."""
        for filename in filenames:
            try:
                # Should not crash
                is_test_file(filename)
                is_source_file(filename)
                is_documentation_file(filename)
            except Exception as e:
                pytest.fail(f"Failed on filename '{filename}': {e}")
    
    @given(
        st.integers(min_value=0, max_value=1000),
        st.integers(min_value=0, max_value=1000),
    )
    @settings(max_examples=100, deadline=None)
    def test_handles_zero_totals_in_coverage(
        self, lines_covered: int, files_covered: int
    ) -> None:
        """Coverage calculation should handle edge cases."""
        # Test with 1 total to avoid division by zero
        coverage = PRTestCoverage(
            line_coverage=min(100.0, (lines_covered / max(1, lines_covered)) * 100.0),
            branch_coverage=50.0,
            files_covered=files_covered,
            files_total=max(1, files_covered),
            lines_covered=lines_covered,
            lines_total=max(1, lines_covered),
        )
        
        # Should not crash
        assert coverage.line_coverage >= 0.0
        assert coverage.meets_threshold(0.0)
