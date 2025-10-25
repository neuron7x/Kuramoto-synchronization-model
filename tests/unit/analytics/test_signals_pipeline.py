"""Unit tests for analytics.signal pipelines and model selection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analytics.signals import (
    FeaturePipelineConfig,
    LeakageGate,
    SignalFeaturePipeline,
    SignalModelSelector,
    build_supervised_learning_frame,
    make_default_candidates,
)
from backtest.time_splits import WalkForwardSplitter


def _sample_market_frame(rows: int = 300) -> pd.DataFrame:
    index = pd.date_range("2023-01-01", periods=rows, freq="1h")
    rng = np.random.default_rng(42)
    price = 100 + np.cumsum(rng.normal(0, 0.5, size=rows))
    high = price + rng.normal(0.2, 0.1, size=rows)
    low = price - rng.normal(0.2, 0.1, size=rows)
    volume = rng.integers(1000, 5000, size=rows).astype(float)
    bid_volume = volume * rng.uniform(0.4, 0.6, size=rows)
    ask_volume = volume - bid_volume
    signed_volume = rng.normal(0, 1.0, size=rows) * volume * 0.01
    frame = pd.DataFrame(
        {
            "close": price,
            "high": high,
            "low": low,
            "volume": volume,
            "bid_volume": bid_volume,
            "ask_volume": ask_volume,
            "signed_volume": signed_volume,
        },
        index=index,
    )
    return frame


def test_feature_pipeline_generates_expected_columns() -> None:
    frame = _sample_market_frame(120)
    cfg = FeaturePipelineConfig(technical_windows=(5, 10), microstructure_window=20)
    pipeline = SignalFeaturePipeline(cfg)
    features = pipeline.transform(frame)
    expected = {
        "return_1",
        "sma_5",
        "sma_10",
        "ema_5",
        "ema_10",
        "volatility_5",
        "volatility_10",
        "rsi",
        "macd_ema_fast",
        "macd_ema_slow",
        "macd",
        "macd_signal",
        "macd_histogram",
        "price_range",
        "log_volume",
        "volume_z",
        "queue_imbalance",
        "kyles_lambda_20",
        "hasbrouck_20",
        "signed_volume_ema",
    }
    assert expected.issubset(features.columns)
    # MACD should now be available from the first observation
    assert not features["macd"].isna().iloc[0]
    assert not features["macd_signal"].isna().iloc[0]
    # ensure leakage control ready: there should be NaNs at start because of rolling windows
    assert features.isna().sum().max() > 0


def test_feature_pipeline_filters_invalid_rows() -> None:
    idx = pd.Index(
        [
            pd.Timestamp("2024-01-01 00:00:00"),
            pd.Timestamp("2024-01-01 01:00:00"),
            pd.Timestamp("2024-01-01 02:00:00"),
            pd.Timestamp("2024-01-01 00:00:00"),
            pd.Timestamp("2024-01-01 03:00:00"),
            pd.Timestamp("2024-01-01 04:00:00"),
        ]
    )
    frame = pd.DataFrame(
        {
            "close": [100.0, np.nan, 101.0, 102.0, 103.0, -1.0],
            "high": [100.5, 101.5, 101.5, 102.5, 103.5, 0.0],
            "low": [99.5, 100.5, 100.5, 101.5, 102.5, -2.0],
            "volume": [1_000.0, 1_100.0, "bad", 1_200.0, 1_300.0, 1_400.0],
        },
        index=idx,
    )

    pipeline = SignalFeaturePipeline(FeaturePipelineConfig(technical_windows=(2,)))
    features = pipeline.transform(frame)

    expected_index = pd.DatetimeIndex(
        [
            pd.Timestamp("2024-01-01 00:00:00"),
            pd.Timestamp("2024-01-01 02:00:00"),
            pd.Timestamp("2024-01-01 03:00:00"),
        ]
    )

    assert features.index.equals(expected_index)
    assert features.index.is_monotonic_increasing
    assert features.index.is_unique
    assert pd.isna(features.loc[pd.Timestamp("2024-01-01 02:00:00"), "log_volume"])


def test_feature_pipeline_float_precision_consistency() -> None:
    frame_64 = _sample_market_frame(160)
    frame_32 = frame_64.astype(np.float32)
    cfg = FeaturePipelineConfig(technical_windows=(5, 12), microstructure_window=30)
    pipeline = SignalFeaturePipeline(cfg)

    features_64 = pipeline.transform(frame_64)
    features_32 = pipeline.transform(frame_32)

    common_columns = [col for col in features_64.columns if col in features_32.columns]
    features_64 = features_64[common_columns]
    features_32 = features_32[common_columns]

    mask = features_64.notna() & features_32.notna()
    assert mask.to_numpy().any(), "There should be overlapping finite observations"

    stacked_64 = features_64.where(mask).stack()
    stacked_32 = features_32.where(mask).stack()
    np.testing.assert_allclose(
        stacked_64.values, stacked_32.values, rtol=5e-4, atol=1e-6
    )
    assert not np.isinf(
        features_32.to_numpy(dtype=float)
    ).any(), "No overflow should occur in float32 path"


def test_leakage_gate_alignment() -> None:
    frame = _sample_market_frame(60)
    pipeline = SignalFeaturePipeline(FeaturePipelineConfig(technical_windows=(3,)))
    features = pipeline.transform(frame)
    target = frame["close"].pct_change().shift(-1)
    gate = LeakageGate(lag=1, dropna=True)
    gated_features, gated_target = gate.apply(features, target)
    assert not gated_features.isna().any().any()
    assert len(gated_features) == len(gated_target)
    assert len(gated_features) > 0
    # the gating operation should discard at least the first `lag` observations
    assert all(idx >= features.index[gate.lag] for idx in gated_features.index)


def test_leakage_gate_special_value_handling() -> None:
    index = pd.RangeIndex(start=0, stop=3)
    features = pd.DataFrame(
        {
            "a": [1.0, np.inf, -np.inf],
            "b": [0.5, np.nan, 2.0],
        },
        index=index,
    )
    target = pd.Series([0.1, np.inf, -0.3], index=index)
    gate = LeakageGate(lag=0, dropna=False)

    cleaned_features, cleaned_target = gate.apply(features, target)

    assert np.isnan(cleaned_features.loc[1, "a"])
    assert np.isnan(cleaned_features.loc[2, "a"])
    assert np.isnan(cleaned_target.loc[1])
    assert cleaned_target.loc[2] == target.loc[2]


def test_model_selector_walk_forward_runs() -> None:
    frame = _sample_market_frame(220)
    cfg = replace(FeaturePipelineConfig(), technical_windows=(5, 10))
    features, target = build_supervised_learning_frame(
        frame, config=cfg, gate=LeakageGate(lag=0)
    )
    splitter = WalkForwardSplitter(train_window=100, test_window=40, freq="h")
    candidates = [c for c in make_default_candidates() if c.name == "ols"]
    selector = SignalModelSelector(splitter, candidates=candidates)
    evaluations = selector.evaluate(features, target)
    assert evaluations, "At least one evaluation should be produced"
    report = evaluations[0]
    assert "hit_rate" in report.aggregate_metrics
    assert "sharpe_ratio" in report.aggregate_metrics
    assert "total_pnl" in report.aggregate_metrics
    assert not report.regression_report.empty
    # Ensure regression report has the same number of rows as evaluated splits
    assert len(report.regression_report) == len(report.split_details)


@pytest.mark.parametrize(
    "window, expected_non_nan",
    [
        (1, 0),
        (5, 6),
        (10, 1),
        (50, 0),
    ],
)
def test_microstructure_window_edge_cases(window: int, expected_non_nan: int) -> None:
    frame = _sample_market_frame(10)
    cfg = FeaturePipelineConfig(technical_windows=(3,), microstructure_window=window)
    pipeline = SignalFeaturePipeline(cfg)
    features = pipeline.transform(frame)

    kyles_col = f"kyles_lambda_{window}"
    hasbrouck_col = f"hasbrouck_{window}"

    assert kyles_col in features
    assert hasbrouck_col in features

    assert features[kyles_col].notna().sum() == expected_non_nan
    assert features[hasbrouck_col].notna().sum() == expected_non_nan


def test_macd_signal_window_follows_configuration() -> None:
    frame = _sample_market_frame(200)
    default_pipeline = SignalFeaturePipeline(FeaturePipelineConfig())
    fast_signal_pipeline = SignalFeaturePipeline(FeaturePipelineConfig(macd_signal=5))

    default_features = default_pipeline.transform(frame)
    fast_signal_features = fast_signal_pipeline.transform(frame)

    assert "macd_signal" in default_features
    assert "macd_signal" in fast_signal_features

    mask = (
        default_features["macd_signal"].notna()
        & fast_signal_features["macd_signal"].notna()
    )
    assert mask.any(), "Both pipelines should produce overlapping finite observations"

    default_values = default_features.loc[mask, "macd_signal"].to_numpy()
    fast_values = fast_signal_features.loc[mask, "macd_signal"].to_numpy()

    assert not np.allclose(
        default_values, fast_values
    ), "Signal smoothing should depend on the configured window"


def test_macd_pipeline_matches_golden_baseline() -> None:
    """Ensure MACD-related features stay aligned with the golden baseline."""

    golden_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "golden"
        / "indicator_macd_baseline.csv"
    )
    golden_frame = pd.read_csv(golden_path, parse_dates=["ts"])
    golden_frame.set_index("ts", inplace=True)

    price_frame = pd.DataFrame(
        {"close": golden_frame["close"]}, index=golden_frame.index
    )

    pipeline = SignalFeaturePipeline(
        FeaturePipelineConfig(
            technical_windows=(), macd_fast=12, macd_slow=26, macd_signal=9
        )
    )
    features = pipeline.transform(price_frame)

    macd_columns = {
        "macd_ema_fast": "ema_12",
        "macd_ema_slow": "ema_26",
        "macd": "macd",
        "macd_signal": "signal",
        "macd_histogram": "histogram",
    }

    for feature_col, golden_col in macd_columns.items():
        assert feature_col in features, f"Missing feature column: {feature_col}"
        expected = golden_frame[golden_col].to_numpy(dtype=float)
        actual = features.loc[golden_frame.index, feature_col].to_numpy(dtype=float)
        np.testing.assert_allclose(
            actual,
            expected,
            rtol=2e-6,
            atol=5e-7,
            err_msg=f"Mismatch for {feature_col}",
        )


def test_feature_pipeline_handles_empty_frame() -> None:
    frame = pd.DataFrame(
        {
            "close": pd.Series(dtype=float),
            "high": pd.Series(dtype=float),
            "low": pd.Series(dtype=float),
            "volume": pd.Series(dtype=float),
            "bid_volume": pd.Series(dtype=float),
            "ask_volume": pd.Series(dtype=float),
            "signed_volume": pd.Series(dtype=float),
        }
    )
    pipeline = SignalFeaturePipeline(
        FeaturePipelineConfig(technical_windows=(3,), microstructure_window=4)
    )
    features = pipeline.transform(frame)

    assert features.empty
