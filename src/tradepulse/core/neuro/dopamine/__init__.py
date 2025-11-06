"""Dopamine modulation primitives for the decision-making core."""

from __future__ import annotations

from .dopamine_controller import DopamineController

try:  # pragma: no cover - optional helper
    from .dopamine_step_extension import StepResult, dopamine_step
except Exception:  # pragma: no cover - safe import guard for optional dependency
    StepResult = None  # type: ignore
    dopamine_step = None  # type: ignore

__all__ = ["DopamineController", "dopamine_step", "StepResult"]
