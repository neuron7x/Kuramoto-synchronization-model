# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Rosenstein (1993) maximal Lyapunov exponent estimator.

Algorithm:
  1. Reconstruct phase space via delay embedding (m=3, τ=1)
  2. Find nearest neighbor for each point (exclude temporal neighbors)
  3. Track average log divergence over time
  4. λ_max = slope of divergence curve (linear region)

λ > 0 → chaotic (sensitive dependence on initial conditions)
λ < 0 → stable (perturbations decay)
λ ≈ 0 → marginal (edge of chaos)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class LyapunovEstimate:
    """Maximal Lyapunov exponent with derived metrics."""

    lambda_max: float  # largest Lyapunov exponent
    is_chaotic: bool  # λ > 0
    doubling_time: float  # ln(2) / λ (inf if stable)
    divergence_rate: float  # normalized to [0, 1]
    is_valid: bool  # enough data + finite result


class RosensteinLyapunov:
    """Rosenstein et al. (1993) largest Lyapunov exponent.

    Parameters
    ----------
    m
        Embedding dimension.
    tau
        Time delay for embedding.
    mean_period
        Minimum temporal separation for neighbor search.
    max_divergence_steps
        Number of steps to track divergence.
    """

    def __init__(
        self,
        m: int = 3,
        tau: int = 1,
        mean_period: int = 5,
        max_divergence_steps: int = 15,
    ) -> None:
        self.m = m
        self.tau = tau
        self.mean_period = mean_period
        self.max_steps = max_divergence_steps

    def compute(self, series: np.ndarray) -> LyapunovEstimate:
        """Compute largest Lyapunov exponent from 1D series.

        Behaviour is unchanged from the pre-ARC-001 monolith; the divergence
        accumulation and the scaling-region fit are extracted into
        :func:`_accumulate_log_divergence` and :func:`_fit_scaling_region` so
        each stays within the code-hygiene complexity budget. INV-LE1/LE2/LE3
        are preserved bit-for-bit (see test_lyapunov_compute_characterization).
        """
        x = np.asarray(series, dtype=np.float64)
        if x.ndim != 1 or not np.all(np.isfinite(x)):
            return _invalid_estimate()

        min_len = (self.m - 1) * self.tau + self.max_steps + self.mean_period + 10
        if x.size < max(min_len, 200):
            return _invalid_estimate()

        # 1. Delay embedding
        emb = _delay_embed(x, self.m, self.tau)
        n_pts = emb.shape[0]

        if n_pts < self.max_steps + self.mean_period + 5:
            return _invalid_estimate()

        # 2. Find nearest neighbors (exclude temporal neighbors)
        nn_idx = _find_nearest_neighbors(emb, self.mean_period)

        # 3. Track divergence
        usable = n_pts - self.max_steps
        if usable < 10:
            return _invalid_estimate()

        divergence, counts = _accumulate_log_divergence(emb, nn_idx, n_pts, usable, self.max_steps)

        # Average log divergence
        valid_mask = counts > 0
        if valid_mask.sum() < 3:
            return _invalid_estimate()

        avg_div = np.zeros_like(divergence)
        avg_div[valid_mask] = divergence[valid_mask] / counts[valid_mask]

        # 4. Fit the linear scaling region and apply the INV-LE3 R² gate.
        return _fit_scaling_region(avg_div, valid_mask)


def _invalid_estimate() -> LyapunovEstimate:
    """Fail-closed sentinel (INV-LE3): non-scaling / insufficient data.

    A fresh instance per call so no shared mutable/identity state leaks; the
    frozen dataclass compares by value regardless.
    """
    return LyapunovEstimate(0.0, False, math.inf, 0.0, False)


