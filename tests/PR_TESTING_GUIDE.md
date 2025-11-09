# PR Testing Guide

This guide explains how to use the PR testing utilities and write tests for pull request workflows.

## Overview

The PR testing infrastructure provides tools to validate pull requests, analyze changes, check test coverage, and ensure quality gates are met.

## Quick Start

```python
from tests.utils.pr_testing import (
    PRFileChange,
    PRTestCoverage,
    analyze_pr_changes,
    validate_pr_test_requirements,
    check_pr_description_quality,
)

# Analyze PR changes
changes = [
    PRFileChange("src/module.py", "modified", 100, 20),
    PRFileChange("tests/test_module.py", "modified", 80, 10),
]

analysis = analyze_pr_changes(changes)
print(f"Has tests: {analysis['has_tests']}")
print(f"Test ratio: {analysis['test_to_source_ratio']:.2f}")

# Validate coverage
coverage = PRTestCoverage(
    line_coverage=98.0,
    branch_coverage=97.0,
    files_covered=50,
    files_total=50,
    lines_covered=1960,
    lines_total=2000,
)

validation = validate_pr_test_requirements(changes, coverage)
if not validation['valid']:
    print("Issues:", validation['issues'])
```

## Core Components

### PRFileChange

Represents a file change in a pull request.

```python
change = PRFileChange(
    filename="src/indicator.py",
    status="modified",  # added, modified, removed, renamed
    additions=50,
    deletions=20,
    patch="<optional diff content>"
)

# Properties
change.is_test_file      # True if file is a test
change.is_source_file    # True if file is source code
change.is_documentation  # True if file is documentation
```

### PRTestCoverage

Represents test coverage metrics.

```python
coverage = PRTestCoverage(
    line_coverage=98.0,
    branch_coverage=97.0,
    files_covered=50,
    files_total=50,
    lines_covered=1960,
    lines_total=2000,
)

# Methods
coverage.meets_threshold(97.0)  # Check if meets threshold
coverage.coverage_delta          # Distance from perfect coverage
```

## Utility Functions

### analyze_pr_changes

Analyzes PR file changes to determine testing requirements.

```python
changes = [...]
analysis = analyze_pr_changes(changes)

# Returns:
# {
#     "total_files": int,
#     "test_files": int,
#     "source_files": int,
#     "documentation_files": int,
#     "has_tests": bool,
#     "has_source_changes": bool,
#     "is_documentation_only": bool,
#     "test_to_source_ratio": float,
#     "requires_new_tests": bool,
# }
```

### validate_pr_test_requirements

Validates that a PR meets test requirements.

```python
validation = validate_pr_test_requirements(
    changes,
    coverage,
    min_coverage=97.0
)

# Returns:
# {
#     "valid": bool,
#     "issues": List[str],        # Blocking issues
#     "warnings": List[str],       # Non-blocking warnings
#     "analysis": dict,
#     "coverage": dict,
# }
```

### check_pr_description_quality

Checks the quality of a PR description.

```python
quality = check_pr_description_quality(description_text)

# Returns:
# {
#     "has_description": bool,
#     "word_count": int,
#     "missing_sections": List[str],
#     "issues": List[str],
#     "warnings": List[str],
#     "quality_score": int,  # 0-100
# }
```

### get_affected_test_files

Determines which test files should run based on changed source files.

```python
from pathlib import Path

changed_files = [
    "src/core/indicator.py",
    "tests/test_other.py",
]

affected = get_affected_test_files(changed_files, Path("tests"))
# Returns: [Path("tests/test_indicator.py"), Path("tests/test_other.py")]
```

### suggest_test_improvements

Suggests test improvements based on PR analysis.

```python
suggestions = suggest_test_improvements(analysis)
# Returns: List[str] of improvement suggestions
```

## File Type Detection

### is_test_file

Detects if a file is a test file.

```python
from tests.utils.pr_testing import is_test_file

is_test_file("tests/test_module.py")        # True
is_test_file("test_something.py")           # True
is_test_file("module_test.py")              # True
is_test_file("component.test.ts")           # True
is_test_file("src/module.py")               # False
```

Patterns recognized:
- Files in `tests/`, `test/`, `__tests__/`, `specs/`, `spec/` directories
- Files with `test_` prefix or `_test` suffix
- Files with `.test.*` or `.spec.*` extensions

### is_source_file

Detects if a file is source code.

```python
from tests.utils.pr_testing import is_source_file

is_source_file("src/module.py")      # True
is_source_file("app.ts")             # True
is_source_file("service.go")         # True
is_source_file("README.md")          # False
```

