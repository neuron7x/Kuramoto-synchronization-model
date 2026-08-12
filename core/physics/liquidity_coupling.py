# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T1 — Liquidity-weighted Kuramoto coupling.

Coupling matrix:
    A_ij(t) = C_ij(t) · √(m_i · m_j) / max(m)

where:
    C_ij(t) = rolling correlation between asset returns
    m_i     = rolling 30-period dollar volume (liquidity mass)
    max(m)  = normalisation to keep A_ij ∈ [0, 1]

Hypothesis: liquidity-weighting improves regime detection accuracy
vs uniform coupling, because:
    1. High-liquidity pairs have more reliable correlation estimates
    2. Liquidity concentration precedes systemic stress
    3. The √(m_i·m_j)/max(m) factor is dimensionless and bounded

Benchmark targets: 2008 GFC and 2020 COVID crash data.
This is a novel contribution if positive — no prior paper combines
Kuramoto synchronization with liquidity-weighted coupling.

References:
    Acebrón et al. "The Kuramoto model" Rev. Mod. Phys. (2005)
    Mantegna "Hierarchical structure in financial markets" Eur. Phys. J. B (1999)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class CouplingBenchmarkResult:
    """Comparison of coupling methods on regime detection."""

    uniform_R_trajectory: NDArray[np.float64]
    liquidity_R_trajectory: NDArray[np.float64]
    uniform_regime_accuracy: float
    liquidity_regime_accuracy: float
    improvement_pct: float


