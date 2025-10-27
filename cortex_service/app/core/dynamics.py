"""Core dynamical computations for the cognition service."""

from __future__ import annotations

import cmath
import math
from dataclasses import dataclass
from typing import Iterable, Sequence

from ..config import SignalSettings


@dataclass(slots=True)
class CognitionResult:
    """Container for the non-linear state, signal, and coherence."""

    state: float
    signal: float
    coherence: float


def _ensure_values(values: Sequence[float], label: str) -> None:
    if not values:
        msg = f"{label} cannot be empty"
        raise ValueError(msg)


def _normalized_moment(values: Sequence[float], floor: float) -> float:
    _ensure_values(values, "feature bundle")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    scale = math.sqrt(max(variance, floor))
    return mean / scale


def _phase(values: Sequence[float], floor: float) -> float:
    _ensure_values(values, "phase vector")
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return math.atan2(mean, math.sqrt(max(variance, floor)))


def _kuramoto(phases: Sequence[float]) -> float:
    if not phases:
        return 1.0
    complex_sum = sum(cmath.exp(1j * phase) for phase in phases)
    return abs(complex_sum) / len(phases)


def compute_cognition(
    features: Sequence[float],
    neighbors: Iterable[Sequence[float]],
    valence: float,
    settings: SignalSettings,
) -> CognitionResult:
    """Compute the cognition state, signal, and coherence."""

    _ensure_values(features, "features")
    floor = max(settings.volatility_floor, 1e-12)
    primary = _normalized_moment(features, floor)

    neighbor_inputs: list[float] = []
    neighbor_phases: list[float] = []
    for index, bundle in enumerate(neighbors, start=1):
        if not bundle:
            msg = f"neighbor bundle at position {index} cannot be empty"
            raise ValueError(msg)
        neighbor_inputs.append(_normalized_moment(bundle, floor))
        neighbor_phases.append(_phase(bundle, floor))

    if neighbor_inputs:
        coupling = settings.neighbor_coupling
        primary += coupling * sum(neighbor_inputs) / len(neighbor_inputs)

    state = settings.signal_gain * (-primary**3 + primary)
    valence_scale = 1.0 + settings.valence_coupling * valence
    signal = math.tanh(valence_scale * state)

    phases = [_phase(features, floor), *neighbor_phases]
    coherence = _kuramoto(phases)
    return CognitionResult(state=state, signal=signal, coherence=coherence)


__all__ = ["CognitionResult", "compute_cognition"]
