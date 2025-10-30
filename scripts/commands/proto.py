"""Regenerate protobuf artefacts consistently across platforms."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import logging
from argparse import _SubParsersAction

from scripts.commands.base import CommandError, register, run_subprocess

LOGGER = logging.getLogger(__name__)


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    parser = subparsers.add_parser(
        "gen-proto", help="Regenerate protobuf artefacts via buf"
    )
    parser.set_defaults(command="gen-proto", handler=handle)


@register("gen-proto")
def handle(args: object) -> int:  # noqa: ARG001 - required signature
    from shutil import which

    if which("buf") is None:
        raise CommandError("buf executable is required to regenerate protobuf code.")

    LOGGER.info("Linting proto files with buf…")
    run_subprocess(["buf", "lint"])

    LOGGER.info("Generating code from proto definitions…")
    run_subprocess(["buf", "generate"])

    LOGGER.info("Protobuf generation completed.")
    return 0
