"""Command implementations for the consolidated scripts CLI."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
from . import (
    dev,
    fpma,
    lint,
    live,
    proto,
    secrets,
    style,
    supply_chain,
    test,
)  # noqa: F401
from .base import CommandError, register

__all__ = ["CommandError", "register"]
