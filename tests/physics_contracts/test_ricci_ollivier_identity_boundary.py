# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Identity- and boundary-level witnesses for the Ollivier–Ricci curvature.

These go one level deeper than a bound check. Rather than only asserting that
κ stays inside an interval, they certify *what the implementation actually
computes* and *exactly when* its [−1, 1] envelope can break:

* ``ricci.ollivier_bounds`` (identity) — the code's edge curvature equals,
  to float precision, the first-principles definition
  κ(x,y) = 1 − W₁(μₓ, μᵧ) / d(x,y), recomputed independently from SciPy's
  1-D optimal-transport distance over the positional embedding and NetworkX's
  weighted geodesic. INV-RC1 anchors the resulting κ ≤ 1 bound.

* INV-RC3 boundary — the lower bound κ ≥ −1 is algebraically equivalent to
  W₁/d ≤ 2. The witness certifies that equivalence edge-by-edge and then shows
  the equivalence is non-vacuous on ``build_price_graph``: because W₁ is measured
  in the positional (price-level) metric while d is the |Δp|+1 weighted-graph
  metric, the two are incommensurate, so W₁/d exceeds 2 on some edges and κ
  descends below −1. INV-RC3's [−1, 1] therefore holds only where the two
  metrics stay commensurate (path-like, small jumps).

Nothing here is a market claim. These are optimal-transport-geometry facts.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
from scipy.stats import wasserstein_distance

from core.indicators.ricci import (
    _build_node_distribution,
    _graph_geometry,
    build_price_graph,
    ricci_curvature_edge,
)
from physics_contracts.law import law

# The identity is exact arithmetic; allow only float round-off.
IDENTITY_TOLERANCE = 1e-9
# κ = 1 − W₁/d, so κ ≥ −1 ⇔ W₁/d ≤ 2. This ratio threshold is the law, not a
# magic number.
LOWER_BOUND_RATIO = 2.0
RATIO_EPS = 1e-9


def _independent_curvature(g: nx.Graph, x: int, y: int) -> tuple[float, float]:
    """Recompute (κ, W₁/d) from first principles, independent of the code path.

    W₁ via SciPy optimal transport over the positional embedding; d via the
    NetworkX weighted geodesic — exactly the two ingredients of the definition.
    """
    offset, scale = _graph_geometry(g)
    dist_x = _build_node_distribution(g, x, offset, scale)
    dist_y = _build_node_distribution(g, y, offset, scale)
    w1 = float(
        wasserstein_distance(
            dist_x.positions,
            dist_y.positions,
            u_weights=dist_x.probabilities,
            v_weights=dist_y.probabilities,
        )
    )
    d = float(nx.shortest_path_length(g, x, y, weight="weight"))
    return 1.0 - w1 / d, w1 / d


def _price_graphs(seed: int, n_graphs: int, length: int, delta: float) -> list[nx.Graph]:
    rng = np.random.default_rng(seed)
    graphs = []
    for _ in range(n_graphs):
        prices = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, size=length)))
        graphs.append(build_price_graph(prices, delta=delta))
    return graphs


