# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Time-varying coupling ``K_{ij}(t)`` (protocol M2.3).

Sliding-window sparse regression on top of :mod:`coupling_estimator`.
For each window ``[t, t+W)`` we run the full MCP-penalised row
regression and produce a ``(T_win, N, N)`` tensor of coupling
snapshots. The rolling snapshot sequence is then fed into breakpoint
detection and into :func:`core.kuramoto.metrics.compute_metrics` as
the ``K_series`` argument for edge-entropy computation.

The heavier Fused Graphical Lasso variant (``gglasso``) is a drop-in
alternative documented in the methodology but is not required for the
default pipeline — our stock MCP row regression with stability
selection already gives temporally smooth solutions because its
regularisation path is strictly convex in the active set.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .contracts import PhaseMatrix
from .coupling_estimator import (
    CouplingEstimationConfig,
    _estimate_K_single,
)

__all__ = [
    "DynamicGraphConfig",
    "DynamicGraphEstimator",
    "detect_breakpoints",
]


@dataclass(frozen=True, slots=True)
class DynamicGraphConfig:
    """Sliding-window hyperparameters.

    Attributes
    ----------
    window : int
        Window size in timesteps. Must be ≥ ``min_window_for_solver``.
    step : int
        Stride between window starts. ``step = 1`` gives the finest
        temporal resolution; ``step = window // 10`` is a sensible
        default for N ≈ 20.
    coupling_config : CouplingEstimationConfig
        Per-window estimator configuration. The default uses the
        same MCP penalty as the static coupling estimator.
    min_window_for_solver : int
        Safety floor below which the MCP solver is ill-conditioned.
    """

    window: int = 150
    step: int = 15
    coupling_config: CouplingEstimationConfig = CouplingEstimationConfig(
        penalty="mcp", lambda_reg=0.1, max_iter=500, tol=1e-5
    )
    min_window_for_solver: int = 60

    def __post_init__(self) -> None:
        if self.window < self.min_window_for_solver:
            raise ValueError(
                f"window={self.window} must be ≥ min_window_for_solver={self.min_window_for_solver}"
            )
        if self.step < 1:
            raise ValueError("step must be ≥ 1")


class DynamicGraphEstimator:
    """Sliding-window coupling estimator returning a ``(T_win, N, N)`` tensor.

    The per-window fit re-uses the static MCP solver from
    :mod:`coupling_estimator`, so hyperparameters are tuned once and
    apply uniformly across the sliding window. The caller can pass a
    custom :class:`CouplingEstimationConfig` to, for example, switch
    the penalty or tighten the tolerance for longer windows.
    """

    def __init__(self, config: DynamicGraphConfig | None = None) -> None:
        self.config = config or DynamicGraphConfig()

    def estimate(self, phases: PhaseMatrix) -> tuple[np.ndarray, np.ndarray]:
        """Return ``(K_series, window_centres)``.

        ``K_series`` has shape ``(T_win, N, N)`` and
        ``window_centres`` gives the integer time index at the centre
        of each window (useful for aligning with downstream metrics).
        """
        cfg = self.config
        theta = np.asarray(phases.theta, dtype=np.float64)
        T, N = theta.shape
        if T < cfg.window:
            raise ValueError(f"phase length {T} smaller than window {cfg.window}")
        starts = np.arange(0, T - cfg.window + 1, cfg.step)
        n_windows = starts.shape[0]
        K_series = np.zeros((n_windows, N, N), dtype=np.float64)
        centres = np.zeros(n_windows, dtype=np.int64)
        for w, start in enumerate(starts):
            theta_win = theta[start : start + cfg.window]
            K_series[w] = _estimate_K_single(
                theta_win, cfg.coupling_config.lambda_reg, cfg.coupling_config
            )
            centres[w] = int(start + cfg.window // 2)
        return K_series, centres


def detect_breakpoints(K_series: np.ndarray, *, z_threshold: float = 2.5) -> np.ndarray:
    """Detect regime-change timestamps in a ``K_series`` tensor.

    For each consecutive pair of snapshots we compute the Frobenius
    distance ``‖K(t) − K(t − 1)‖_F`` and flag indices whose distance
    exceeds the median by more than ``z_threshold`` robust standard
    deviations (``1.4826 · MAD``). Returns the sorted integer indices
    of the detected breakpoints within the ``K_series`` timeline.
    """
    if K_series.ndim != 3:
        raise ValueError("K_series must have shape (T_win, N, N)")
    diff = np.diff(K_series, axis=0)
    dists = np.linalg.norm(diff.reshape(diff.shape[0], -1), axis=1)
    if dists.size == 0:
        return np.zeros(0, dtype=np.int64)
    med = float(np.median(dists))
    mad = float(np.median(np.abs(dists - med))) or 1e-12
    robust_sigma = 1.4826 * mad
    z = (dists - med) / robust_sigma
    idx = np.where(z > z_threshold)[0] + 1  # +1 because diff index i → snapshot i+1
    return idx.astype(np.int64)
