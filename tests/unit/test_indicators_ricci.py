# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for Ollivier-Ricci curvature indicators.

This module tests the MeanRicciFeature class and related functions for computing
Ollivier-Ricci curvature on price graphs. MeanRicciFeature now supports optional
optimization parameters (use_float32, chunk_size) which are conditionally
included in metadata only when explicitly enabled.

Tests verify:
- Price graph construction is correct
- Ricci curvature calculations are within valid bounds
- Metadata contains required keys (delta, nodes, edges)
- Optional metadata fields appear only when parameters are enabled
- Performance optimizations preserve accuracy
"""

from __future__ import annotations

import asyncio
import math
from typing import Any

import numpy as np
import pytest

import core.indicators.ricci as ricci_module
from core.indicators.ricci import (
    MeanRicciFeature,
    build_price_graph,
    compute_node_distributions,
    local_distribution,
    mean_ricci,
    ricci_curvature_edge,
)


def test_build_price_graph_connects_consecutive_levels() -> None:
    prices = np.array([100, 101, 102, 103], dtype=float)
    graph = build_price_graph(prices, delta=0.01)
    assert graph.number_of_nodes() >= 3
    assert graph.number_of_edges() >= 2


def test_local_distribution_normalizes_probabilities() -> None:
    prices = np.array([100, 101, 101.5, 102], dtype=float)
    graph = build_price_graph(prices, delta=0.005)
    edges = list(graph.edges())
    assert edges, "Graph must have edges for distribution test"
    node = edges[0][0]
    probs = local_distribution(graph, node)
    assert abs(probs.sum() - 1.0) < 1e-9


def test_ricci_curvature_bounded_between_minus_one_and_one() -> None:
    # INV-RC3 (P1): the symmetric band κ ∈ [−1, 1] holds for build_price_graph
    # output specifically — its consecutive integer node IDs make the 1-D
    # positional embedding equal to the combinatorial distance.
    prices = np.array([100, 100.5, 101.0, 101.5, 102.0], dtype=float)
    graph = build_price_graph(prices, delta=0.005)
    edges = list(graph.edges())
    for u, v in edges:
        kappa = ricci_curvature_edge(graph, u, v)
        assert -1.0 <= kappa <= 1.0, f"Curvature {kappa} outside bounds"


def _build_cycle_graph(n: int) -> Any:
    """Build a non-price-graph topology: an n-node cycle with consecutive
    integer IDs and a wrap-around edge (n-1, 0).

    This is NOT build_price_graph output. The wrap-around edge connects two
    nodes that are graph-distance 1 apart but (n-1) apart in the default 1-D
    positional embedding (offset=0, scale=1), so its Wasserstein transport cost
    is large and κ descends below −1. This exercises the construction-conditional
    nature of the lower bound documented in INV-RC1 / INV-RC3.
    """
    graph = ricci_module.nx.Graph()
    for i in range(n):
        graph.add_edge(i, (i + 1) % n, weight=1.0)
    return graph


def test_ricci_universal_upper_bound_holds_on_non_price_topology() -> None:
    """INV-RC1 (P0, universal): κ ≤ 1 for every edge of every connected graph.

    The 12-node cycle is a deliberately non-price-graph topology whose
    wrap-around edge produces κ = −2 under the 1-D positional embedding. The
    universal upper bound κ ≤ 1 must still hold on every edge — it is a
    definitional consequence of κ = 1 − W₁/d with W₁ ≥ 0, independent of
    topology or walk laziness.
    """
    n_nodes = 12
    graph = _build_cycle_graph(n_nodes)
    edges = [(int(u), int(v)) for u, v in graph.edges()]
    assert len(edges) > 0, (
        f"INV-RC1 setup: cycle graph must have edges, observed n_edges=0 "
        f"must produce edges with n_nodes={n_nodes}"
    )
    kappas = [ricci_curvature_edge(graph, u, v) for u, v in edges]

    for (u, v), kappa in zip(edges, kappas):
        assert kappa <= 1.0 + 1e-9, (
            f"INV-RC1 VIOLATED: observed κ={kappa:.6f} > 1.0 on edge ({u},{v}) "
            f"of a non-price cycle graph; κ must not exceed the universal "
            f"upper bound 1.0. "
            f"κ = 1 − W₁/d and W₁ ≥ 0 always, so κ ≤ 1 is topology-independent "
            f"(no lazy-walk assumption). "
            f"with n_nodes={n_nodes}, n_edges={len(edges)}, min_kappa={min(kappas):.6f}"
        )


def test_ricci_lower_bound_band_conditional_on_price_graph() -> None:
    """INV-RC3 (P1): κ ∈ [−1, 1] holds for build_price_graph output but NOT
    necessarily for arbitrary topologies.

    (a) build_price_graph output satisfies the symmetric band [−1, 1].
    (b) A non-price-graph topology (12-node cycle) legitimately produces κ < −1
        under the 1-D positional embedding, so the lower bound −1 is
        construction-conditional and is NOT a universal invariant.
    """
    # (a) price-graph output: full symmetric band holds (INV-RC3).
    delta = 0.005
    prices = np.array([100.0, 100.5, 101.0, 101.5, 102.0], dtype=float)
    price_graph = build_price_graph(prices, delta=delta)
    price_edges = [(int(u), int(v)) for u, v in price_graph.edges()]
    assert len(price_edges) > 0, (
        f"INV-RC3 setup: build_price_graph must yield edges, observed n_edges=0 "
        f"must produce edges with delta={delta}"
    )
    for u, v in price_edges:
        kappa = ricci_curvature_edge(price_graph, u, v)
        assert -1.0 <= kappa <= 1.0 + 1e-9, (
            f"INV-RC3 VIOLATED: observed κ={kappa:.6f} outside [−1, 1] on edge "
            f"({u},{v}) of build_price_graph output; price-graph κ must stay in "
            f"the symmetric band. "
            f"Price graphs have consecutive integer node IDs, so the 1-D "
            f"positional embedding equals the combinatorial distance, giving "
            f"the tightened Ollivier band [−1, 1]. "
            f"with delta={delta}, n_edges={len(price_edges)}"
        )

    # (b) non-price topology: lower bound −1 is NOT universal.
    n_nodes = 12
    cycle = _build_cycle_graph(n_nodes)
    cycle_kappas = [
        ricci_curvature_edge(cycle, int(u), int(v)) for u, v in cycle.edges()
    ]
    min_kappa = min(cycle_kappas)
    assert min_kappa < -1.0, (
        f"INV-RC3 scope check: observed min_kappa={min_kappa:.6f} should be < -1.0 "
        f"on a non-price-graph topology to confirm the lower bound is "
        f"construction-conditional and NOT universal. "
        f"The symmetric band [−1, 1] is INV-RC3 (build_price_graph only); only "
        f"κ ≤ 1 (INV-RC1) is universal. "
        f"with n_nodes={n_nodes}, n_edges={len(cycle_kappas)}"
    )
    # And the universal upper bound still holds on this topology.
    max_kappa = max(cycle_kappas)
    assert max_kappa <= 1.0 + 1e-9, (
        f"INV-RC1 VIOLATED: observed max_kappa={max_kappa:.6f} > 1.0 on a "
        f"non-price cycle graph; κ ≤ 1 must hold regardless of topology. "
        f"κ = 1 − W₁/d and W₁ ≥ 0 always. "
        f"with n_nodes={n_nodes}, n_edges={len(cycle_kappas)}"
    )


def test_compute_node_distributions_matches_local_distribution() -> None:
    prices = np.array([101.0, 101.4, 101.8, 102.2, 102.4], dtype=float)
    graph = build_price_graph(prices, delta=0.01)
    distributions = compute_node_distributions(graph)

    for node, dist in distributions.items():
        local = local_distribution(graph, node)
        assert np.allclose(dist.probabilities, local)
        assert np.isfinite(dist.positions).all()


def test_ricci_curvature_edge_with_precomputed_distributions() -> None:
    prices = np.linspace(100.0, 102.0, 25)
    graph = build_price_graph(prices, delta=0.01)
    distributions = compute_node_distributions(graph)

    for u, v in graph.edges():
        direct = ricci_curvature_edge(graph, u, v)
        cached = ricci_curvature_edge(graph, u, v, distributions=distributions)
        assert np.isfinite(direct)
        assert cached == pytest.approx(direct, rel=1e-9, abs=1e-9)


def test_mean_ricci_feature_matches_function() -> None:
    """Test MeanRicciFeature with default parameters produces expected metadata."""
    prices = np.linspace(100.0, 105.0, 20)
    feature = MeanRicciFeature(delta=0.01)
    result = feature.transform(prices)
    graph = build_price_graph(prices, delta=0.01)
    assert result.name == "mean_ricci"
    # With default parameters, metadata should contain delta, nodes, edges only
    assert "delta" in result.metadata
    assert "nodes" in result.metadata
    assert "edges" in result.metadata
    assert result.metadata["nodes"] == graph.number_of_nodes()
    assert result.metadata["edges"] == graph.number_of_edges()
    # Optional flags should not be present with default settings
    assert "use_float32" not in result.metadata
    assert "chunk_size" not in result.metadata
    assert result.value == pytest.approx(mean_ricci(graph), rel=1e-9)


def test_mean_ricci_feature_metadata_contains_required_keys() -> None:
    """Test that MeanRicciFeature metadata always contains required keys."""
    prices = np.linspace(100.0, 105.0, 20)
    feature = MeanRicciFeature(delta=0.005)
    result = feature.transform(prices)

    # Required keys must always be present
    assert "delta" in result.metadata
    assert "nodes" in result.metadata
    assert "edges" in result.metadata
    assert result.metadata["delta"] == 0.005

    # With default settings, only required keys should be present
    assert set(result.metadata.keys()) == {"delta", "nodes", "edges"}


def test_mean_ricci_feature_with_float32_adds_metadata() -> None:
    """Test that use_float32 parameter adds metadata when enabled."""
    prices = np.linspace(100.0, 105.0, 20)
    feature = MeanRicciFeature(delta=0.01, use_float32=True)
    result = feature.transform(prices)

    # Required keys
    assert "delta" in result.metadata
    assert "nodes" in result.metadata
    assert "edges" in result.metadata

    # Optional optimization flag should be present when enabled
    assert "use_float32" in result.metadata
    assert result.metadata["use_float32"] is True

    # Verify computation still works correctly
    assert isinstance(result.value, float)
    assert np.isfinite(result.value)


def test_mean_ricci_feature_with_chunk_size_adds_metadata() -> None:
    """Test that chunk_size parameter adds metadata when enabled."""
    prices = np.linspace(100.0, 105.0, 30)
    feature = MeanRicciFeature(delta=0.01, chunk_size=10)
    result = feature.transform(prices)

    # Required keys
    assert "delta" in result.metadata
    assert "nodes" in result.metadata
    assert "edges" in result.metadata

    # Optional optimization flag should be present when enabled
    assert "chunk_size" in result.metadata
    assert result.metadata["chunk_size"] == 10

    # Verify computation still works correctly
    assert isinstance(result.value, float)
    assert np.isfinite(result.value)


def test_mean_ricci_feature_with_combined_optimizations() -> None:
    """Test MeanRicciFeature with both float32 and chunk_size enabled."""
    prices = np.linspace(100.0, 105.0, 30)
    feature = MeanRicciFeature(delta=0.01, use_float32=True, chunk_size=10)
    result = feature.transform(prices)

    # All keys should be present
    assert "delta" in result.metadata
    assert "nodes" in result.metadata
    assert "edges" in result.metadata
    assert "use_float32" in result.metadata
    assert "chunk_size" in result.metadata

    assert result.metadata["use_float32"] is True
    assert result.metadata["chunk_size"] == 10

    # Verify value is computed
    assert isinstance(result.value, float)
    assert np.isfinite(result.value)


def test_mean_ricci_feature_float32_preserves_accuracy() -> None:
    """Test that float32 optimization doesn't significantly change results."""
    prices = np.linspace(100.0, 105.0, 30)

    feature_64 = MeanRicciFeature(delta=0.01, use_float32=False)
    feature_32 = MeanRicciFeature(delta=0.01, use_float32=True)

    result_64 = feature_64.transform(prices)
    result_32 = feature_32.transform(prices)

    # Skip comparison if graph has no edges
    if result_64.metadata["edges"] == 0:
        pytest.skip("Graph has no edges")

    # Results should be close (allow reasonable tolerance for float32)
    assert (
        abs(result_64.value - result_32.value) < 0.5
    ), f"Float32 and float64 Ricci values differ too much: {result_64.value} vs {result_32.value}"


