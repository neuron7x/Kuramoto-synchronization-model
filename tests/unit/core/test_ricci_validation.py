# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for Ricci curvature computations in the Kuramoto-Ricci flow engine.

Validates Ollivier-Ricci curvature against known analytic results:
- Complete graph K5: all edges should have positive curvature
- Path graph: interior edges should have negative curvature
- Curvature is bounded and symmetric (kappa(i,j) == kappa(j,i))

Uses the lightweight curvature estimator from ricci_flow_engine.py
to avoid external NetworkX/GraphRicciCurvature dependencies.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.config import KuramotoConfig
from core.kuramoto.ricci_flow_engine import (
    KuramotoRicciFlowEngine,
    _LocalOllivierRicciCurvatureLite,
    _SimpleUndirectedGraph,
)

# Level auto-assigned by conftest from tests/test_levels.yaml


# ── Graph construction helpers ───────────────────────────────────────────


def _complete_graph(n: int) -> _SimpleUndirectedGraph:
    """Build complete graph K_n."""
    g = _SimpleUndirectedGraph(n)
    g.add_nodes_from(range(n))
    for i in range(n):
        for j in range(i + 1, n):
            g.add_edge(i, j, weight=1.0)
    return g


def _path_graph(n: int) -> _SimpleUndirectedGraph:
    """Build path graph P_n (linear chain 0-1-2-...-n-1)."""
    g = _SimpleUndirectedGraph(n)
    g.add_nodes_from(range(n))
    for i in range(n - 1):
        g.add_edge(i, i + 1, weight=1.0)
    return g


def _cycle_graph(n: int) -> _SimpleUndirectedGraph:
    """Build cycle graph C_n."""
    g = _SimpleUndirectedGraph(n)
    g.add_nodes_from(range(n))
    for i in range(n):
        g.add_edge(i, (i + 1) % n, weight=1.0)
    return g


def _star_graph(n: int) -> _SimpleUndirectedGraph:
    """Build star graph: center=0, leaves=1..n-1."""
    g = _SimpleUndirectedGraph(n)
    g.add_nodes_from(range(n))
    for i in range(1, n):
        g.add_edge(0, i, weight=1.0)
    return g


# ═══════════════════════════════════════════════════════════════════════
# Curvature on known graphs
# ═══════════════════════════════════════════════════════════════════════


