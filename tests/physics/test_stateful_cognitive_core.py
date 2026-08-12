# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Stateful witnesses for the cognitive-core admissibility law."""

from __future__ import annotations

import math
from collections.abc import Mapping

from core.physics.cognitive_core import CognitiveCore, Decision, Status

_NOMINAL: dict[str, object] = {
    "order_parameter_R": 0.5,
    "z_abs": 0.4,
    "ollivier_kappa": 0.2,
    "gamma": 1.5,
    "serotonin_level": 0.3,
    "gaba_gate": 0.8,
    "dopamine_signal": 0.5,
    "kelly_fraction": 0.25,
    "free_energy_components": (1.0, 0.5, 0.2),
}

_SEQUENCE: tuple[dict[str, object], ...] = (
    dict(_NOMINAL),
    {**_NOMINAL, "order_parameter_R": 0.91, "dopamine_signal": -0.75},
    {**_NOMINAL, "z_abs": 0.99, "kelly_fraction": 0.0},
    {**_NOMINAL, "gamma": 0.0, "free_energy_components": (0.0, 0.0, 0.0)},
    {**_NOMINAL, "ollivier_kappa": 1.0, "serotonin_level": 1.0},
)


def _finite_scalar(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    as_float = float(value)
    return as_float if math.isfinite(as_float) else None


def _model_admissible(snapshot: Mapping[str, object]) -> bool:
    if not snapshot:
        return False
    for key in ("order_parameter_R", "z_abs", "serotonin_level", "gaba_gate", "kelly_fraction"):
        value = _finite_scalar(snapshot.get(key))
        if value is None or not (0.0 <= value <= 1.0):
            return False
    kappa = _finite_scalar(snapshot.get("ollivier_kappa"))
    if kappa is None or kappa > 1.0:
        return False
    gamma = _finite_scalar(snapshot.get("gamma"))
    if gamma is None or gamma < 0.0:
        return False
    dopamine = _finite_scalar(snapshot.get("dopamine_signal"))
    if dopamine is None or abs(dopamine) > 1.0:
        return False
    free_energy = snapshot.get("free_energy_components")
    if not isinstance(free_energy, (tuple, list)) or len(free_energy) != 3:
        return False
    components = [_finite_scalar(component) for component in free_energy]
    return not any(component is None or component < 0.0 for component in components)


def test_stateful_admissibility_holds_over_sequences() -> None:
    core = CognitiveCore()
    decisions: list[Decision] = []
    for index, snapshot in enumerate(_SEQUENCE):
        expected = _model_admissible(snapshot)
        verdict = core.admissibility(snapshot)
        decisions.append(verdict.decision)
        assert verdict.admissible is expected, (
            f"transition {index}: admissible={verdict.admissible}, expected {expected}; "
            f"decision={verdict.decision}, violations={verdict.violations}"
        )
        if expected:
            assert verdict.decision is Decision.GO
            assert verdict.status is Status.ADMISSIBLE
            assert verdict.violations == ()
        else:
            assert verdict.decision is Decision.NO_GO
    assert decisions == [Decision.GO] * len(_SEQUENCE)


def test_stateful_model_oracle_is_discriminating() -> None:
    core = CognitiveCore()
    nominal = dict(_NOMINAL)
    changed = dict(_NOMINAL)
    changed["free_energy_components"] = (1.0, -0.01, 0.2)
    assert _model_admissible(nominal) is True
    assert _model_admissible(changed) is False
    nominal_verdict = core.admissibility(nominal)
    changed_verdict = core.admissibility(changed)
    assert nominal_verdict.decision is Decision.GO
    assert changed_verdict.decision is Decision.NO_GO
    assert changed_verdict.binding_constraint == "INV-FE2"
    assert changed_verdict.violations == ("INV-FE2",)
