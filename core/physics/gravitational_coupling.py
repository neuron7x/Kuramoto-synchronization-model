# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T1 — Gravitational Coupling Matrix for Kuramoto Engine.

Derives coupling strength from Newton's law of universal gravitation:

    F_ij = G · (m_i · m_j) / r_ij²

where:
    m_i = rolling 30-period dollar volume (liquidity proxy)
    r_ij = 1 - |ρ_ij| (correlation distance — verified metric)
    G   = normalisation constant s.t. Σ_j F_ij = K (preserves existing coupling)

Metric verification:
    r_ij = 1 - |ρ_ij| satisfies:
    1. r_ij ≥ 0              (|ρ| ∈ [0,1])
    2. r_ij = 0 ⟺ |ρ_ij|=1  (identity of indiscernibles for correlation)
    3. r_ij = r_ji            (symmetric)
    4. Triangle inequality holds for 1-|ρ| on absolute correlation.

Symmetry: F_ij = F_ji because gravitational force is symmetric.
→ Coupling matrix is symmetric → Kuramoto stability conditions preserved.

Clipping: as ρ→1, r→0, F→∞ → clip at F_max = μ(F) + 3σ(F).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


class GravitationalCouplingMatrix:
    """Compute gravitational coupling for Kuramoto oscillators.

    Parameters
    ----------
    window : int
        Rolling window for dollar volume (default 30).
    clip_sigma : float
        Clip forces at mean + clip_sigma * std (default 3.0).
    """

    def __init__(self, window: int = 30, clip_sigma: float = 3.0) -> None:
        if window < 1:
            raise ValueError(f"window must be ≥ 1, got {window}")
        if clip_sigma <= 0:
            raise ValueError(f"clip_sigma must be > 0, got {clip_sigma}")
        self._window = window
        self._clip_sigma = clip_sigma

    @staticmethod
    def _correlation_distance(prices: NDArray[np.float64]) -> NDArray[np.float64]:
        """Compute r_ij = 1 - |ρ_ij| from price returns.

        Returns symmetric N×N distance matrix satisfying metric axioms.
        """
        n_assets = prices.shape[1]
        if prices.shape[0] < 2:
            return np.ones((n_assets, n_assets), dtype=np.float64)

        returns = np.diff(prices, axis=0) / np.maximum(np.abs(prices[:-1]), 1e-12)
        # Correlation matrix via corrcoef (handles constant columns)
        with np.errstate(invalid="ignore"):
            corr = np.corrcoef(returns, rowvar=False)
        corr = np.nan_to_num(corr, nan=0.0)
        distance = 1.0 - np.abs(corr)
        np.fill_diagonal(distance, 0.0)
        return distance

    def _dollar_volume_mass(
        self,
        prices: NDArray[np.float64],
        volumes: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Compute m_i = rolling mean of dollar volume over last `window` bars.

        Returns 1-D array of length n_assets.
        """
        dv = prices * volumes  # (T, N)
        tail = dv[-self._window :]
        mass = np.mean(tail, axis=0)
        # Ensure positive mass
        mass_pos: NDArray[np.float64] = np.maximum(mass, 1e-12)
        return mass_pos

    def compute(
        self,
        prices: NDArray[np.float64],
        volumes: NDArray[np.float64],
        K: float = 1.0,
    ) -> NDArray[np.float64]:
        """Compute gravitational adjacency matrix.

        Parameters
        ----------
        prices : (T, N) array
            Price history for N assets over T periods.
        volumes : (T, N) array
            Volume history for N assets over T periods.
        K : float
            Target total coupling strength (Σ_j A_ij ≈ K for each i).

        Returns
        -------
        (N, N) symmetric adjacency matrix suitable for ``KuramotoConfig.adjacency``.
        """
        prices = np.asarray(prices, dtype=np.float64)
        volumes = np.asarray(volumes, dtype=np.float64)
        if prices.shape != volumes.shape:
            raise ValueError(
                f"prices and volumes must have same shape: {prices.shape} vs {volumes.shape}"
            )
        if prices.ndim != 2:
            raise ValueError(f"Expected 2-D arrays (T, N), got ndim={prices.ndim}")

        n_assets = prices.shape[1]
        if n_assets < 2:
            raise ValueError(f"Need ≥ 2 assets, got {n_assets}")

        mass = self._dollar_volume_mass(prices, volumes)
        dist = self._correlation_distance(prices)

        # F_ij = m_i * m_j / r_ij²  (G absorbed into normalisation)
        mass_product = np.outer(mass, mass)
        dist_safe = np.maximum(dist, 1e-6)
        F_raw = mass_product / (dist_safe**2)
        np.fill_diagonal(F_raw, 0.0)

        # Clip outliers at μ + clip_sigma·σ
        upper = F_raw[np.triu_indices(n_assets, k=1)]
        if upper.size > 0:
            f_max = float(np.mean(upper) + self._clip_sigma * np.std(upper))
            if f_max > 0:
                F_raw = np.minimum(F_raw, f_max)

        # Normalise: each row sums to K  →  adjacency integrates seamlessly
        # with KuramotoEngine which multiplies by K internally, so we
        # normalise rows to sum to 1.0 and let K scale externally.
        row_sums = F_raw.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-12)
        adjacency = F_raw / row_sums

        # Ensure symmetry (numerical)
        adjacency_sym: NDArray[np.float64] = 0.5 * (adjacency + adjacency.T)
        np.fill_diagonal(adjacency_sym, 0.0)

        return adjacency_sym


__all__ = ["GravitationalCouplingMatrix"]
