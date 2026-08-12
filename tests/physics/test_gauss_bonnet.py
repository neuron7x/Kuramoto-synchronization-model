# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable falsification witnesses for ``ricci.gauss_bonnet``.

Discrete Gauss-Bonnet (Knill): for the clique complex of any finite simple
graph ``G``, the sum of Knill vertex curvatures equals the Euler characteristic,

    Sum_{x in V} K(x) = chi(G),

with ``K(x) = Sum_k (-1)^k V_k(x)/(k+1)`` and ``chi(G) = Sum_k (-1)^k v_k``.
The identity is EXACT over the rationals, so the residual ``Sum_x K(x) - chi(G)``
is exactly ``0`` (a ``fractions.Fraction``), never a float "close to zero".

The math is reused from :mod:`core.indicators.gauss_bonnet` (Fraction
arithmetic) -- this file does not reimplement it; it binds the law to the
executable falsification catalog with a positive witness and a negative control.

Nothing here is a market claim. These are geometry facts about the data
structure, used as a fail-closed integrity gate.

Reference: Knill, O. "A graph theoretical Gauss-Bonnet theorem." arXiv:1111.5395.
"""

from __future__ import annotations

from fractions import Fraction

import networkx as nx
import pytest

from core.indicators.gauss_bonnet import (
    GaussBonnetViolation,
    assert_gauss_bonnet,
    euler_characteristic,
    gauss_bonnet_residual,
    knill_vertex_curvature,
)

# The law's tolerance is "exact: residual == 0 over the rationals". The only
# admissible deviation is the exact rational zero -- not a float epsilon.
EXACT_ZERO = Fraction(0)


def _graph_battery() -> list[tuple[str, nx.Graph, int]]:
    """Finite simple graphs paired with their first-principles Euler characteristic.

    Each ``expected_chi`` is derived independently of the code under test, so the
    witness checks the implementation against ground truth, not against itself.
    """
    raw: list[tuple[str, nx.Graph, int | None]] = [
        # Trees (path / star / balanced): chi = V - E = 1.
        ("path_8", nx.path_graph(8), 1),
        ("star_7", nx.star_graph(7), 1),
        ("balanced_tree_2_3", nx.balanced_tree(2, 3), 1),
        # Cycles (triangle-free): chi = V - E = 0.
        ("cycle_5", nx.cycle_graph(5), 0),
        ("cycle_6", nx.cycle_graph(6), 0),
        # Complete graphs K_n: a single (n-1)-simplex (contractible) => chi = 1.
        # K_3 has a triangle, K_5/K_6 exercise V_k up to k=4/5 (deep cancellation).
        ("complete_3", nx.complete_graph(3), 1),
        ("complete_5", nx.complete_graph(5), 1),
        ("complete_6", nx.complete_graph(6), 1),
        # Two disjoint edges: chi = V - E = 4 - 2 = 2 (two components).
        ("two_edges", nx.Graph([(0, 1), (2, 3)]), 2),
        # Petersen graph (triangle-free, 3-regular): chi = 10 - 15 = -5.
        ("petersen", nx.petersen_graph(), -5),
        # Small-world graph: chi = V - E + T, computed from independent ground truth.
        ("watts_strogatz_12", nx.connected_watts_strogatz_graph(12, 4, 0.3, seed=7), None),
    ]
    out: list[tuple[str, nx.Graph, int]] = []
    for name, graph, chi in raw:
        if chi is None:
            triangles = sum(nx.triangles(graph).values()) // 3
            chi = graph.number_of_nodes() - graph.number_of_edges() + triangles
        out.append((name, graph, chi))
    return out


def test_gauss_bonnet_residual_is_exactly_zero() -> None:
    """Positive witness: Sum_x K(x) = chi(G) holds EXACTLY over a graph battery.

    For every graph the exact rational residual must be ``0`` and chi must match
    the first-principles ground truth. Anti-vacuity: the battery must span >=3
    distinct chi, exercise triangles (higher-order V_k), and produce genuinely
    fractional curvatures -- otherwise a broken implementation could pass on a
    trivial all-integer / single-chi slice.
    """
    distinct_chi: set[int] = set()
    triangle_bearing = 0
    fractional_curvature = 0

    for name, graph, expected_chi in _graph_battery():
        chi = euler_characteristic(graph)
        assert chi == expected_chi, (
            f"ricci.gauss_bonnet VIOLATED (Euler characteristic): graph '{name}' "
            f"has chi={chi} but first-principles ground truth is {expected_chi}. "
            f"chi = Sum_k (-1)^k v_k over clique counts. "
            f"Tolerance: exact integer equality. "
            f"nodes={graph.number_of_nodes()}, edges={graph.number_of_edges()}"
        )

        residual = gauss_bonnet_residual(graph)
        assert residual == EXACT_ZERO, (
            f"ricci.gauss_bonnet VIOLATED (residual): graph '{name}' has "
            f"Sum_x K(x) - chi = {residual} but discrete Gauss-Bonnet requires "
            f"exactly 0. K(x) = Sum_k (-1)^k V_k(x)/(k+1), exact Fraction arithmetic. "
            f"Tolerance: exact rational zero, no float slack. "
            f"chi={chi}, nodes={graph.number_of_nodes()}"
        )
        assert isinstance(residual, Fraction), (
            f"ricci.gauss_bonnet VIOLATED (type): graph '{name}' residual is "
            f"{type(residual).__name__}, expected fractions.Fraction. "
            f"The law is exact over Q; a float residual would launder violations. "
            f"Tolerance: residual must be an exact rational. value={residual!r}"
        )

        curvature = knill_vertex_curvature(graph)
        supplied = gauss_bonnet_residual(graph, curvature=curvature)
        assert supplied == EXACT_ZERO, (
            f"ricci.gauss_bonnet VIOLATED (supplied-field): graph '{name}' "
            f"residual {supplied} != 0 when verifying its own recomputed curvature "
            f"field. K(x) field must reconcile with chi. "
            f"Tolerance: exact rational zero. chi={chi}"
        )

        distinct_chi.add(chi)
        if sum(nx.triangles(graph).values()) > 0:
            triangle_bearing += 1
        if any(value.denominator != 1 for value in curvature.values()):
            fractional_curvature += 1

    assert len(distinct_chi) >= 3, (
        f"ricci.gauss_bonnet vacuity guard: distinct chi values {sorted(distinct_chi)} "
        f"must span >=3 topologies; a single chi would let a broken implementation "
        f"pass on one fixed point. Tolerance: >=3 distinct. battery covers "
        f"trees/cycles/complete/petersen."
    )
    assert triangle_bearing >= 3, (
        f"ricci.gauss_bonnet vacuity guard: triangle_bearing={triangle_bearing} "
        f"must be >=3 so higher-order V_k (k>=2) terms of K(x) are exercised, not "
        f"only the V-E skeleton. Tolerance: >=3. K_3/K_5/K_6 contribute triangles."
    )
    assert fractional_curvature >= 3, (
        f"ricci.gauss_bonnet vacuity guard: fractional_curvature={fractional_curvature} "
        f"must be >=3; if every K(x) were an integer the exact-Fraction machinery "
        f"would be untested. Tolerance: >=3 graphs with non-integer K(x)."
    )


def test_gauss_bonnet_detects_corruption_and_rejects_bad_input() -> None:
    """Negative control: the residual is a LIVE falsifier, not a vacuous identity.

    Three discriminating corruptions, each of which the gate MUST catch:
      1. perturb one vertex curvature by a nonzero rational  => residual != 0;
      2. drop one vertex's contribution (corrupt the field)  => residual != 0;
      3. feed an out-of-domain (non-simple) graph            => fail closed.
    A gate that cannot fail is vacuous; these prove it discriminates.
    """
    graph = nx.complete_graph(5)

    # (1) Tamper a single vertex curvature by a nonzero rational. The exact
    # identity is broken and the residual reports the exact deviation.
    good = knill_vertex_curvature(graph)
    tampered = dict(good)
    victim = next(iter(tampered))
    tampered[victim] = tampered[victim] + Fraction(1, 3)
    residual = gauss_bonnet_residual(graph, curvature=tampered)
    assert residual == Fraction(1, 3), (
        f"ricci.gauss_bonnet negative control FAILED: a +1/3 curvature tamper on "
        f"vertex {victim!r} produced residual {residual}, expected exactly 1/3. "
        f"The residual must report the exact rational deviation. "
        f"Tolerance: exact rational equality. chi={euler_characteristic(graph)}"
    )
    with pytest.raises(GaussBonnetViolation):
        assert_gauss_bonnet(graph, curvature=tampered)

    # (2) Corrupt the curvature accounting by zeroing one vertex's contribution to
    # mimic a missing clique in the f-vector: the alternating sum no longer cancels
    # against chi, so the residual is forced off zero.
    dropped = dict(good)
    dropped[victim] = Fraction(0)
    assert gauss_bonnet_residual(graph, curvature=dropped) != EXACT_ZERO, (
        f"ricci.gauss_bonnet negative control FAILED: zeroing one vertex curvature "
        f"left the residual at 0; a dropped clique must break Sum_x K(x) = chi. "
        f"Tolerance: residual != 0. dropped vertex={victim!r}"
    )

    # (3) Out-of-domain inputs (non-simple graphs) must fail closed, never coerce.
    looped = nx.Graph()
    looped.add_edge(0, 0)  # self-loop is not a 1-simplex
    with pytest.raises(GaussBonnetViolation):
        gauss_bonnet_residual(looped)

    multi = nx.MultiGraph()
    multi.add_edge(0, 1)
    multi.add_edge(0, 1)  # parallel edge breaks the clique complex
    with pytest.raises(GaussBonnetViolation):
        gauss_bonnet_residual(multi)

    directed = nx.DiGraph([(0, 1), (1, 2)])
    with pytest.raises(GaussBonnetViolation):
        gauss_bonnet_residual(directed)