Supported extensions: `.py`, `.pyx`, `.pyi`, `.js`, `.jsx`, `.ts`, `.tsx`, `.go`, `.rs`, `.c`, `.cpp`, `.h`, `.java`, `.kt`, `.rb`, `.php`, `.swift`

### is_documentation_file

Detects if a file is documentation.

```python
from tests.utils.pr_testing import is_documentation_file

is_documentation_file("README.md")           # True
is_documentation_file("docs/guide.md")       # True
is_documentation_file("LICENSE")             # True
is_documentation_file("CHANGELOG.md")        # True
```

## Test Fixtures

Use pre-built fixtures from `tests/fixtures/pr_scenarios.py`:

```python
from tests.fixtures.pr_scenarios import (
    well_tested_pr_changes,
    excellent_coverage,
    sample_pr_description_good,
)

def test_something(well_tested_pr_changes, excellent_coverage):
    validation = validate_pr_test_requirements(
        well_tested_pr_changes,
        excellent_coverage
    )
    assert validation['valid']
```

Available fixtures:
- **PR Changes**: `minimal_pr_changes`, `well_tested_pr_changes`, `untested_pr_changes`, `documentation_only_pr_changes`, `test_only_pr_changes`, `mixed_pr_changes`
- **Coverage**: `excellent_coverage`, `good_coverage`, `marginal_coverage`, `poor_coverage`
- **Descriptions**: `sample_pr_description_good`, `sample_pr_description_minimal`, `sample_pr_description_empty`
- **Workflow Context**: `github_workflow_context`, `workflow_test_matrix`
- **Reports**: `coverage_report_xml`, `pytest_junit_xml`, `flaky_test_report`

## Writing Workflow Tests

Test GitHub Actions workflows using the workflow testing pattern:

```python
from pathlib import Path
from typing import Any, Dict
import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "my-workflow.yml"

def _load_workflow() -> Dict[str, Any]:
    """Load and parse the workflow."""
    raw = WORKFLOW_PATH.read_text(encoding="utf-8")
    loaded = yaml.safe_load(raw)
    if not isinstance(loaded, dict):
        raise TypeError("workflow should deserialize into a mapping")
    return loaded

def test_workflow_triggers():
    """Verify workflow triggers."""
    workflow = _load_workflow()
    on_config = workflow.get(True) or workflow.get("on")
    assert "pull_request" in on_config

def test_workflow_permissions():
    """Ensure minimal permissions."""
    workflow = _load_workflow()
    permissions = workflow.get("permissions")
    assert permissions.get("contents") == "read"
```

See `tests/workflows/test_pr_quality_labels.py` for a complete example.

## Property-Based Testing

Use Hypothesis for property-based tests:

```python
from hypothesis import given, strategies as st
from tests.utils.pr_testing import is_test_file

@given(st.sampled_from([
    "tests/test_foo.py",
    "test_bar.py",
    "something_test.py",
]))
def test_known_test_files_are_detected(filepath: str) -> None:
    """Known test file patterns should always be detected."""
    assert is_test_file(filepath)
```

See `tests/property/test_pr_testing_properties.py` for examples.

## Integration Testing

Test complete workflows end-to-end:

```python
def test_complete_pr_validation_workflow_success() -> None:
    """Test complete PR validation for a well-formed PR."""
    changes = [
        PRFileChange("src/module.py", "modified", 100, 20),
        PRFileChange("tests/test_module.py", "modified", 80, 10),
    ]
    
    coverage = PRTestCoverage(...)
    
    analysis = analyze_pr_changes(changes)
    validation = validate_pr_test_requirements(changes, coverage)
    
    assert validation["valid"]
    assert analysis["has_tests"]
```

See `tests/integration/test_pr_workflow_integration.py` for examples.

## Best Practices

### 1. Test All File Types

Ensure your tests cover all file type detection scenarios:

```python
def test_detects_all_test_patterns():
    """Test all test file patterns."""
    patterns = [
        "tests/test_foo.py",
        "test_bar.py",
        "baz_test.py",
        "component.test.ts",
        "module.spec.js",
    ]
    for pattern in patterns:
        assert is_test_file(pattern)
```

### 2. Test Edge Cases

Use property-based testing for edge cases:

```python
from hypothesis import given, strategies as st

@given(st.text())
def test_handles_unusual_filenames(filename: str):
    """File detection should handle unusual filenames gracefully."""
    try:
        is_test_file(filename)
        is_source_file(filename)
        is_documentation_file(filename)
    except Exception as e:
        pytest.fail(f"Failed on filename '{filename}': {e}")
```

### 3. Validate Complete Workflows