class TestOllivierRicciCurvatureOnKnownGraphs:
    """Test the lightweight Ollivier-Ricci estimator against analytic expectations."""

    def setup_method(self):
        self.ricci = _LocalOllivierRicciCurvatureLite(alpha=0.5)

    # ── Complete graph K5 ────────────────────────────────────────────

    def test_complete_graph_k5_positive_curvature(self):
        """On K5, every edge should have strictly positive Ollivier-Ricci curvature."""
        g = _complete_graph(5)
        for i, j in g.edges():
            kappa = self.ricci.compute_edge_curvature(g, (i, j))
            assert kappa > 0.0, f"K5 edge ({i},{j}) curvature={kappa:.6f} should be positive"

    def test_complete_graph_k5_curvature_uniform(self):
        """All edges in K5 should have the same curvature by symmetry."""
        g = _complete_graph(5)
        curvatures = [self.ricci.compute_edge_curvature(g, e) for e in g.edges()]
        assert len(curvatures) == 10  # C(5,2) = 10 edges
        assert np.std(curvatures) < 1e-10, "K5 curvatures should be identical by symmetry"

    # ── Path graph ───────────────────────────────────────────────────

    def test_path_graph_interior_edges_negative_curvature(self):
        """Interior edges of a path graph should have negative curvature.

        On a path, interior nodes have degree 2 but the random walks
        from adjacent nodes have minimal overlap, leading to negative curvature.
        """
        g = _path_graph(6)
        # Interior edges: (1,2), (2,3), (3,4)
        for i in range(1, 4):
            kappa = self.ricci.compute_edge_curvature(g, (i, i + 1))
            assert kappa <= 0.5 + 1e-10, (
                f"Path interior edge ({i},{i + 1}) curvature={kappa:.6f} "
                "should not exceed 0.5 (lazy-RW with alpha=0.5 caps overlap)"
            )

    def test_path_graph_boundary_edges(self):
        """Boundary edges (touching degree-1 nodes) on a path graph."""
        g = _path_graph(5)
        # Edge (0,1): node 0 has degree 1, node 1 has degree 2
        kappa_boundary = self.ricci.compute_edge_curvature(g, (0, 1))
        assert np.isfinite(kappa_boundary)

    # ── Symmetry ─────────────────────────────────────────────────────

    def test_curvature_symmetric(self):
        """kappa(i,j) should equal kappa(j,i) for undirected graphs."""
        g = _complete_graph(5)
        for i, j in g.edges():
            k_ij = self.ricci.compute_edge_curvature(g, (i, j))
            k_ji = self.ricci.compute_edge_curvature(g, (j, i))
            assert (
                abs(k_ij - k_ji) < 1e-12
            ), f"Curvature not symmetric: kappa({i},{j})={k_ij}, kappa({j},{i})={k_ji}"

    def test_curvature_symmetric_on_path(self):
        g = _path_graph(5)
        for i in range(4):
            k_ij = self.ricci.compute_edge_curvature(g, (i, i + 1))
            k_ji = self.ricci.compute_edge_curvature(g, (i + 1, i))
            assert abs(k_ij - k_ji) < 1e-12

    # ── Boundedness ──────────────────────────────────────────────────

    def test_curvature_bounded(self):
        """Ollivier-Ricci curvature should be in [-1, 1] for connected unweighted graphs."""
        for graph_fn, n in [
            (_complete_graph, 5),
            (_path_graph, 8),
            (_cycle_graph, 6),
            (_star_graph, 6),
        ]:
            g = graph_fn(n)
            for edge in g.edges():
                kappa = self.ricci.compute_edge_curvature(g, edge)
                assert (
                    -1.0 - 1e-10 <= kappa <= 1.0 + 1e-10
                ), f"Curvature {kappa:.6f} out of bounds for {graph_fn.__name__}({n}) edge {edge}"

    # ── Cycle graph ──────────────────────────────────────────────────

    def test_cycle_graph_uniform_curvature(self):
        """All edges in C_n should have the same curvature by symmetry."""
        g = _cycle_graph(8)
        curvatures = [self.ricci.compute_edge_curvature(g, e) for e in g.edges()]
        assert np.std(curvatures) < 1e-10

    # ── Star graph ───────────────────────────────────────────────────

    def test_star_graph_all_edges_same(self):
        """All edges in a star graph connect center to leaf -- same curvature."""
        g = _star_graph(6)
        curvatures = [self.ricci.compute_edge_curvature(g, e) for e in g.edges()]
        assert np.std(curvatures) < 1e-10

    # ── Degenerate cases ─────────────────────────────────────────────

    def test_single_edge_graph(self):
        """Graph with just one edge."""
        g = _SimpleUndirectedGraph(2)
        g.add_nodes_from(range(2))
        g.add_edge(0, 1, weight=1.0)
        kappa = self.ricci.compute_edge_curvature(g, (0, 1))
        assert np.isfinite(kappa)

    def test_isolated_node_lazy_rw(self):
        """Lazy random walk on isolated node should return self-loop probability 1."""
        g = _SimpleUndirectedGraph(3)
        g.add_nodes_from(range(3))
        # Node 2 is isolated
        rw = self.ricci._lazy_rw(g, 2)
        assert rw == {2: 1.0}


# ═══════════════════════════════════════════════════════════════════════
# SimpleUndirectedGraph internals
# ═══════════════════════════════════════════════════════════════════════


