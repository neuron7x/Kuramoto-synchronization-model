"""Execute the project's automated test suites."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import logging
from argparse import _SubParsersAction
from pathlib import Path

from scripts.commands.base import CommandError, register, run_subprocess

LOGGER = logging.getLogger(__name__)
DEFAULT_TEST_ROOTS = (Path("domains"), Path("tests"))


def build_parser(subparsers: _SubParsersAction[object]) -> None:
    parser = subparsers.add_parser(
        "test", help="Run automated tests across supported stacks"
    )
    parser.set_defaults(command="test", handler=handle)
    parser.add_argument(
        "--pytest-args",
        nargs="*",
        default=(),
        help="Additional arguments forwarded to pytest.",
    )


@register("test")
def handle(args: object) -> int:
    namespace = getattr(args, "__dict__", args)
    pytest_args: tuple[str, ...] = tuple(namespace.get("pytest_args", ()))

    if not _run_python_tests(pytest_args):
        raise CommandError("No Python test suites were discovered.")

    _run_node_tests()
    LOGGER.info("All tests completed.")
    return 0


def _run_python_tests(pytest_args: tuple[str, ...]) -> bool:
    roots = [root for root in DEFAULT_TEST_ROOTS if root.exists()]
    if not roots:
        LOGGER.info("No Python test directories found – skipping pytest stage.")
        return False

    pytest_command = ["pytest", "-q", *pytest_args, *map(str, roots)]
    LOGGER.info("Running pytest for roots: %s", ", ".join(map(str, roots)))
    run_subprocess(pytest_command)
    return True


def _run_node_tests() -> None:
    from shutil import which

    dashboard = Path("domains/ui/dashboard/tests/test.js")
    if which("node") is None:
        LOGGER.info("Node.js not available – skipping front-end tests.")
        return

    if not dashboard.exists():
        LOGGER.info("No Node.js test suite found at %s – skipping.", dashboard)
        return

    LOGGER.info("Running Node.js dashboard tests…")
    run_subprocess(["node", str(dashboard)])
