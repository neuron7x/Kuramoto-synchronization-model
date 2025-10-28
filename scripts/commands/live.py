# SPDX-License-Identifier: MIT
"""Run the production live execution loop using TOML configuration."""

from __future__ import annotations

import logging
from argparse import ArgumentParser, _SubParsersAction
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.commands.base import register

LOGGER = logging.getLogger(__name__)


def build_parser(subparsers: _SubParsersAction[ArgumentParser]) -> None:
    parser = subparsers.add_parser("live", help=__doc__)
    parser.set_defaults(command="live", handler=handle)
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "Path to the live trading TOML configuration file "
            "(defaults to configs/live/default.toml)."
        ),
    )
    parser.add_argument(
        "--venue",
        dest="venues",
        action="append",
        default=None,
        help="Restrict execution to the specified venue (can be supplied multiple times).",
    )
    parser.add_argument(
        "--state-dir",
        type=Path,
        default=None,
        help="Override the state directory used by the live loop.",
    )
    parser.add_argument(
        "--cold-start",
        action="store_true",
        help="Skip reconciliation and treat this launch as a cold start.",
    )
    parser.add_argument(
        "--metrics-port",
        type=int,
        default=None,
        help="Expose Prometheus metrics on the provided port.",
    )


@register("live")
def handle(args: object) -> int:
    from interfaces.live_runner import LiveTradingRunner

    namespace: Mapping[str, Any]
    if isinstance(args, Mapping):
        namespace = args
    elif hasattr(args, "__dict__"):
        namespace = vars(args)
    else:
        namespace = {}

    config_path = namespace.get("config")
    venues = namespace.get("venues")
    state_dir = namespace.get("state_dir")
    cold_start = bool(namespace.get("cold_start", False))
    metrics_port = namespace.get("metrics_port")

    resolved_config: Path | None
    if isinstance(config_path, Path) or config_path is None:
        resolved_config = config_path
    else:
        resolved_config = Path(str(config_path))

    resolved_state_dir: Path | None
    if isinstance(state_dir, Path) or state_dir is None:
        resolved_state_dir = state_dir
    else:
        resolved_state_dir = Path(str(state_dir))
    resolved_venues: Sequence[str] | None
    if isinstance(venues, Sequence) and not isinstance(venues, (str, bytes)):
        resolved_venues = [str(item) for item in venues]
    elif venues is None:
        resolved_venues = None
    else:
        resolved_venues = [str(venues)]

    resolved_metrics_port: int | None
    if isinstance(metrics_port, int):
        resolved_metrics_port = metrics_port
    elif metrics_port is None:
        resolved_metrics_port = None
    else:
        resolved_metrics_port = int(str(metrics_port))

    runner = LiveTradingRunner(
        resolved_config,
        venues=resolved_venues,
        state_dir_override=resolved_state_dir,
        metrics_port=resolved_metrics_port,
    )

    LOGGER.info(
        "Launching live trading command",
        extra={
            "event": "scripts.live.start",
            "config": str(runner.config_path),
            "venues": list(runner.connectors.keys()),
            "cold_start": cold_start,
        },
    )
    runner.run(cold_start=cold_start)
    return 0


__all__ = ["build_parser", "handle"]
