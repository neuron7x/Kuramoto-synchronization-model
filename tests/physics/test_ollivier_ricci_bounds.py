# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Executable falsification witnesses for the law ``ricci.ollivier_bounds``.

Ollivier (J. Funct. Anal. 2009) defines edge curvature

    kappa(x, y) = 1 - W_1(m_x, m_y) / d(x, y)

with W_1 >= 0, so the upper bound ``kappa <= 1`` is UNIVERSAL: it holds for
every edge of every connected graph (INV-RC1, P0). The *symmetric* band
``kappa in [-1, 1]`` is NOT universal — its lower bound ``kappa >= -1`` assumes
the positional embedding (in which W_1 is measured) is commensurate with the
combinatorial geodesic ``d``. The implementation in ``core/indicators/ricci.py``
uses a 1-D positional embedding (offset/scale from graph attrs) with
``alpha = 1/(deg + 1)``; that commensurateness holds only for
:func:`build_price_graph` output, whose consecutive integer node IDs make the
embedding equal to the combinatorial distance (INV-RC3, P1).

- POSITIVE witness: over a fuzz of random connected weighted graphs the maximal
  edge curvature never exceeds ``1`` (INV-RC1), and every ``build_price_graph``
  edge stays inside ``[-1, 1]`` (INV-RC3).
- NEGATIVE control: the documented counterexample — a 12-node cycle — yields
  ``kappa = -2`` on its wrap-around edge (endpoints 11 apart in the integer
  embedding but graph-distance 1), proving the symmetric band is a price-graph
  ONLY claim and refuting any over-broad universal ``kappa >= -1``. Invalid
  inputs (degenerate graph, non-finite probability mass) fail closed.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import pytest

from core.indicators.ricci import (
    NodeDistribution,
    assert_ricci_regime,
    build_price_graph,
    compute_node_distributions,
    ricci_curvature_edge,
)

#: Float round-off tolerance for the kappa bound checks.
_TOL: float = 1e-9


def _random_connected_weighted_graph(rng: np.random.Generator) -> nx.Graph:
    """Return a random connected graph with strictly positive edge weights."""
    n = int(rng.integers(4, 14))
    p = float(rng.uniform(0.3, 0.85))
    seed = int(rng.integers(0, 2**31 - 1))
    g: nx.Graph = nx.gnp_random_graph(n, p, seed=seed)
    if not nx.is_connected(g) or g.number_of_edges() == 0:
        # Fall back to a guaranteed-connected topology with the same node count.
        g = nx.path_graph(max(2, n))
    for u, v in g.edges():
        g[u][v]["weight"] = float(rng.uniform(0.5, 5.0))
    return g


def test_ollivier_upper_bound_is_universal() -> None:
    """Positive witness: kappa <= 1 over a graph fuzz (INV-RC1) and in [-1,1] on price graphs (INV-RC3)."""
    rng = np.random.default_rng(20240601)

    # Leg 1 — INV-RC1: the universal upper bound kappa <= 1 over arbitrary
    # connected topologies and weightings (W_1 >= 0 => kappa = 1 - W_1/d <= 1).
    max_kappa = -np.inf
    n_graphs = 0
    n_edges = 0
    for _ in range(400):
        g = _random_connected_weighted_graph(rng)
        dists = compute_node_distributions(g)
        for u, v in g.edges():
            kappa = ricci_curvature_edge(g, u, v, distributions=dists)
            if np.isfinite(kappa):
                max_kappa = max(max_kappa, kappa)
                n_edges += 1
        n_graphs += 1

    assert max_kappa <= 1.0 + _TOL, (
        f"INV-RC1 VIOLATED: max kappa={max_kappa:.6f} > 1 over a connected-graph fuzz. "
        f"kappa = 1 - W_1/d with W_1 >= 0 forces the universal upper bound kappa <= 1. "
        f"Source: Ollivier J. Funct. Anal. 2009; core/indicators/ricci.py::ricci_curvature_edge. "
        f"tol={_TOL:.1e}. "
        f"fuzz: graphs={n_graphs}, edges={n_edges}, seed=20240601"
    )

    # Leg 2 — INV-RC3: the symmetric band kappa in [-1, 1] for build_price_graph
    # output (consecutive integer node IDs => positional embedding == d).
    rng2 = np.random.default_rng(7)
    pg_min, pg_max = np.inf, -np.inf
    n_pg_edges = 0
    for _ in range(60):
        steps = rng2.normal(0.0, 0.002, size=200)
        prices = 100.0 * np.exp(np.cumsum(steps))
        g = build_price_graph(prices, delta=0.005)
        if g.number_of_edges() == 0:
            continue
        dists = compute_node_distributions(g)
        for u, v in g.edges():
            kappa = ricci_curvature_edge(g, u, v, distributions=dists)
            if np.isfinite(kappa):
                pg_min = min(pg_min, kappa)
                pg_max = max(pg_max, kappa)
                n_pg_edges += 1

    assert n_pg_edges > 0, (
        "INV-RC3 VACUOUS WITNESS: build_price_graph produced no finite curvature "
        "edges across the seeded price-path ensemble; the symmetric-band leg must "
        "fail closed instead of passing with pg_min=inf and pg_max=-inf. "
        "Source: core/indicators/ricci.py::build_price_graph; seed=7"
    )
    assert np.isfinite(pg_min) and np.isfinite(pg_max), (
        "INV-RC3 VACUOUS WITNESS: price-graph curvature bounds remained non-finite "
        f"after {n_pg_edges} counted edges; fail closed before checking the band."
    )
    assert -1.0 - _TOL <= pg_min and pg_max <= 1.0 + _TOL, (
        f"INV-RC3 VIOLATED: build_price_graph kappa range "
        f"[{pg_min:.6f}, {pg_max:.6f}] left the symmetric band [-1, 1]. "
        f"Consecutive integer levels make the 1-D embedding equal the combinatorial "
        f"metric, so W_1/d <= 2 and kappa >= -1. "
        f"Source: INV-RC3, P1; core/indicators/ricci.py::build_price_graph. "
        f"tol={_TOL:.1e}, price-graph edges={n_pg_edges}, seed=7"
    )


