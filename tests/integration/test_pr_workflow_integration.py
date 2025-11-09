"""Integration tests for PR workflow.

This test suite validates end-to-end PR workflow scenarios including
validation, coverage checking, and label management.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pytest

from tests.utils.pr_testing import (
    PRFileChange,
    PRTestCoverage,
    analyze_pr_changes,
    check_pr_description_quality,
    get_affected_test_files,
    suggest_test_improvements,
    validate_pr_test_requirements,
)


class TestPRWorkflowIntegration:
    """Integration tests for complete PR workflows."""
    
    def test_complete_pr_validation_workflow_success(self) -> None:
        """Test complete PR validation for a well-formed PR."""
        # Setup: Good PR with source, tests, and documentation
        changes = [
            PRFileChange("src/core/indicator.py", "modified", 100, 20),
            PRFileChange("tests/test_indicator.py", "modified", 80, 10),
            PRFileChange("docs/indicators.md", "modified", 20, 5),
        ]
        
        coverage = PRTestCoverage(
            line_coverage=98.5,
            branch_coverage=97.5,
            files_covered=50,
            files_total=50,
            lines_covered=1970,
            lines_total=2000,
        )
        
        description = """
        ## Summary
        Improved indicator performance through vectorization.
        
        ## Changes
        - Optimized calculations
        - Added tests for edge cases
        - Updated documentation
        
        ## Testing
        - All tests pass
        - Coverage maintained at 98%
        
        ## Checklist
        - [x] Tests added
        - [x] Documentation updated
        """
        
        # Execute: Validate PR
        analysis = analyze_pr_changes(changes)
        validation = validate_pr_test_requirements(changes, coverage)
        desc_quality = check_pr_description_quality(description)
        suggestions = suggest_test_improvements(analysis)
        
        # Assert: PR should pass all validations
        assert analysis["has_tests"]
        assert analysis["has_source_changes"]
        assert analysis["test_to_source_ratio"] > 0.5
        
        assert validation["valid"]
        assert len(validation["issues"]) == 0
        
        assert desc_quality["has_description"]
        assert desc_quality["quality_score"] > 80
        
        # Should have minimal suggestions
        assert len(suggestions) <= 1
    
    def test_complete_pr_validation_workflow_failure(self) -> None:
        """Test complete PR validation for a poorly-formed PR."""
        # Setup: Bad PR with only source changes
        changes = [
            PRFileChange("src/new_module.py", "added", 300, 0),
            PRFileChange("src/helper.py", "added", 150, 0),
        ]
        
        coverage = PRTestCoverage(
            line_coverage=85.0,
            branch_coverage=80.0,
            files_covered=40,
            files_total=52,
            lines_covered=1700,
            lines_total=2000,
        )
        
        description = "Quick fix"
        
        # Execute: Validate PR
        analysis = analyze_pr_changes(changes)
        validation = validate_pr_test_requirements(changes, coverage, min_coverage=90.0)
        desc_quality = check_pr_description_quality(description)
        suggestions = suggest_test_improvements(analysis)
        
        # Assert: PR should fail validations
        assert not analysis["has_tests"]
        assert analysis["requires_new_tests"]
        
        assert not validation["valid"]
        assert len(validation["issues"]) > 0
        
        assert desc_quality["quality_score"] < 50
        assert len(desc_quality["warnings"]) > 0
        
        # Should have multiple suggestions
        assert len(suggestions) >= 2
    
    def test_documentation_only_pr_workflow(self) -> None:
        """Test PR workflow for documentation-only changes."""
        # Setup: Documentation-only PR
        changes = [
            PRFileChange("README.md", "modified", 50, 10),
            PRFileChange("docs/guide.md", "added", 200, 0),
            PRFileChange("CHANGELOG.md", "modified", 10, 0),
        ]
        
        description = """
        ## Summary
        Updated documentation for v2.0 release.
        
        ## Changes
        - Updated README with new features
        - Added user guide
        - Updated changelog
        """
        
        # Execute: Validate PR
        analysis = analyze_pr_changes(changes)
        validation = validate_pr_test_requirements(changes, None)
        desc_quality = check_pr_description_quality(description)
        
        # Assert: Documentation-only PR should be valid without tests
        assert analysis["is_documentation_only"]
        assert not analysis["requires_new_tests"]
        
        # Should be valid (no test requirement for docs)
        assert validation["valid"]
        
        assert desc_quality["has_description"]
    
    def test_test_only_pr_workflow(self) -> None:
        """Test PR workflow for test-only changes."""
        # Setup: Test-only PR
        changes = [
            PRFileChange("tests/test_new_feature.py", "added", 200, 0),
            PRFileChange("tests/integration/test_workflow.py", "modified", 50, 10),
        ]
        
        coverage = PRTestCoverage(
            line_coverage=98.0,
            branch_coverage=97.0,
            files_covered=51,
            files_total=51,
            lines_covered=1960,
            lines_total=2000,
        )
        
        # Execute: Validate PR
        analysis = analyze_pr_changes(changes)
        validation = validate_pr_test_requirements(changes, coverage)
        
        # Assert: Test-only PR should be valid
        assert analysis["has_tests"]
        assert not analysis["has_source_changes"]
        assert not analysis["requires_new_tests"]
        
        assert validation["valid"]


class TestAffectedTestDetection:
    """Integration tests for detecting affected test files."""
    
    def test_finds_tests_for_changed_source_files(self, tmp_path: Path) -> None:
        """Test detection of test files for changed source files."""
        # Setup: Create test file structure
        test_root = tmp_path / "tests"
        test_root.mkdir()
        
        (test_root / "test_module.py").touch()
        
        unit_dir = test_root / "unit" / "core"
        unit_dir.mkdir(parents=True)
        (unit_dir / "test_indicator.py").touch()
        
        # Execute: Find affected tests
        changed_files = [
            "core/indicator.py",
            "src/module.py",
        ]
        
        affected = get_affected_test_files(changed_files, test_root)
        
        # Assert: Should find corresponding test files
        assert len(affected) > 0
        assert any("test_module.py" in str(f) for f in affected)
        assert any("test_indicator.py" in str(f) for f in affected)
    
    def test_includes_directly_modified_test_files(self, tmp_path: Path) -> None:
        """Test that directly modified test files are included."""
        # Setup
        test_root = tmp_path / "tests"
        test_root.mkdir()
        
        test_file = test_root / "test_feature.py"
        test_file.touch()
        
        # Execute
        changed_files = [
            str(test_file),
            "src/feature.py",
        ]
        
        affected = get_affected_test_files(changed_files, test_root)
        
        # Assert: Should include the test file
        assert any(str(test_file) in str(f) for f in affected)


class TestPRValidationScenarios:
    """Integration tests for various PR validation scenarios."""
    
    def test_large_refactoring_pr_with_comprehensive_tests(self) -> None:
        """Test validation of large refactoring PR."""
        changes = [
            # Many source files changed
            PRFileChange("src/core/indicator.py", "modified", 200, 150),
            PRFileChange("src/core/phase.py", "modified", 100, 80),
            PRFileChange("src/utils/math.py", "modified", 50, 30),
            # Comprehensive test updates
            PRFileChange("tests/test_indicator.py", "modified", 150, 100),
            PRFileChange("tests/test_phase.py", "modified", 80, 50),
            PRFileChange("tests/test_math.py", "modified", 40, 20),
            # Integration tests added
            PRFileChange("tests/integration/test_refactor.py", "added", 200, 0),
        ]
        
        coverage = PRTestCoverage(
            line_coverage=97.5,
            branch_coverage=97.0,
            files_covered=50,
            files_total=50,
            lines_covered=1950,
            lines_total=2000,
        )
        
        validation = validate_pr_test_requirements(changes, coverage)
        
        # Large refactoring with tests should be valid
        assert validation["valid"]
        
        analysis = analyze_pr_changes(changes)
        # Good test ratio
        assert analysis["test_to_source_ratio"] > 0.8
    
    def test_bugfix_pr_with_regression_test(self) -> None:
        """Test validation of bugfix PR with regression test."""
        changes = [
            PRFileChange("src/module.py", "modified", 5, 2),
            PRFileChange("tests/test_module_regression.py", "added", 30, 0),
        ]
        
        coverage = PRTestCoverage(
            line_coverage=98.0,
            branch_coverage=97.5,
            files_covered=50,
            files_total=50,
            lines_covered=1960,
            lines_total=2000,
        )
        
        validation = validate_pr_test_requirements(changes, coverage)
        
        # Bugfix with regression test should be valid
        assert validation["valid"]
    
    def test_feature_pr_missing_integration_tests(self) -> None:
        """Test validation catches missing integration tests."""
        changes = [
            # New feature files
            PRFileChange("src/features/new_feature.py", "added", 300, 0),
            PRFileChange("src/features/helper.py", "added", 100, 0),
            # Only unit tests, no integration tests
            PRFileChange("tests/unit/test_new_feature.py", "added", 150, 0),
        ]
        
        coverage = PRTestCoverage(
            line_coverage=95.0,
            branch_coverage=93.0,
            files_covered=49,
            files_total=52,
            lines_covered=1900,
            lines_total=2000,
        )
        
        analysis = analyze_pr_changes(changes)
        suggestions = suggest_test_improvements(analysis)
        
        # Should suggest integration tests
        assert any("integration" in s.lower() for s in suggestions)


class TestCoverageWorkflow:
    """Integration tests for coverage calculation workflow."""
    
    def test_coverage_improvement_tracking(self) -> None:
        """Test tracking of coverage improvements in PR."""
        # Before: Lower coverage
        before_coverage = PRTestCoverage(
            line_coverage=95.0,
            branch_coverage=93.0,
            files_covered=48,
            files_total=50,
            lines_covered=1900,
            lines_total=2000,
        )
        
        # After: Improved coverage
        after_coverage = PRTestCoverage(
            line_coverage=98.0,
            branch_coverage=97.0,
            files_covered=50,
            files_total=50,
            lines_covered=1960,
            lines_total=2000,
        )
        
        # Coverage improved
        assert after_coverage.line_coverage > before_coverage.line_coverage
        assert after_coverage.branch_coverage > before_coverage.branch_coverage
        
        # Meets threshold now
        assert after_coverage.meets_threshold(97.0)
    
    def test_coverage_regression_detection(self) -> None:
        """Test detection of coverage regressions."""
        # Good coverage that regresses
        coverage = PRTestCoverage(
            line_coverage=96.0,
            branch_coverage=94.0,
            files_covered=48,
            files_total=50,
            lines_covered=1920,
            lines_total=2000,
        )
        
        changes = [
            PRFileChange("src/new_code.py", "added", 200, 0),
            # Insufficient tests for new code
            PRFileChange("tests/test_new_code.py", "added", 50, 0),
        ]
        
        validation = validate_pr_test_requirements(changes, coverage, min_coverage=97.0)
        
        # Should detect coverage below threshold
        assert not validation["valid"]
        assert any("coverage" in issue.lower() for issue in validation["issues"])


class TestDescriptionQualityWorkflow:
    """Integration tests for PR description quality workflow."""
    
    def test_description_improvement_suggestions(self) -> None:
        """Test generation of description improvement suggestions."""
        descriptions = [
            "Fix",  # Too short
            "Updated code",  # Brief
            "Fixed bug in module",  # Missing sections
        ]
        
        for desc in descriptions:
            quality = check_pr_description_quality(desc)
            
            # Should have issues or warnings
            assert len(quality["issues"]) > 0 or len(quality["warnings"]) > 0
            
            # Quality score should be low
            assert quality["quality_score"] < 70
    
    def test_complete_description_workflow(self) -> None:
        """Test complete description validation workflow."""
        # Good description
        good_desc = """
        ## Summary
        This PR adds comprehensive test coverage for the indicator module.
        
        ## Changes
        - Added 50 new unit tests
        - Added integration tests
        - Fixed edge case bugs
        
        ## Testing
        - All tests pass
        - Coverage increased from 95% to 98%
        
        ## Checklist
        - [x] Tests added
        - [x] Documentation updated
        """
        
        quality = check_pr_description_quality(good_desc)
        
        assert quality["has_description"]
        assert quality["quality_score"] > 85
        assert len(quality["missing_sections"]) <= 1
        assert quality["word_count"] > 30
