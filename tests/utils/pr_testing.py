"""Utilities for PR-related testing.

This module provides helpers for testing PR validation logic, test coverage,
and quality gates that run during the PR lifecycle.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class PRFileChange:
    """Represents a file change in a pull request."""
    
    filename: str
    status: str  # 'added', 'modified', 'removed', 'renamed'
    additions: int
    deletions: int
    patch: Optional[str] = None
    
    @property
    def is_test_file(self) -> bool:
        """Check if this is a test file."""
        return is_test_file(self.filename)
    
    @property
    def is_source_file(self) -> bool:
        """Check if this is a source code file (non-test)."""
        return is_source_file(self.filename) and not self.is_test_file
    
    @property
    def is_documentation(self) -> bool:
        """Check if this is a documentation file."""
        return is_documentation_file(self.filename)


@dataclass
class PRTestCoverage:
    """Represents test coverage metrics for a PR."""
    
    line_coverage: float
    branch_coverage: float
    files_covered: int
    files_total: int
    lines_covered: int
    lines_total: int
    
    @property
    def meets_threshold(self, threshold: float = 97.0) -> bool:
        """Check if coverage meets the required threshold."""
        return self.line_coverage >= threshold and self.branch_coverage >= threshold
    
    @property
    def coverage_delta(self) -> float:
        """Calculate the coverage delta from perfect coverage."""
        return 100.0 - min(self.line_coverage, self.branch_coverage)


def is_test_file(filepath: str) -> bool:
    """Determine if a file is a test file.
    
    Args:
        filepath: Path to the file
        
    Returns:
        True if the file is a test file
    """
    path = Path(filepath)
    normalized = filepath.lower()
    
    # Check directory-based patterns
    parts = path.parts
    if any(part in {"tests", "test", "__tests__", "specs", "spec"} for part in parts):
        return True
    
    # Check filename patterns
    name = path.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    if name.startswith("test-") or name.endswith("-test.py"):
        return True
    if name.endswith("_spec.py") or name.endswith(".spec.py"):
        return True
    if name.endswith(".test.ts") or name.endswith(".test.tsx"):
        return True
    if name.endswith(".spec.ts") or name.endswith(".spec.tsx"):
        return True
    if name.endswith(".test.js") or name.endswith(".test.jsx"):
        return True
    
    return False


def is_source_file(filepath: str) -> bool:
    """Determine if a file is a source code file.
    
    Args:
        filepath: Path to the file
        
    Returns:
        True if the file is source code
    """
    source_extensions = {
        ".py", ".pyx", ".pyi",
        ".js", ".jsx", ".ts", ".tsx",
        ".go", ".rs", ".c", ".cpp", ".cc", ".h", ".hpp",
        ".java", ".kt", ".scala",
        ".rb", ".php", ".swift",
    }
    
    path = Path(filepath)
    return path.suffix in source_extensions


def is_documentation_file(filepath: str) -> bool:
    """Determine if a file is documentation.
    
    Args:
        filepath: Path to the file
        
    Returns:
        True if the file is documentation
    """
    path = Path(filepath)
    
    # Check for documentation directories
    parts = path.parts
    if any(part in {"docs", "doc", "documentation"} for part in parts):
        return True
    
    # Check for documentation file extensions
    doc_extensions = {".md", ".rst", ".txt", ".adoc"}
    if path.suffix in doc_extensions:
        return True
    
    # Check for common documentation files
    doc_names = {
        "README", "CHANGELOG", "CONTRIBUTING", "LICENSE",
        "AUTHORS", "NOTICE", "SECURITY", "CODE_OF_CONDUCT"
    }
    if path.stem.upper() in doc_names:
        return True
    
    return False


def analyze_pr_changes(files: List[PRFileChange]) -> Dict[str, Any]:
    """Analyze PR file changes to determine testing requirements.
    
    Args:
        files: List of file changes in the PR
        
    Returns:
        Dictionary with analysis results
    """
    test_files = [f for f in files if f.is_test_file]
    source_files = [f for f in files if f.is_source_file]
    doc_files = [f for f in files if f.is_documentation]
    
    return {
        "total_files": len(files),
        "test_files": len(test_files),
        "source_files": len(source_files),
        "documentation_files": len(doc_files),
        "has_tests": len(test_files) > 0,
        "has_source_changes": len(source_files) > 0,
        "is_documentation_only": len(doc_files) > 0 and len(source_files) == 0 and len(test_files) == 0,
        "test_to_source_ratio": len(test_files) / max(len(source_files), 1),
        "requires_new_tests": len(source_files) > 0 and len(test_files) == 0,
    }


def extract_test_markers_from_file(filepath: Path) -> Set[str]:
    """Extract pytest markers from a test file.
    
    Args:
        filepath: Path to the test file
        
    Returns:
        Set of marker names found in the file
    """
    if not filepath.exists():
        return set()
    
    content = filepath.read_text(encoding="utf-8")
    markers = set()
    
    # Find @pytest.mark.marker_name patterns
    marker_pattern = r"@pytest\.mark\.(\w+)"
    for match in re.finditer(marker_pattern, content):
        markers.add(match.group(1))
    
    return markers


def calculate_test_coverage_for_module(module_path: str, coverage_data: Dict[str, Any]) -> Optional[float]:
    """Calculate test coverage for a specific module.
    
    Args:
        module_path: Path to the module
        coverage_data: Coverage data dictionary
        
    Returns:
        Coverage percentage or None if not found
    """
    if not coverage_data:
        return None
    
    # Normalize path
    normalized_path = Path(module_path).as_posix()
    
    # Check if coverage data contains this module
    files = coverage_data.get("files", {})
    if normalized_path in files:
        file_data = files[normalized_path]
        covered = file_data.get("covered_lines", 0)
        total = file_data.get("num_statements", 0)
        if total > 0:
            return (covered / total) * 100.0
    
    return None


def validate_pr_test_requirements(
    changes: List[PRFileChange],
    coverage: Optional[PRTestCoverage] = None,
    min_coverage: float = 97.0,
) -> Dict[str, Any]:
    """Validate that a PR meets test requirements.
    
    Args:
        changes: List of file changes in the PR
        coverage: Test coverage metrics
        min_coverage: Minimum required coverage percentage
        
    Returns:
        Validation results dictionary
    """
    analysis = analyze_pr_changes(changes)
    
    issues = []
    warnings = []
    
    # Check if source changes have corresponding tests
    if analysis["requires_new_tests"]:
        issues.append("Source code changes without accompanying tests")
    
    # Check coverage threshold
    if coverage and not coverage.meets_threshold(min_coverage):
        issues.append(
            f"Coverage {coverage.line_coverage:.2f}% below threshold {min_coverage}%"
        )
    
    # Check test-to-source ratio
    if analysis["has_source_changes"]:
        ratio = analysis["test_to_source_ratio"]
        if ratio < 0.5:
            warnings.append(
                f"Low test-to-source ratio: {ratio:.2f} (expected >= 0.5)"
            )
    
    return {
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "analysis": analysis,
        "coverage": {
            "line": coverage.line_coverage if coverage else None,
            "branch": coverage.branch_coverage if coverage else None,
            "meets_threshold": coverage.meets_threshold(min_coverage) if coverage else None,
        }
    }


def get_affected_test_files(changed_files: List[str], test_root: Path = Path("tests")) -> List[Path]:
    """Determine which test files should run based on changed source files.
    
    Args:
        changed_files: List of changed file paths
        test_root: Root directory for tests
        
    Returns:
        List of test files that should be executed
    """
    affected_tests = set()
    
    for filepath in changed_files:
        if is_test_file(filepath):
            # Test file was directly modified
            affected_tests.add(Path(filepath))
        elif is_source_file(filepath):
            # Find corresponding test files
            path = Path(filepath)
            
            # Strategy 1: Look for test_{name}.py pattern
            test_file = test_root / f"test_{path.stem}.py"
            if test_file.exists():
                affected_tests.add(test_file)
            
            # Strategy 2: Look for tests/unit/{module}/test_{name}.py pattern
            if path.parts:
                module = path.parts[0]
                unit_test = test_root / "unit" / module / f"test_{path.stem}.py"
                if unit_test.exists():
                    affected_tests.add(unit_test)
            
            # Strategy 3: Look for tests/{module}/test_{name}.py pattern
            if len(path.parts) > 1:
                module = path.parts[0]
                test_file = test_root / module / f"test_{path.stem}.py"
                if test_file.exists():
                    affected_tests.add(test_file)
    
    return sorted(affected_tests)


def check_pr_description_quality(description: str) -> Dict[str, Any]:
    """Check the quality of a PR description.
    
    Args:
        description: PR description text
        
    Returns:
        Dictionary with quality metrics
    """
    issues = []
    warnings = []
    
    if not description or len(description.strip()) < 10:
        issues.append("PR description is too short")
    
    # Check for common sections
    description_lower = description.lower()
    
    sections = {
        "summary": ["summary", "overview", "description"],
        "changes": ["changes", "what's changed", "modifications"],
        "testing": ["testing", "tests", "test plan"],
        "checklist": ["checklist", "- [ ]", "- [x]"],
    }
    
    missing_sections = []
    for section, keywords in sections.items():
        if not any(keyword in description_lower for keyword in keywords):
            missing_sections.append(section)
    
    if missing_sections:
        warnings.append(f"PR description missing sections: {', '.join(missing_sections)}")
    
    # Check word count
    words = len(description.split())
    if words < 20:
        warnings.append(f"PR description is brief ({words} words)")
    
    return {
        "has_description": bool(description and description.strip()),
        "word_count": words if description else 0,
        "missing_sections": missing_sections,
        "issues": issues,
        "warnings": warnings,
        "quality_score": max(0, 100 - len(issues) * 30 - len(warnings) * 10),
    }


def suggest_test_improvements(analysis: Dict[str, Any]) -> List[str]:
    """Suggest test improvements based on PR analysis.
    
    Args:
        analysis: PR analysis results from analyze_pr_changes
        
    Returns:
        List of improvement suggestions
    """
    suggestions = []
    
    if analysis.get("requires_new_tests"):
        suggestions.append(
            "Add unit tests for new source code files"
        )
    
    if analysis.get("test_to_source_ratio", 1.0) < 0.3:
        suggestions.append(
            "Consider adding more test coverage (current ratio is low)"
        )
    
    if analysis.get("has_source_changes") and not analysis.get("has_tests"):
        suggestions.append(
            "Add integration tests to verify end-to-end behavior"
        )
        suggestions.append(
            "Consider adding property-based tests for edge cases"
        )
    
    return suggestions
