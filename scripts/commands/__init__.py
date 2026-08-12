# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Command implementations for the consolidated scripts CLI."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
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
