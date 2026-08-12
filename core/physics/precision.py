# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Precision fortress — numerical stability, ULP distance, drift, reproducibility.

Deterministic hashing reuses :func:`core.physics.determinism_kit.state_hash`
(ULP-sensitive, INV-DET2). The conditioning guard
:func:`assert_numerical_stability` gives teeth to the otherwise-vacuous
``cond(A) <= kappa_max`` clause of the HPC numerical-stability law: it actually
computes the condition number and fails closed when it exceeds an explicit
ceiling, alongside the NaN/Inf finiteness check.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike

from core.physics.determinism_kit import state_hash

__all__ = [
    "ulp_distance",
    "stable_sum",
    "drift_bound",
    "deterministic_hash",
    "assert_numerical_stability",
]


def ulp_distance(a: float, b: float) -> int:
    """Number of representable doubles between ``a`` and ``b`` (signed-magnitude).

    Zero iff bit-identical. Fails closed on NaN/Inf so an undefined distance is
    never silently returned as 0.
    """
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError(f"ulp_distance needs finite inputs, got a={a!r} b={b!r}; fail-closed")
    ia = _ordered_int(a)
    ib = _ordered_int(b)
    return int(abs(ia - ib))


def stable_sum(values: ArrayLike) -> float:
    """Compensated (Kahan/Neumaier via ``math.fsum``) sum of a 1-D sequence.

    Exact to one rounding of the true sum — used to detect when a naive running
    sum has drifted. Fails closed on NaN/Inf.
    """
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1:
        raise ValueError(f"values must be 1-D, got ndim={array.ndim}; fail-closed")
    if not np.all(np.isfinite(array)):
        raise ValueError("values contain NaN/Inf; fail-closed")
    return math.fsum(array.tolist())


def drift_bound(reference: float, candidate: float) -> int:
    """ULP drift between a reference value and a candidate (alias of ULP distance)."""
    return ulp_distance(reference, candidate)


def deterministic_hash(array: ArrayLike) -> str:
    """ULP-sensitive deterministic hash of a float array via the reproducibility kit."""
    values = np.asarray(array, dtype=np.float64)
    if not np.all(np.isfinite(values)):
        raise ValueError("array contains NaN/Inf; fail-closed")
    return state_hash(values)


def assert_numerical_stability(
    matrix: ArrayLike,
    *,
    kappa_max: float,
) -> float:
    """Fail closed on NaN/Inf or ``cond(matrix) > kappa_max``; return the cond number.

    ``kappa_max`` is an explicit, required ceiling — the configured condition
    number bound the HPC numerical-stability law refers to. A singular matrix has
    ``cond = +inf`` and therefore always violates a finite ceiling.
    """
    mat = np.asarray(matrix, dtype=np.float64)
    if mat.ndim != 2:
        raise ValueError(f"matrix must be 2-D, got ndim={mat.ndim}; fail-closed")
    if not np.all(np.isfinite(mat)):
        raise ValueError("NUMERICAL-STABILITY VIOLATED: matrix contains NaN/Inf; fail-closed")
    if not math.isfinite(kappa_max) or kappa_max <= 0.0:
        raise ValueError(f"kappa_max must be finite and > 0, got {kappa_max!r}; fail-closed")
    cond = float(np.linalg.cond(mat))
    if not math.isfinite(cond) or cond > kappa_max:
        raise ValueError(
            f"NUMERICAL-STABILITY VIOLATED: cond(A)={cond:.6g} > kappa_max={kappa_max:.6g}; "
            f"the linear system is ill-conditioned beyond the declared ceiling. Fail-closed."
        )
    return cond


def _ordered_int(value: float) -> int:
    """Map a double to a monotone signed integer ordering (for ULP arithmetic)."""
    bits = int(np.asarray(value, dtype=np.float64).view(np.int64))
    if bits < 0:
        # Flip negatives to a continuous descending range below positives.
        return -(bits & 0x7FFFFFFFFFFFFFFF)
    return bits
