# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Combinatorial Gauss–Bonnet integrity invariant for discrete graph geometry.

This module gives GeoSync a *first-principles* topological verification
operator that is exact and falsifiable — not a metaphor. For the clique
complex of any finite simple graph ``G``, Knill's discrete Gauss–Bonnet
theorem states that the sum of vertex curvatures equals the Euler
characteristic:

    Σ_{x ∈ V}  K(x)  =  χ(G)

where

* ``K(x) = Σ_{k≥0} (−1)^k · V_k(x) / (k + 1)`` is the Knill vertex curvature,
  ``V_k(x)`` the number of ``(k+1)``-cliques containing ``x``
  (``V_0(x) = 1``, ``V_1(x) = deg(x)``, ``V_2(x)`` = triangles at ``x``, …);
* ``χ(G) = Σ_{k≥0} (−1)^k v_k`` with ``v_k`` the number of ``(k+1)``-cliques
  in ``G`` (``v_0`` = vertices, ``v_1`` = edges, ``v_2`` = triangles, …).

The identity is *exact over the rationals*. Because both sides are computed
from independent traversals of the same complex, a non-zero residual is never
"numerical noise": it is hard evidence that a transported / serialised /
externally supplied curvature field is inconsistent with the topology it
claims to describe — i.e. corrupted or tampered state. The operator therefore
fails closed.

Nothing here is a market claim. This is a geometry fact about the data
structure, used as an integrity gate.

