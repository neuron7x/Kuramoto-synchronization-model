from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence
import math
import numbers

import numpy as np


ALLOWED_ACTIONS: tuple[str, ...] = (
    "increase_risk",
    "decrease_risk",
    "switch_to_alt",
    "hedge",
    "hold",
)
ALLOWED_MODES: tuple[str, ...] = ("GREEN", "AMBER", "RED")
OBS_KEYS: tuple[str, ...] = ("dd", "liq", "reg", "vol", "reward")


class ContractViolation(ValueError):
    """Raised when strict contract checks fail."""


@dataclass(frozen=True)
class SignalContract:
    required: tuple[str, ...] = ()
    ranges: Mapping[str, tuple[float, float]] = field(default_factory=dict)
    non_negative: tuple[str, ...] = ()
    categorical: Mapping[str, Sequence[str]] = field(default_factory=dict)

    def validate(self, payload: Mapping[str, Any], label: str) -> list[str]:
        errors: list[str] = []
        missing = [key for key in self.required if key not in payload]
        if missing:
            errors.append(f"{label} missing required fields: {sorted(missing)}")
        for key, (low, high) in self.ranges.items():
            if key not in payload:
                continue
            value = payload[key]
            if not _is_real(value):
                errors.append(f"{label}.{key} must be numeric")
                continue
            numeric = float(value)
            if not (low <= numeric <= high):
                errors.append(
                    f"{label}.{key} out of range [{low}, {high}]: {numeric}"
                )
        for key in self.non_negative:
            if key not in payload:
                continue
            value = payload[key]
            if not _is_real(value):
                errors.append(f"{label}.{key} must be numeric")
                continue
            if float(value) < 0.0:
                errors.append(f"{label}.{key} must be non-negative: {value}")
        for key, allowed in self.categorical.items():
            if key not in payload:
                continue
            value = payload[key]
            if value not in allowed:
                errors.append(
                    f"{label}.{key} must be one of {sorted(allowed)}: {value!r}"
                )
        return errors


@dataclass(frozen=True)
class LipschitzSpec:
    keys: tuple[str, ...]
    constant: float
    epsilon: float = 0.4


def _is_real(value: Any) -> bool:
    return isinstance(value, numbers.Real) and math.isfinite(float(value))


def _obs_distance(
    current: Mapping[str, Any], previous: Mapping[str, Any]
) -> float:
    deltas = []
    for key in OBS_KEYS:
        if key in current and key in previous and _is_real(current[key]):
            deltas.append(float(current[key]) - float(previous[key]))
    if not deltas:
        return 0.0
    return float(np.linalg.norm(np.asarray(deltas, dtype=float)))


def _check_lipschitz(
    label: str,
    current: Mapping[str, Any],
    previous: Mapping[str, Any],
    input_delta: float,
    spec: LipschitzSpec,
) -> list[str]:
    errors: list[str] = []
    bound = spec.constant * input_delta + spec.epsilon
    for key in spec.keys:
        if key not in current or key not in previous:
            continue
        if not _is_real(current[key]) or not _is_real(previous[key]):
            continue
        delta = abs(float(current[key]) - float(previous[key]))
        if delta > bound:
            errors.append(
                f"{label}.{key} Lipschitz violation: {delta:.4f} > {bound:.4f}"
            )
    return errors


@dataclass(frozen=True)
class SignalContracts:
    obs: SignalContract = field(
        default_factory=lambda: SignalContract(
            required=("dd", "liq", "reg", "vol"),
            ranges={
                "dd": (0.0, 1.0),
                "liq": (0.0, 1.0),
                "reg": (0.0, 1.0),
                "vol": (0.0, 1.0),
                "reward": (-1.0, 1.0),
                "sensory_confidence": (0.0, 1.0),
                "m_proxy": (0.0, 1.0),
            },
        )
    )
    state: SignalContract = field(
        default_factory=lambda: SignalContract(
            required=("H", "M", "E", "S"),
            ranges={
                "H": (0.0, 1.0),
                "M": (0.0, 1.0),
                "E": (0.0, 1.0),
                "S": (0.0, 1.0),
                "D": (0.0, 1.0),
            },
            categorical={"mode": ALLOWED_MODES},
        )
    )
    decision: SignalContract = field(
        default_factory=lambda: SignalContract(
            required=("action", "alloc_main", "alloc_alt", "alloc_scale"),
            ranges={
                "alloc_main": (0.0, 1.0),
                "alloc_alt": (0.0, 1.0),
                "alloc_scale": (0.0, 1.0),
                "sensory_confidence": (0.0, 1.0),
                "belief": (0.0, 1.0),
                "prediction_error": (0.0, 2.0),
            },
            non_negative=(
                "prediction_error",
                "timing_sensory_ms",
                "timing_predictive_ms",
                "timing_model_step_ms",
                "timing_ctrl_decide_ms",
            ),
            categorical={"action": ALLOWED_ACTIONS},
        )
    )
    lipschitz_state: LipschitzSpec = LipschitzSpec(
        keys=("H", "M", "E", "S", "D"), constant=3.0
    )
    lipschitz_decision: LipschitzSpec = LipschitzSpec(
        keys=("alloc_main", "alloc_alt", "alloc_scale"), constant=3.0
    )

    def validate_obs(self, obs: Mapping[str, Any]) -> list[str]:
        return self.obs.validate(obs, "obs")

    def validate_state(self, state: Mapping[str, Any]) -> list[str]:
        return self.state.validate(state, "state")

    def validate_decision(self, decision: Mapping[str, Any]) -> list[str]:
        return self.decision.validate(decision, "decision")

    def validate_lipschitz(
        self,
        obs: Mapping[str, Any],
        decision: Mapping[str, Any],
        previous_obs: Mapping[str, Any] | None,
        previous_decision: Mapping[str, Any] | None,
    ) -> list[str]:
        if previous_obs is None or previous_decision is None:
            return []
        input_delta = _obs_distance(obs, previous_obs)
        errors = []
        errors.extend(
            _check_lipschitz(
                "state",
                decision,
                previous_decision,
                input_delta,
                self.lipschitz_state,
            )
        )
        errors.extend(
            _check_lipschitz(
                "decision",
                decision,
                previous_decision,
                input_delta,
                self.lipschitz_decision,
            )
        )
        return errors


def check_alloc_monotonicity(
    scale: float,
    pre_scale_main: float,
    pre_scale_alt: float,
    post_scale_main: float,
    post_scale_alt: float,
) -> list[str]:
    errors: list[str] = []
    if scale <= 1.0:
        if post_scale_main > pre_scale_main + 1e-6:
            errors.append("alloc_main increased despite scaling factor <= 1.0")
        if post_scale_alt > pre_scale_alt + 1e-6:
            errors.append("alloc_alt increased despite scaling factor <= 1.0")
    return errors
