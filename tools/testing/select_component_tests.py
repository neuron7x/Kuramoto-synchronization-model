#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CLI wrapper for deterministic component-test planning and execution."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from tools.testing.component_test_planner import (
    BLOCKING_STATUSES,
    MATRIX,
    ROOT,
    Plan,
    execution_python,
    max_run_selectors,
    plan_pytest_command,
    plan_selectors,
    plan_status,
    select_plan,
    validate_matrix,
)

# Backwards-compatible names for tests and scripts that import this entrypoint.
_execution_python = execution_python
_plan_pytest_command = plan_pytest_command
_plan_selectors = plan_selectors
_plan_status = plan_status


def _read_changed_files(args: argparse.Namespace) -> list[str]:
    changed: list[str] = list(args.changed_file or [])
    if args.changed_files_from:
        changed.extend(
            line.strip()
            for line in args.changed_files_from.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=MATRIX)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--changed-file", action="append", default=[])
    parser.add_argument("--changed-files-from", type=Path)
    parser.add_argument("--python-executable")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--print-pytest", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)

    errors = validate_matrix(args.matrix, args.repo_root)
    if errors:
        print("COMPONENT TEST MATRIX: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  {error}", file=sys.stderr)
        return 1
    if args.validate_only:
        print("COMPONENT TEST MATRIX: PASS")
        return 0

    plan: Plan = select_plan(
        _read_changed_files(args),
        args.matrix,
        args.repo_root,
        args.python_executable,
        os.environ,
    )
    if args.print_pytest:
        print(" ".join(plan_pytest_command(plan)))
    else:
        print(json.dumps(plan, indent=2, sort_keys=True))

    status = plan_status(plan)
    if status in BLOCKING_STATUSES:
        return 2
    selectors = plan_selectors(plan)
    if args.run and selectors:
        limit = max_run_selectors(os.environ.get("COMPONENT_ROUTER_MAX_SELECTORS"), args.matrix)
        selected = selectors[:limit]
        print(f"COMPONENT_ROUTER_SELECTED {len(selected)}/{len(selectors)}")
        command = [
            execution_python(args.repo_root, args.matrix, args.python_executable, os.environ),
            "-m",
            "pytest",
            *selected,
        ]
        return subprocess.run(command, cwd=args.repo_root, check=False).returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
