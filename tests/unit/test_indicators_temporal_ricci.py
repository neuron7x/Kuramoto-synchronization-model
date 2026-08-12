# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.indicators.temporal_ricci import (
    LightGraph,
    PriceLevelGraph,
    PriceLevelGraphBuilder,
    TemporalRicciAnalyzer,
)


def _synthetic_series(length: int, volatility: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    increments = rng.normal(0.0, volatility, length)
    return np.cumsum(increments) + 100.0


def test_light_graph_caches_edges_and_reports_connectivity() -> None:
    graph = LightGraph(4)

    graph.add_edge(0, 1, weight=0.5)
    graph.add_edge(1, 2, weight=1.0)
    graph.add_edge(2, 3, weight=1.5)

    cached_once = set(graph.edges())
    cached_twice = set(graph.edges())

    assert cached_once == {(0, 1), (1, 2), (2, 3)}
    assert cached_twice == cached_once
    assert graph.number_of_nodes() == 4
    assert graph.number_of_edges() == 3
    assert graph.is_connected()
    assert graph.shortest_path_length(0, 3) == 3


def test_price_level_graph_build_respects_level_bounds() -> None:
    prices = np.array([100.0, 101.5, 102.0, 101.0, 103.0])
    volumes = np.array([10.0, 12.0, 18.0, 20.0, 22.0])

    builder = PriceLevelGraph(n_levels=5, connection_threshold=0.0)
    graph = builder.build(prices, volumes)

    assert graph.number_of_nodes() == 5
    assert graph.number_of_edges() >= 3
    assert all(0 <= node < builder.n_levels for edge in graph.edges() for node in edge)


def test_price_level_graph_builder_creates_edges_based_on_threshold() -> None:
    prices = np.linspace(100.0, 104.0, 24)
    volumes = np.ones(prices.size - 1)
    builder = PriceLevelGraphBuilder(n_levels=6, connection_threshold=0.05)
    graph = builder.build(prices, volumes)
    assert graph.number_of_nodes() == 6
    assert graph.number_of_edges() > 0


def test_price_level_graph_builder_validates_volume_length() -> None:
    prices = np.linspace(100.0, 101.0, 10)
    builder = PriceLevelGraphBuilder(n_levels=4)

    with pytest.raises(ValueError):
        builder.build(prices, np.ones(prices.size - 3))


def test_temporal_ricci_analyzer_reports_metrics() -> None:
    prices = np.concatenate(
        [
            _synthetic_series(120, 0.05, seed=1),
            _synthetic_series(120, 0.25, seed=2),
        ]
    )
    volumes = np.abs(np.sin(np.linspace(0, 4 * np.pi, prices.size - 1))) + 0.1
    dates = pd.date_range("2024-01-01", periods=prices.size, freq="1min")
    df = pd.DataFrame({"close": prices, "volume": np.append(volumes, volumes[-1])}, index=dates)

    analyzer = TemporalRicciAnalyzer(window_size=32, n_snapshots=5, n_levels=8)
    result = analyzer.analyze(df)

    assert result.graph_snapshots
    assert result.temporal_curvature <= 0.0
    assert 0.0 <= result.topological_transition_score <= 1.0
    assert 0.0 <= result.structural_stability <= 1.0
    assert 0.0 <= result.edge_persistence <= 1.0


def test_temporal_ricci_analyzer_handles_small_dataset() -> None:
    prices = np.linspace(100.0, 101.0, 24)
    dates = pd.date_range("2024-01-01", periods=prices.size, freq="1min")
    df = pd.DataFrame({"close": prices}, index=dates)

    analyzer = TemporalRicciAnalyzer(window_size=40, n_snapshots=4, n_levels=6)
    outcome = analyzer.analyze(df)

    assert outcome.graph_snapshots == []
    assert outcome.temporal_curvature == 0.0
    assert outcome.topological_transition_score == 0.0
    assert outcome.structural_stability == 1.0
    assert outcome.edge_persistence == 1.0


def test_temporal_ricci_analyzer_requires_close_column_and_non_empty_df() -> None:
    analyzer = TemporalRicciAnalyzer()
    dates = pd.date_range("2024-01-01", periods=4, freq="1min")
    df_missing = pd.DataFrame({"price": np.linspace(100.0, 101.0, 4)}, index=dates)

    with pytest.raises(ValueError):
        analyzer.analyze(df_missing)

    empty_df = pd.DataFrame({"close": []}, index=pd.DatetimeIndex([], name="ts"))

    with pytest.raises(ValueError):
        analyzer.analyze(empty_df)


def test_temporal_transition_score_reacts_to_regime_change() -> None:
    steady_prices = _synthetic_series(160, 0.05, seed=11)
    volatile_prices = np.concatenate(
        [
            _synthetic_series(80, 0.05, seed=21),
            _synthetic_series(80, 0.35, seed=22),
        ]
    )

    dates = pd.date_range("2024-01-01", periods=steady_prices.size, freq="1min")
    steady_df = pd.DataFrame({"close": steady_prices}, index=dates)

    dates_vol = pd.date_range("2024-01-01", periods=volatile_prices.size, freq="1min")
    volatile_df = pd.DataFrame({"close": volatile_prices}, index=dates_vol)

    # Use separate analyzers to avoid non-monotonic timestamp warning
    # (both DataFrames start from 2024-01-01, so reusing one analyzer
    # triggers a legitimate reset-on-overlap warning).
    steady_analyzer = TemporalRicciAnalyzer(window_size=48, n_snapshots=4, n_levels=8)
    volatile_analyzer = TemporalRicciAnalyzer(window_size=48, n_snapshots=4, n_levels=8)

    steady_result = steady_analyzer.analyze(steady_df)
    volatile_result = volatile_analyzer.analyze(volatile_df)

    assert (
        volatile_result.topological_transition_score >= steady_result.topological_transition_score
    )


def test_temporal_ricci_analyzer_resets_on_non_monotonic_index() -> None:
    analyzer = TemporalRicciAnalyzer(window_size=24, n_snapshots=3, retain_history=True)
    first = pd.DataFrame(
        {
            "close": np.linspace(100.0, 102.0, 48),
            "volume": np.linspace(10.0, 15.0, 48),
        },
        index=pd.date_range("2024-01-01", periods=48, freq="1min"),
    )
    analyzer.analyze(first)

    later = pd.DataFrame(
        {
            "close": np.linspace(101.0, 103.0, 48),
            "volume": np.linspace(12.0, 18.0, 48),
        },
        index=pd.date_range("2023-12-31", periods=48, freq="1min"),
    )

    with pytest.warns(RuntimeWarning, match="non-monotonic"):
        result = analyzer.analyze(later)

    assert result.graph_snapshots
    assert result.graph_snapshots[0].timestamp >= later.index[0]
