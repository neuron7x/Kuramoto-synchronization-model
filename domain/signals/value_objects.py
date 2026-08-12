# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Value objects for signal semantics."""

from __future__ import annotations

from enum import Enum


class SignalAction(str, Enum):
    """Supported signal directives."""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    EXIT = "exit"


__all__ = ["SignalAction"]
