# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T10 — Ollivier–Ricci curvature bound witnesses for INV-RC1 and INV-RC3.

The production implementation in ``core.indicators.ricci`` computes
κ = 1 − W₁(m_x, m_y)/d(x, y) using a 1-D positional embedding (integer
node IDs, unit spacing by default) and an α = 1/(deg+1) lazy random
walk. Under this choice, two distinct universal bounds hold:

* **INV-RC1 — upper bound (universal)**: κ ≤ 1 for every edge of every
  connected graph. This follows from W₁ ≥ 0 alone and is independent
  of topology or walk laziness.

* **INV-RC3 — full interval on price graphs**: κ ∈ [−1, 1] for every
  edge produced by ``build_price_graph``. The tighter lower bound
  holds because consecutive integer node IDs make the 1-D embedding
  distance match the combinatorial graph distance on every edge, so
  the standard Ollivier theorem recovers its full [−1, 1] guarantee.

Note: the earlier statement of INV-RC1 in INVARIANTS.yaml claimed
κ ∈ [−1, 1] universally. This witness, on a cycle_12 graph, falsified
that statement (κ = −2 on adjacent nodes separated by 9 in the integer
embedding). The YAML has been corrected to split the universal upper
bound (INV-RC1) from the scoped two-sided bound (INV-RC3), and this
file now carries both witnesses.
"""

from __future__ import annotations

import math

import networkx as nx
import numpy as np

from core.indicators.ricci import build_price_graph, ricci_curvature_edge

# Numerical slack for the 1-Wasserstein solver. Anything above 1e-9 is
# a real violation of the bound — SciPy's cdf_distance or our fallback
# never leaks ULPs bigger than that on these graphs.
_NUMERICAL_SLACK_EPSILON = 1e-9


def _unit_weight(graph: nx.Graph) -> nx.Graph:
    """Return a copy of ``graph`` with every edge weight set to 1.0.

    Ensures the witness does not pick up spurious weighting from the
    networkx default generators.
    """
    normalised = graph.copy()
    for edge_u, edge_v in normalised.edges():
        normalised[edge_u][edge_v]["weight"] = 1.0
    return normalised


def _canonical_graphs() -> dict[str, nx.Graph]:
    """Build a dictionary of canonical unweighted topologies for the sweep."""
    graphs: dict[str, nx.Graph] = {
        "path_10": nx.path_graph(10),
        "cycle_12": nx.cycle_graph(12),
        "complete_6": nx.complete_graph(6),
        "star_8": nx.star_graph(7),
        "erdos_renyi_20_p30_s1": nx.erdos_renyi_graph(20, 0.3, seed=1),
        "erdos_renyi_20_p30_s2": nx.erdos_renyi_graph(20, 0.3, seed=2),
    }
    return {name: _unit_weight(g) for name, g in graphs.items()}


def test_ollivier_ricci_upper_bound_is_universal() -> None:
    """INV-RC1: κ(x, y) ≤ 1 for every edge of every connected graph.

    Iterates six canonical topologies (path, cycle, complete, star, two
    seeded Erdős–Rényi graphs) and asserts the universal upper bound
    κ ≤ 1 on every edge. The upper bound is a definitional consequence
    of W₁ ≥ 0 and is independent of walk laziness or positional
    embedding, so the only slack is the 1-Wasserstein solver's ULP.
    """
    graphs = _canonical_graphs()
    upper_bound = 1.0 + _NUMERICAL_SLACK_EPSILON

    n_edges_checked = 0
    for graph_name, graph in graphs.items():
        if not nx.is_connected(graph):
            continue
        for edge_u, edge_v in graph.edges():
            kappa = ricci_curvature_edge(graph, int(edge_u), int(edge_v))
            n_edges_checked += 1
            assert math.isfinite(kappa), (
                f"INV-RC1 VIOLATED on graph={graph_name}, "
                f"edge=({edge_u},{edge_v}): κ={kappa} is non-finite. "
                f"Expected finite κ for a finite connected graph. "
                f"Observed at N={graph.number_of_nodes()} nodes, "
                f"|E|={graph.number_of_edges()} edges. "
                f"Physical reasoning: W₁ and shortest-path are finite on finite "
                f"graphs, so 1 − W₁/d must be finite."
            )
            assert kappa <= upper_bound, (
                f"INV-RC1 VIOLATED on graph={graph_name}, "
                f"edge=({edge_u},{edge_v}): κ={kappa:.6f} > 1. "
                f"Expected κ ≤ 1 by the definitional bound W₁ ≥ 0. "
                f"Observed at N={graph.number_of_nodes()} nodes, "
                f"|E|={graph.number_of_edges()} edges. "
                f"Physical reasoning: κ = 1 − W₁/d with W₁ ≥ 0 ⟹ κ ≤ 1 "
                f"independent of graph topology or random-walk laziness."
            )

    assert n_edges_checked >= 30, (
        f"INV-RC1 sweep too shallow: only {n_edges_checked} edges checked. "
        f"Expected ≥ 30 edges across the six canonical graphs. "
        f"Observed after iterating all graphs. "
        f"Physical reasoning: a handful of edges is not a universal-property "
        f"witness — at N=6 canonical graphs we expect tens of edges."
    )


def test_price_graph_ricci_curvature_in_unit_interval() -> None:
    """INV-RC3: κ ∈ [−1, 1] for every edge of a build_price_graph output.

    Constructs three price-graph instances from synthetic price series
    (trending, mean-reverting, random walk) and asserts the full Ollivier
    two-sided bound on every edge. The tighter lower bound holds here
    because ``build_price_graph`` lays nodes out as consecutive integers
    with unit spacing, matching the 1-D embedding to the combinatorial
    distance and recovering the standard Ollivier theorem.
    """
    rng = np.random.default_rng(seed=42)
    price_series = {
        "trending": 100.0 + np.cumsum(rng.normal(0.02, 0.3, size=200)),
        "mean_reverting": 100.0 + rng.normal(0.0, 0.5, size=200),
        "random_walk": 100.0 + np.cumsum(rng.normal(0.0, 0.4, size=200)),
    }
    lower_bound = -1.0 - _NUMERICAL_SLACK_EPSILON
    upper_bound = 1.0 + _NUMERICAL_SLACK_EPSILON

    n_edges_checked = 0
    for label, prices in price_series.items():
        graph = build_price_graph(prices, delta=0.005)
        if graph.number_of_edges() == 0:
            continue
        if not nx.is_connected(graph):
            largest_cc = max(nx.connected_components(graph), key=len)
            graph = graph.subgraph(largest_cc).copy()
        for edge_u, edge_v in graph.edges():
            kappa = ricci_curvature_edge(graph, int(edge_u), int(edge_v))
            n_edges_checked += 1
            assert math.isfinite(kappa), (
                f"INV-RC3 VIOLATED on series={label}, "
                f"edge=({edge_u},{edge_v}): κ={kappa} non-finite. "
                f"Expected finite κ for a finite price graph. "
                f"Observed at N={graph.number_of_nodes()} nodes, "
                f"|E|={graph.number_of_edges()} edges, delta=0.005. "
                f"Physical reasoning: price graph is finite and connected."
            )
            assert lower_bound <= kappa <= upper_bound, (
                f"INV-RC3 VIOLATED on series={label}, "
                f"edge=({edge_u},{edge_v}): κ={kappa:.6f} outside [−1, 1]. "
                f"Expected κ ∈ [−1, 1] by Ollivier's theorem on the price "
                f"graph's consecutive-integer 1-D embedding. "
                f"Observed at N={graph.number_of_nodes()} nodes, "
                f"|E|={graph.number_of_edges()} edges, delta=0.005, seed=42. "
                f"Physical reasoning: consecutive integer node IDs make the "
                f"1-D position distance equal the combinatorial graph distance "
                f"on every edge, so the standard lazy-walk Ollivier bound applies."
            )

    assert n_edges_checked >= 20, (
        f"INV-RC3 sweep too shallow: only {n_edges_checked} edges checked "
        f"across 3 price series. "
        f"Expected ≥ 20 edges to exercise the price-graph constructor. "
        f"Observed at N=200 prices per series, delta=0.005, seed=42. "
        f"Physical reasoning: fewer than 20 edges means the series length or "
        f"delta parameter starved the constructor of structure."
    )