def test_mean_ricci_feature_chunk_size_behavior() -> None:
    """Test that chunk_size affects processing of graphs with many edges."""
    # Create data that produces a graph with many edges
    prices = np.linspace(100.0, 110.0, 50)

    feature_unchunked = MeanRicciFeature(delta=0.005)
    feature_chunked = MeanRicciFeature(delta=0.005, chunk_size=5)

    result_unchunked = feature_unchunked.transform(prices)
    result_chunked = feature_chunked.transform(prices)

    # Skip if graph has no edges
    if result_unchunked.metadata["edges"] == 0:
        pytest.skip("Graph has no edges")

    # Both should produce valid results
    assert np.isfinite(result_unchunked.value)
    assert np.isfinite(result_chunked.value)

    # Results should be identical (chunking doesn't change computation, just order)
    assert abs(result_unchunked.value - result_chunked.value) < 0.01

    # Metadata should reflect the difference
    assert "chunk_size" not in result_unchunked.metadata
    assert result_chunked.metadata["chunk_size"] == 5


def test_ricci_curvature_edge_warns_without_scipy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices = np.array([100.0, 100.5, 101.2, 100.9, 101.5], dtype=float)
    graph = build_price_graph(prices, delta=0.01)
    edges = [(u, v) for u, v in graph.edges() if u != v]
    assert edges, "Expected at least one non-loop edge in price graph"
    x, y = edges[0]

    distributions = compute_node_distributions(graph)
    dist_x = distributions[int(x)]
    dist_y = distributions[int(y)]
    d_xy = ricci_module._shortest_path_length_safe(graph, x, y)
    assert d_xy > 0
    expected_transport = ricci_module._w1_fallback(
        dist_x.positions,
        dist_x.probabilities,
        dist_y.positions,
        dist_y.probabilities,
    )
    expected_fallback = float(1.0 - expected_transport / d_xy)

    monkeypatch.setattr(ricci_module, "W1", None, raising=False)

    with pytest.warns(RuntimeWarning):
        curvature = ricci_curvature_edge(graph, x, y)

    assert curvature == pytest.approx(expected_fallback)