References
----------
Knill, O. "A graph theoretical Gauss-Bonnet theorem." arXiv:1111.5395 (2011).
"""

from __future__ import annotations

from fractions import Fraction
from typing import Hashable, Mapping

import networkx as nx

__all__ = [
    "GaussBonnetViolation",
    "assert_gauss_bonnet",
    "euler_characteristic",
    "gauss_bonnet_residual",
    "knill_vertex_curvature",
]


class GaussBonnetViolation(AssertionError):
    """Raised when the discrete Gauss–Bonnet identity is violated.

    A violation means a supplied curvature field does not reconcile with the
    Euler characteristic of its graph to the exact rational residual ``0``. The
    state is rejected fail-closed; it is never downgraded to a warning.
    """


def _reject_non_simple(graph: nx.Graph) -> None:
    """Fail closed on inputs outside the clique-complex domain.

    The combinatorial theorem is stated for finite *simple* undirected graphs.
    Self-loops and multi/directed edges are out of domain, so we refuse them
    rather than return a silently wrong invariant.
    """
    if graph.is_directed():
        raise GaussBonnetViolation(
            "Gauss–Bonnet domain error: directed graphs are not simple "
            "complexes; pass an undirected nx.Graph"
        )
    if graph.is_multigraph():
        raise GaussBonnetViolation(
            "Gauss–Bonnet domain error: multigraphs carry parallel edges that "
            "break the clique complex; collapse to a simple nx.Graph first"
        )
    selfloops = list(nx.selfloop_edges(graph))
    if selfloops:
        raise GaussBonnetViolation(
            "Gauss–Bonnet domain error: self-loops "
            f"{selfloops!r} are not 1-simplices; remove them first"
        )


def _clique_spectrum(graph: nx.Graph) -> tuple[list[int], dict[Hashable, list[int]]]:
    """Return global and per-vertex clique counts of the clique complex.

    Returns
    -------
    v_k : list[int]
        ``v_k[k]`` is the number of ``(k+1)``-cliques in ``graph`` (the count of
        ``k``-dimensional simplices of the clique complex).
    per_vertex : dict
        Maps each vertex ``x`` to a list ``V_k(x)`` where ``V_k(x)[k]`` is the
        number of ``(k+1)``-cliques containing ``x``.

    The two are produced from a single ``enumerate_all_cliques`` pass so they
    are guaranteed mutually consistent; the residual's discriminating power
    comes from comparing this against an *externally supplied* field.
    """
    v_k: list[int] = []
    per_vertex: dict[Hashable, list[int]] = {node: [] for node in graph.nodes()}

    def _ensure(index: int, store: list[int]) -> None:
        while len(store) <= index:
            store.append(0)

    for clique in nx.enumerate_all_cliques(graph):
        dimension = len(clique) - 1  # k for a (k+1)-clique
        _ensure(dimension, v_k)
        v_k[dimension] += 1
        for node in clique:
            store = per_vertex[node]
            _ensure(dimension, store)
            store[dimension] += 1

    return v_k, per_vertex


def euler_characteristic(graph: nx.Graph) -> int:
    """Euler characteristic ``χ`` of the clique complex of ``graph``.

    ``χ = Σ_k (−1)^k v_k`` — an exact integer alternating sum over clique
    counts. For a triangle-free graph this reduces to ``V − E``.
    """
    _reject_non_simple(graph)
    v_k, _ = _clique_spectrum(graph)
    return sum((-1) ** k * count for k, count in enumerate(v_k))


def knill_vertex_curvature(graph: nx.Graph) -> dict[Hashable, Fraction]:
    """Exact Knill vertex curvature ``K(x)`` for every vertex of ``graph``.

    ``K(x) = Σ_k (−1)^k · V_k(x) / (k + 1)``. Computed with
    :class:`fractions.Fraction` so the curvature field — and any residual built
    from it — is exact, with no floating-point slack to launder a violation.
    """
    _reject_non_simple(graph)
    _, per_vertex = _clique_spectrum(graph)
    curvature: dict[Hashable, Fraction] = {}
    for node, counts in per_vertex.items():
        total = Fraction(0)
        for k, v in enumerate(counts):
            total += Fraction((-1) ** k * v, k + 1)
        curvature[node] = total
    return curvature


def _as_fraction(value: object) -> Fraction:
    """Coerce a supplied curvature value to an exact ``Fraction``.

    Floats are admitted (they are converted exactly, preserving any deviation
    that would signal corruption) but ``int``/``Fraction`` pass through without
    binary-float artefacts.
    """
    if isinstance(value, Fraction):
        return value
    if isinstance(value, bool):  # bool is an int subclass; reject the foot-gun
        raise GaussBonnetViolation(f"Gauss–Bonnet type error: boolean curvature value {value!r}")
    if isinstance(value, int):
        return Fraction(value)
    if isinstance(value, float):
        return Fraction(value).limit_denominator(10**12)
    raise GaussBonnetViolation(f"Gauss–Bonnet type error: non-numeric curvature value {value!r}")


def gauss_bonnet_residual(
    graph: nx.Graph,
    *,
    curvature: Mapping[Hashable, object] | None = None,
) -> Fraction:
    """Exact residual ``Σ_x K(x) − χ(G)`` of the discrete Gauss–Bonnet identity.

    Parameters
    ----------
    graph:
        Finite simple undirected graph.
    curvature:
        Optional *externally supplied* vertex-curvature field to verify. When
        given it must cover exactly ``graph``'s vertex set; the residual then
        measures the supplied field against the recomputed Euler characteristic
        — this is the integrity check on transported state. When ``None`` the
        curvature is recomputed internally, in which case the residual is ``0``
        by the theorem (a self-consistency probe of the implementation).

    Returns
    -------
    Fraction
        Exactly ``0`` iff the field reconciles with the topology.
    """
    chi = euler_characteristic(graph)
    if curvature is None:
        field = knill_vertex_curvature(graph)
    else:
        nodes = set(graph.nodes())
        supplied = set(curvature.keys())
        if supplied != nodes:
            missing = nodes - supplied
            extra = supplied - nodes
            raise GaussBonnetViolation(
                "Gauss–Bonnet domain error: supplied curvature vertex set does "
                f"not match the graph (missing={sorted(map(repr, missing))}, "
                f"extra={sorted(map(repr, extra))})"
            )
        field = {node: _as_fraction(value) for node, value in curvature.items()}
    total = sum(field.values(), Fraction(0))
    return total - Fraction(chi)


def assert_gauss_bonnet(
    graph: nx.Graph,
    *,
    curvature: Mapping[Hashable, object] | None = None,
) -> None:
    """Fail-closed gate: raise :class:`GaussBonnetViolation` on any deviation.

    This is the verification operator intended for use at integrity boundaries
    (deserialisation, transport, PR artefact validation). It admits state only
    when the exact residual is ``0``.
    """
    residual = gauss_bonnet_residual(graph, curvature=curvature)
    if residual != 0:
        raise GaussBonnetViolation(
            "Discrete Gauss–Bonnet violated: Σ K(x) − χ(G) = "
            f"{residual} (must be exactly 0). The supplied curvature field is "
            "inconsistent with the graph topology — state rejected."
        )
