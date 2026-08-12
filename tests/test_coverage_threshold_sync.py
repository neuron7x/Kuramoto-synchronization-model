#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
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
    with open(pyproject_path, encoding="utf-8") as f:
        pyproject_content = f.read()

    match = re.search(r"fail_under\s*=\s*(\d+)", pyproject_content)
    if not match:
        print("❌ Could not find fail_under in pyproject.toml")
        return False
    pyproject_threshold = int(match.group(1))

    # Read coverage_baseline.json
    baseline_path = repo_root / "configs" / "quality" / "coverage_baseline.json"
    with open(baseline_path, encoding="utf-8") as f:
        baseline = json.load(f)
    baseline_threshold = int(baseline["line_rate"])

    # Read workflow file (may have been renamed from tests.yml)
    workflow_threshold = None
    for candidate in ("tests.yml", "main-validation.yml"):
        tests_yml_path = repo_root / ".github" / "workflows" / candidate
        if tests_yml_path.exists():
            with open(tests_yml_path) as f:
                tests_yml_content = f.read()
            match = re.search(r'LINE_THRESHOLD:\s*"(\d+(?:\.\d+)?)"', tests_yml_content)
            if match:
                workflow_threshold = int(float(match.group(1)))
                break

    # Verify pyproject.toml and baseline always match
    print(f"pyproject.toml fail_under: {pyproject_threshold}%")
    print(f"coverage_baseline.json line_rate: {baseline_threshold}%")
    if workflow_threshold is not None:
        print(f"workflow LINE_THRESHOLD: {workflow_threshold}%")

    thresholds = [pyproject_threshold, baseline_threshold]
    if workflow_threshold is not None:
        thresholds.append(workflow_threshold)

    if len(set(thresholds)) == 1:
        print(f"✅ All coverage thresholds synchronized at {pyproject_threshold}%")
        return True
    else:
        print(f"❌ Coverage thresholds are NOT synchronized: {thresholds}")
        assert (
            pyproject_threshold == baseline_threshold
        ), f"Coverage thresholds are NOT synchronized: {thresholds}"


def test_release_and_aspirational_gates_are_named_and_consistent():
    """The 90 (release) and 98 (aspirational) gates must be explicit, not drift.

    The plan's Phase 0 rule: 'No config claims 98 while release policy claims
    90 unless explicitly named aspirational.' This test makes that relationship
    a tested invariant:

      coverage_targets.current_release_gate    == 90  (release gate)
      coverage_targets.final_aspirational_gate == 98  (aspirational gate)
                                                == pyproject fail_under
                                                == coverage_baseline.line_rate
    """
    import tomllib

    repo_root = Path(__file__).parent.parent

    targets = tomllib.loads(
        (repo_root / "configs" / "quality" / "coverage_targets.toml").read_text(
            encoding="utf-8"
        )
    )
    release_gate = int(targets["global"]["current_release_gate"])
    aspirational_gate = int(targets["global"]["final_aspirational_gate"])

    assert release_gate < aspirational_gate, (
        "release gate must be strictly below the aspirational gate; "
        f"got release={release_gate}, aspirational={aspirational_gate}"
    )

    pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    fail_under = int(re.search(r"fail_under\s*=\s*(\d+)", pyproject).group(1))
    baseline = json.loads(
        (repo_root / "configs" / "quality" / "coverage_baseline.json").read_text(
            encoding="utf-8"
        )
    )
    baseline_rate = int(baseline["line_rate"])

    assert fail_under == aspirational_gate == baseline_rate, (
        "the aspirational gate must be a single named number across configs: "
        f"coverage_targets.final_aspirational_gate={aspirational_gate}, "
        f"pyproject fail_under={fail_under}, "
        f"coverage_baseline.line_rate={baseline_rate}"
    )


def test_canonical_release_coveragerc_declares_release_surface():
    """release_90.coveragerc must measure the full production surface, not a
    convenient subset — that subsetting is exactly the F02 lie this profile
    was created to end."""
    repo_root = Path(__file__).parent.parent
    text = (repo_root / "configs" / "quality" / "release_90.coveragerc").read_text(
        encoding="utf-8"
    )
    for surface in ("core", "backtest", "execution", "analytics"):
        assert re.search(rf"^\s+{surface}\s*$", text, re.MULTILINE), (
            f"release_90.coveragerc must declare '{surface}' under [run] source"
        )


if __name__ == "__main__":
    success = test_coverage_threshold_sync()
    sys.exit(0 if success else 1)
