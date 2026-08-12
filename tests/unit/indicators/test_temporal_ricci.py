# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest

from core.indicators.temporal_ricci import (
    LightGraph,
    PriceLevelGraph,
    TemporalRicciAnalyzer,
)


class TestLightGraph:
    def test_add_edges_and_connectivity(self) -> None:
        graph = LightGraph(4)

        graph.add_edge(0, 1, weight=0.5)
        graph.add_edge(1, 2, weight=1.2)
        graph.add_edge(2, 3, weight=0.8)

        # Cached edge list should be stable across calls.
        first_edges = set(graph.edges())
        second_edges = set(graph.edges())

        assert first_edges == {(0, 1), (1, 2), (2, 3)}
        assert second_edges == first_edges
        assert graph.number_of_nodes() == 4
        assert graph.number_of_edges() == 3
        assert set(graph.neighbors(1)) == {0, 2}
        assert graph.shortest_path_length(0, 3) == 3
        assert graph.is_connected()

    def test_edge_count_and_cache_avoid_rebuild(self) -> None:
        """TD-005: the graph utilities are cached, not recomputed per call.

        ``number_of_edges`` must be O(1) off the running ``_edge_count`` without
        materialising the edge list, and ``edges()`` must build its cache exactly
        once and invalidate it only when the topology changes. This pins the
        optimisation invariant deterministically — no wall-clock flake."""
        graph = LightGraph(64)
        for i in range(63):
            graph.add_edge(i, i + 1, weight=1.0)

        # Counting never materialises the edge-list cache.
        assert graph.number_of_edges() == 63
        assert graph._edges_cache is None

        # First edges() builds the cache; second call reuses the same backing list.
        first = graph.edges()
        assert graph._edges_cache is not None
        backing_after_first = graph._edges_cache
        second = graph.edges()
        assert graph._edges_cache is backing_after_first  # not rebuilt
        assert first == second

        # A topology change invalidates the cache (and only then).
        graph.add_edge(0, 5, weight=1.0)
        assert graph._edges_cache is None
        assert graph.number_of_edges() == 64


class TestPriceLevelGraph:
    def test_build_graph_with_volume_weights(self) -> None:
        prices = np.array([100.0, 101.5, 102.0, 101.0, 103.0])
        volumes = np.array([10.0, 15.0, 20.0, 25.0, 30.0])

        builder = PriceLevelGraph(n_levels=5, connection_threshold=0.0)
        graph = builder.build(prices, volumes)

        # Transitions should create a connected path between multiple levels.
        assert graph.number_of_nodes() == 5
        assert graph.number_of_edges() >= 3
        for start, end in graph.edges():
            assert start != end
            assert start < builder.n_levels
            assert end < builder.n_levels

    def test_volume_length_mismatch_raises(self) -> None:
        prices = np.array([100.0, 101.0, 102.0])
        volumes = np.array([1.0])

        builder = PriceLevelGraph(n_levels=3)

        with pytest.raises(ValueError, match="volumes length must match"):
            builder.build(prices, volumes)


class TestTemporalRicciAnalyzer:
    def _build_dataframe(self, start: str, periods: int, freq: str = "1min") -> pd.DataFrame:
        index = pd.date_range(start=start, periods=periods, freq=freq)
        prices = np.linspace(100.0, 110.0, periods)
        volumes = np.linspace(5.0, 50.0, periods)
        return pd.DataFrame({"close": prices, "volume": volumes}, index=index)

    def test_analyze_returns_metrics_with_history(self) -> None:
        analyzer = TemporalRicciAnalyzer(window_size=10, n_snapshots=3, retain_history=True)
        df = self._build_dataframe("2024-01-01", periods=40)

        result = analyzer.analyze(df)

        assert 0.0 <= result.structural_stability <= 1.0
        assert 0.0 <= result.edge_persistence <= 1.0
        assert len(result.graph_snapshots) <= analyzer.n_snapshots
        assert result.topological_transition_score >= 0.0
        assert isinstance(result.temporal_curvature, float)

    def test_analyze_insufficient_data_returns_neutral_metrics(self) -> None:
        analyzer = TemporalRicciAnalyzer(window_size=20, n_snapshots=5)
        df = self._build_dataframe("2024-01-01", periods=5)

        result = analyzer.analyze(df)

        assert result.temporal_curvature == 0.0
        assert result.topological_transition_score == 0.0
        assert result.structural_stability == 1.0
        assert result.edge_persistence == 1.0
        assert result.graph_snapshots == []

    def test_non_monotonic_timestamps_reset_history(self) -> None:
        analyzer = TemporalRicciAnalyzer(window_size=5, n_snapshots=2, retain_history=True)
        first = self._build_dataframe("2024-01-01", periods=10)
        analyzer.analyze(first)

        # Provide a frame that starts before the previous snapshot timestamp.
        later = self._build_dataframe("2023-12-31", periods=10)

        with pytest.warns(RuntimeWarning, match="non-monotonic"):
            result = analyzer.analyze(later)

        assert len(result.graph_snapshots) > 0
        assert result.graph_snapshots[0].timestamp >= later.index[0] + timedelta(minutes=4)