def test_w1_fallback_matches_known_transport_cost() -> None:
    positions = np.array([0.0, 1.0, 2.0])
    a = np.array([0.5, 0.5, 0.0])
    b = np.array([0.0, 0.5, 0.5])

    distance = ricci_module._w1_fallback(positions, a, positions, b)

    assert distance == pytest.approx(1.0)


def test_w1_fallback_sanitises_non_finite_mass() -> None:
    positions = np.array([0.0, 1.0, 2.0])
    a = np.array([np.nan, 1.0, -0.5])
    b = np.array([np.inf, 0.0, 0.5])

    distance = ricci_module._w1_fallback(positions, a, positions, b)

    assert distance == pytest.approx(1.0)


def test_w1_fallback_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError):
        ricci_module._w1_fallback(np.ones(2), np.ones(3), np.ones(2), np.ones(2))


def test_shortest_path_length_safe_falls_back_to_unweighted() -> None:
    class WeightedRaisesGraph:
        def __init__(self) -> None:
            self.calls: list[str | None] = []

        def shortest_path_length(
            self, source: int, target: int, weight: str | None = None
        ) -> float:
            self.calls.append(weight)
            if weight == "weight":
                raise ValueError("invalid weight data")
            if weight is None:
                return 3.0
            raise AssertionError("unexpected weight parameter")

    graph = WeightedRaisesGraph()
    distance = ricci_module._shortest_path_length_safe(graph, 1, 2)

    assert distance == pytest.approx(3.0)
    assert graph.calls == ["weight", None]


