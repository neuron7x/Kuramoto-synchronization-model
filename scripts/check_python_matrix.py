#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Python Version Matrix Guard - Ensures consistency across Dockerfile, CI workflows, and pyproject.toml
This script prevents version drift by validating that all Python versions are within the supported range.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple


def parse_requires_python(pyproject_path: Path) -> Tuple[str, str]:
    """Parse requires-python from pyproject.toml."""
    content = pyproject_path.read_text()
    match = re.search(r'requires-python\s*=\s*"([^"]+)"', content)
    if not match:
        print("❌ ERROR: Could not find requires-python in pyproject.toml")
        sys.exit(1)

    version_spec = match.group(1)
    # Parse >=X.Y,<X.Z format
    min_match = re.search(r">=(\d+\.\d+)", version_spec)
    max_match = re.search(r"<(\d+\.\d+)", version_spec)

    if not min_match or not max_match:
        print(f"❌ ERROR: Unexpected requires-python format: {version_spec}")
        print("Expected format: '>=X.Y,<X.Z'")
        sys.exit(1)

    return min_match.group(1), max_match.group(1)


def check_dockerfiles(repo_root: Path, min_ver: str, max_ver: str) -> List[str]:
    """Check Python versions in Dockerfiles."""
    issues = []
    dockerfiles = list(repo_root.glob("**/Dockerfile*"))

    min_major, min_minor = map(int, min_ver.split("."))
    max_major, max_minor = map(int, max_ver.split("."))

    for dockerfile in dockerfiles:
        content = dockerfile.read_text()
        # Find all FROM python:X.Y lines
        for match in re.finditer(r"FROM\s+python:(\d+\.\d+)", content):
            version = match.group(1)
            major, minor = map(int, version.split("."))

            # Check if version is in range [min_ver, max_ver)
            if (major, minor) < (min_major, min_minor) or (major, minor) >= (max_major, max_minor):
                rel_path = dockerfile.relative_to(repo_root)
                issues.append(
                    f"  ❌ {rel_path}: python:{version} (out of range: >={min_ver},<{max_ver})"
                )

    return issues


def check_workflows(repo_root: Path, min_ver: str, max_ver: str) -> List[str]:
    """Check Python versions in GitHub workflows."""
    issues = []
    workflow_dir = repo_root / ".github" / "workflows"

    if not workflow_dir.exists():
        return issues

    min_major, min_minor = map(int, min_ver.split("."))
    max_major, max_minor = map(int, max_ver.split("."))

    for workflow in workflow_dir.glob("*.yml"):
        content = workflow.read_text()

        # Find python-version specifications
        # Match: python-version: "X.Y" or python-version: ['X.Y', 'X.Z']
        for match in re.finditer(r'python-version:\s*["\']?(\d+\.\d+)["\']?', content):
            version = match.group(1)
            major, minor = map(int, version.split("."))

            if (major, minor) < (min_major, min_minor) or (major, minor) >= (max_major, max_minor):
                rel_path = workflow.relative_to(repo_root)
                line_no = content[: match.start()].count("\n") + 1
                issues.append(
                    f"  ❌ {rel_path}:{line_no}: python-version: {version} (out of range: >={min_ver},<{max_ver})"
                )

        # Also check matrix definitions like ["3.11", "3.12", "3.13"]
        for match in re.finditer(r"python-version:\s*\[([^\]]+)\]", content):
            versions_str = match.group(1)
            versions = re.findall(r'["\'](\d+\.\d+)["\']', versions_str)

            for version in versions:
                major, minor = map(int, version.split("."))

                if (major, minor) < (min_major, min_minor) or (major, minor) >= (
                    max_major,
                    max_minor,
                ):
                    rel_path = workflow.relative_to(repo_root)
                    line_no = content[: match.start()].count("\n") + 1
                    issues.append(
                        f"  ❌ {rel_path}:{line_no}: matrix includes {version} (out of range: >={min_ver},<{max_ver})"
                    )

    return issues


def main():
    """Main guard logic."""
    # Navigate up from scripts/ to repo root
    repo_root = Path(__file__).parent.parent.resolve()
    pyproject_path = repo_root / "pyproject.toml"

    print("🐍 Python Version Matrix Guard")
    print("=" * 60)

    # Parse canonical version from pyproject.toml
    min_ver, max_ver = parse_requires_python(pyproject_path)
    print(f"✓ pyproject.toml requires-python: >={min_ver},<{max_ver}")
    print()

    # Check Dockerfiles
    print("Checking Dockerfiles...")
    docker_issues = check_dockerfiles(repo_root, min_ver, max_ver)

    # Check workflows
    print("Checking GitHub workflows...")
    workflow_issues = check_workflows(repo_root, min_ver, max_ver)

    # Report results
    all_issues = docker_issues + workflow_issues

    if all_issues:
        print()
        print("❌ FAILURE: Python version drift detected!")
        print()
        print("Issues found:")
        for issue in all_issues:
            print(issue)
        print()
        print("Remediation:")
        print(f"  All Python versions must be in range: >={min_ver},<{max_ver}")
        print(f"  - Dockerfiles: Use python:{min_ver}-slim or python:3.12-slim")
        print(f'  - Workflows: Use matrix python-version: ["{min_ver}", "3.12"]')
        print()
        print("Source of truth: pyproject.toml requires-python field")
        sys.exit(1)

    print()
    print("✅ SUCCESS: All Python versions are consistent with pyproject.toml")
    print(f"   Supported range: >={min_ver},<{max_ver}")
    sys.exit(0)


if __name__ == "__main__":
    main()
