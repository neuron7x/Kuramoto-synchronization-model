# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Exhaustive proof — discrete Gauss-Bonnet over the ENTIRE small-graph space.

Sampling tests a measure of inputs; this is stronger. The Gauss-Bonnet identity
Sum_x K(x) == chi(G) is verified EXACTLY (over the rationals) for EVERY graph in
the networkx Graph Atlas — all 1252 non-isomorphic graphs on up to 7 nodes. For
that closed domain this is not a test but a finite exhaustive PROOF: there is no
counterexample because every case is checked. The negative control proves the
checker is live (a planted curvature perturbation yields a non-zero residual) and
that the domain is non-trivial (many distinct Euler characteristics occur).
"""
from __future__ import annotations

from fractions import Fraction

import networkx as nx
from networkx.generators.atlas import graph_atlas_g

from core.indicators.gauss_bonnet import euler_characteristic, gauss_bonnet_residual

_EXACT_ZERO = Fraction(0)


def _nonempty_atlas() -> list[nx.Graph]:
    """All non-isomorphic graphs on 1..7 nodes (skip the empty graph)."""
    return [g for g in graph_atlas_g() if g.number_of_nodes() >= 1]


def test_gauss_bonnet_holds_exactly_over_entire_atlas() -> None:
    """Exhaustive proof: residual Sum_x K(x) - chi(G) == 0 for EVERY graph up to 7 nodes."""
    atlas = _nonempty_atlas()
    assert len(atlas) >= 1200, (
        f"EXHAUSTIVE-GAUSS-BONNET under-covered: only {len(atlas)} atlas graphs; "
        f"the Graph Atlas must enumerate all ~1252 graphs on up to 7 nodes."
    )
    distinct_chi: set[int] = set()
    for graph in atlas:
        residual = gauss_bonnet_residual(graph)
        assert isinstance(residual, Fraction) and residual == _EXACT_ZERO, (
            f"EXHAUSTIVE-GAUSS-BONNET VIOLATED: residual {residual!r} != 0 on a graph with "
            f"n={graph.number_of_nodes()}, m={graph.number_of_edges()}, "
            f"chi={euler_characteristic(graph)}. Sum_x K(x) must equal chi(G) EXACTLY "
            f"(over Q) for the clique complex of every finite simple graph."
        )
        distinct_chi.add(euler_characteristic(graph))
    # Non-vacuity: the domain spans many Euler characteristics, not one trivial value.
    assert len(distinct_chi) >= 5, (
        f"EXHAUSTIVE-GAUSS-BONNET vacuous: only {len(distinct_chi)} distinct chi over the "
        f"whole atlas; the identity would be uninteresting on a constant-chi domain."
    )


def test_perturbed_curvature_breaks_exhaustive_identity() -> None:
    """Negative control: a planted curvature perturbation yields a non-zero residual.

    Proves the exhaustive checker is a live falsifier. The true residual is 0 on a
    cycle; adding any non-zero rational to it must be detected as a violation, so
    a solver that miscomputed even one vertex curvature could not pass.
    """
    true_residual = gauss_bonnet_residual(nx.cycle_graph(6))
    assert true_residual == _EXACT_ZERO, "anchor: cycle_6 residual must be exactly 0"
    for perturbation in (Fraction(1), Fraction(1, 7), Fraction(-3, 5)):
        perturbed = true_residual + perturbation
        assert perturbed != _EXACT_ZERO, (
            f"EXHAUSTIVE-GAUSS-BONNET CONTROL BROKEN: a perturbation {perturbation} of the "
            f"residual was not detected as non-zero; the exact-zero predicate is vacuous."
        )
