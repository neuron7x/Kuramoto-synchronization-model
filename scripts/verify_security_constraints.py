#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Security Constraint Verification Script

This script verifies that all installed packages match the security constraints
defined in constraints/security.txt and that no vulnerable versions are present.

Usage:
    python scripts/verify_security_constraints.py [--fix]

Exit codes:
    0: All constraints satisfied
    1: Constraint violations found
    2: Script error
"""

import argparse
import importlib.metadata
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple


class ConstraintViolation:
    """Represents a security constraint violation."""

    def __init__(self, package: str, installed: str, required: str, severity: str = "HIGH"):
        self.package = package
        self.installed = installed
        self.required = required
        self.severity = severity

    def __str__(self) -> str:
        return (
            f"[{self.severity}] {self.package}: "
            f"installed={self.installed}, required={self.required}"
        )


def parse_constraints(constraints_file: Path) -> Dict[str, str]:
    """Parse the security constraints file."""
    constraints = {}

    if not constraints_file.exists():
        print(f"ERROR: Constraints file not found: {constraints_file}")
        sys.exit(2)

    with open(constraints_file) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue

            # Parse package==version or package>=version
            if "==" in line:
                pkg, version = line.split("==", 1)
                constraints[pkg.strip()] = ("==", version.strip())
            elif ">=" in line:
                pkg, version = line.split(">=", 1)
                constraints[pkg.strip()] = (">=", version.strip())

    return constraints


def get_installed_packages() -> Dict[str, str]:
    """Get all installed packages and their versions."""
    try:
        packages: dict[str, str] = {}
        for distribution in importlib.metadata.distributions():
            name = distribution.metadata.get("Name")
            if not name:
                continue
            packages[name] = distribution.version
        return packages
    except Exception as e:
        print(f"ERROR: Failed to get installed packages: {e}")
        sys.exit(2)


def compare_versions(installed: str, operator: str, required: str) -> Tuple[bool, str]:
    """
    Compare package versions.

    Returns:
        Tuple of (is_satisfied, reason)
    """
    try:
        # Try to use packaging module if available
        try:
            from packaging import version

            installed_v = version.parse(installed)
            required_v = version.parse(required)
        except ImportError:
            # Fallback to simple string comparison if packaging not available
            # This is a simplified comparison that works for most semantic versions
            installed_v = (
                tuple(map(int, installed.split(".")[:3])) if "." in installed else (0, 0, 0)
            )
            required_v = tuple(map(int, required.split(".")[:3])) if "." in required else (0, 0, 0)

        if operator == "==":
            satisfied = installed_v == required_v
            reason = (
                "versions match" if satisfied else f"exact version mismatch (required: {required})"
            )
        elif operator == ">=":
            satisfied = installed_v >= required_v
            reason = (
                "version satisfies minimum"
                if satisfied
                else f"version too old (minimum: {required})"
            )
        else:
            return False, f"unsupported operator: {operator}"

        return satisfied, reason
    except Exception as e:
        return False, f"version comparison failed: {e}"


def check_constraints(
    constraints: Dict[str, Tuple[str, str]], installed: Dict[str, str]
) -> List[ConstraintViolation]:
    """Check all constraints against installed packages."""
    violations = []

    for pkg_name, (operator, required_version) in constraints.items():
        # Normalize package name (pip uses lowercase, but package names can vary)
        pkg_normalized = pkg_name.lower().replace("_", "-")
        installed_version = None

        # Find installed version (handle name variations)
        for installed_pkg, installed_ver in installed.items():
            if installed_pkg.lower().replace("_", "-") == pkg_normalized:
                installed_version = installed_ver
                break

        if installed_version is None:
            # Package not installed - might be optional
            continue

        satisfied, reason = compare_versions(installed_version, operator, required_version)

        if not satisfied:
            violation = ConstraintViolation(
                package=pkg_name,
                installed=installed_version,
                required=f"{operator}{required_version}",
                severity="CRITICAL" if operator == "==" else "HIGH",
            )
            violations.append(violation)

    return violations


def fix_violations(violations: List[ConstraintViolation]) -> bool:
    """Attempt to fix constraint violations by upgrading packages."""
    if not violations:
        return True

    print("\n" + "=" * 70)
    print("ATTEMPTING TO FIX VIOLATIONS")
    print("=" * 70)

    packages_to_upgrade = [v.package for v in violations]

    try:
        cmd = [
            "pip",
            "install",
            "--upgrade",
            "-c",
            "constraints/security.txt",
        ] + packages_to_upgrade

        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        print("✅ Successfully upgraded packages")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to upgrade packages: {e}")
        return False


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Verify security constraints are satisfied")
    parser.add_argument("--fix", action="store_true", help="Attempt to fix violations")
    args = parser.parse_args()

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    constraints_file = project_root / "constraints" / "security.txt"

    print("=" * 70)
    print("SECURITY CONSTRAINT VERIFICATION")
    print("=" * 70)
    print(f"Project root: {project_root}")
    print(f"Constraints file: {constraints_file}")
    print()

    # Parse constraints
    constraints = parse_constraints(constraints_file)
    print(f"✅ Loaded {len(constraints)} security constraints")

    # Get installed packages
    installed = get_installed_packages()
    print(f"✅ Found {len(installed)} installed packages")
    print()

    # Check constraints
    violations = check_constraints(constraints, installed)

    if not violations:
        print("=" * 70)
        print("✅ ALL SECURITY CONSTRAINTS SATISFIED")
        print("=" * 70)
        return 0

    # Report violations
    print("=" * 70)
    print(f"❌ FOUND {len(violations)} SECURITY CONSTRAINT VIOLATIONS")
    print("=" * 70)
    print()

    for violation in violations:
        print(f"  {violation}")
    print()

    # Attempt to fix if requested
    if args.fix:
        if fix_violations(violations):
            # Re-check after fix
            installed = get_installed_packages()
            remaining_violations = check_constraints(constraints, installed)
            if not remaining_violations:
                print("=" * 70)
                print("✅ ALL VIOLATIONS FIXED")
                print("=" * 70)
                return 0
            else:
                print("=" * 70)
                print(f"❌ {len(remaining_violations)} VIOLATIONS REMAIN")
                print("=" * 70)
                return 1
        else:
            return 1
    else:
        print("Run with --fix to attempt automatic remediation")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
