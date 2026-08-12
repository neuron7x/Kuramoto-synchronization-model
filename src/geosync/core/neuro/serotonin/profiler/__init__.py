# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deprecated mirror. Canonical module lives in core.neuro.serotonin.profiler."""

__CANONICAL__ = True

from core.neuro.serotonin.profiler.behavioral_profiler import (
    BehavioralProfile,
    ProfileStatistics,
    SerotoninProfiler,
    TonicPhasicCharacteristics,
    VetoCooldownCharacteristics,
)

__all__ = [
    "BehavioralProfile",
    "ProfileStatistics",
    "SerotoninProfiler",
    "TonicPhasicCharacteristics",
    "VetoCooldownCharacteristics",
]
