"""Neuro-inspired desensitization primitives for stable trading behavior."""

from .reward_desensitizer import RewardDesensitizer, RewardDesensitizerConfig
from .sensory_habituation import SensoryHabituation, SensoryHabituationConfig
from .threat_gating import ThreatGate, ThreatGateConfig
from .manager import DesensitizationConfig, DesensitizationManager
from .gate import DesensitizationGate, DesensitizationGateConfig
from . import integration

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
