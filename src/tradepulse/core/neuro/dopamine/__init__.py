"""Dopamine modulation primitives for the decision-making core.

Public API (v1.0):
- DopamineController: Main controller with TD(0) RPE, tonic/phasic DA, temperature
- ActionGate: Go/Hold/No-Go decision gate with neuromodulator fusion
- DDMThresholds: Drift-diffusion model threshold container
- DDMAdjustment: DDM parameter adjustment container
- ddm_thresholds: Compute DDM-derived thresholds from parameters
- adapt_ddm_parameters: Translate DA level to DDM adjustments
- StepResult: Typed result from dopamine_step helper
- dopamine_step: Unified step helper for policy pipelines

Invariants & Safety:
- assert_no_nan_inf: Global NaN/Inf checker with context dumping
- check_monotonic_thresholds: Enforce go >= hold >= no_go constraint
- clamp: Numeric clamping utility
"""

from __future__ import annotations

__CANONICAL__ = True

from ._invariants import assert_no_nan_inf, check_monotonic_thresholds, clamp
from .action_gate import ActionGate, GateEvaluation
from .ddm_adapter import (
    DDMAdjustment,
    DDMThresholds,
    adapt_ddm_parameters,
    ddm_thresholds,
)
from .dopamine_controller import DopamineController

try:  # pragma: no cover - optional helper
    from .dopamine_step_extension import StepResult, dopamine_step
except Exception:  # pragma: no cover - safe import guard for optional dependency
    StepResult = None  # type: ignore
    dopamine_step = None  # type: ignore

__all__ = [
    # Core components
    "DopamineController",
    "ActionGate",
    "GateEvaluation",
    # DDM adapters
    "DDMAdjustment",
    "DDMThresholds",
    "adapt_ddm_parameters",
    "ddm_thresholds",
    # Helpers
    "dopamine_step",
    "StepResult",
    # Invariants
    "assert_no_nan_inf",
    "check_monotonic_thresholds",
    "clamp",
]
