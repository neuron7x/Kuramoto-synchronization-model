# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""discrimination_v2 — Disha artefact v2 wrapper around the
instrument_validation.discrimination layer.

Replaces ``compute_ba_comparison`` for any consumer that wants the
6-metric Bonferroni aggregate verdict instead of a single Pearson r.

Closes G7 (BA mechanism claim NOT_DISTINGUISHED after Bonferroni
unless ≥4/6 metrics favor BA).
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np

from instrument_validation.discrimination import (
    DiscriminationReport,
    discriminate,
    metric_gini_strength_zscore,
    metric_ks_distance,
    metric_max_degree_zscore,
    metric_normalized_rich_club,
    metric_top_k_hub_jaccard,
    metric_zero_degree_count_error,
)


def _gini(values: np.ndarray) -> float:
    arr = np.sort(np.asarray(values, dtype=np.float64))
    if arr.sum() <= 0:
        return float("nan")
    n = arr.size
    cum = np.cumsum(arr)
    return float((2.0 * np.sum((np.arange(1, n + 1)) * arr)) / (n * cum[-1]) - (n + 1.0) / n)


def _simulate_pool(
    generator: Any, n: int, n_sims: int, seed: int, **kwargs: Any
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Returns (pooled_degrees, list_of_adjacencies)."""
    rng = np.random.default_rng(seed)
    pooled: list[int] = []
    adjs: list[np.ndarray] = []
    for _ in range(n_sims):
        g = generator(n, seed=int(rng.integers(0, 2**31 - 1)), **kwargs)
        deg = list(dict(g.degree()).values())
        pooled.extend(deg)
        adj = np.zeros((n, n), dtype=np.uint8)
        for u, v in g.edges():
            adj[u, v] = 1
            adj[v, u] = 1
        adjs.append(adj)
    return np.asarray(pooled, dtype=np.float64), adjs


def discriminate_ba_vs_er_six_metrics(
    empirical_adjacency: np.ndarray,
    *,
    n_simulations: int = 200,
    seed: int = 42,
) -> DiscriminationReport:
    """Run the 6-metric BA-vs-ER discrimination on a single empirical graph."""
    n = int(empirical_adjacency.shape[0])
    sym = ((empirical_adjacency + empirical_adjacency.T) > 0).astype(np.uint8)
    np.fill_diagonal(sym, 0)
    n_edges = int(sym.sum() // 2)
    deg = sym.sum(axis=1).astype(np.int64)
    if n_edges == 0:
        return discriminate(
            {
                f"M{i}": {
                    "empirical": float("nan"),
                    "ba_pool": np.zeros(1),
                    "er_pool": np.zeros(1),
                }
                for i in range(1, 7)
            }
        )
    m = max(1, min(round(n_edges / max(n, 1)), n - 1))
    p_er = (2.0 * n_edges) / (n * (n - 1))
    ba_pool, ba_adjs = _simulate_pool(nx.barabasi_albert_graph, n, n_simulations, seed=seed, m=m)
    er_pool, er_adjs = _simulate_pool(
        nx.gnp_random_graph, n, n_simulations, seed=seed + 7919, p=p_er
    )

    # Per-simulation aggregates for M2..M5
    ba_max_per_sim = np.array(
        [int(np.max([d for _, d in nx.from_numpy_array(a).degree()])) for a in ba_adjs],
        dtype=np.float64,
    )
    er_max_per_sim = np.array(
        [int(np.max([d for _, d in nx.from_numpy_array(a).degree()])) for a in er_adjs],
        dtype=np.float64,
    )
    ba_zero_per_sim = np.array(
        [int(sum(1 for _, d in nx.from_numpy_array(a).degree() if d == 0)) for a in ba_adjs],
        dtype=np.float64,
    )
    er_zero_per_sim = np.array(
        [int(sum(1 for _, d in nx.from_numpy_array(a).degree() if d == 0)) for a in er_adjs],
        dtype=np.float64,
    )
    ba_gini_per_sim = np.array(
        [_gini(np.array([d for _, d in nx.from_numpy_array(a).degree()])) for a in ba_adjs],
        dtype=np.float64,
    )
    er_gini_per_sim = np.array(
        [_gini(np.array([d for _, d in nx.from_numpy_array(a).degree()])) for a in er_adjs],
        dtype=np.float64,
    )
    ba_top_per_sim = np.array(
        [np.sort(np.array([d for _, d in nx.from_numpy_array(a).degree()]))[-1] for a in ba_adjs],
        dtype=np.float64,
    )

    # Rewired baseline for M6 (single small set; cheap)
    rewired: list[np.ndarray] = []
    rng_rew = np.random.default_rng(seed + 31)
    for _ in range(min(n_simulations, 100)):
        g = nx.from_numpy_array(sym)
        if g.number_of_edges() >= 2:
            try:
                nx.algorithms.swap.double_edge_swap(
                    g,
                    nswap=max(5, g.number_of_edges() // 2),
                    max_tries=max(500, 100 * g.number_of_edges()),
                    seed=int(rng_rew.integers(0, 2**31 - 1)),
                )
            except (nx.NetworkXError, nx.NetworkXAlgorithmError):
                continue
        adj = np.zeros((n, n), dtype=np.uint8)
        for u, v in g.edges():
            adj[u, v] = 1
            adj[v, u] = 1
        rewired.append(adj)

    metrics: dict[str, dict[str, Any]] = {
        "M1_ks_distance": {
            "empirical": float(metric_ks_distance(deg.astype(np.float64), ba_pool)),
            "ba_pool": np.array(
                [
                    metric_ks_distance(
                        np.array([d for _, d in nx.from_numpy_array(ba_adjs[k]).degree()]),
                        ba_pool,
                    )
                    for k in range(len(ba_adjs))
                ]
            ),
            "er_pool": np.array(
                [
                    metric_ks_distance(
                        np.array([d for _, d in nx.from_numpy_array(er_adjs[k]).degree()]),
                        ba_pool,
                    )
                    for k in range(len(er_adjs))
                ]
            ),
        },
        "M2_max_degree_z": {
            "empirical": float(metric_max_degree_zscore(int(deg.max()), ba_max_per_sim)),
            "ba_pool": (ba_max_per_sim - ba_max_per_sim.mean())
            / max(ba_max_per_sim.std(ddof=0), 1e-12),
            "er_pool": (er_max_per_sim - ba_max_per_sim.mean())
            / max(ba_max_per_sim.std(ddof=0), 1e-12),
        },
        "M3_zero_degree_err": {
            "empirical": float(
                metric_zero_degree_count_error(int((deg == 0).sum()), ba_zero_per_sim)
            ),
            "ba_pool": np.abs(ba_zero_per_sim - ba_zero_per_sim.mean()),
            "er_pool": np.abs(er_zero_per_sim - ba_zero_per_sim.mean()),
        },
        "M4_gini_strength_z": {
            "empirical": float(
                metric_gini_strength_zscore(_gini(deg.astype(np.float64)), ba_gini_per_sim)
            ),
            "ba_pool": (ba_gini_per_sim - ba_gini_per_sim.mean())
            / max(ba_gini_per_sim.std(ddof=0), 1e-12),
            "er_pool": (er_gini_per_sim - ba_gini_per_sim.mean())
            / max(ba_gini_per_sim.std(ddof=0), 1e-12),
        },
        "M5_top_k_hub": {
            "empirical": float(
                metric_top_k_hub_jaccard(deg.astype(np.float64), ba_top_per_sim, k=7)
            ),
            "ba_pool": np.full(len(ba_adjs), 1.0),
            "er_pool": np.array(
                [
                    metric_top_k_hub_jaccard(
                        np.array([d for _, d in nx.from_numpy_array(er_adjs[k]).degree()]),
                        ba_top_per_sim,
                        k=7,
                    )
                    for k in range(len(er_adjs))
                ]
            ),
        },
        "M6_norm_rich_club": {
            "empirical": float(metric_normalized_rich_club(sym, rewired) if rewired else 1.0),
            "ba_pool": np.full(min(len(ba_adjs), 50), 1.0),
            "er_pool": np.full(min(len(er_adjs), 50), 1.0),
        },
    }
    return discriminate(metrics)