class LiquidityCouplingMatrix:
    """Liquidity-weighted Kuramoto coupling matrix.

    Parameters
    ----------
    volume_window : int
        Rolling window for dollar volume computation (default 30).
    correlation_window : int
        Rolling window for return correlation (default 60).
    min_correlation : float
        Minimum absolute correlation for edge inclusion (default 0.0).
        Set > 0 to create sparse coupling.
    """

    def __init__(
        self,
        volume_window: int = 30,
        correlation_window: int = 60,
        min_correlation: float = 0.0,
    ) -> None:
        if volume_window < 1:
            raise ValueError(f"volume_window must be ≥ 1, got {volume_window}")
        if correlation_window < 2:
            raise ValueError(f"correlation_window must be ≥ 2, got {correlation_window}")
        if not 0 <= min_correlation < 1:
            raise ValueError(f"min_correlation must be in [0, 1), got {min_correlation}")
        self._vol_window = volume_window
        self._corr_window = correlation_window
        self._min_corr = min_correlation

    @property
    def volume_window(self) -> int:
        return self._vol_window

    @property
    def correlation_window(self) -> int:
        return self._corr_window

    def _compute_mass(
        self,
        prices: NDArray[np.float64],
        volumes: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Rolling dollar volume mass. Shape: (N,)."""
        dv = prices * volumes
        tail = dv[-self._vol_window :]
        mass = np.mean(tail, axis=0)
        result: NDArray[np.float64] = np.maximum(
            mass, 1e-12
        )  # INV-FE2: liquidity mass non-negative — prevents division by zero in coupling
        return result

    def _compute_correlation(self, prices: NDArray[np.float64]) -> NDArray[np.float64]:
        """Rolling return correlation matrix. Shape: (N, N)."""
        returns = np.diff(prices, axis=0) / np.maximum(np.abs(prices[:-1]), 1e-12)
        tail = returns[-self._corr_window :]
        with np.errstate(invalid="ignore"):
            corr = np.corrcoef(tail, rowvar=False)
        return np.asarray(np.nan_to_num(corr, nan=0.0), dtype=np.float64)

    def compute(
        self,
        prices: NDArray[np.float64],
        volumes: NDArray[np.float64],
    ) -> NDArray[np.float64]:
        """Compute liquidity-weighted adjacency matrix.

        A_ij = C_ij · √(m_i · m_j) / max(m)

        Parameters
        ----------
        prices : (T, N) price history.
        volumes : (T, N) volume history.

        Returns
        -------
        (N, N) adjacency matrix with values in [0, 1].
        """
        prices = np.asarray(prices, dtype=np.float64)
        volumes = np.asarray(volumes, dtype=np.float64)
        if prices.shape != volumes.shape:
            raise ValueError(f"Shape mismatch: prices {prices.shape} vs volumes {volumes.shape}")
        if prices.ndim != 2 or prices.shape[1] < 2:
            raise ValueError(f"Need (T, N≥2) arrays, got {prices.shape}")

        mass = self._compute_mass(prices, volumes)
        corr = self._compute_correlation(prices)

        # √(m_i · m_j) / max(m)
        mass_factor = np.sqrt(np.outer(mass, mass)) / np.max(mass)

        # A_ij = |C_ij| · mass_factor (use absolute correlation)
        A = np.abs(corr) * mass_factor

        # Apply minimum correlation filter
        if self._min_corr > 0:
            mask = np.abs(corr) < self._min_corr
            A[mask] = 0.0

        # Zero diagonal
        np.fill_diagonal(A, 0.0)

        # Clip to [0, 1]
        A = np.clip(
            A, 0.0, 1.0
        )  # INV-K1: adjacency weights bounded to [0,1] — coupling strength normalisation

        return A

    def benchmark_vs_uniform(
        self,
        prices: NDArray[np.float64],
        volumes: NDArray[np.float64],
        regime_labels: NDArray[np.int32],
        K: float = 2.0,
        steps: int = 500,
        regime_threshold: float = 0.7,
    ) -> CouplingBenchmarkResult:
        """Benchmark liquidity coupling vs uniform on regime detection.

        Parameters
        ----------
        prices : (T, N) price history.
        volumes : (T, N) volume history.
        regime_labels : (T,) binary labels (1=crisis, 0=normal).
        K : float, coupling strength.
        steps : int, Kuramoto steps per window.
        regime_threshold : float, R threshold for regime detection.

        Returns
        -------
        CouplingBenchmarkResult comparing both methods.
        """
        from core.kuramoto.config import KuramotoConfig
        from core.kuramoto.engine import KuramotoEngine

        prices = np.asarray(prices, dtype=np.float64)
        volumes = np.asarray(volumes, dtype=np.float64)
        regime_labels = np.asarray(regime_labels, dtype=np.int32)
        n = prices.shape[1]
        T = prices.shape[0]

        window = max(self._corr_window, self._vol_window) + 1
        n_windows = T - window

        if n_windows < 1:
            raise ValueError(f"Not enough data: T={T}, need > {window}")

        uniform_Rs = []
        liquidity_Rs = []

        for t in range(n_windows):
            p_win = prices[t : t + window]
            v_win = volumes[t : t + window]

            # Liquidity coupling
            A_liq = self.compute(p_win, v_win)
            cfg = KuramotoConfig(
                N=n,
                K=K,
                adjacency=A_liq,
                adjacency_kind="normalized_topology",
                dt=0.01,
                steps=steps,
                seed=42,
            )
            R_liq = KuramotoEngine(cfg).run().order_parameter[-1]
            liquidity_Rs.append(R_liq)

            # Uniform coupling (no adjacency → global)
            cfg_uni = KuramotoConfig(N=n, K=K, dt=0.01, steps=steps, seed=42)
            R_uni = KuramotoEngine(cfg_uni).run().order_parameter[-1]
            uniform_Rs.append(R_uni)

        uniform_R = np.array(uniform_Rs)
        liquidity_R = np.array(liquidity_Rs)

        # Regime detection accuracy
        labels = regime_labels[window : window + n_windows]
        if len(labels) < n_windows:
            labels = np.pad(labels, (0, n_windows - len(labels)))

        uniform_pred = (uniform_R > regime_threshold).astype(int)
        liquidity_pred = (liquidity_R > regime_threshold).astype(int)

        uniform_acc = float(np.mean(uniform_pred == labels)) if labels.size > 0 else 0.0
        liquidity_acc = float(np.mean(liquidity_pred == labels)) if labels.size > 0 else 0.0

        improvement = (liquidity_acc - uniform_acc) / max(uniform_acc, 1e-12) * 100

        return CouplingBenchmarkResult(
            uniform_R_trajectory=uniform_R,
            liquidity_R_trajectory=liquidity_R,
            uniform_regime_accuracy=uniform_acc,
            liquidity_regime_accuracy=liquidity_acc,
            improvement_pct=improvement,
        )


__all__ = ["LiquidityCouplingMatrix", "CouplingBenchmarkResult"]
