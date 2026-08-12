# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed runtime invariant monitor for ActionGate evaluations."""

from __future__ import annotations

import math
from typing import Protocol

from geosync.core.neuro.dopamine.action_gate import GateEvaluation


class RuntimeTemperatureBoundsProvider(Protocol):
    def temperature_bounds(self) -> tuple[float, float]:
        """Return inclusive lower/upper temperature bounds."""


def validate_action_gate_evaluation(
    evaluation: GateEvaluation,
    bounds_provider: RuntimeTemperatureBoundsProvider,
) -> None:
    """Raise immediately when an ActionGate evaluation violates runtime invariants."""
    lower, upper = bounds_provider.temperature_bounds()
    lower = float(lower)
    upper = float(upper)

    if not math.isfinite(lower) or not math.isfinite(upper):
        raise ValueError("ActionGate runtime bounds must be finite")
    if lower > upper:
        raise ValueError("ActionGate runtime bounds must satisfy lower <= upper")
    if evaluation.decision not in {"GO", "HOLD", "NO_GO"}:
        raise AssertionError("ActionGate emitted an unknown decision")
    if not math.isfinite(evaluation.score) or not 0.0 <= evaluation.score <= 1.0:
        raise AssertionError("ActionGate score invariant violated")
    if not math.isfinite(evaluation.dopamine_level) or not 0.0 <= evaluation.dopamine_level <= 1.0:
        raise AssertionError("ActionGate dopamine invariant violated")
    if not math.isfinite(evaluation.temperature):
        raise AssertionError("ActionGate temperature must be finite")
    if evaluation.temperature < lower or evaluation.temperature > upper:
        raise AssertionError("ActionGate temperature bounds invariant violated")
    if evaluation.go is not (evaluation.decision == "GO"):
        raise AssertionError("ActionGate GO flag invariant violated")
    if evaluation.decision == "GO" and (evaluation.hold or evaluation.no_go):
        raise AssertionError("ActionGate GO decision cannot also hold/no-go")
    if evaluation.decision == "HOLD" and (evaluation.go or evaluation.no_go):
        raise AssertionError("ActionGate HOLD decision cannot also go/no-go")
    if evaluation.decision == "NO_GO" and not evaluation.no_go:
        raise AssertionError("ActionGate NO_GO decision must assert no_go")
