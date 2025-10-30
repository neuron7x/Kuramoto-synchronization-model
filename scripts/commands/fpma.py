"""Thin wrappers around the existing FPM-A integration tooling."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import logging
import sys
from argparse import _SubParsersAction
from pathlib import Path

from scripts.commands.base import CommandError, register, run_subprocess

LOGGER = logging.getLogger(__name__)

TOOL_PATH = Path("tools/fpma_runner.py")


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    parser = subparsers.add_parser("fpma", help="Interact with FPM-A tooling")
    mode = parser.add_subparsers(dest="fpma_mode", required=True)

    graph = mode.add_parser("graph", help="Generate the project graph")
    graph.set_defaults(command="fpma-graph", handler=handle_graph)

    check = mode.add_parser("check", help="Validate the project graph")
    check.set_defaults(command="fpma-check", handler=handle_check)


@register("fpma-graph")
def handle_graph(args: object) -> int:  # noqa: ARG001 - required signature
    return _invoke_runner("graph")


@register("fpma-check")
def handle_check(args: object) -> int:  # noqa: ARG001 - required signature
    return _invoke_runner("check")


def _invoke_runner(mode: str) -> int:
    if not TOOL_PATH.exists():
        raise CommandError(
            "tools/fpma_runner.py is missing. Ensure the repository is complete before running this command."
        )
    LOGGER.info("Running fpma_runner.py with mode '%s'…", mode)
    run_subprocess([sys.executable, str(TOOL_PATH), mode])
    LOGGER.info("FPM-A command '%s' completed successfully.", mode)
    return 0
