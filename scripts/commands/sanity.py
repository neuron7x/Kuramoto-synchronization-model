# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Commands for running repository sanity cleanup tasks."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import argparse
from pathlib import Path

from scripts.commands.base import register
from scripts.sanity_cleanup import CleanupOptions, run_all


def build_parser(subparsers: "argparse._SubParsersAction[object]") -> None:
    parser = subparsers.add_parser(
        "sanity",
        help="Run repository hygiene and sanity cleanup tasks.",
        description="Audit and optionally remediate repository hygiene concerns.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without modifying the working tree.",
    )
    parser.add_argument(
        "--archive-legacy",
        action="store_true",
        help="Create tarball archives for legacy directories instead of only listing them.",
    )
    parser.set_defaults(command="sanity", handler=handle)


@register("sanity")
def handle(args: argparse.Namespace) -> int:
    options = CleanupOptions(dry_run=args.dry_run, archive_legacy=args.archive_legacy)
    result = run_all(Path.cwd(), options=options)
    return result.exit_code
