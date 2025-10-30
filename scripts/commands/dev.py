"""Manage local development infrastructure."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import logging
from argparse import _SubParsersAction

from scripts.commands.base import CommandError, register, run_subprocess

LOGGER = logging.getLogger(__name__)
DOCKER_COMPOSE_COMMAND = ("docker", "compose")


def _ensure_docker_available() -> None:
    from shutil import which

    if which("docker") is None:
        raise CommandError("Docker CLI is required for dev infrastructure commands.")


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    up = subparsers.add_parser(
        "dev-up", help="Start local services defined in docker-compose.yml"
    )
    up.set_defaults(command="dev-up", handler=handle_up)

    down = subparsers.add_parser(
        "dev-down", help="Stop local services defined in docker-compose.yml"
    )
    down.set_defaults(command="dev-down", handler=handle_down)


@register("dev-up")
def handle_up(args: object) -> int:  # noqa: ARG001 - required signature
    _ensure_docker_available()
    LOGGER.info("Starting docker compose services…")
    run_subprocess([*DOCKER_COMPOSE_COMMAND, "up", "-d"])
    LOGGER.info("Services started successfully.")
    return 0


@register("dev-down")
def handle_down(args: object) -> int:  # noqa: ARG001 - required signature
    _ensure_docker_available()
    LOGGER.info("Stopping docker compose services…")
    run_subprocess([*DOCKER_COMPOSE_COMMAND, "down"])
    LOGGER.info("Services stopped successfully.")
    return 0
