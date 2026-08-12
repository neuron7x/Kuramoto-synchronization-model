# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Runtime entrypoints for the GeoSync application."""

from __future__ import annotations

from typing import Any, Dict, Optional

__all__ = ["run"]


def run(
    *, config_path: Optional[str] = None, cli_overrides: Optional[Dict[str, Any]] = None
) -> None:
    from .server import run as _run

    _run(config_path=config_path, cli_overrides=cli_overrides)
