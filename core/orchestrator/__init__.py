# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Core orchestration primitives.

This module exposes the public entry points used by the trading runtime
for mode management and module interaction sequencing. The implementation
deliberately keeps the interface minimal so that both Python- and Rust-based
runtimes can share the same state-machine semantics.
"""

from .interaction_sequencer import (
    ExecutionContext,
    ModuleDefinition,
    ModuleInteractionOrchestrator,
    ModulePhase,
)
from .mode_orchestrator import (
    DelayBudget,
    GuardBand,
    GuardConfig,
    MetricsSnapshot,
    ModeOrchestrator,
    ModeOrchestratorConfig,
    ModeState,
    TimeoutConfig,
)

__all__ = [
    "DelayBudget",
    "ExecutionContext",
    "GuardBand",
    "GuardConfig",
    "MetricsSnapshot",
    "ModuleDefinition",
    "ModuleInteractionOrchestrator",
    "ModeOrchestrator",
    "ModeOrchestratorConfig",
    "ModeState",
    "ModulePhase",
    "TimeoutConfig",
]
