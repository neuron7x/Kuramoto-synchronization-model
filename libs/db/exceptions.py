# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Domain specific exceptions raised by the database access layer."""

from __future__ import annotations

__all__ = ["DatabaseError", "RetryableDatabaseError"]


class DatabaseError(RuntimeError):
    """Base class for database access related failures."""


class RetryableDatabaseError(DatabaseError):
    """Marker exception used to force retry logic for known transient states."""
