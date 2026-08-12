# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Augmented Forman-Ricci curvature v2 — adaptive threshold, neckpinch, distribution.

κ > 0 → robust/redundant topology (multiple paths)
κ < 0 → fragile bottleneck (single point of failure)

Neckpinch: rapid transition from κ>0 to κ<0 = topology tearing.
Empirical calibration required (see ricci_calibrator.py).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class RicciResult:
    """Full curvature distribution, not just mean."""

    mean_kappa: float
    std_kappa: float
    min_kappa: float
    max_kappa: float
    fragile_fraction: float  # fraction of edges with κ < 0
    neckpinch_detected: bool
    n_edges: int
    effective_threshold: float


class AugmentedFormanRicci:
    """Topology-sensitive Forman-Ricci with adaptive threshold and neckpinch."""

    def __init__(self, correlation_threshold: float = 0.2) -> None:
        self._base_threshold = correlation_threshold

    def compute(
        self,
        returns: np.ndarray,
        symbols: list[str],
    ) -> RicciResult:
        """Full curvature computation with distribution statistics."""
        if returns.ndim != 2 or returns.shape[1] != len(symbols):
            raise ValueError("returns shape must match symbols")
        if returns.shape[0] < 16 or returns.shape[1] < 2:
            return RicciResult(0.0, 0.0, 0.0, 0.0, 0.0, False, 0, self._base_threshold)

        # Adaptive threshold: high vol → raise to avoid false edges
        vol = float(np.std(returns, axis=0).mean())
        eff_thresh = float(np.clip(self._base_threshold * (1.0 + vol * 2.0), 0.15, 0.60))

        # Correlation → adjacency
        corr = np.corrcoef(returns.T)
        corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
        adj = np.abs(corr)
        np.fill_diagonal(adj, 0.0)
        adj[adj < eff_thresh] = 0.0

        deg = adj.sum(axis=1)
        n_nodes = adj.shape[0]

        i_idx, j_idx = np.where(np.triu(adj, k=1) > 0.0)
        n_edges = len(i_idx)

        if n_edges == 0:
            return RicciResult(0.0, 0.0, 0.0, 0.0, 0.0, False, 0, eff_thresh)

        eps = 1e-12
        w = adj[i_idx, j_idx]
        deg_i = deg[i_idx]
        deg_j = deg[j_idx]

        # Triangle strength: Σ_k min(w_ik, w_jk) for k ≠ i,j (bugfix v2)
        tri_strength = np.zeros(n_edges, dtype=np.float64)
        for e in range(n_edges):
            i, j = int(i_idx[e]), int(j_idx[e])
            mask = np.ones(n_nodes, dtype=bool)
            mask[i] = False
            mask[j] = False
            if mask.any():
                tri_strength[e] = np.minimum(adj[i, mask], adj[j, mask]).sum()

        edge_support = 2.0 * w / np.sqrt((deg_i + eps) * (deg_j + eps))
        degree_penalty = deg_i + deg_j - 2.0 * w

        kappa_all = edge_support + tri_strength - degree_penalty

        mean_k = float(np.mean(kappa_all))
        std_k = float(np.std(kappa_all)) if n_edges > 1 else 0.0
        min_k = float(np.min(kappa_all))
        max_k = float(np.max(kappa_all))
        fragile = float((kappa_all < 0).mean())

        neckpinch = fragile > 0.5 and mean_k < -0.5

        return RicciResult(
            mean_kappa=mean_k,
            std_kappa=std_k,
            min_kappa=min_k,
            max_kappa=max_k,
            fragile_fraction=fragile,
            neckpinch_detected=neckpinch,
            n_edges=n_edges,
            effective_threshold=round(eff_thresh, 4),
        )

    def compute_mean(
        self,
        returns: np.ndarray,
        symbols: list[str],
    ) -> float:
        """Backward-compatible: returns only mean κ."""
        return self.compute(returns, symbols).mean_kappa
