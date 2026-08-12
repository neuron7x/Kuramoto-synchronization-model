# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import pytest

from geosync.core.neuro.dopamine.action_gate import GateEvaluation
from geosync.core.neuro.dopamine.action_gate_runtime_monitor import (
    validate_action_gate_evaluation,
)


class _Bounds:
    def __init__(self, lower: float = 0.2, upper: float = 0.6) -> None:
        self.lower = lower
        self.upper = upper

    def temperature_bounds(self) -> tuple[float, float]:
        return (self.lower, self.upper)


def test_runtime_monitor_accepts_valid_evaluation() -> None:
    validate_action_gate_evaluation(
        GateEvaluation(
            decision="GO",
            score=0.7,
            go=True,
            hold=False,
            no_go=False,
            temperature=0.4,
            dopamine_level=0.8,
        ),
        _Bounds(),
    )


def test_runtime_monitor_rejects_flag_inconsistency() -> None:
    with pytest.raises(AssertionError, match="GO flag"):
        validate_action_gate_evaluation(
            GateEvaluation(
                decision="GO",
                score=0.7,
                go=False,
                hold=False,
                no_go=False,
                temperature=0.4,
                dopamine_level=0.8,
            ),
            _Bounds(),
        )


def test_runtime_monitor_rejects_temperature_escape() -> None:
    with pytest.raises(AssertionError, match="temperature bounds"):
        validate_action_gate_evaluation(
            GateEvaluation(
                decision="HOLD",
                score=0.4,
                go=False,
                hold=False,
                no_go=False,
                temperature=9.0,
                dopamine_level=0.4,
            ),
            _Bounds(),
        )


def test_runtime_monitor_rejects_invalid_provider_bounds() -> None:
    with pytest.raises(ValueError, match="lower <= upper"):
        validate_action_gate_evaluation(
            GateEvaluation(
                decision="NO_GO",
                score=0.0,
                go=False,
                hold=True,
                no_go=True,
                temperature=0.4,
                dopamine_level=0.1,
            ),
            _Bounds(lower=0.6, upper=0.2),
        )
