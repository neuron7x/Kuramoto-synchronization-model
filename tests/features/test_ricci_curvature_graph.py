# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Dedicated deterministic claim-lock for the correlation-graph Ricci adapter.

Claim → source → test → command → failure-mode binding for
``src/geosync/features/ricci.py::RicciCurvatureGraph``:

    command: pytest -q tests/features/test_ricci_curvature_graph.py

Boundary: this adapter computes Ollivier-Ricci curvature on a **cross-asset
return-correlation graph**. It is NOT L2 order-book microstructure Ricci, NOT a
predictor, NOT evidence-bearing market physics. The L2 microstructure line stays
at ``HYPOTHESIS`` until a real depth-5 session with a real data hash, baseline,
falsifier and replay path is committed.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Load the module by file path to avoid importing the geosync package __init__.
_SPEC = importlib.util.spec_from_file_location(
    "ricci_adapter_under_test",
    Path(__file__).resolve().parents[2] / "src/geosync/features/ricci.py",
)
assert _SPEC is not None and _SPEC.loader is not None
_ricci = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_ricci)
RicciCurvatureGraph = _ricci.RicciCurvatureGraph


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2024-01-01", periods=n, freq="1h")


def test_insufficient_window_fails_closed() -> None:
    """Fewer rows than the window → ValueError, never a partial/silent result."""
    returns = pd.DataFrame(
        {"a": np.arange(10) * 0.01, "b": np.arange(10) * 0.01},
        index=_dates(10),
    )
    detector = RicciCurvatureGraph(window=30)
    with pytest.raises(ValueError, match="Insufficient data"):
        detector.fit_transform(returns)


def test_zero_edge_returns_neutral_curvature() -> None:
    """No correlation clears the threshold → edgeless graph → neutral output.

    Pins the ``G.number_of_edges() == 0`` branch: kappa_min == 0.0 and
    edge_kappa == {}, never a fabricated curvature. Deterministic via an
    impossibly-high threshold over seeded independent series.
    """
    rng = np.random.default_rng(0)
    returns = pd.DataFrame(
        {f"a{i}": rng.standard_normal(40) * 0.01 for i in range(3)},
        index=_dates(40),
    )
    result = RicciCurvatureGraph(window=30, correlation_threshold=0.99).fit_transform(returns)
    assert result["edge_kappa"] == {}
    assert result["kappa_min"] == 0.0


def test_fixed_single_edge_curvature_is_half() -> None:
    """Two perfectly-correlated assets → one edge → kappa == 0.5 exactly.

    Deterministic small-graph pin of the Ollivier-Ricci adapter at alpha=0.5:
    for a 2-node single-edge graph the simplified Wasserstein transport gives
    W = 0.5 over unit edge distance, so kappa = 1 - 0.5 = 0.5, independent of
    the (correlation) edge weight.
    """
    base = np.linspace(-1.0, 1.0, 40)
    returns = pd.DataFrame(
        {"a": base * 0.01, "b": base * 0.02},  # b == 2a -> corr == 1.0
        index=_dates(40),
    )
    result = RicciCurvatureGraph(
        window=30, correlation_threshold=0.3, alpha=0.5
    ).fit_transform(returns)
    assert len(result["edge_kappa"]) == 1
    assert result["kappa_min"] == pytest.approx(0.5, abs=1e-12)


def test_star_edge_curvature_uses_per_node_neighbor_mass() -> None:
    """Regression: μ_v must be normalized by v's OWN degree, not u's.

    Star graph, center (deg 4) -- leaf (deg 1), alpha=0.5. The transported
    measure μ_v is uniform over v's neighbors and must sum to 1. The prior
    defect reused the center's neighbor mass (1-alpha)/deg(u)=0.125 for the
    leaf's measure, so μ_v summed to only 0.625, inflating the Wasserstein
    transport and returning kappa=0.3125. With per-node mass the leaf measure
    sums to 1 (self 0.5, center 0.5) and the correct curvature is:

        W = 0.875 over unit edge distance  ->  kappa = 1 - 0.875 = 0.125

    Symmetric by construction: kappa(center,leaf) == kappa(leaf,center).
    """
    nx = pytest.importorskip("networkx")
    graph = nx.star_graph(4)  # node 0 = center (deg 4), nodes 1..4 = leaves
    detector = RicciCurvatureGraph(alpha=0.5)
    shortest_paths = dict(nx.all_pairs_shortest_path_length(graph))

    kappa_cl = detector._edge_curvature(graph, 0, 1, shortest_paths)
    kappa_lc = detector._edge_curvature(graph, 1, 0, shortest_paths)

    assert kappa_cl == pytest.approx(0.125, abs=1e-12)
    assert kappa_lc == pytest.approx(0.125, abs=1e-12)


def test_non_finite_input_excluded_no_phantom_edges() -> None:
    """NaN/inf columns are excluded, never crashing or fabricating an edge.

    A constant-inf column and a column with a NaN yield NaN correlations
    (``abs(NaN) >= threshold`` is False), so they cannot enter the graph. The
    failure mode is pinned: non-finite input is handled by exclusion and the
    result stays finite.
    """
    rng = np.random.default_rng(1)
    returns = pd.DataFrame(
        {
            "ok_a": rng.standard_normal(40) * 0.01,
            "ok_b": rng.standard_normal(40) * 0.01,
            "nan_col": np.concatenate([[np.nan], rng.standard_normal(39) * 0.01]),
            "inf_col": np.full(40, np.inf),
        },
        index=_dates(40),
    )
    result = RicciCurvatureGraph(window=30, correlation_threshold=0.3).fit_transform(returns)
    for u, v in result["edge_kappa"]:
        assert u not in {"nan_col", "inf_col"}
        assert v not in {"nan_col", "inf_col"}
    assert all(np.isfinite(k) for k in result["edge_kappa"].values())
    assert np.isfinite(result["kappa_min"])


def test_correlation_graph_claim_is_not_l2_microstructure() -> None:
    """Boundary lock: the public result carries no L2/microstructure/predictive
    field. The adapter is a correlation-graph descriptor only."""
    base = np.linspace(-1.0, 1.0, 40)
    returns = pd.DataFrame(
        {"a": base * 0.01, "b": base * 0.02}, index=_dates(40)
    )
    result = RicciCurvatureGraph(window=30, correlation_threshold=0.3).fit_transform(returns)
    assert set(result.keys()) == {"kappa_min", "edge_kappa"}
    forbidden = {"l2", "microstructure", "order_book", "predictive", "alpha", "signal"}
    assert not (set(result.keys()) & forbidden)