def test_symmetric_band_is_not_universal() -> None:
    """Negative control: the 12-cycle wrap edge gives kappa < -1, refuting a universal [-1,1] band; invalid input fails closed."""
    # The documented counterexample (Ollivier J. Funct. Anal. 2009; recorded in
    # core/indicators/ricci.py::ricci_curvature_edge): a 12-node cycle. Its
    # wrap-around edge (11, 0) joins endpoints 11 apart in the integer embedding
    # yet graph-distance 1, so W_1/d ~ 3 and kappa ~ -2 < -1.
    cycle = nx.cycle_graph(12)
    dists = compute_node_distributions(cycle)
    wrap_kappa = ricci_curvature_edge(cycle, 11, 0, distributions=dists)
    kappa_min = min(
        ricci_curvature_edge(cycle, u, v, distributions=dists) for u, v in cycle.edges()
    )

    assert wrap_kappa < -1.0 - _TOL, (
        f"REFUTATION FAILED: 12-cycle wrap edge kappa={wrap_kappa:.6f} did not fall "
        f"below -1; the symmetric band would then be (wrongly) universal. "
        f"The integer embedding puts endpoints 11 apart at graph-distance 1, so "
        f"W_1/d ~ 3 must push kappa to ~ -2. "
        f"Source: Ollivier J. Funct. Anal. 2009 counterexample; INV-RC3 is price-graph ONLY. "
        f"measured kappa_min={kappa_min:.6f} over the 12 cycle edges"
    )

    # The only UNIVERSAL bound that survives this topology is the upper bound.
    assert wrap_kappa <= 1.0 + _TOL, (
        f"INV-RC1 VIOLATED: even the over-curved wrap edge must obey the universal "
        f"upper bound kappa <= 1; got kappa={wrap_kappa:.6f}. "
        f"kappa = 1 - W_1/d, W_1 >= 0. "
        f"Source: Ollivier J. Funct. Anal. 2009. "
        f"12-cycle wrap edge (11, 0), kappa_min={kappa_min:.6f}"
    )

    # The runtime regime gate must NOT certify this non-price topology as INV-RC3:
    # it downgrades to the universal INV-RC1 and records the band violation.
    cert = assert_ricci_regime(cycle)
    assert cert.asserted_tier == "INV-RC1", (
        f"REGIME-DOWNGRADE FAILED: 12-cycle certified as {cert.asserted_tier}, not "
        f"INV-RC1; an out-of-regime kappa was presented as INV-RC3-valid. "
        f"commensurate={cert.commensurate}, kappa_min={cert.kappa_min:.6f}. "
        f"Source: core/indicators/ricci.py::assert_ricci_regime. "
        f"n_edges_below_lower_bound={cert.n_edges_below_lower_bound}"
    )
    assert cert.n_edges_below_lower_bound > 0 and not cert.commensurate

    # Fail-closed leg A: a non-price topology cannot raise INV-RC3 on demand.
    with pytest.raises(ValueError, match="commensurate-metric regime violated"):
        assert_ricci_regime(cycle, raise_on_violation=True)

    # Fail-closed leg B: a degenerate (empty) graph cannot support the band.
    with pytest.raises(ValueError, match="commensurate-metric regime violated"):
        assert_ricci_regime(nx.Graph(), raise_on_violation=True)

    # Fail-closed leg C: non-finite / zero probability mass is rejected, not
    # silently repaired into a fabricated curvature.
    for bad_probs in ([np.nan, 0.1], [0.0, 0.0]):
        with pytest.raises(ValueError, match="must sum to a positive finite value"):
            NodeDistribution(
                support=np.array([0.0, 1.0]),
                probabilities=np.array(bad_probs, dtype=float),
                positions=np.array([0.0, 1.0]),
            )
