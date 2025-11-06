"""Dopamine modulation primitives for the decision-making core."""

from __future__ import annotations

from .dopamine_controller import DopamineController
from .action_gate import ActionGate, GateEvaluation
from .ddm_adapter import DDMAdjustment, adapt_ddm_parameters

try:  # pragma: no cover - optional helper
    from .dopamine_step_extension import StepResult, dopamine_step
except Exception:  # pragma: no cover - safe import guard for optional dependency
    StepResult = None  # type: ignore
    dopamine_step = None  # type: ignore

__all__ = [
    "DopamineController",
    "dopamine_step",
    "StepResult",
    "ActionGate",
    "GateEvaluation",
    "DDMAdjustment",
    "adapt_ddm_parameters",
]
