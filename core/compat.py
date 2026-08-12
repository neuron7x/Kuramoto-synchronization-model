# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Legacy-namespace shim for :mod:`geosync.core.compat`.

The ``core/`` package predates the canonical ``src/geosync/`` layout. New code
should import from :mod:`geosync.core.compat`. This shim keeps existing
``from core.compat import ...`` statements working without a second copy of
the logic — importing this module is functionally identical to importing the
canonical one, and every symbol is the same object (identity-equal).
"""

from __future__ import annotations

from geosync.core.compat import (
    UTC,
    Clock,
    FrozenClock,
    SystemClock,
    default_clock,
    frozen_clock,
    monotonic_ns,
    safe_isoformat,
    set_default_clock,
    use_clock,
    utc_now,
)

__all__ = [
    "UTC",
    "Clock",
    "FrozenClock",
    "SystemClock",
    "default_clock",
    "frozen_clock",
    "monotonic_ns",
    "safe_isoformat",
    "set_default_clock",
    "use_clock",
    "utc_now",
]
