"""Unit tests for NeuroTradePulseStrategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies.neuro_trade_pulse import NeuroTradePulseConfig, NeuroTradePulseStrategy


def _sample_bars(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Create sample data with DatetimeIndex."""
    rng = np.random.default_rng(seed=seed)
    idx = pd.date_range("2024-01-01", periods=n, freq="5min")
    price = 100 + np.cumsum(rng.normal(0, 0.5, n))
    volume = np.exp(rng.normal(9.0, 0.3, n))
    return pd.DataFrame({"close": price, "volume": volume}, index=idx)


def test_strategy_requires_datetime_index() -> None:
    """Strategy should raise ValueError if bars lack DatetimeIndex."""
    bars = pd.DataFrame({"close": [100, 101, 102], "volume": [1000, 1000, 1000]})
    strat = NeuroTradePulseStrategy()
    with pytest.raises(ValueError, match="DatetimeIndex"):
        strat.generate_signals(bars)


def test_strategy_requires_price_and_volume_columns() -> None:
    """Strategy should raise ValueError if required columns are missing."""
    idx = pd.date_range("2024-01-01", periods=10, freq="1min")
    bars_no_volume = pd.DataFrame({"close": [100] * 10}, index=idx)
    bars_no_close = pd.DataFrame({"volume": [1000] * 10}, index=idx)

    strat = NeuroTradePulseStrategy()
    with pytest.raises(ValueError, match="close"):
        strat.generate_signals(bars_no_volume)
    with pytest.raises(ValueError, match="volume"):
        strat.generate_signals(bars_no_close)


def test_strategy_generates_signals_with_correct_shape() -> None:
    """Generated signals should match input bars length and index."""
    bars = _sample_bars(150)
    strat = NeuroTradePulseStrategy()
    signals = strat.generate_signals(bars)

    assert len(signals) == len(bars)
    assert signals.index.equals(bars.index)
    assert signals.name == "neuro_action"


def test_warmup_period_returns_zero_signals() -> None:
    """During warmup period, all signals should be 0.0."""
    warmup = 50
    cfg = NeuroTradePulseConfig(warmup=warmup)
    bars = _sample_bars(100)
    strat = NeuroTradePulseStrategy(cfg)
    signals = strat.generate_signals(bars)

    assert (signals.iloc[:warmup] == 0.0).all()


def test_signals_are_in_valid_range() -> None:
    """All signals should be in {-1.0, 0.0, 1.0}."""
    bars = _sample_bars(200)
    strat = NeuroTradePulseStrategy()
    signals = strat.generate_signals(bars)

    unique_values = signals.unique()
    assert all(v in {-1.0, 0.0, 1.0} for v in unique_values)


def test_analyze_snapshot_returns_composite_signal() -> None:
    """analyze_snapshot should return a CompositeSignal."""
    bars = _sample_bars(100)
    strat = NeuroTradePulseStrategy()
    snap = strat.analyze_snapshot(bars)

    # Check that CompositeSignal has expected attributes
    assert hasattr(snap, "phase")
    assert hasattr(snap, "confidence")
    assert hasattr(snap, "entry_signal")
    assert hasattr(snap, "exit_signal")
    assert hasattr(snap, "kuramoto_R")


def test_low_confidence_suppresses_signals() -> None:
    """Signals should be suppressed when confidence is below threshold."""
    cfg = NeuroTradePulseConfig(min_confidence=0.99, warmup=10)
    bars = _sample_bars(100)
    strat = NeuroTradePulseStrategy(cfg)
    signals = strat.generate_signals(bars)

    # With very high confidence threshold, most signals should be suppressed
    non_zero = (signals != 0.0).sum()
    # Allow some non-zero signals after warmup period has passed
    assert non_zero < len(signals) * 0.5  # Less than 50% should be non-zero


def test_negative_curvature_gate_suppresses_signals() -> None:
    """Signals should be suppressed when curvature is too negative."""
    cfg = NeuroTradePulseConfig(negative_curvature_gate=1.0, warmup=10)
    bars = _sample_bars(100)
    strat = NeuroTradePulseStrategy(cfg)
    signals = strat.generate_signals(bars)

    # With positive curvature gate, all negative curvature should suppress signals
    non_zero = (signals != 0.0).sum()
    # Most signals should be suppressed
    assert non_zero < len(signals) * 0.5


def test_state_from_signal_returns_correct_shape() -> None:
    """_state_from_signal should return an 8-element array."""
    bars = _sample_bars(100)
    strat = NeuroTradePulseStrategy()
    snap = strat.analyze_snapshot(bars)
    state_vec = strat._state_from_signal(snap)

    assert state_vec.shape == (8,)
    assert state_vec.dtype == np.float64


def test_hidden_states_returns_correct_shape() -> None:
    """_hidden_states should return a 3xN array."""
    bars = _sample_bars(100)
    strat = NeuroTradePulseStrategy()
    snap = strat.analyze_snapshot(bars)
    state_vec = strat._state_from_signal(snap)
    hidden = strat._hidden_states(state_vec, None)

    assert hidden.shape == (3, 8)


def test_config_defaults() -> None:
    """NeuroTradePulseConfig should have sensible defaults."""
    cfg = NeuroTradePulseConfig()
    assert cfg.discount_rate == 0.95
    assert cfg.min_confidence == 0.55
    assert cfg.negative_curvature_gate == -0.15
    assert cfg.warmup == 64
    assert cfg.motivation_scale == 0.5
    assert cfg.motivation_threshold == 0.05
    assert cfg.state_scaling_factor == 0.5
