# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Metric / embedding consistency — does the geometry lie?

Quantifies whether an embedding preserves the original metric within an
explicit bi-Lipschitz bound, so downstream curvature is intrinsic and not an
embedding artifact. Thresholds are always explicit arguments — never magic
constants baked into the bound. Fails closed on singular/degenerate metrics.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike, NDArray

__all__ = [
    "pairwise_distances",
    "distortion",
    "assert_distortion_bound",
    "perturb_embedding",
    "condition_number",
]


def _as_2d_finite(name: str, values: ArrayLike) -> NDArray[np.float64]:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 2:
        raise ValueError(f"{name} must be 2-D (n_points, n_dims), got ndim={array.ndim}")
    if array.shape[0] < 2:
        raise ValueError(f"{name} needs >= 2 points, got {array.shape[0]}; fail-closed")
    if not np.all(np.isfinite(array)):
        raise ValueError(f"{name} contains NaN/Inf; fail-closed")
    return array


def pairwise_distances(points: ArrayLike) -> NDArray[np.float64]:
    """Euclidean pairwise-distance matrix of a point cloud (n_points, n_dims)."""
    pts = _as_2d_finite("points", points)
    diff = pts[:, np.newaxis, :] - pts[np.newaxis, :, :]
    return np.sqrt((diff * diff).sum(axis=-1))


def _validate_metric(name: str, matrix: ArrayLike) -> NDArray[np.float64]:
    dist = np.asarray(matrix, dtype=np.float64)
    if dist.ndim != 2 or dist.shape[0] != dist.shape[1]:
        raise ValueError(f"{name} must be a square distance matrix; fail-closed")
    if dist.shape[0] < 2:
        raise ValueError(f"{name} must have >= 2 nodes; fail-closed")
    if not np.all(np.isfinite(dist)):
        raise ValueError(f"{name} contains NaN/Inf — singular/undefined metric; fail-closed")
    if np.any(dist < 0.0):
        raise ValueError(f"{name} has negative distances; fail-closed")
    off_diag = ~np.eye(dist.shape[0], dtype=bool)
    if np.any(dist[off_diag] <= 0.0):
        raise ValueError(
            f"{name} has a zero/degenerate off-diagonal distance — coincident or "
            f"disconnected points make distortion undefined; fail-closed"
        )
    return dist


def distortion(original_metric: ArrayLike, embedded_metric: ArrayLike) -> float:
    """Multiplicative bi-Lipschitz distortion of an embedding.

    distortion = max_ij (d_emb/d_orig) * max_ij (d_orig/d_emb) over off-diagonal
    pairs. A perfect isometry gives exactly 1.0; larger values mean the embedded
    geometry stretches/compresses distances relative to the original.
    """
    orig = _validate_metric("original_metric", original_metric)
    emb = _validate_metric("embedded_metric", embedded_metric)
    if orig.shape != emb.shape:
        raise ValueError(
            f"metric shapes differ: original {orig.shape} vs embedded {emb.shape}; fail-closed"
        )
    off_diag = ~np.eye(orig.shape[0], dtype=bool)
    ratio = emb[off_diag] / orig[off_diag]
    expansion = float(ratio.max())
    contraction = float((1.0 / ratio).max())
    return expansion * contraction


def assert_distortion_bound(
    original_metric: ArrayLike,
    embedded_metric: ArrayLike,
    *,
    max_distortion: float,
) -> float:
    """Fail closed unless ``distortion - 1 <= max_distortion``.

    ``max_distortion`` is a REQUIRED, explicit, non-negative bound (a value of
    0.0 demands a perfect isometry). Returns the measured distortion on success.
    """
    if not np.isfinite(max_distortion) or max_distortion < 0.0:
        raise ValueError(f"max_distortion must be finite and >= 0, got {max_distortion!r}")
    measured = distortion(original_metric, embedded_metric)
    excess = measured - 1.0
    if excess > max_distortion:
        raise ValueError(
            f"METRIC-DISTORTION VIOLATED: distortion-1={excess:.6g} > "
            f"max_distortion={max_distortion:.6g} (measured distortion={measured:.6g}). "
            f"Embedding does not preserve the metric within the declared bound. Fail-closed."
        )
    return measured


def perturb_embedding(points: ArrayLike, epsilon: float, seed: int) -> NDArray[np.float64]:
    """Add seeded Gaussian noise of scale ``epsilon`` to a point cloud.

    Deterministic given ``seed``. Used to manufacture a controlled metric
    distortion for the negative control.
    """
    pts = _as_2d_finite("points", points)
    if not np.isfinite(epsilon) or epsilon < 0.0:
        raise ValueError(f"epsilon must be finite and >= 0, got {epsilon!r}; fail-closed")
    # Explicit seeded generator (deterministic, not ambient nondeterminism).
    rng = np.random.Generator(np.random.PCG64(seed))
    return pts + rng.normal(0.0, epsilon, size=pts.shape)


def condition_number(matrix: ArrayLike) -> float:
    """2-norm condition number of a matrix; +inf for a singular matrix.

    Mirrors the conditioning guard used in ``analytics/math_trading`` covariance
    inversion. Fails closed on NaN/Inf input rather than returning a NaN.
    """
    mat = np.asarray(matrix, dtype=np.float64)
    if mat.ndim != 2:
        raise ValueError(f"matrix must be 2-D, got ndim={mat.ndim}; fail-closed")
    if not np.all(np.isfinite(mat)):
        raise ValueError("matrix contains NaN/Inf; fail-closed")
    return float(np.linalg.cond(mat))