Test entire PR workflows, not just individual functions:

```python
def test_complete_workflow():
    """Test entire PR validation workflow."""
    # Setup
    changes = [...]
    coverage = PRTestCoverage(...)
    description = "..."
    
    # Analyze
    analysis = analyze_pr_changes(changes)
    validation = validate_pr_test_requirements(changes, coverage)
    quality = check_pr_description_quality(description)
    suggestions = suggest_test_improvements(analysis)
    
    # Assert complete workflow
    assert validation["valid"]
    assert quality["quality_score"] > 80
    assert len(suggestions) <= 1
```

### 4. Use Fixtures for Consistency

Use shared fixtures for common scenarios:

```python
def test_with_fixture(well_tested_pr_changes, excellent_coverage):
    """Use fixtures for consistent test data."""
    validation = validate_pr_test_requirements(
        well_tested_pr_changes,
        excellent_coverage
    )
    assert validation["valid"]
```

## Common Patterns

### Pattern 1: Validate PR Before Merge

```python
def validate_pr(pr_number: int) -> bool:
    """Validate PR meets all requirements."""
    changes = fetch_pr_changes(pr_number)
    coverage = fetch_pr_coverage(pr_number)
    description = fetch_pr_description(pr_number)
    
    analysis = analyze_pr_changes(changes)
    validation = validate_pr_test_requirements(changes, coverage)
    quality = check_pr_description_quality(description)
    
    return (
        validation["valid"] and
        quality["quality_score"] > 70 and
        not analysis["requires_new_tests"]
    )
```

### Pattern 2: Auto-Label PRs

```python
def determine_pr_labels(changes: List[PRFileChange]) -> List[str]:
    """Determine which labels to apply to PR."""
    labels = []
    
    analysis = analyze_pr_changes(changes)
    
    if analysis["requires_new_tests"]:
        labels.append("test-needed")
    
    if analysis["is_documentation_only"]:
        labels.append("documentation")
    
    if not analysis["has_source_changes"]:
        labels.append("test-only")
    
    return labels
```

### Pattern 3: Generate PR Reports

```python
def generate_pr_report(changes, coverage, description):
    """Generate comprehensive PR quality report."""
    analysis = analyze_pr_changes(changes)
    validation = validate_pr_test_requirements(changes, coverage)
    quality = check_pr_description_quality(description)
    suggestions = suggest_test_improvements(analysis)
    
    report = {
        "summary": {
            "valid": validation["valid"],
            "quality_score": quality["quality_score"],
        },
        "analysis": analysis,
        "issues": validation["issues"],
        "warnings": validation["warnings"],
        "suggestions": suggestions,
    }
    
    return report
```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: PR Quality Check

on:
  pull_request:
    types: [opened, reopened, synchronize]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      
      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r requirements-dev.txt
      
      - name: Run PR validation tests
        run: |
          pytest tests/workflows/ -v
          pytest tests/integration/test_pr_workflow_integration.py -v
```

## Troubleshooting

### Issue: Tests not detected

**Problem**: `is_test_file()` returns False for valid test files.

**Solution**: Check if the file matches any of the recognized patterns:
- In `tests/`, `test/`, `__tests__/`, `specs/`, `spec/` directory
- Has `test_` prefix or `_test` suffix
- Has `.test.*` or `.spec.*` extension

### Issue: Coverage validation fails

**Problem**: `validate_pr_test_requirements()` fails even with good coverage.

**Solution**: Check that both line and branch coverage meet the threshold:
```python
coverage.meets_threshold(97.0)  # Checks both line AND branch
```

### Issue: PR description quality too low

**Problem**: Good descriptions get low quality scores.

**Solution**: Ensure the description includes key sections:
- Summary/Overview
- Changes/Modifications
- Testing/Test Plan
- Checklist

## Further Reading

- [TESTING.md](../TESTING.md) - Main testing guide
- [tests/workflows/](../tests/workflows/) - Workflow test examples
- [tests/property/](../tests/property/) - Property-based test examples
- [tests/integration/](../tests/integration/) - Integration test examples

## Contributing

When adding new PR testing utilities:

1. Add utility function to `tests/utils/pr_testing.py`
2. Add unit tests to `tests/unit/utils/test_pr_testing.py`
3. Add property tests to `tests/property/test_pr_testing_properties.py`
4. Add integration tests to `tests/integration/test_pr_workflow_integration.py`
5. Add fixtures to `tests/fixtures/pr_scenarios.py` if needed
6. Update this guide with examples

## Support

For questions or issues:
- Open an issue on GitHub
- Check existing workflow tests for examples
- Review property-based tests for edge case handling
