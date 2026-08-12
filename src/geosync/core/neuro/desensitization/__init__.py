# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Neuro-inspired desensitization primitives for stable trading behavior."""

__CANONICAL__ = True

from . import integration
from .gate import DesensitizationGate, DesensitizationGateConfig
from .manager import DesensitizationConfig, DesensitizationManager
from .reward_desensitizer import RewardDesensitizer, RewardDesensitizerConfig
from .sensory_habituation import SensoryHabituation, SensoryHabituationConfig
from .threat_gating import ThreatGate, ThreatGateConfig

__all__ = [
    "RewardDesensitizer",
    "RewardDesensitizerConfig",
    "SensoryHabituation",
    "SensoryHabituationConfig",
    "ThreatGate",
    "ThreatGateConfig",
    "DesensitizationConfig",
    "DesensitizationManager",
    "DesensitizationGate",
    "DesensitizationGateConfig",
    "integration",
]
