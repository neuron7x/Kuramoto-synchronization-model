"""Unit tests for trading strategies built on lightweight indicators."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from core.indicators.trading import HurstIndicator, KuramotoIndicator, VPINIndicator
from core.strategies.trading import HurstVPINStrategy, KuramotoStrategy


def _frame_from_closes(values: list[float]) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=len(values), freq="min")
    return pd.DataFrame({"close": values}, index=index)


def test_kuramoto_strategy_applies_warmup(monkeypatch: pytest.MonkeyPatch) -> None:
    """The initial warmup window should force Hold signals with zero confidence."""

    closes = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0]
    data = _frame_from_closes(closes)
    strategy = KuramotoStrategy(
        symbol="XYZ",
        params={"window": 5, "sync_threshold": 0.6, "coupling": 1.0},
    )

    def fake_compute(self: KuramotoIndicator, _: np.ndarray) -> np.ndarray:
        return np.full(len(closes), 0.9)

    monkeypatch.setattr(KuramotoIndicator, "compute", fake_compute)

    signals = strategy.generate_signals(data)
    warmup = max(0, min(strategy._indicator.window, 10) - 1)

    assert (signals.iloc[:warmup]["signal"] == "Hold").all()
    assert (signals.iloc[:warmup]["confidence"] == 0.0).all()
    post_warmup = signals.iloc[warmup:]
    assert (post_warmup["signal"] == "Buy").all()
    assert (post_warmup["confidence"] > 0.0).all()


def test_kuramoto_strategy_sell_confidence_when_threshold_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When sync threshold is maximal the sell confidence should be 1."""

    closes = [100.0, 100.5, 101.0]
    data = _frame_from_closes(closes)
    strategy = KuramotoStrategy(
        symbol="XYZ", params={"window": 1, "sync_threshold": 1.0}
    )

    def fake_compute(self: KuramotoIndicator, _: np.ndarray) -> np.ndarray:
        return np.array([0.0, 0.0, 1.0])

    monkeypatch.setattr(KuramotoIndicator, "compute", fake_compute)

    signals = strategy.generate_signals(data)

    assert list(signals["signal"])[:2] == ["Sell", "Sell"]
    assert (signals.loc[signals["signal"] == "Sell", "confidence"] == 1.0).all()
    assert signals.iloc[-1]["signal"] == "Buy"


def test_hurst_vpin_strategy_branch_logic(monkeypatch: pytest.MonkeyPatch) -> None:
    """The blended strategy should choose actions based on indicator thresholds."""

    index = pd.date_range("2025-01-01", periods=3, freq="h")
    data = pd.DataFrame(
        {
            "close": [100.0, 101.0, 102.0],
            "volume": [1_000, 1_000, 1_000],
            "buy_volume": [600, 400, 300],
            "sell_volume": [400, 600, 900],
        },
        index=index,
    )
    strategy = HurstVPINStrategy(
        symbol="XYZ",
        params={
            "hurst_window": 5,
            "vpin_bucket_size": 2,
            "hurst_trend_threshold": 0.6,
            "vpin_safe_threshold": 0.5,
        },
    )

    def fake_hurst(self: HurstIndicator, _: np.ndarray) -> np.ndarray:
        return np.array([0.8, 0.7, 0.3])

    def fake_vpin(self: VPINIndicator, _: np.ndarray) -> np.ndarray:
        return np.array([0.2, 0.8, 0.4])

    monkeypatch.setattr(HurstIndicator, "compute", fake_hurst)
    monkeypatch.setattr(VPINIndicator, "compute", fake_vpin)

    signals = strategy.generate_signals(data)

    assert list(signals["signal"]) == ["Buy", "Sell", "Hold"]
    assert signals.loc[signals["signal"] == "Buy", "confidence"].iloc[
        0
    ] == pytest.approx(0.8)
    assert signals.loc[signals["signal"] == "Sell", "confidence"].iloc[
        0
    ] == pytest.approx(0.8)
    assert signals.loc[signals["signal"] == "Hold", "confidence"].iloc[
        0
    ] == pytest.approx(0.5)


def test_hurst_vpin_strategy_symbol_and_index(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generated frame should align timestamps and symbol with the input."""

    index = pd.date_range("2025-01-01", periods=2, freq="h")
    data = pd.DataFrame(
        {
            "close": [100.0, 101.0],
            "volume": [500, 700],
            "buy_volume": [300, 400],
            "sell_volume": [200, 300],
        },
        index=index,
    )
    strategy = HurstVPINStrategy(symbol="ABC", params={})

    monkeypatch.setattr(HurstIndicator, "compute", lambda self, _: np.zeros(2))
    monkeypatch.setattr(VPINIndicator, "compute", lambda self, _: np.zeros(2))

    signals = strategy.generate_signals(data)

    assert list(signals["timestamp"]) == list(index)
    assert signals["symbol"].eq("ABC").all()
    assert set(signals["signal"].unique()) == {"Hold"}
    assert np.all(signals["confidence"] == 0.5)
