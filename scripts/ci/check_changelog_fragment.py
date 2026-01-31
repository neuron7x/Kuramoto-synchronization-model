#!/usr/bin/env python3
"""Enforce towncrier changelog fragments for non-docs changes."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Sequence

VALID_TYPES = {
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


def _load_pr_number(event_path: Path | None) -> str | None:
    if event_path is None or not event_path.exists():
        return None
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    number = payload.get("pull_request", {}).get("number")
    return str(number) if number else None


def _git_diff_names(base_ref: str, head_ref: str) -> list[str]:
    output = subprocess.check_output(
        ["git", "diff", "--name-only", f"{base_ref}...{head_ref}"],
        text=True,
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def _is_docs_only(paths: Sequence[str]) -> bool:
    for path in paths:
        if not re.match(r".*\.md$|^docs/", path):
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", default="origin/main", help="Base ref for diff.")
    parser.add_argument("--head-ref", default="HEAD", help="Head ref for diff.")
    parser.add_argument(
        "--pr-number",
        default=None,
        help="Explicit PR number override.",
    )
    parser.add_argument(
        "--event-path",
        type=Path,
        default=None,
        help="Path to GitHub event payload (defaults to GITHUB_EVENT_PATH).",
    )
    args = parser.parse_args()

    event_path = args.event_path or Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    pr_number = args.pr_number or _load_pr_number(event_path)

    if not pr_number:
        print("PR number unavailable; cannot enforce changelog fragment.")
        return 2

    fragments = list(Path("newsfragments").glob(f"{pr_number}.*.md"))
    if fragments:
        for fragment in fragments:
            fragment_type = fragment.stem.split(".", 1)[-1]
            if fragment_type not in VALID_TYPES:
                print(f"Invalid fragment type '{fragment_type}' in {fragment.name}")
                print(f"Valid types: {', '.join(sorted(VALID_TYPES))}")
                return 1
        print("Changelog fragment present.")
        return 0

    changed_files = _git_diff_names(args.base_ref, args.head_ref)
    if _is_docs_only(changed_files):
        print("Docs-only change; changelog fragment not required.")
        return 0

    print(f"Missing: newsfragments/{pr_number}.<type>.md")
    print(f"Valid types: {', '.join(sorted(VALID_TYPES))}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
