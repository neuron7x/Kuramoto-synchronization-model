#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Check for central file changes and require justification."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Iterable

CENTRAL_FILE_SUFFIXES = (
    "core/params.py",
    "bridge.py",
    "neural_params.yaml",
)

JUSTIFICATION_HEADER = "Central File Justification"


def _run_git_command(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def _list_changed_files(*, base_ref: str | None, head_ref: str | None, staged: bool) -> list[str]:
    if staged:
        output = _run_git_command(["diff", "--name-only", "--cached"])
    else:
        if not base_ref or not head_ref:
            raise ValueError("base_ref and head_ref are required unless --staged is set")
        output = _run_git_command(["diff", "--name-only", f"{base_ref}...{head_ref}"])

    return [line.strip() for line in output.splitlines() if line.strip()]


def _is_central_file(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in CENTRAL_FILE_SUFFIXES)


def _load_pr_body(event_path: Path | None) -> str:
    if not event_path or not event_path.exists():
        return ""

    data = json.loads(event_path.read_text(encoding="utf-8"))
    return data.get("pull_request", {}).get("body", "") or ""


def _extract_justification(pr_body: str) -> str:
    if not pr_body:
        return ""

    header_pattern = re.compile(rf"^##\s+{re.escape(JUSTIFICATION_HEADER)}\s*$", re.M)
    match = header_pattern.search(pr_body)
    if not match:
        return ""

    body_after = pr_body[match.end() :]
    next_header = re.search(r"^##\s+", body_after, re.M)
    if next_header:
        body_after = body_after[: next_header.start()]

    cleaned_lines = []
    for line in body_after.splitlines():
        stripped = line.strip()
        if stripped.startswith("<!--"):
            continue
        cleaned_lines.append(line)

    cleaned_body = "\n".join(cleaned_lines).strip()
    if not re.search(r"[A-Za-zА-Яа-я0-9]", cleaned_body):
        return ""

    return cleaned_body


def _format_list(items: Iterable[str]) -> str:
    return "\n".join(f"  - {item}" for item in items)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ref", help="Base ref/sha for diff")
    parser.add_argument("--head-ref", help="Head ref/sha for diff")
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes instead of a base/head diff",
    )
    parser.add_argument(
        "--justification",
        help="Explicit justification text for local runs",
    )
    parser.add_argument(
        "--event-path",
        help="GitHub event payload path (defaults to GITHUB_EVENT_PATH)",
    )
    args = parser.parse_args()

    try:
        changed_files = _list_changed_files(
            base_ref=args.base_ref,
            head_ref=args.head_ref,
            staged=args.staged,
        )
    except ValueError as exc:
        print(str(exc))
        return 2

    central_changes = [path for path in changed_files if _is_central_file(path)]
    if not central_changes:
        print("No central files changed.")
        return 0

    event_path = Path(args.event_path) if args.event_path else None
    pr_body = _load_pr_body(event_path or Path(os.environ.get("GITHUB_EVENT_PATH", "")))
    justification = (
        args.justification
        or os.environ.get("CENTRAL_FILES_JUSTIFICATION", "")
        or _extract_justification(pr_body)
    )

    print("Central files touched:")
    print(_format_list(central_changes))

    if justification:
        print("Justification detected; central file changes allowed.")
        return 0

    print(
        "Missing justification for central file changes. "
        "Add a 'Central File Justification' section in the PR body "
        "or provide CENTRAL_FILES_JUSTIFICATION for local checks."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
