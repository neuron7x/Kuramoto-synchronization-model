# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Lightweight receptor-based safety modulators for SerotoninController.

Each receptor implements two functions:
    - compute_activation(ctx, state) -> float in [0, 1]
    - compute_deltas(ctx, activation) -> ParamDeltas

The bank orchestrates receptor evaluation and aggregation.
"""

from .bank import ReceptorBank
from .types import ParamDeltas, ReceptorActivation, ReceptorContext, ReceptorState

__CANONICAL__ = True

__all__ = [
    "ReceptorActivation",
    "ReceptorBank",
    "ReceptorContext",
    "ReceptorState",
    "ParamDeltas",
]
