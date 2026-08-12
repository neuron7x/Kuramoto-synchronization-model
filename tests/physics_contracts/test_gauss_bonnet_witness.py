# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Mathematical witness for the discrete Gauss–Bonnet law ``ricci.gauss_bonnet``.

This witness binds a pytest function to a first-principles topological law via
``@law(...)`` and proves the law holds in the real code, deriving its tolerance
directly from the law (``exact: residual == 0`` over the rationals — no magic
literal, no float slack). It certifies two things:

1. **The identity** Σ_x K(x) = χ(G) holds *exactly* across a deterministic
   suite of graph families (trees, cycles, complete graphs with high-order
   simplices, small-world graphs, and ``build_price_graph`` output).
2. **The gate fails closed** — a single tampered curvature value makes
   ``assert_gauss_bonnet`` raise ``GaussBonnetViolation``. Without this leg the
   invariant could be a vacuous always-true identity; the leg proves it is a
   live falsifier of corrupted topology.

Nothing here is a market claim. These are geometry facts about the code.
"""

from __future__ import annotations

from fractions import Fraction

import networkx as nx
import numpy as np

from core.indicators.gauss_bonnet import (
    GaussBonnetViolation,
    assert_gauss_bonnet,
    euler_characteristic,
    gauss_bonnet_residual,
    knill_vertex_curvature,
)
from core.indicators.ricci import build_price_graph
from physics_contracts.law import law

# The law's tolerance is "exact: residual == 0 over the rationals". The only
# admissible deviation is the exact rational zero — encoded here, not as a magic
# float epsilon.
EXACT_ZERO = Fraction(0)


def _graph_suite() -> list[tuple[str, nx.Graph, int]]:
    """Deterministic graph families paired with their known Euler characteristic.

    Each entry is (name, graph, expected_chi). The expected χ is derived from
    first principles per family, independent of the code under test, so the
    witness checks the implementation against ground truth — not against itself.
    """
    suite: list[tuple[str, nx.Graph, int]] = []

    # Tree (path): χ = V − E = n − (n−1) = 1.
    suite.append(("path_8", nx.path_graph(8), 1))
    # Star: also a tree, χ = 1.
    suite.append(("star_7", nx.star_graph(7), 1))
    # Even cycle (triangle-free): χ = V − E = n − n = 0.
    suite.append(("cycle_6", nx.cycle_graph(6), 0))
    # Complete graph K_5: a single 4-simplex (contractible) ⇒ χ = 1, exercises
    # cliques up to dimension 4 (V_4 terms), the deepest alternating cancellation.
    suite.append(("complete_5", nx.complete_graph(5), 1))
    # Triangle K_3: χ = V − E + T = 3 − 3 + 1 = 1.
    suite.append(("triangle", nx.complete_graph(3), 1))
    # Two disjoint edges: χ = V − E = 4 − 2 = 2 (two components).
    suite.append(("two_edges", nx.Graph([(0, 1), (2, 3)]), 2))
    # Small-world graph with weights — exercises mixed triangle structure.
    sw: nx.Graph = nx.connected_watts_strogatz_graph(12, 4, 0.3, seed=7)
    suite.append(("watts_strogatz_12", sw, nx.number_of_nodes(sw) - nx.number_of_edges(sw) + sum(nx.triangles(sw).values()) // 3))

    return suite


@law("ricci.gauss_bonnet", n_graph_families=8, n_price_graphs=40)
def test_gauss_bonnet_identity_is_exact_and_fails_closed() -> None:
    """ricci.gauss_bonnet: Σ_x K(x) = χ(G) exactly, and the gate is a live filter.

    The witness sweeps a deterministic suite of graph families plus a battery of
    ``build_price_graph`` outputs, requiring the exact rational residual to be
    zero everywhere (the law admits no float slack). It then proves the residual
    is non-trivially informative: vertex curvatures are genuinely fractional and
    χ takes several distinct values across the suite (anti-vacuity), and a single
    tampered curvature value makes the fail-closed gate raise.
    """
    distinct_chi: set[int] = set()
    triangle_bearing_seen = 0
    fractional_curvature_seen = 0

    for name, graph, expected_chi in _graph_suite():
        chi = euler_characteristic(graph)
        assert chi == expected_chi, (
            f"ricci.gauss_bonnet VIOLATED (Euler characteristic): graph '{name}' "
            f"has χ={chi} but first-principles ground truth is {expected_chi}. "
            "χ = Σ_k (−1)^k v_k over clique counts. "
            "Tolerance: exact integer equality. "
            f"nodes={graph.number_of_nodes()}, edges={graph.number_of_edges()}"
        )

        residual = gauss_bonnet_residual(graph)
        assert residual == EXACT_ZERO, (
            f"ricci.gauss_bonnet VIOLATED (self-consistency): graph '{name}' has "
            f"Σ_x K(x) − χ = {residual} but the discrete Gauss–Bonnet theorem "
            "requires exactly 0. "
            "K(x) = Σ_k (−1)^k V_k(x)/(k+1), exact Fraction arithmetic. "
            "Tolerance: exact rational zero, no float slack. "
            f"χ={chi}, nodes={graph.number_of_nodes()}"
        )

        curvature = knill_vertex_curvature(graph)
        # Supplying the *recomputed* field through the residual must also be 0.
        supplied_residual = gauss_bonnet_residual(graph, curvature=curvature)
        assert supplied_residual == EXACT_ZERO, (
            f"ricci.gauss_bonnet VIOLATED (supplied-field path): graph '{name}' "
            f"residual {supplied_residual} ≠ 0 when verifying its own recomputed "
            "curvature field. Tolerance: exact rational zero."
        )

        distinct_chi.add(chi)
        if sum(nx.triangles(graph).values()) > 0:
            triangle_bearing_seen += 1
        if any(value.denominator != 1 for value in curvature.values()):
            fractional_curvature_seen += 1

    # build_price_graph battery — the law must hold on the production graph type.
    rng = np.random.default_rng(seed=2026)
    n_price_graphs = 40
    for _ in range(n_price_graphs):
        prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 5e-3, size=48)))
        gp = build_price_graph(prices, delta=0.005)
        if gp.number_of_nodes() == 0:
            continue
        # build_price_graph encodes level-persistence as self-loops; those are
        # not 1-simplices, so per the law's validity clause we verify on the
        # simple underlying graph (self-loops removed explicitly, not silently
        # tolerated by the operator).
        gp.remove_edges_from(list(nx.selfloop_edges(gp)))
        residual = gauss_bonnet_residual(gp)
        assert residual == EXACT_ZERO, (
            "ricci.gauss_bonnet VIOLATED on build_price_graph output: residual "
            f"{residual} ≠ 0 over n_price_graphs={n_price_graphs}, delta=0.005, "
            "seed=2026. Tolerance: exact rational zero."
        )

    # Anti-vacuity: the suite must span ≥3 distinct χ, exercise higher-order
    # simplices (triangles), and produce genuinely fractional curvatures — else
    # the identity could be passing on a trivial all-zero/all-integer slice.
    assert len(distinct_chi) >= 3, (
        "ricci.gauss_bonnet vacuity guard: observed distinct χ values "
        f"{sorted(distinct_chi)} must span ≥3 topologies; a single χ would let a "
        "broken implementation pass on one fixed point."
    )
    assert triangle_bearing_seen >= 2, (
        "ricci.gauss_bonnet vacuity guard: triangle_bearing_seen="
        f"{triangle_bearing_seen} must be ≥2 so the higher-order V_k (k≥2) terms "
        "of K(x) are genuinely exercised, not just the V−E skeleton."
    )
    assert fractional_curvature_seen >= 2, (
        "ricci.gauss_bonnet vacuity guard: fractional_curvature_seen="
        f"{fractional_curvature_seen} must be ≥2; if every K(x) were an integer "
        "the exact-Fraction machinery would be untested."
    )

    # Falsifiability leg: a single tampered curvature value MUST trip the gate.
    g = nx.complete_graph(5)
    good = knill_vertex_curvature(g)
    tampered = dict(good)
    victim = next(iter(tampered))
    tampered[victim] = tampered[victim] + Fraction(1)  # inject a unit of fake curvature
    raised = False
    try:
        assert_gauss_bonnet(g, curvature=tampered)
    except GaussBonnetViolation:
        raised = True
    assert raised, (
        "ricci.gauss_bonnet falsifiability guard: assert_gauss_bonnet accepted a "
        "curvature field tampered by +1 on one vertex. A gate that cannot fail is "
        "vacuous — the discrete Gauss–Bonnet residual must reject it."
    )


def test_gauss_bonnet_refuses_out_of_domain_inputs() -> None:
    """Domain rejections are fail-closed, not silently coerced.

    Self-loops, multigraphs and directed graphs lie outside the clique-complex
    domain; the operator must raise rather than return a wrong invariant.
    """
    looped = nx.Graph()
    looped.add_edge(0, 0)
    try:
        euler_characteristic(looped)
        raise AssertionError("self-loop graph must be rejected")
    except GaussBonnetViolation:
        pass

    directed = nx.DiGraph([(0, 1), (1, 2)])
    try:
        gauss_bonnet_residual(directed)
        raise AssertionError("directed graph must be rejected")
    except GaussBonnetViolation:
        pass

    multi = nx.MultiGraph()
    multi.add_edge(0, 1)
    multi.add_edge(0, 1)
    try:
        knill_vertex_curvature(multi)
        raise AssertionError("multigraph must be rejected")
    except GaussBonnetViolation:
        pass


def test_gauss_bonnet_rejects_mismatched_vertex_set() -> None:
    """A supplied curvature field must cover exactly the graph's vertices."""
    g = nx.path_graph(4)
    field = {0: Fraction(1), 1: Fraction(0)}  # missing vertices 2, 3
    try:
        gauss_bonnet_residual(g, curvature=field)
        raise AssertionError("mismatched vertex set must be rejected")
    except GaussBonnetViolation:
        pass