def test_shortest_path_length_safe_returns_inf_when_unweighted_fails() -> None:
    class AlwaysFailGraph:
        def shortest_path_length(
            self, source: int, target: int, weight: str | None = None
        ) -> float:
            if weight == "weight":
                raise ValueError("malformed weights")
            raise RuntimeError("graph disconnected")

    graph = AlwaysFailGraph()
    distance = ricci_module._shortest_path_length_safe(graph, 5, 7)

    assert math.isinf(distance)


def test_mean_ricci_async_is_loop_agnostic() -> None:
    """parallel='async' must match the serial path AND work inside an
    already-running event loop (Jupyter / FastAPI / Celery), with no leaked
    loop or unawaited coroutine.

    Regression guard: the prior asyncio-driver re-raised
    ``RuntimeError: asyncio.run() cannot be called from a running event loop``
    in any nested-loop runtime (its fallback matched the wrong error string and
    could not nest loops on one thread anyway). The thread-pool implementation
    is loop-agnostic, so both contexts return the identical curvature.
    """
    prices = np.array([100.0, 101.0, 102.5, 101.8], dtype=float)
    graph = build_price_graph(prices, delta=0.01)
    baseline = mean_ricci(graph)

    # 1) Plain (no running loop) context.
    assert mean_ricci(graph, parallel="async", max_workers=2) == pytest.approx(baseline)

    # 2) Nested running-loop context — this is what previously raised.
    async def _nested() -> float:
        return mean_ricci(graph, parallel="async", max_workers=2)

    assert asyncio.run(_nested()) == pytest.approx(baseline)

    # The async path must not leave a running loop bound to this thread.
    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()


