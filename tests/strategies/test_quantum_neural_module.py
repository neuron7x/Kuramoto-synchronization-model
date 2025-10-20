import math
from typing import Dict

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")

from strategies.quantum_neural import (
    AdaptiveFundamentalTransformer,
    AdvancedTradingDataset,
    QuantumNeuralModel,
    QuantumNeuralStrategy,
    TrainConfig,
    _analyze_performance,
    _check_df,
    backtest,
    get_strategy,
)


@pytest.fixture(scope="module")
def base_dataframe() -> pd.DataFrame:
    dates = pd.date_range("2020-01-01", periods=50, freq="D")
    data = {
        "date": dates[::-1],  # intentionally reversed to verify sorting
        "open": np.linspace(100, 150, len(dates)),
        "high": np.linspace(101, 151, len(dates)),
        "low": np.linspace(99, 149, len(dates)),
        "close": np.linspace(100, 160, len(dates)),
        "volume": np.linspace(1_000, 5_000, len(dates)),
    }
    return pd.DataFrame(data)


def test_check_df_validates_and_sorts(base_dataframe: pd.DataFrame) -> None:
    processed = _check_df(base_dataframe)
    assert processed["date"].is_monotonic_increasing
    assert processed["date"].dtype.kind == "M"

    with pytest.raises(ValueError):
        _check_df(processed.drop(columns=["volume"]))


def test_dataset_shapes_and_targets(base_dataframe: pd.DataFrame) -> None:
    ds = AdvancedTradingDataset(base_dataframe, sequence_length=6, augment=False)
    assert len(ds) == len(base_dataframe) - 1 - 6
    window, price, action = ds[0]
    assert window.shape == (6, 5)
    assert price.shape == (1,)
    assert action.shape == ()
    assert set(ds.scalers.keys()) == {"open", "high", "low", "close", "volume"}


def test_adaptive_transformer_accepts_full_statistics() -> None:
    torch.manual_seed(7)
    transformer = AdaptiveFundamentalTransformer(feature_size=20, d_model=32, nhead=8)
    stats = torch.randn(4, 5, 20)
    encoded = transformer(stats)
    assert encoded.shape == (4, 32)

    flat_stats = torch.randn(4, 20)
    encoded_flat = transformer(flat_stats)
    assert encoded_flat.shape == (4, 32)


def test_quantum_model_forward_shapes() -> None:
    torch.manual_seed(11)
    model = QuantumNeuralModel()
    sample = torch.randn(3, 30, 5)
    price, logits = model(sample)
    assert price.shape == (3, 1)
    assert logits.shape == (3, 3)


def test_strategy_fit_and_predict_flow(base_dataframe: pd.DataFrame, monkeypatch: pytest.MonkeyPatch) -> None:
    torch.manual_seed(21)
    np.random.seed(21)

    cfg = TrainConfig(epochs=1, seq_len=5, batch_size=4, device="cpu")
    strategy = QuantumNeuralStrategy(cfg)
    monkeypatch.setattr(strategy, "_save", lambda path: None)

    strategy.fit(base_dataframe)

    window = base_dataframe.sort_values("date").tail(cfg.seq_len + 1)
    prediction = strategy.predict_window(window)
    assert set(["actions", "confidence", "price_pred"]).issubset(prediction.keys())
    assert prediction["actions"].shape == (3,)
    assert math.isfinite(prediction["price_pred"])
    assert 0.0 <= prediction["confidence"] <= 1.0


def test_backtest_generates_metrics(base_dataframe: pd.DataFrame) -> None:
    class DummyStrategy:
        def __init__(self) -> None:
            self.cfg = TrainConfig(seq_len=4)
            self._step = 0

        def predict_window(self, window: pd.DataFrame) -> Dict[str, np.ndarray]:
            self._step += 1
            if self._step % 3 == 1:
                probs = np.array([0.05, 0.9, 0.05])
            elif self._step % 3 == 2:
                probs = np.array([0.9, 0.05, 0.05])
            else:
                probs = np.array([0.05, 0.05, 0.9])
            return {
                "actions": probs,
                "confidence": float(probs.max()),
                "price_pred": float(window.iloc[-1]["close"]),
            }

    df = base_dataframe.sort_values("date")
    metrics = backtest(df, DummyStrategy())
    expected_keys = {
        "total_return",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown",
        "win_rate",
        "avg_profit_per_trade",
        "profit_factor",
        "total_trades",
        "final_balance",
        "calmar_ratio",
    }
    assert expected_keys.issubset(metrics.keys())


def test_get_strategy_provides_configured_strategy() -> None:
    strategy = get_strategy({"epochs": 1, "seq_len": 5, "batch_size": 2})
    assert isinstance(strategy, QuantumNeuralStrategy)
    assert strategy.cfg.epochs == 1
    assert strategy.cfg.seq_len == 5
    assert strategy.cfg.batch_size == 2


def test_analyze_performance_handles_empty_inputs() -> None:
    metrics = _analyze_performance([], [])
    assert metrics == {"error": 1.0}