class TestSimpleUndirectedGraph:
    def test_shortest_path_self(self):
        g = _complete_graph(4)
        assert g.shortest_path_length(0, 0) == 0.0

    def test_shortest_path_adjacent(self):
        g = _path_graph(5)
        assert g.shortest_path_length(0, 1) == 1.0

    def test_shortest_path_multi_hop(self):
        g = _path_graph(5)
        assert g.shortest_path_length(0, 4) == 4.0

    def test_edges_count(self):
        g = _complete_graph(5)
        assert len(g.edges()) == 10

    def test_number_of_nodes(self):
        g = _complete_graph(5)
        assert g.number_of_nodes() == 5

    def test_get_edge_data_existing(self):
        g = _complete_graph(3)
        data = g.get_edge_data(0, 1)
        assert data is not None
        assert "weight" in data

    def test_get_edge_data_missing(self):
        g = _path_graph(5)
        data = g.get_edge_data(0, 3, default=None)
        assert data is None


# ═══════════════════════════════════════════════════════════════════════
# KuramotoRicciFlowEngine integration sanity
# ═══════════════════════════════════════════════════════════════════════


class TestKuramotoRicciFlowEngineSanity:
    def test_basic_run_order_parameter_bounded(self):
        cfg = KuramotoConfig(N=6, K=3.0, dt=0.01, steps=200, seed=42)
        engine = KuramotoRicciFlowEngine(cfg, ricci_update_interval=50)
        result = engine.run()
        assert np.all(result.order_parameter >= 0.0)
        assert np.all(result.order_parameter <= 1.0 + 1e-12)

    def test_result_has_curvature_diagnostics(self):
        cfg = KuramotoConfig(N=5, K=2.0, dt=0.01, steps=200, seed=7)
        result = KuramotoRicciFlowEngine(cfg, ricci_update_interval=50).run()
        assert result.curvature_timestamps.shape[0] > 0
        assert result.mean_curvature_trajectory.shape[0] == result.curvature_timestamps.shape[0]
        assert np.all(np.isfinite(result.mean_curvature_trajectory))

    def test_coupling_history_shape(self):
        N = 5
        cfg = KuramotoConfig(N=N, K=2.0, dt=0.01, steps=200, seed=7)
        result = KuramotoRicciFlowEngine(
            cfg, ricci_update_interval=50, coupling_history_enabled=True
        ).run()
        n_updates = result.curvature_timestamps.shape[0]
        assert result.coupling_matrix_history.shape == (n_updates, N, N)

    def test_phi_function_bounded(self):
        """The modulation function phi(kappa) should be in [0, sigma]."""
        cfg = KuramotoConfig(N=4, K=2.0, dt=0.01, steps=10, seed=0)
        engine = KuramotoRicciFlowEngine(cfg, sigma=2.0, alpha=4.0)
        for kappa in np.linspace(-5.0, 5.0, 50):
            phi_val = engine._phi(kappa)
            assert 0.0 <= phi_val <= engine.sigma + 1e-10

    def test_invalid_curvature_method_raises(self):
        cfg = KuramotoConfig(N=4, K=1.0, dt=0.01, steps=10, seed=0)
        with pytest.raises(ValueError, match="curvature_method"):
            KuramotoRicciFlowEngine(cfg, curvature_method="invalid")

    def test_negative_K_base_raises(self):
        cfg = KuramotoConfig(N=4, K=1.0, dt=0.01, steps=10, seed=0)
        with pytest.raises(ValueError):
            KuramotoRicciFlowEngine(cfg, K_base=-1.0)

    def test_herding_and_fragility_finite(self):
        cfg = KuramotoConfig(N=6, K=3.0, dt=0.01, steps=200, seed=42)
        result = KuramotoRicciFlowEngine(cfg, ricci_update_interval=50).run()
        assert np.all(np.isfinite(result.herding_index))
        assert np.all(np.isfinite(result.fragility_index))
        assert np.all(np.isfinite(result.coupling_entropy))