def test_mean_ricci_async_preserves_edge_order_and_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The thread pool yields results in edge order, so the async mean equals
    the serial mean deterministically regardless of worker scheduling."""
    prices = np.linspace(100.0, 110.0, 24)
    graph = build_price_graph(prices, delta=0.01)
    serial = mean_ricci(graph, parallel="none")

    captured: list[float] = []
    real_runner = ricci_module._run_ricci_async

    def spy(graph_arg, edges, workers, distributions):
        result = real_runner(graph_arg, edges, workers, distributions)
        captured.extend(result)
        return result

    monkeypatch.setattr(ricci_module, "_run_ricci_async", spy)
    async_value = mean_ricci(graph, parallel="async", max_workers=4)

    assert async_value == pytest.approx(serial)
    serial_edge_values = [
        ricci_module.ricci_curvature_edge(graph, int(u), int(v)) for u, v in graph.edges()
    ]
    assert captured == pytest.approx(serial_edge_values)


def test_w1_fallback_emits_runtime_warning() -> None:
    """TD-017: the SciPy-unavailable Wasserstein fallback degrades loudly — it emits
    a RuntimeWarning so the degraded-accuracy path is observable, not silent."""
    # pytest.warns installs an "always" filter, which _maybe_warn_w1 honours via
    # _is_runtime_warning_forced regardless of whether SciPy is actually present.
    with pytest.warns(RuntimeWarning, match="SciPy unavailable"):
        ricci_module._maybe_warn_w1()
