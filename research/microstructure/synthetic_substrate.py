# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synthetic ground-truth substrate for the ten-axis falsification battery.

A *deterministic* generator that plants a known predictive edge (and known
persistence) into a (signal, forward-return) panel, so each of the ten
validation axes can be exercised against a substrate whose answer is known by
construction. This is the offline driver (path B) for the same battery that
path A drives with the frozen Session-1 substrate: it validates that the axis
*methods* detect an edge that is present and reject one that is not — it does
not, and must not, manufacture a signal out of noise.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray


def make_persistent_signal(
    n: int, n_symbols: int, *, phi: float = 0.96, seed: int = 0
) -> NDArray[np.float64]:
    """AR(1) panel with high autocorrelation → persistent (red-spectrum) signal."""
    rng = np.random.default_rng(seed)
    out = np.zeros((n, n_symbols), dtype=np.float64)
    for j in range(n_symbols):
        x = 0.0
        for t in range(n):
            x = phi * x + rng.standard_normal()
            out[t, j] = x
    return out


def make_white_signal(n: int, n_symbols: int, *, seed: int = 0) -> NDArray[np.float64]:
    """i.i.d. panel → no persistence (Hurst≈0.5, flat spectrum)."""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n, n_symbols))


def plant_edge(
    signal_panel: NDArray[np.float64],
    *,
    edge: float = 0.3,
    lag: int = 1,
    noise: float = 1.0,
    seed: int = 1,
) -> NDArray[np.float64]:
    """target[t] = edge * signal[t-lag] + noise·N(0,1) — a known predictive lag."""
    rng = np.random.default_rng(seed)
    n, m = signal_panel.shape
    target = noise * rng.standard_normal((n, m))
    if lag < n:
        target[lag:, :] += edge * signal_panel[: n - lag, :]
    return target


def permute_target(target_panel: NDArray[np.float64], *, seed: int = 2) -> NDArray[np.float64]:
    """Row-permute the target → destroys the signal→target link (the null)."""
    rng = np.random.default_rng(seed)
    idx = rng.permutation(target_panel.shape[0])
    return target_panel[idx, :]
