# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Non-self-similar cluster-growth witness — engineering analog of S8.

pattern_id:        P8_NON_SELFSIMILAR_CLUSTER_GROWTH
source_id:         S8_ACTIVE_COARSENING_NON_SELFSIMILAR
claim_tier:        ENGINEERING_ANALOG

Cluster-growth modelling must not collapse multi-window dynamics into a
single exponent. The named lie blocked here is "one growth exponent
explains all windows": a cluster-growth process is classified
SELF_SIMILAR only when every per-window exponent agrees with the
assumed exponent within ``tolerance``. Any window whose exponent
diverges beyond tolerance falsifies self-similarity.

Statuses:
    SELF_SIMILAR        every per-window exponent within tolerance of
                        the assumed exponent
    NON_SELF_SIMILAR    at least one window exponent diverges beyond
                        tolerance; ``divergent_windows`` lists offenders
    INSUFFICIENT_DATA   any window has fewer than two data points
                        (cannot fit an exponent)
    INVALID_INPUT       degenerate inputs (non-positive sizes, zero-
                        variance window) that prevent fitting

Non-claims: no one-to-one correspondence with active-matter physics; no
forecast / signal / trading interpretation; the witness emits per-
window exponent measurements and a deterministic comparison verdict.
Determinism: pure function, no I/O / clock / random.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

import numpy as np

__all__ = [
    "GrowthStatus",
    "GrowthInput",
    "GrowthWitness",
    "assess_non_selfsimilar_growth",
]


_FALSIFIER_TEXT = (
    "SELF_SIMILAR was returned but at least one per-window exponent "
    "diverged from the assumed exponent beyond the documented "
    "tolerance. OR: the per-window check was collapsed into a single "
    "global exponent fit and a non-self-similar window was silently "
    "absorbed into the global fit."
)


class GrowthStatus(str, Enum):
    SELF_SIMILAR = "SELF_SIMILAR"
    NON_SELF_SIMILAR = "NON_SELF_SIMILAR"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    INVALID_INPUT = "INVALID_INPUT"


def _fit_exponent(series: np.ndarray, start: int, end: int) -> float:
    """Fit growth exponent on log-log axes via linear regression.

    Window covers indices [start, end); cluster size at index t is
    ``series[t]``, time at index t is ``t + 1`` (1-based to keep
    log(time) finite for t == 0). Returns the slope of
    log(size) vs log(time). Returns NaN on zero-variance or
    non-positive-size windows.
    """
    n = end - start
    if n < 2:
        return float("nan")
    sizes = series[start:end]
    if np.any(sizes <= 0.0):
        return float("nan")
    times = np.arange(start + 1, end + 1, dtype=float)
    log_t = np.log(times)
    log_s = np.log(sizes)
    if float(log_t.std(ddof=0)) == 0.0:
        return float("nan")
    slope, _intercept = np.polyfit(log_t, log_s, 1)
    return float(slope)


