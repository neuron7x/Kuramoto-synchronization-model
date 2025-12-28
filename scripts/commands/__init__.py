"""Command implementations for the consolidated scripts CLI."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from . import (  # noqa: F401
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
    test,
)
from .base import CommandError, register

__all__ = ["CommandError", "register"]
