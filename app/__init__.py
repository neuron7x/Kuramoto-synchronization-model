"""Runtime entrypoint package for containerized TradePulse deployments."""

from __future__ import annotations

from interfaces.cli import main as _main

__all__ = ["run"]


def run() -> None:
    """Execute the TradePulse command-line entrypoint."""

    _main()
