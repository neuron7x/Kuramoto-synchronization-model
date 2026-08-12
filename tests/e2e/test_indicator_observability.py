# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.indicators.kuramoto import compute_phase
from core.indicators.temporal_ricci import TemporalRicciAnalyzer
from core.indicators.trading import KuramotoIndicator, VPINIndicator
from core.utils import metrics as metrics_module


@pytest.mark.slow
def test_indicator_observability_pipeline() -> None:
    """Run key indicators end-to-end and assert observability wiring."""

    prometheus = pytest.importorskip("prometheus_client")
    registry = prometheus.CollectorRegistry()

    # Reset collector to ensure a fresh registry for the test run.
    metrics_module._collector = None  # type: ignore[attr-defined]
    collector = metrics_module.get_metrics_collector(registry)

    # Ensure indicator modules reuse the fresh collector.
    from core.indicators import kuramoto as kuramoto_module  # noqa: WPS433
    from core.indicators import temporal_ricci as ricci_module  # noqa: WPS433
    from core.indicators import trading as trading_module  # noqa: WPS433

    trading_module._metrics = collector  # type: ignore[attr-defined]
    kuramoto_module._metrics = collector  # type: ignore[attr-defined]
    ricci_module._metrics = collector  # type: ignore[attr-defined]

    csv_path = Path(__file__).resolve().parents[2] / "data" / "sample.csv"
    df = pd.read_csv(csv_path)
    df["timestamp"] = pd.to_datetime(df["ts"], unit="s")
    df = df.set_index("timestamp")

    prices = df["price"].astype(float).to_numpy()
    volumes = df["volume"].astype(float).to_numpy()

    raw_indicator = KuramotoIndicator(
        window=32,
        coupling=1.1,
        min_samples=6,
        volume_weighting="sqrt",
        smoothing=0.0,
    )
    raw_values = raw_indicator.compute(prices, volumes=volumes)

    smoothed_indicator = KuramotoIndicator(
        window=32,
        coupling=1.1,
        min_samples=6,
        volume_weighting="sqrt",
        smoothing=0.2,
    )
    kuramoto_values = smoothed_indicator.compute(prices, volumes=volumes)

    assert kuramoto_values.shape == prices.shape
    assert np.all((kuramoto_values >= 0.0) & (kuramoto_values <= 1.0))
    assert np.count_nonzero(kuramoto_values) > 0

    phases = compute_phase(prices)
    window_slice = phases[-smoothed_indicator.window :]
    weight_slice = np.sqrt(np.clip(volumes[-smoothed_indicator.window :], 0.0, None))
    manual_total = np.sum(np.exp(1j * window_slice) * weight_slice)
    manual_order = np.abs(manual_total) / np.sum(weight_slice)
    expected_raw = float(np.clip(1.1 * manual_order, 0.0, 1.0))
    assert raw_values[-1] == pytest.approx(expected_raw, rel=1e-6, abs=1e-6)

    analyzer = TemporalRicciAnalyzer(
        window_size=64,
        n_snapshots=6,
        n_levels=12,
        volume_mode="sqrt",
        volume_floor=1.0,
        shock_sensitivity=6.0,
        transition_midpoint=0.12,
        curvature_ema_alpha=0.3,
    )

    analysis_frame = df.tail(160)[["price", "volume"]].rename(columns={"price": "close"})
    result = analyzer.analyze(
        analysis_frame, price_col="close", volume_col="volume", reset_history=True
    )

    assert np.isfinite(result.temporal_curvature)
    assert -1.0 <= result.temporal_curvature <= 1.0
    assert 0.0 <= result.topological_transition_score <= 1.0
    assert 0.0 <= result.structural_stability <= 1.0
    assert 0.0 <= result.edge_persistence <= 1.0
    assert len(result.graph_snapshots) <= analyzer.n_snapshots

    oscillation = 0.55 + 0.05 * np.sin(np.linspace(0.0, 2 * np.pi, volumes.size))
    buy_flow = np.clip(volumes * oscillation, 0.0, None)
    sell_flow = np.clip(volumes - buy_flow, 0.0, None)
    volume_data = np.column_stack([volumes, buy_flow, sell_flow])

    vpin = VPINIndicator(
        bucket_size=24,
        threshold=0.8,
        smoothing=0.25,
        min_volume=1e-6,
        use_signed_imbalance=True,
    )
    vpin_values = vpin.compute(volume_data)

    assert vpin_values.shape == volumes.shape
    assert np.all(np.abs(vpin_values) <= 1.0)
    assert np.count_nonzero(vpin_values) > 0

    if collector.enabled:
        total_kuramoto = registry.get_sample_value(
            "geosync_indicator_compute_total",
            {"indicator_name": "kuramoto_indicator", "status": "success"},
        )
        assert total_kuramoto is not None and total_kuramoto >= 2.0

        kuramoto_gauge = registry.get_sample_value(
            "geosync_indicator_value", {"indicator_name": "kuramoto_indicator"}
        )
        assert kuramoto_gauge == pytest.approx(kuramoto_values[-1])

        kuramoto_samples = registry.get_sample_value(
            "geosync_indicator_sample_size",
            {"indicator_name": "kuramoto_indicator"},
        )
        assert kuramoto_samples == pytest.approx(float(prices.size))

        kuramoto_window = registry.get_sample_value(
            "geosync_indicator_window_size",
            {"indicator_name": "kuramoto_indicator"},
        )
        assert kuramoto_window == pytest.approx(float(smoothed_indicator.window))

        kuramoto_finite = registry.get_sample_value(
            "geosync_indicator_quality_ratio",
            {"indicator_name": "kuramoto_indicator", "metric": "input_finite"},
        )
        assert kuramoto_finite is not None and 0.99 <= kuramoto_finite <= 1.0

        kuramoto_valid = registry.get_sample_value(
            "geosync_indicator_quality_ratio",
            {"indicator_name": "kuramoto_indicator", "metric": "valid_windows"},
        )
        assert kuramoto_valid is not None and 0.2 <= kuramoto_valid <= 1.0

        kuramoto_weight = registry.get_sample_value(
            "geosync_indicator_quality_ratio",
            {"indicator_name": "kuramoto_indicator", "metric": "weight_positive"},
        )
        assert kuramoto_weight is not None and 0.9 <= kuramoto_weight <= 1.0

        temporal_total = registry.get_sample_value(
            "geosync_indicator_compute_total",
            {"indicator_name": "temporal_ricci", "status": "success"},
        )
        assert temporal_total == pytest.approx(1.0)

        transition_gauge = registry.get_sample_value(
            "geosync_indicator_value",
            {"indicator_name": "temporal_ricci.transition_score"},
        )
        assert transition_gauge == pytest.approx(result.topological_transition_score)

        curvature_gauge = registry.get_sample_value(
            "geosync_indicator_value",
            {"indicator_name": "temporal_ricci.avg_curvature"},
        )
        assert curvature_gauge is not None

        temporal_samples = registry.get_sample_value(
            "geosync_indicator_sample_size",
            {"indicator_name": "temporal_ricci"},
        )
        assert temporal_samples == pytest.approx(float(len(analysis_frame)))

        temporal_window = registry.get_sample_value(
            "geosync_indicator_window_size",
            {"indicator_name": "temporal_ricci"},
        )
        assert temporal_window == pytest.approx(float(analyzer.window_size))

        temporal_coverage = registry.get_sample_value(
            "geosync_indicator_quality_ratio",
            {"indicator_name": "temporal_ricci", "metric": "snapshot_coverage"},
        )
        assert temporal_coverage is not None and 0.5 <= temporal_coverage <= 1.0

        temporal_volume = registry.get_sample_value(
            "geosync_indicator_quality_ratio",
            {"indicator_name": "temporal_ricci", "metric": "volume_coverage"},
        )
        assert temporal_volume is not None and 0.5 <= temporal_volume <= 1.0

        vpin_total = registry.get_sample_value(
            "geosync_indicator_compute_total",
            {"indicator_name": "vpin_indicator", "status": "success"},
        )
        assert vpin_total == pytest.approx(1.0)

        vpin_gauge = registry.get_sample_value(
            "geosync_indicator_value", {"indicator_name": "vpin_indicator"}
        )
        assert vpin_gauge == pytest.approx(vpin_values[-1])

        vpin_samples = registry.get_sample_value(
            "geosync_indicator_sample_size",
            {"indicator_name": "vpin_indicator"},
        )
        assert vpin_samples == pytest.approx(float(volume_data.shape[0]))

        vpin_window = registry.get_sample_value(
            "geosync_indicator_window_size",
            {"indicator_name": "vpin_indicator"},
        )
        assert vpin_window == pytest.approx(float(vpin.bucket_size))

        vpin_finite = registry.get_sample_value(
            "geosync_indicator_quality_ratio",
            {"indicator_name": "vpin_indicator", "metric": "input_finite"},
        )
        assert vpin_finite is not None and 0.95 <= vpin_finite <= 1.0

        vpin_valid = registry.get_sample_value(
            "geosync_indicator_quality_ratio",
            {"indicator_name": "vpin_indicator", "metric": "valid_windows"},
        )
        assert vpin_valid is not None and 0.2 <= vpin_valid <= 1.0

        vpin_positive = registry.get_sample_value(
            "geosync_indicator_quality_ratio",
            {"indicator_name": "vpin_indicator", "metric": "positive_volume"},
        )
        assert vpin_positive is not None and 0.5 <= vpin_positive <= 1.0
