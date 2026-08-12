# SPDX-License-Identifier: MIT
"""T10 (universal upper bound) — INV-RC1 Hypothesis fuzz battery.

The companion file (`test_T10_ricci_bounds.py`) verifies INV-RC1
(κ ≤ 1, universal) and INV-RC3 (κ ∈ [−1, 1] on price graphs) on
hand-picked graphs (cycles, complete graphs, paths). INV-RC1 is
universal — it must hold for **every** edge of **every** connected
graph, not just the canonical ones.

This file closes the gap with a Hypothesis-driven fuzz across
three families of random graphs:

* **Erdős–Rényi G(n, p)** — random edge inclusion at varied p.
* **Watts–Strogatz small-world** — ring lattice with rewiring.
* **Barabási–Albert preferential attachment** — scale-free.

For every connected sample, every edge is checked against
``κ ≤ 1 + ε``. A single violation falsifies INV-RC1 — and would
indicate either a bug in the Wasserstein-1 kernel (negative W₁,
violating the metric axiom) or a divisor ``d(x, y) = 0`` slipping
past the connectedness guard.

Why Hypothesis fuzz over hand-picked sweeps
-------------------------------------------

Hand-picked graphs catch bugs in topologies *the author thought of*.
Hypothesis catches bugs in topologies that emerge from the
joint distribution over (n, p, seed) — including pathological
examples (single edges, near-disconnected graphs, dense graphs
with high-degree hubs) that exercise the W₁ kernel in regimes
the canonical tests miss.
"""

from __future__ import annotations

import networkx as nx
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from core.indicators.ricci import ricci_curvature_edge

# ULP slack on the upper bound. Any κ > 1 + this is a real violation.
_UPPER_BOUND_SLACK: float = 1e-9


def _assert_all_edges_bounded(label: str, G: nx.Graph, **params: object) -> None:
    """Iterate every edge and assert κ ≤ 1 + ε."""
    if G.number_of_edges() == 0:
        return
    for u, v in G.edges():
        kappa = ricci_curvature_edge(G, u, v)
        assert kappa <= 1.0 + _UPPER_BOUND_SLACK, (
            f"INV-RC1 VIOLATED on {label}: κ({u}, {v}) = {kappa:.6e} > "
            f"1 + ε ({_UPPER_BOUND_SLACK:.0e}). "
            f"Observed at params={params}, edges={G.number_of_edges()}, "
            f"nodes={G.number_of_nodes()}. "
            "Physical reasoning: κ = 1 − W₁/d. Since W₁ ≥ 0 by the "
            "metric axiom and d > 0 on connected graphs, κ ≤ 1 always. "
            "Violation implies either negative W₁ (kernel bug) or "
            "d ≤ 0 (connectedness guard failed)."
        )


@given(
    n=st.integers(min_value=4, max_value=20),
    p=st.floats(min_value=0.2, max_value=0.95, allow_nan=False, allow_infinity=False),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_inv_rc1_erdos_renyi_random_graphs(n: int, p: float, seed: int) -> None:
    """INV-RC1: κ ≤ 1 on every edge of every connected G(n, p)."""
    G = nx.erdos_renyi_graph(n, p, seed=seed)
    assume(nx.is_connected(G))
    _assert_all_edges_bounded("erdos_renyi", G, n=n, p=p, seed=seed)


@given(
    n=st.integers(min_value=6, max_value=20),
    k=st.integers(min_value=2, max_value=4),
    p=st.floats(min_value=0.0, max_value=0.5, allow_nan=False, allow_infinity=False),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_inv_rc1_watts_strogatz_small_world(n: int, k: int, p: float, seed: int) -> None:
    """INV-RC1: κ ≤ 1 on every edge of every connected Watts-Strogatz graph."""
    # Watts-Strogatz requires k < n and k even-or-odd, both ok via constructor.
    assume(k < n)
    G = nx.watts_strogatz_graph(n, k, p, seed=seed)
    assume(nx.is_connected(G))
    _assert_all_edges_bounded("watts_strogatz", G, n=n, k=k, p=p, seed=seed)


@given(
    n=st.integers(min_value=6, max_value=20),
    m=st.integers(min_value=1, max_value=4),
    seed=st.integers(min_value=0, max_value=10_000),
)
@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
)
def test_inv_rc1_barabasi_albert_scale_free(n: int, m: int, seed: int) -> None:
    """INV-RC1: κ ≤ 1 on every edge of every Barabási-Albert graph."""
    assume(m < n)
    G = nx.barabasi_albert_graph(n, m, seed=seed)
    assume(nx.is_connected(G))
    _assert_all_edges_bounded("barabasi_albert", G, n=n, m=m, seed=seed)


def test_inv_rc1_path_graph_extremal_case() -> None:
    """INV-RC1: κ ≤ 1 on every edge of a path graph (degree-1 endpoints).

    Endpoint edges are the extremal case for INV-RC1 — high
    asymmetry in neighborhood structure. The universal bound must
    hold for *all* edges, asserted explicitly over the edge set.
    """
    G = nx.path_graph(20)
    _assert_all_edges_bounded("path_graph_20", G, n=20)
    kappas = [ricci_curvature_edge(G, u, v) for u, v in G.edges()]
    assert all(k <= 1.0 + _UPPER_BOUND_SLACK for k in kappas), (
        f"INV-RC1 VIOLATED on path_graph_20: max κ={max(kappas):.6e} > "
        f"1 + ε; κ ≤ 1 must hold for every edge (W₁ ≥ 0, d > 0). "
        f"n=20, edges={G.number_of_edges()}."
    )


def test_inv_rc1_complete_graph_uniform_curvature() -> None:
    """INV-RC1: κ ≤ 1 on every edge of complete K_n (uniform curvature)."""
    G = nx.complete_graph(8)
    _assert_all_edges_bounded("complete_graph_8", G, n=8)
    kappas = [ricci_curvature_edge(G, u, v) for u, v in G.edges()]
    assert all(k <= 1.0 + _UPPER_BOUND_SLACK for k in kappas), (
        f"INV-RC1 VIOLATED on complete_graph_8: max κ={max(kappas):.6e} > "
        f"1 + ε; the universal upper bound κ ≤ 1 must hold for every edge. "
        f"n=8, edges={G.number_of_edges()}."
    )


def test_inv_rc1_star_graph_extremal_hub_curvature() -> None:
    """INV-RC1: κ ≤ 1 on every edge of star K_{1,n} (max degree asymmetry).

    Center node is degree n; leaves are degree 1. The center–leaf
    edges stress the W₁ kernel hardest, yet κ ≤ 1 must still hold
    for every edge.
    """
    G = nx.star_graph(15)
    _assert_all_edges_bounded("star_graph_15", G, n=15)
    kappas = [ricci_curvature_edge(G, u, v) for u, v in G.edges()]
    assert all(k <= 1.0 + _UPPER_BOUND_SLACK for k in kappas), (
        f"INV-RC1 VIOLATED on star_graph_15: max κ={max(kappas):.6e} > "
        f"1 + ε; the universal upper bound κ ≤ 1 must hold for every "
        f"center–leaf edge. n=15, edges={G.number_of_edges()}."
    )
