#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Warn when central config files grow instead of splitting configs."""

from __future__ import annotations

import argparse
import subprocess
from typing import Iterable

CONFIG_FILE_SUFFIXES = (
    "core/params.py",
    "neural_params.yaml",
)


def _run_git(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout


def _list_staged_files() -> list[str]:
    output = _run_git(["diff", "--name-only", "--cached"])
    return [line.strip() for line in output.splitlines() if line.strip()]


def _is_config_file(path: str) -> bool:
    return any(path.endswith(suffix) for suffix in CONFIG_FILE_SUFFIXES)


def _has_added_lines(path: str) -> bool:
    diff = _run_git(["diff", "--cached", "--unified=0", "--", path])
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        content = line[1:].strip()
        if not content:
            continue
        if content.startswith("#"):
            continue
        return True
    return False


def _format_list(items: Iterable[str]) -> str:
    return "\n".join(f"  - {item}" for item in items)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Check staged changes (default behavior)",
    )
    args = parser.parse_args()

    if not args.staged:
        print("This hook expects --staged for pre-commit usage.")
        return 2

    staged_files = _list_staged_files()
    touched_configs = [path for path in staged_files if _is_config_file(path)]
    if not touched_configs:
        return 0

    with_additions = [path for path in touched_configs if _has_added_lines(path)]
    if not with_additions:
        return 0

    print("New config entries detected in central config files:")
    print(_format_list(with_additions))
    print(
        "Hint: move new configs into dedicated files (e.g. under configs/ or the module's "
        "config/ directory) and reference them instead of expanding central files."
    )
    print("If this change is intentional, bypass with SKIP=central-config-hint.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
