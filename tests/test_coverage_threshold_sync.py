#!/usr/bin/env python3
"""Test to ensure coverage threshold configuration stays synchronized.

This test validates that coverage thresholds are consistent across:
- pyproject.toml (fail_under)
- configs/quality/coverage_baseline.json (line_rate)
- .github/workflows/tests.yml (LINE_THRESHOLD)
"""

import json
import re
import sys
from pathlib import Path


def test_coverage_threshold_sync():
    """Verify all coverage thresholds are synchronized."""
    repo_root = Path(__file__).parent.parent
    
    # Read pyproject.toml
    pyproject_path = repo_root / "pyproject.toml"
    with open(pyproject_path) as f:
        pyproject_content = f.read()
    
    match = re.search(r'fail_under\s*=\s*(\d+)', pyproject_content)
    if not match:
        print("❌ Could not find fail_under in pyproject.toml")
        return False
    pyproject_threshold = int(match.group(1))
    
    # Read coverage_baseline.json
    baseline_path = repo_root / "configs" / "quality" / "coverage_baseline.json"
    with open(baseline_path) as f:
        baseline = json.load(f)
    baseline_threshold = int(baseline["line_rate"])
    
    # Read tests.yml
    tests_yml_path = repo_root / ".github" / "workflows" / "tests.yml"
    with open(tests_yml_path) as f:
        tests_yml_content = f.read()
    
    match = re.search(r'LINE_THRESHOLD:\s*"(\d+(?:\.\d+)?)"', tests_yml_content)
    if not match:
        print("❌ Could not find LINE_THRESHOLD in tests.yml")
        return False
    workflow_threshold = int(float(match.group(1)))
    
    # Verify all match
    print(f"pyproject.toml fail_under: {pyproject_threshold}%")
    print(f"coverage_baseline.json line_rate: {baseline_threshold}%")
    print(f"tests.yml LINE_THRESHOLD: {workflow_threshold}%")
    
    if pyproject_threshold == baseline_threshold == workflow_threshold:
        print(f"✅ All coverage thresholds synchronized at {pyproject_threshold}%")
        return True
    else:
        print(f"❌ Coverage thresholds are NOT synchronized!")
        print(f"   Expected all to be {pyproject_threshold}%, but found:")
        print(f"   - pyproject.toml: {pyproject_threshold}%")
        print(f"   - coverage_baseline.json: {baseline_threshold}%")
        print(f"   - tests.yml: {workflow_threshold}%")
        return False


if __name__ == "__main__":
    success = test_coverage_threshold_sync()
    sys.exit(0 if success else 1)
