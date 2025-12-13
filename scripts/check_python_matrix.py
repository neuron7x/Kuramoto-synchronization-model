#!/usr/bin/env python3
"""
Python Version Matrix Consistency Checker

Verifies that Python versions are consistently declared across:
- pyproject.toml (requires-python)
- Dockerfiles (FROM python:X.Y)
- GitHub Actions workflows (python-version)
- .python-version file

This script enforces that pyproject.toml is the single source of truth.
Exit code 0 = all aligned, 1 = drift detected
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ANSI color codes for output
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def parse_requires_python(pyproject_path: Path) -> Tuple[str, str, str]:
    """Parse requires-python from pyproject.toml.
    
    Returns:
        Tuple of (min_version, max_version, constraint)
    """
    content = pyproject_path.read_text()
    match = re.search(r'requires-python\s*=\s*"([^"]+)"', content)
    if not match:
        raise ValueError("Could not find requires-python in pyproject.toml")
    
    constraint = match.group(1)
    
    # Parse constraints like ">=3.11,<3.13"
    min_match = re.search(r'>=(\d+\.\d+)', constraint)
    max_match = re.search(r'<(\d+\.\d+)', constraint)
    
    min_version = min_match.group(1) if min_match else None
    max_version = max_match.group(1) if max_match else None
    
    if not min_version:
        raise ValueError(f"Could not parse min version from: {constraint}")
    
    return min_version, max_version, constraint


def get_allowed_versions(min_ver: str, max_ver: str) -> Set[str]:
    """Generate set of allowed minor versions from constraint."""
    min_major, min_minor = map(int, min_ver.split('.'))
    
    if max_ver:
        max_major, max_minor = map(int, max_ver.split('.'))
        allowed = set()
        
        # Generate all minor versions in range
        for major in range(min_major, max_major + 1):
            start_minor = min_minor if major == min_major else 0
            end_minor = max_minor if major == max_major else 99
            
            for minor in range(start_minor, end_minor):
                if major == max_major and minor >= max_minor:
                    break
                allowed.add(f"{major}.{minor}")
        
        return allowed
    else:
        # No upper bound, just return min version
        return {min_ver}


def check_dockerfiles(repo_root: Path, allowed: Set[str]) -> List[str]:
    """Check Python versions in all Dockerfiles."""
    issues = []
    dockerfiles = list(repo_root.glob("**/Dockerfile*"))
    
    # Filter out .dockerignore and similar
    dockerfiles = [f for f in dockerfiles if f.name.startswith("Dockerfile")]
    
    for dockerfile in dockerfiles:
        content = dockerfile.read_text()
        # Match FROM python:X.Y or FROM python:X.Y-slim, etc.
        matches = re.finditer(r'FROM\s+python:([\d.]+)', content)
        
        for match in matches:
            version = match.group(1)
            # Extract just major.minor
            minor_version = '.'.join(version.split('.')[:2])
            
            if minor_version not in allowed:
                rel_path = dockerfile.relative_to(repo_root)
                issues.append(
                    f"  ❌ {rel_path} uses Python {version} "
                    f"(allowed: {', '.join(sorted(allowed))})"
                )
    
    return issues


def check_github_workflows(repo_root: Path, allowed: Set[str]) -> List[str]:
    """Check Python versions in GitHub Actions workflows."""
    issues = []
    workflows_dir = repo_root / ".github" / "workflows"
    
    if not workflows_dir.exists():
        return issues
    
    for workflow in workflows_dir.glob("*.yml"):
        content = workflow.read_text()
        
        # Check python-version in setup-python steps
        single_matches = re.finditer(r"python-version:\s*['\"]?([\d.]+)['\"]?", content)
        for match in single_matches:
            version = match.group(1)
            minor_version = '.'.join(version.split('.')[:2])
            
            if minor_version not in allowed:
                rel_path = workflow.relative_to(repo_root)
                line_num = content[:match.start()].count('\n') + 1
                issues.append(
                    f"  ❌ {rel_path}:{line_num} uses Python {version} "
                    f"(allowed: {', '.join(sorted(allowed))})"
                )
        
        # Check matrix python-version arrays
        matrix_matches = re.finditer(
            r"python-version:\s*\[([\d.',\s]+)\]", content
        )
        for match in matrix_matches:
            versions_str = match.group(1)
            # Extract all version numbers
            versions = re.findall(r'([\d.]+)', versions_str)
            
            for version in versions:
                minor_version = '.'.join(version.split('.')[:2])
                
                if minor_version not in allowed:
                    rel_path = workflow.relative_to(repo_root)
                    line_num = content[:match.start()].count('\n') + 1
                    issues.append(
                        f"  ❌ {rel_path}:{line_num} matrix includes Python {version} "
                        f"(allowed: {', '.join(sorted(allowed))})"
                    )
    
    return issues


def check_python_version_file(repo_root: Path, allowed: Set[str]) -> List[str]:
    """Check .python-version file if it exists."""
    issues = []
    python_version_file = repo_root / ".python-version"
    
    if python_version_file.exists():
        content = python_version_file.read_text().strip()
        minor_version = '.'.join(content.split('.')[:2])
        
        if minor_version not in allowed:
            issues.append(
                f"  ❌ .python-version contains Python {content} "
                f"(allowed: {', '.join(sorted(allowed))})"
            )
    
    return issues


def main():
    """Main entry point."""
    repo_root = Path(__file__).parent.parent
    pyproject_path = repo_root / "pyproject.toml"
    
    if not pyproject_path.exists():
        print(f"{RED}ERROR: pyproject.toml not found{RESET}")
        return 1
    
    print(f"{YELLOW}🔍 Python Version Matrix Consistency Check{RESET}")
    print("=" * 60)
    
    # Parse source of truth
    try:
        min_ver, max_ver, constraint = parse_requires_python(pyproject_path)
        allowed = get_allowed_versions(min_ver, max_ver)
    except Exception as e:
        print(f"{RED}ERROR: Failed to parse pyproject.toml: {e}{RESET}")
        return 1
    
    print(f"📋 Source of Truth: pyproject.toml")
    print(f"   requires-python = \"{constraint}\"")
    print(f"   Allowed versions: {', '.join(sorted(allowed))}")
    print()
    
    # Collect all issues
    all_issues = []
    
    print("🐳 Checking Dockerfiles...")
    dockerfile_issues = check_dockerfiles(repo_root, allowed)
    all_issues.extend(dockerfile_issues)
    if not dockerfile_issues:
        print(f"  {GREEN}✅ All Dockerfiles compliant{RESET}")
    else:
        for issue in dockerfile_issues:
            print(issue)
    print()
    
    print("⚙️  Checking GitHub Actions workflows...")
    workflow_issues = check_github_workflows(repo_root, allowed)
    all_issues.extend(workflow_issues)
    if not workflow_issues:
        print(f"  {GREEN}✅ All workflows compliant{RESET}")
    else:
        for issue in workflow_issues:
            print(issue)
    print()
    
    print("📄 Checking .python-version file...")
    version_file_issues = check_python_version_file(repo_root, allowed)
    all_issues.extend(version_file_issues)
    if not version_file_issues:
        print(f"  {GREEN}✅ .python-version compliant{RESET}")
    else:
        for issue in version_file_issues:
            print(issue)
    print()
    
    # Summary
    print("=" * 60)
    if all_issues:
        print(f"{RED}❌ DRIFT DETECTED: {len(all_issues)} inconsistencies found{RESET}")
        print()
        print("To fix these issues:")
        print("1. Update versions in the listed files to match pyproject.toml")
        print("2. Re-run this script to verify compliance")
        print("3. pyproject.toml is the SINGLE SOURCE OF TRUTH")
        return 1
    else:
        print(f"{GREEN}✅ SUCCESS: All Python versions aligned!{RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
