# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Core state representation for NaK controller."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Union


def clip(value: float, lo: float, hi: float) -> float:
    """Clamp *value* into the closed interval [lo, hi]."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


@dataclass(slots=True)
class StrategyState:
    """State maintained per strategy across controller steps."""

    L: float = 0.0
    E: float = 0.5
    EI: float = 0.5
    I: float = 0.0  # noqa: E741 - integral accumulator
    suspended: bool = False
    health: float = 0.5
    debt: float = 0.0
    last_risk: float = 1.0
    last: Dict[str, Union[float, str]] = field(default_factory=dict)


__all__ = ["StrategyState", "clip"]
