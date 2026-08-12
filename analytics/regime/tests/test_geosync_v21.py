# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from typing import Iterable

import numpy as np
import pandas as pd
import pytest

from analytics.regime.src.core import geosync_v21 as v21
from analytics.regime.src.core.geosync_v21 import (
    BacktestConfig,
    EnsembleConfig,
    FeatureBuilderConfig,
    GeoSyncV21Pipeline,
    LogisticIsotonicTrainer,
    ModelTrainingConfig,
    ProbabilityBacktester,
    RegimeHMMAdapter,
    RegimeHMMConfig,
    StrictCausalFeatureBuilder,
    result_to_json,
)


def _synth_returns(rows: int = 320, cols: int = 3, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=rows, freq="D")
    returns = rng.normal(0.0, 0.01, size=(rows, cols))
    return pd.DataFrame(returns, index=index, columns=[f"asset_{i}" for i in range(cols)])


def _structured_returns(rows: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    half = rows // 2
    noisy = rng.normal(0.0, 0.02, size=(half, 3))
    driver = rng.normal(0.0, 0.01, size=(rows - half,))
    in_phase = np.column_stack(
        [driver + rng.normal(0.0, 0.001, size=rows - half) for _ in range(3)]
    )
    data = np.vstack([noisy, in_phase])
    index = pd.date_range("2024-05-01", periods=rows, freq="D")
    return pd.DataFrame(data, index=index, columns=["a", "b", "c"])


def _count_flags(labels: Iterable[int]) -> int:
    return int(np.sum(np.asarray(list(labels)) == 1))


def test_feature_builder_strict_alignment() -> None:
    returns = _structured_returns()
    cfg = FeatureBuilderConfig(window=30, horizon=5, label_threshold=-0.0005)
    builder = StrictCausalFeatureBuilder(cfg)

    features = builder.build(returns)

    expected_length = len(returns) - cfg.window - cfg.horizon
    assert len(features.features) == expected_length
    assert features.features.index[0] == returns.index[cfg.window]
    assert features.features.index[-1] == returns.index[-cfg.horizon - 1]
    assert set(features.features.columns) == {
        "dr",
        "ricci_mean",
        "topo_intensity",
        "causal_strength",
    }
    assert features.labels.shape == (expected_length,)
    assert set(np.unique(features.labels)) <= {0, 1}
    assert _count_flags(features.labels) > 0


def test_feature_builder_rejects_empty_dataframe() -> None:
    builder = StrictCausalFeatureBuilder()

    with pytest.raises(ValueError):
        builder.build(pd.DataFrame(columns=["x", "y"]))


def test_delta_r_detects_coherence_shift() -> None:
    builder = StrictCausalFeatureBuilder()
    returns = _structured_returns(rows=90).values

    positive = builder._compute_delta_r(returns, alpha=0.3)
    reversed_window = np.flipud(returns)
    negative = builder._compute_delta_r(reversed_window, alpha=0.3)

    assert positive > 0.0
    assert negative <= 0.0


def test_granger_strength_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(v21, "_HAS_STATSMODELS", False, raising=False)
    monkeypatch.setattr(v21, "sm", None, raising=False)
    builder = StrictCausalFeatureBuilder()
    returns = _synth_returns(rows=80).values

    strength = builder._compute_granger_strength(returns, maxlag=2)

    assert 0.0 <= strength <= 1.0


def test_logistic_trainer_outputs_calibrated_artifacts() -> None:
    returns = _synth_returns(rows=260)
    builder = StrictCausalFeatureBuilder(FeatureBuilderConfig(window=40, horizon=5))
    features = builder.build(returns)
    trainer = LogisticIsotonicTrainer(
        ModelTrainingConfig(splits=4, random_state=5, conformal_alpha=0.1)
    )

    artifacts = trainer.fit(features.features.values, features.labels)

    assert artifacts.oof_probabilities.shape == features.labels.shape
    assert artifacts.conformal_epsilon >= 0.0
    assert artifacts.performance.auc_ci[1][0] <= artifacts.performance.auc_ci[1][1]
    assert artifacts.performance.pr_ci[1][0] <= artifacts.performance.pr_ci[1][1]


def test_pipeline_runs_end_to_end() -> None:
    returns = _synth_returns()
    builder = StrictCausalFeatureBuilder(FeatureBuilderConfig(window=40, horizon=5))
    features = builder.build(returns)
    trainer = LogisticIsotonicTrainer(
        ModelTrainingConfig(splits=4, random_state=11, conformal_alpha=0.1)
    )
    hmm = RegimeHMMAdapter(RegimeHMMConfig(states=2, stay_probability=0.85))
    backtester = ProbabilityBacktester(BacktestConfig(tau_high=0.2, tau_low=0.4))
    pipeline = GeoSyncV21Pipeline(
        builder,
        trainer,
        hmm,
        backtester,
        EnsembleConfig(lambda_base=0.7),
    )

    result = pipeline.run(features, returns)

    assert result.probabilities.final.shape[0] == len(features.features)
    assert 0.0 <= result.artifacts.performance.auc <= 1.0
    assert 0.0 <= result.artifacts.performance.pr_auc <= 1.0
    assert result.backtest is not None
    assert result.drift_guard is not None
    assert set(result.drift_guard.keys()) == {
        "dr",
        "ricci_mean",
        "topo_intensity",
        "causal_strength",
    }


def test_pipeline_without_backtest() -> None:
    returns = _synth_returns()
    builder = StrictCausalFeatureBuilder(FeatureBuilderConfig(window=30, horizon=4))
    features = builder.build(returns)
    trainer = LogisticIsotonicTrainer(ModelTrainingConfig(splits=3, random_state=21))
    hmm = RegimeHMMAdapter(RegimeHMMConfig(states=2))
    pipeline = GeoSyncV21Pipeline(
        builder,
        trainer,
        hmm,
        backtester=None,
        ensemble=EnsembleConfig(lambda_base=0.5),
    )

    result = pipeline.run(features, returns=None, evaluate_backtest=False)

    assert result.backtest is None
    assert result.stress is None


def test_regime_hmm_adapter_pads_coefficients() -> None:
    probabilities = np.linspace(0.1, 0.9, num=5)
    adapter = RegimeHMMAdapter(RegimeHMMConfig(states=3))

    adjusted, _ = adapter.adjust(probabilities)

    assert adjusted.shape == probabilities.shape


def test_regime_hmm_adapter_state_path_and_bounds() -> None:
    rng = np.random.default_rng(123)
    probs = np.clip(rng.beta(0.7, 0.6, size=30), 1e-3, 1 - 1e-3)
    adapter = RegimeHMMAdapter(RegimeHMMConfig(states=2, stay_probability=0.8))

    adjusted, path = adapter.adjust(probs)

    assert np.all((adjusted >= 0.0) & (adjusted <= 1.0))
    assert path.shape == probs.shape
    assert set(np.unique(path)).issubset({0, 1})


def test_probability_backtester_generates_positions() -> None:
    returns = _synth_returns(rows=150)
    builder = StrictCausalFeatureBuilder(FeatureBuilderConfig(window=30, horizon=4))
    features = builder.build(returns)
    trainer = LogisticIsotonicTrainer(ModelTrainingConfig(splits=3, random_state=3))
    artifacts = trainer.fit(features.features.values, features.labels)

    standardized = (features.features.values - artifacts.mean) / artifacts.std
    base_probs = 1.0 / (1.0 + np.exp(-artifacts.base_model.decision_function(standardized)))
    calibrated = artifacts.isotonic.predict(base_probs)

    backtester = ProbabilityBacktester(BacktestConfig(tau_high=0.2, tau_low=0.6))
    summary = backtester.backtest(calibrated, returns.loc[features.features.index].values)

    assert np.isfinite(summary.sharpe)
    assert 0.0 <= summary.max_drawdown <= 1.0
    assert summary.equity_final > 0.0


def test_probability_backtester_stress_test_statistics() -> None:
    returns = _synth_returns(rows=120)
    builder = StrictCausalFeatureBuilder(FeatureBuilderConfig(window=30, horizon=3))
    features = builder.build(returns)
    trainer = LogisticIsotonicTrainer(ModelTrainingConfig(splits=3, random_state=17))
    artifacts = trainer.fit(features.features.values, features.labels)

    standardized = (features.features.values - artifacts.mean) / artifacts.std
    calibrated = artifacts.isotonic.predict(
        1.0 / (1.0 + np.exp(-artifacts.base_model.decision_function(standardized)))
    )

    backtester = ProbabilityBacktester(BacktestConfig())
    stress = backtester.stress_test(
        calibrated,
        returns.loc[features.features.index].values,
        simulations=200,
        seed=19,
    )

    assert np.isfinite(stress.sharpe_mean)
    assert np.isfinite(stress.drawdown_mean)
    assert 0.0 <= stress.win_rate_vs_buyhold <= 1.0


def test_pipeline_result_serialization_roundtrip() -> None:
    returns = _synth_returns(rows=200)
    builder = StrictCausalFeatureBuilder(FeatureBuilderConfig(window=30, horizon=4))
    features = builder.build(returns)
    trainer = LogisticIsotonicTrainer(ModelTrainingConfig(splits=3, random_state=9))
    hmm = RegimeHMMAdapter(RegimeHMMConfig(states=2))
    backtester = ProbabilityBacktester(BacktestConfig())
    pipeline = GeoSyncV21Pipeline(
        builder,
        trainer,
        hmm,
        backtester,
        EnsembleConfig(lambda_base=0.55),
    )

    result = pipeline.run(features, returns)
    payload = result.to_dict()
    json_blob = result_to_json(result)

    assert json.loads(json_blob)["p_final"] == payload["p_final"]
    assert "backtest" in payload
    assert "stress" in payload
    assert payload["drift_guard"]["dr"]["PSI"] >= 0.0
