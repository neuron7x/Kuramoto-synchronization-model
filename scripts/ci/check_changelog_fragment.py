#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Enforce towncrier changelog fragment exists for non-docs PRs.

Usage:
    python scripts/ci/check_changelog_fragment.py <PR_NUMBER>

Fragment types (from pyproject.toml [tool.towncrier.type]):
    feature, bugfix, performance, maintenance, docs, tests, ci, build, security, chore
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

VALID_TYPES = frozenset(
    {
        "feature",
        "bugfix",
        "performance",
        "maintenance",
        "docs",
        "tests",
        "ci",
        "build",
        "security",
        "chore",
    }
)

FRAGMENTS_DIR = Path("newsfragments")


def main(pr_num: str) -> int:
    # Check for existing fragment
    if FRAGMENTS_DIR.exists():
        found = [
            f
            for f in FRAGMENTS_DIR.iterdir()
            if f.name.startswith(f"{pr_num}.") and f.suffix == ".md"
        ]
        if found:
            for fragment in found:
                parts = fragment.stem.split(".", 1)
                fragment_type = parts[1] if len(parts) > 1 else ""
                if fragment_type not in VALID_TYPES:
                    print(f"::error::Invalid fragment type '{fragment_type}' in {fragment.name}")
                    print(f"  Valid: {', '.join(sorted(VALID_TYPES))}")
                    return 1
            print(f"OK: found {[fragment.name for fragment in found]}")
            return 0

    # No fragment — exempt if only docs/md changed
    try:
        diff_output = subprocess.check_output(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        diff_output = subprocess.check_output(
            ["git", "diff", "--name-only", "HEAD~1"],
            text=True,
        )

    changed = [path for path in diff_output.strip().split("\n") if path]
    non_doc = [path for path in changed if not re.match(r".*\.md$|^docs/", path)]

    if not non_doc:
        print("Docs-only change — fragment not required")
        return 0

    print(f"::error::Missing: newsfragments/{pr_num}.<type>.md")
    print(f"  Valid types: {', '.join(sorted(VALID_TYPES))}")
    print(f"  Non-doc files changed: {len(non_doc)}")
    return 1


if __name__ == "__main__":
    number = sys.argv[1] if len(sys.argv) > 1 else "0"
    sys.exit(main(number))
