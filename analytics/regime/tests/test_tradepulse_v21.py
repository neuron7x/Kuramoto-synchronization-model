from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.regime.src.core.tradepulse_v21 import (
    BacktestConfig,
    EnsembleConfig,
    FeatureBuilderConfig,
    LogisticIsotonicTrainer,
    ModelTrainingConfig,
    ProbabilityBacktester,
    RegimeHMMAdapter,
    RegimeHMMConfig,
    StrictCausalFeatureBuilder,
    TradePulseV21Pipeline,
)


def _synth_returns(rows: int = 320, cols: int = 3, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2024-01-01", periods=rows, freq="D")
    returns = rng.normal(0.0, 0.01, size=(rows, cols))
    return pd.DataFrame(returns, index=index, columns=[f"asset_{i}" for i in range(cols)])


def test_pipeline_runs_end_to_end() -> None:
    returns = _synth_returns()
    builder = StrictCausalFeatureBuilder(FeatureBuilderConfig(window=40, horizon=5))
    features = builder.build(returns)
    trainer = LogisticIsotonicTrainer(
        ModelTrainingConfig(splits=4, random_state=11, conformal_alpha=0.1)
    )
    hmm = RegimeHMMAdapter(RegimeHMMConfig(states=2, stay_probability=0.85))
    backtester = ProbabilityBacktester(BacktestConfig(tau_high=0.2, tau_low=0.4))
    pipeline = TradePulseV21Pipeline(
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
    assert set(result.drift_guard.keys()) == {"dr", "ricci_mean", "topo_intensity", "causal_strength"}


def test_pipeline_without_backtest() -> None:
    returns = _synth_returns()
    builder = StrictCausalFeatureBuilder(FeatureBuilderConfig(window=30, horizon=4))
    features = builder.build(returns)
    trainer = LogisticIsotonicTrainer(ModelTrainingConfig(splits=3, random_state=21))
    hmm = RegimeHMMAdapter(RegimeHMMConfig(states=2))
    pipeline = TradePulseV21Pipeline(
        builder,
        trainer,
        hmm,
        backtester=None,
        ensemble=EnsembleConfig(lambda_base=0.5),
    )

    result = pipeline.run(features, returns=None, evaluate_backtest=False)

    assert result.backtest is None
    assert result.stress is None
