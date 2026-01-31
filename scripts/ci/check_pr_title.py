#!/usr/bin/env python3
"""Validate pull request titles against Conventional Commits."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

_TITLE_PATTERN = re.compile(
    r"^(feat|fix|perf|refactor|docs|test|ci|build|chore|security|revert)(\(.+\))?: .{10,}$"
)


def _load_title(event_path: Path | None) -> str:
    if event_path is None or not event_path.exists():
        return ""
    payload = json.loads(event_path.read_text(encoding="utf-8"))
    return str(payload.get("pull_request", {}).get("title", "") or "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--title",
        type=str,
        default=None,
        help="Explicit PR title (defaults to GitHub event payload).",
    )
    parser.add_argument(
        "--event-path",
        type=Path,
        default=None,
        help="Path to GitHub event payload (defaults to GITHUB_EVENT_PATH).",
    )
    args = parser.parse_args()

    event_path = args.event_path or Path(os.environ.get("GITHUB_EVENT_PATH", ""))
    title = args.title or _load_title(event_path)

    if not title:
        print("Unable to determine PR title.")
        return 2

    if _TITLE_PATTERN.match(title):
        print(f"PR title OK: {title}")
        return 0

    print("PR title must follow Conventional Commits:")
    print("Pattern: type(scope): description (min 10 chars)")
    print("Types: feat|fix|perf|refactor|docs|test|ci|build|chore|security|revert")
    print(f"Found: {title}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
