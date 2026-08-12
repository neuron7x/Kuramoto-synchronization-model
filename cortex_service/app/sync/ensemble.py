# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synchronization utilities for the signal ensemble."""

from __future__ import annotations

import cmath
from typing import Sequence

from ..core.signals import Signal


def kuramoto_order_parameter(signals: Sequence[Signal]) -> float:
    """Return the Kuramoto order parameter for the ensemble."""

    if not signals:
        return 0.0
    phases = [signal.strength for signal in signals]
    complex_sum = sum(cmath.exp(1j * phase) for phase in phases)
    return abs(complex_sum) / len(phases)


def aggregate_strength(signals: Sequence[Signal]) -> float:
    """Compute the mean strength for monitoring and gating decisions."""

    if not signals:
        return 0.0
    return sum(signal.strength for signal in signals) / len(signals)


__all__ = ["aggregate_strength", "kuramoto_order_parameter"]
