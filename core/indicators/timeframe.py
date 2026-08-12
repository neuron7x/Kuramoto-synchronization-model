# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Discrete trading-horizon enumeration shared across the indicator package.

``TimeFrame`` lives in its own leaf module so that both
``multiscale_kuramoto`` (which produces per-horizon descriptors) and
``cache`` (which partitions cached results per horizon) can depend on it
without importing each other. Keeping the enum here breaks the
``multiscale_kuramoto`` <-> ``cache`` import cycle (py/unsafe-cyclic-import)
at its root rather than papering over it with a lazy or TYPE_CHECKING import.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["TimeFrame"]


class TimeFrame(Enum):
    """Discrete trading horizons expressed in seconds."""

    M1 = 60
    M5 = 300
    M15 = 900
    H1 = 3600

    @property
    def pandas_freq(self) -> str:
        """Return the pandas frequency string for resampling."""

        return f"{int(self.value)}s"

    @property
    def seconds(self) -> int:
        """Expose the time frame in seconds for downstream consumers."""

        return int(self.value)

    def __str__(self) -> str:  # pragma: no cover - tiny helper
        return self.name
