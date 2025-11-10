"""Neuro-inspired adaptive controllers for core decision loops."""

from . import dopamine, desensitization, nak
from .neuro_orchestrator import (
    NeuroOrchestrator,
    OrchestrationOutput,
    TradingScenario,
    ModuleInstruction,
    RiskContour,
    LearningLoop,
    create_orchestration_from_scenario,
)

__all__ = [
    "dopamine",
    "desensitization",
    "nak",
    "NeuroOrchestrator",
    "OrchestrationOutput",
    "TradingScenario",
    "ModuleInstruction",
    "RiskContour",
    "LearningLoop",
    "create_orchestration_from_scenario",
]