def _accumulate_log_divergence(
    emb: np.ndarray,
    nn_idx: np.ndarray,
    n_pts: int,
    usable: int,
    max_steps: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Sum log neighbor-pair divergence per step (Rosenstein step 3).

    Returns ``(divergence, counts)`` where ``divergence[k]`` is the summed
    ``log`` Euclidean distance at step ``k`` and ``counts[k]`` the number of
    contributing pairs. Extracted verbatim from ``compute``; numerics unchanged.
    """
    divergence = np.zeros(max_steps, dtype=np.float64)
    counts = np.zeros(max_steps, dtype=np.int64)

    for i in range(usable):
        j = nn_idx[i]
        if j < 0 or j + max_steps > n_pts or i + max_steps > n_pts:
            continue
        for k in range(max_steps):
            dist = np.linalg.norm(emb[i + k] - emb[j + k])
            if dist > 0:
                divergence[k] += math.log(dist)
                counts[k] += 1

    return divergence, counts


def _fit_scaling_region(avg_div: np.ndarray, valid_mask: np.ndarray) -> LyapunovEstimate:
    """Linear fit over the valid scaling steps + INV-LE3 R² gate (step 4).

    Extracted verbatim from ``compute``; the slope, the R²≥0.80 acceptance gate
    and the fail-closed demotion to λ=0.0 are numerically identical.
    """
    # avg_div is zero-filled at invalid steps (np.zeros_like); those zeros are
    # finite and would slip past np.isfinite, dragging the polyfit slope toward
    # a spurious 0.0 anchor. Select by valid_mask so the time axis (step index
    # k) stays aligned with its divergence value, since valid steps are not
    # guaranteed to be a contiguous prefix.
    valid_idx = np.flatnonzero(valid_mask)
    fit_len = min(10, valid_idx.size)
    sel = valid_idx[:fit_len]
    t_vals = sel.astype(np.float64)
    d_vals = avg_div[sel]

    if len(t_vals) < 3 or not np.all(np.isfinite(d_vals)):
        return _invalid_estimate()

    coeffs = np.polyfit(t_vals, d_vals, deg=1)
    lambda_max = float(coeffs[0])

    if not math.isfinite(lambda_max):
        return _invalid_estimate()

    # INV-LE3: Rosenstein λ is valid ONLY on the LINEAR scaling region. Gate on
    # the coefficient of determination of the fit; below R2_MIN the divergence
    # curve is non-scaling, so demote to is_valid=False and fail closed to
    # λ=0.0 rather than returning a silent (unreliable) slope.
    # bounds: R2_MIN=0.80 per INV-LE3; ss_tot==0 (flat curve) → non-scaling.
    r2_min = 0.80
    fit_vals = np.polyval(coeffs, t_vals)
    ss_res = float(np.sum((d_vals - fit_vals) ** 2))
    ss_tot = float(np.sum((d_vals - float(np.mean(d_vals))) ** 2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 0.0
    if r_squared < r2_min:
        return _invalid_estimate()

    is_chaotic = lambda_max > 0.01  # small positive threshold
    doubling_time = math.log(2) / max(lambda_max, 1e-12) if is_chaotic else math.inf
    divergence_rate = float(np.clip(lambda_max / 1.0, 0.0, 1.0))  # normalize

    return LyapunovEstimate(
        lambda_max=round(lambda_max, 6),
        is_chaotic=is_chaotic,
        doubling_time=(round(doubling_time, 2) if math.isfinite(doubling_time) else math.inf),
        divergence_rate=round(divergence_rate, 4),
        is_valid=True,
    )


def _delay_embed(x: np.ndarray, m: int, tau: int) -> np.ndarray:
    """Takens delay embedding: (N - (m-1)*tau, m) matrix."""
    n = len(x) - (m - 1) * tau
    if n <= 0:
        return np.empty((0, m))
    return np.column_stack([x[i * tau : i * tau + n] for i in range(m)])


def _find_nearest_neighbors(emb: np.ndarray, min_sep: int) -> np.ndarray:
    """Find nearest neighbor for each point, excluding temporal neighbors."""
    n = emb.shape[0]
    nn_idx = np.full(n, -1, dtype=np.int64)

    for i in range(n):
        best_dist = math.inf
        best_j = -1
        for j in range(n):
            if abs(i - j) < min_sep:
                continue
            d = float(np.sum((emb[i] - emb[j]) ** 2))
            if d < best_dist:
                best_dist = d
                best_j = j
        nn_idx[i] = best_j

    return nn_idx
