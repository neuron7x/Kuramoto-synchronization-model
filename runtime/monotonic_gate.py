"""Utilities for enforcing the thermodynamic monotonic invariant."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import fmean
from typing import Iterable, Sequence

DEFAULT_TOLERANCE_MULTIPLIER = 0.01
DEFAULT_DECAY = 0.9


@dataclass(frozen=True, slots=True)
class MonotonicGateResult:
    """Result of evaluating the F_new ≤ F_old + ε invariant."""

    holds: bool
    epsilon_spike: float
    delta_F: float


def compute_epsilon_spike(
    baseline_ema: float, multiplier: float = DEFAULT_TOLERANCE_MULTIPLIER
) -> float:
    """Return the admissible spike magnitude based on the baseline EMA."""

    baseline = max(float(baseline_ema), 0.0)
    epsilon = multiplier * baseline
    return float(epsilon)


def predict_recovery_window(
    F_new: float,
    baseline_F: float,
    window_size: int = 3,
    *,
    decay: float = DEFAULT_DECAY,
) -> list[float]:
    """Predict a short recovery window following a temporary spike."""

    if window_size <= 0:
        return []

    predictions: list[float] = []
    for i in range(1, window_size + 1):
        weight = decay**i
        predictions.append(F_new * weight + baseline_F * (1.0 - weight))
    return predictions


def check_monotonic_invariant(
    F_old: float,
    F_new: float,
    epsilon_spike: float,
    *,
    predictions: Sequence[float] | None = None,
) -> MonotonicGateResult:
    """Check whether the monotonic invariant holds for the given values."""

    epsilon = max(float(epsilon_spike), 0.0)
    delta_F = float(F_new) - float(F_old)

    if delta_F <= epsilon:
        return MonotonicGateResult(True, epsilon, delta_F)

    if delta_F > 0.0 and predictions:
        if fmean(predictions) < float(F_old):
            return MonotonicGateResult(True, epsilon, delta_F)

    return MonotonicGateResult(False, epsilon, delta_F)


def assert_monotonic_invariant(
    F_old: float,
    F_new: float,
    *,
    baseline_ema: float,
    epsilon_multiplier: float = DEFAULT_TOLERANCE_MULTIPLIER,
    predictions: Iterable[float] | None = None,
) -> MonotonicGateResult:
    """Assert that the monotonic invariant holds and raise if it does not."""

    epsilon = compute_epsilon_spike(baseline_ema, multiplier=epsilon_multiplier)
    result = check_monotonic_invariant(F_old, F_new, epsilon, predictions=list(predictions or []))
    if not result.holds:
        raise AssertionError(
            f"Invariant violated: ΔF={result.delta_F} exceeds ε={result.epsilon_spike}"
        )
    return result


__all__ = [
    "MonotonicGateResult",
    "DEFAULT_DECAY",
    "DEFAULT_TOLERANCE_MULTIPLIER",
    "assert_monotonic_invariant",
    "check_monotonic_invariant",
    "compute_epsilon_spike",
    "predict_recovery_window",
]