@dataclass(frozen=True)
class GrowthInput:
    """One non-self-similar growth question.

    ``cluster_size_series`` is a tuple of strictly-positive cluster-size
    measurements at successive time steps (index t corresponds to time
    t+1). ``window_indices`` is a tuple of (start, end) pairs over the
    series, end-exclusive. ``assumed_exponent`` is the self-similar
    growth exponent the caller wishes to test against. ``tolerance`` is
    the absolute distance below which a per-window exponent is
    considered to agree with the assumed exponent.
    """

    cluster_size_series: tuple[float, ...]
    window_indices: tuple[tuple[int, int], ...]
    assumed_exponent: float
    tolerance: float

    def __post_init__(self) -> None:
        if not isinstance(self.cluster_size_series, tuple):
            raise TypeError("cluster_size_series must be a tuple of floats")
        if len(self.cluster_size_series) == 0:
            raise ValueError("cluster_size_series must be non-empty")
        for i, v in enumerate(self.cluster_size_series):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                raise TypeError(f"cluster_size_series[{i}] must be a finite float")
            if not math.isfinite(float(v)):
                raise ValueError(f"cluster_size_series[{i}] must be finite (got {v!r})")
            if float(v) <= 0.0:
                raise ValueError(
                    f"cluster_size_series[{i}] must be > 0 (got {v!r}); "
                    "log-log fit requires strictly positive sizes"
                )

        if not isinstance(self.window_indices, tuple):
            raise TypeError("window_indices must be a tuple of (start, end) pairs")
        if len(self.window_indices) == 0:
            raise ValueError("window_indices must be non-empty")
        n = len(self.cluster_size_series)
        for i, pair in enumerate(self.window_indices):
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise TypeError(f"window_indices[{i}] must be a (start, end) tuple")
            start, end = pair
            if not isinstance(start, int) or isinstance(start, bool):
                raise TypeError(f"window_indices[{i}].start must be int")
            if not isinstance(end, int) or isinstance(end, bool):
                raise TypeError(f"window_indices[{i}].end must be int")
            if not (0 <= start < end <= n):
                raise ValueError(
                    f"window_indices[{i}] = ({start}, {end}) must satisfy 0 <= start < end <= {n}"
                )

        for name, value in (
            ("assumed_exponent", self.assumed_exponent),
            ("tolerance", self.tolerance),
        ):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise TypeError(f"{name} must be a finite float")
            if not math.isfinite(float(value)):
                raise ValueError(f"{name} must be finite (got {value!r})")
        if float(self.tolerance) < 0.0:
            raise ValueError(f"tolerance must be >= 0 (got {self.tolerance!r})")


@dataclass(frozen=True)
class GrowthWitness:
    """One non-self-similar growth verdict."""

    status: GrowthStatus
    per_window_exponents: tuple[float, ...]
    divergent_windows: tuple[int, ...]
    assumed_exponent: float
    tolerance_used: float
    reason: str
    falsifier: str
    evidence_fields: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))


def assess_non_selfsimilar_growth(input_: GrowthInput) -> GrowthWitness:
    """Pure per-window exponent comparison.

    Priority (first failing condition wins):
        1. any window has fewer than 2 points → INSUFFICIENT_DATA
        2. any window exponent fit returns NaN → INVALID_INPUT
        3. any |exponent − assumed| > tolerance → NON_SELF_SIMILAR
        4. otherwise                            → SELF_SIMILAR
    """
    series = np.asarray(input_.cluster_size_series, dtype=float)
    assumed = float(input_.assumed_exponent)
    tolerance = float(input_.tolerance)

    # Per-window slope fits.
    exponents: list[float] = []
    too_short = False
    invalid = False
    for start, end in input_.window_indices:
        if end - start < 2:
            too_short = True
            exponents.append(float("nan"))
            continue
        slope = _fit_exponent(series, start, end)
        if not math.isfinite(slope):
            invalid = True
        exponents.append(slope)
    per_window = tuple(exponents)

    divergent: list[int] = []
    for i, exp in enumerate(per_window):
        if math.isfinite(exp) and abs(exp - assumed) > tolerance:
            divergent.append(i)
    divergent_t = tuple(divergent)

    evidence = MappingProxyType(
        {
            "n_series": len(series),
            "n_windows": len(input_.window_indices),
            "per_window_exponents": per_window,
            "assumed_exponent": assumed,
            "tolerance": tolerance,
            "divergent_windows": divergent_t,
        }
    )

    def _build(status: GrowthStatus, reason: str) -> GrowthWitness:
        return GrowthWitness(
            status=status,
            per_window_exponents=per_window,
            divergent_windows=divergent_t,
            assumed_exponent=assumed,
            tolerance_used=tolerance,
            reason=reason,
            falsifier=_FALSIFIER_TEXT,
            evidence_fields=evidence,
        )

    if too_short:
        return _build(GrowthStatus.INSUFFICIENT_DATA, "WINDOW_BELOW_TWO_POINTS")
    if invalid:
        return _build(GrowthStatus.INVALID_INPUT, "DEGENERATE_WINDOW_NO_VARIANCE_OR_NONPOS_SIZE")
    if divergent_t:
        return _build(
            GrowthStatus.NON_SELF_SIMILAR,
            "PER_WINDOW_EXPONENT_DIVERGES_FROM_ASSUMED",
        )
    return _build(
        GrowthStatus.SELF_SIMILAR,
        "OK_ALL_PER_WINDOW_EXPONENTS_AGREE",
    )