@law("ricci.ollivier_bounds", n_graphs=40, length=128, delta=0.01)
def test_ollivier_curvature_equals_wasserstein_geodesic_formula() -> None:
    """INV-RC1: the implemented κ equals its first-principles definition exactly.

    For every non-degenerate edge of a sweep of price graphs, the code's
    ricci_curvature_edge must equal 1 − W₁/d recomputed independently (SciPy
    optimal transport + NetworkX geodesic). Agreement to float precision
    certifies the implementation IS Ollivier–Ricci, not merely a bounded proxy,
    and that the universal upper bound κ ≤ 1 holds.
    """
    n_graphs = 40
    length = 128
    delta = 0.01
    worst_identity_error = 0.0
    worst_upper = -np.inf
    edges_checked = 0
    for g in _price_graphs(seed=7, n_graphs=n_graphs, length=length, delta=delta):
        for u, v in g.edges():
            if u == v or not np.isfinite(nx.shortest_path_length(g, u, v, weight="weight")):
                continue
            d = float(nx.shortest_path_length(g, u, v, weight="weight"))
            if d <= 0.0:
                continue
            kappa_code = ricci_curvature_edge(g, int(u), int(v))
            kappa_indep, _ = _independent_curvature(g, int(u), int(v))
            worst_identity_error = max(worst_identity_error, abs(kappa_code - kappa_indep))
            worst_upper = max(worst_upper, kappa_code)
            edges_checked += 1
    assert edges_checked > 0, (
        "INV-RC1 identity witness degenerate: observed edges_checked = "
        f"{edges_checked} must be > 0 with seed=7 and delta={delta}; the fixture "
        "must yield at least one non-degenerate edge to verify κ = 1 − W₁/d"
    )
    assert worst_identity_error <= IDENTITY_TOLERANCE, (
        "INV-RC1 violated: observed worst identity error = "
        f"{worst_identity_error:.2e} must be ≤ {IDENTITY_TOLERANCE:.0e} over "
        f"edges_checked={edges_checked} with seed=7 and delta={delta}; the code's κ "
        "must equal 1 − W₁/d from independent SciPy/NetworkX recomputation"
    )
    assert worst_upper <= 1.0 + IDENTITY_TOLERANCE, (
        "INV-RC1 violated: observed max κ = "
        f"{worst_upper:.6f} must be ≤ 1 (tolerance {IDENTITY_TOLERANCE:.0e}) over "
        f"edges_checked={edges_checked} with seed=7 and delta={delta}; W₁ ≥ 0 ⇒ κ ≤ 1"
    )


@law("ricci.ollivier_bounds", n_graphs=40, length=128, delta=0.01)
def test_lower_bound_is_wasserstein_to_geodesic_ratio_condition() -> None:
    """INV-RC3: κ ≥ −1 is exactly the condition W₁/d ≤ 2, and it is conditional.

    Since κ = 1 − W₁/d, the lower bound κ ≥ −1 holds iff W₁/d ≤ 2. The witness
    certifies this equivalence edge-by-edge, then shows it is non-vacuous on
    build_price_graph: W₁ uses the positional (price-level) metric while d uses
    the |Δp|+1 weighted-graph metric, so the two are incommensurate and the ratio
    exceeds 2 on some edges — there κ < −1, so INV-RC3's [−1, 1] is not universal
    but conditional on the two metrics staying commensurate.
    """
    n_graphs = 40
    length = 128
    delta = 0.01
    equivalence_violations = 0
    edges_above_ratio = 0
    worst_low = np.inf
    edges_checked = 0
    for g in _price_graphs(seed=7, n_graphs=n_graphs, length=length, delta=delta):
        for u, v in g.edges():
            if u == v or not np.isfinite(nx.shortest_path_length(g, u, v, weight="weight")):
                continue
            d = float(nx.shortest_path_length(g, u, v, weight="weight"))
            if d <= 0.0:
                continue
            kappa = ricci_curvature_edge(g, int(u), int(v))
            _, ratio = _independent_curvature(g, int(u), int(v))
            below_bound = kappa < -1.0 - RATIO_EPS
            above_ratio = ratio > LOWER_BOUND_RATIO + RATIO_EPS
            if below_bound != above_ratio:
                equivalence_violations += 1
            if above_ratio:
                edges_above_ratio += 1
            worst_low = min(worst_low, kappa)
            edges_checked += 1
    assert edges_checked > 0, (
        "INV-RC3 boundary witness degenerate: observed edges_checked = "
        f"{edges_checked} must be > 0 with seed=7 and delta={delta}; the fixture "
        "must yield at least one non-degenerate edge to test the W₁/d ≤ 2 condition"
    )
    assert equivalence_violations == 0, (
        "INV-RC3 violated: observed equivalence_violations = "
        f"{equivalence_violations} must be 0 over edges_checked={edges_checked} with "
        f"seed=7 and delta={delta}; (κ < −1) and (W₁/d > 2) must agree edge-by-edge"
    )
    assert edges_above_ratio > 0, (
        "INV-RC3 boundary guard: observed edges_above_ratio = "
        f"{edges_above_ratio} must be > 0 over edges_checked={edges_checked} with "
        f"seed=7 and delta={delta} (worst κ = {worst_low:.3f}); the metric-mismatch "
        "boundary must be genuinely crossed, proving the [−1, 1] envelope is conditional"
    )
