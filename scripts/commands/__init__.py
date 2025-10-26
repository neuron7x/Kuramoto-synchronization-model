"""Command implementations for the consolidated scripts CLI."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
from . import (  # noqa: F401
    bootstrap,
    build_core,
    dev,
    fpma,
    lint,
    live,
    proto,
    secrets,
    supply_chain,
    test,
)
from .base import CommandError, register

__all__ = ["CommandError", "register"]
