"""Unified entry point for repository maintenance scripts."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import argparse
import logging
from pathlib import Path
from typing import Sequence

from scripts.commands import CommandError
from scripts.commands import base as command_base
from scripts.runtime import (
    apply_environment,
    configure_deterministic_runtime,
    configure_logging,
    parse_env_file,
)

LOGGER = logging.getLogger(__name__)
DEFAULT_ENV_PATHS = (Path("scripts/.env"), Path(".env"))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase log verbosity (can be provided multiple times).",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="count",
        default=0,
        help="Decrease log verbosity (can be provided multiple times).",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Explicit path to an environment file. Defaults to scripts/.env then .env.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    from scripts.commands import (
        api,
        backup,
        bootstrap,
        build_core,
        dependency_health,
        dev,
        fpma,
        lint,
        live,
        nightly,
        proto,
        sanity,
        secrets,
        supply_chain,
        system,
    )
    from scripts.commands import test as test_cmd

    bootstrap.build_parser(subparsers)
    build_core.build_parser(subparsers)
    backup.build_parser(subparsers)
    api.build_parser(subparsers)
    dev.build_parser(subparsers)
    lint.build_parser(subparsers)
    proto.build_parser(subparsers)
    test_cmd.build_parser(subparsers)
    dependency_health.build_parser(subparsers)
    fpma.build_parser(subparsers)
    live.build_parser(subparsers)
    nightly.build_parser(subparsers)
    sanity.build_parser(subparsers)
    secrets.build_parser(subparsers)
    system.build_parser(subparsers)
    supply_chain.build_parser(subparsers)

    return parser


def _determine_log_level(verbose: int, quiet: int) -> int:
    base_level = logging.INFO
    level = base_level - (verbose * 10) + (quiet * 10)
    return max(logging.DEBUG, min(logging.CRITICAL, level))


def _load_environment(env_file: Path | None) -> None:
    candidates = [env_file] if env_file else list(DEFAULT_ENV_PATHS)
    for candidate in candidates:
        if candidate is None:
            continue
        env = parse_env_file(candidate)
        if env:
            apply_environment(env.variables)
            LOGGER.debug("Loaded environment overrides from %s", candidate)
            break


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    configure_deterministic_runtime()
    configure_logging(_determine_log_level(args.verbose, args.quiet))

    _load_environment(args.env_file)

    handler = command_base.get_handler(getattr(args, "command"))

    try:
        return handler(args)
    except CommandError as exc:
        LOGGER.error("%s", exc)
        return 1


if __name__ == "__main__":  # pragma: no cover - exercised by CLI
    raise SystemExit(main())
