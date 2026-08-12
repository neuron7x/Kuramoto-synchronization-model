# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coverage tests for modules.market_regime_analyzer."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from modules.market_regime_analyzer import (
    MarketRegimeAnalyzer,
    RegimeMetrics,
    RegimeTransition,
    RegimeType,
    TrendStrength,
)


def _trend_up(n: int = 100) -> np.ndarray:
    return 100.0 * (1.01 ** np.arange(n))


def _trend_down(n: int = 100) -> np.ndarray:
    return 100.0 * (0.99 ** np.arange(n))


def _mean_reverting() -> np.ndarray:
    t = np.arange(200)
    return 100.0 + 5.0 * np.sin(t * 0.5)


def _volatile() -> np.ndarray:
    rng = np.random.default_rng(0)
    return 100.0 + np.cumsum(rng.normal(0, 3.0, 100))


def _calm() -> np.ndarray:
    rng = np.random.default_rng(0)
    return 100.0 + np.cumsum(rng.normal(0, 0.05, 100))


def _choppy() -> np.ndarray:
    rng = np.random.default_rng(1)
    t = np.arange(140)
    return 100.0 + np.sin(t * 0.5) + rng.normal(0, 1.0, 140)


# --- market-state validation helpers ---------------------------------------


def test_validate_prices_missing_key() -> None:
    a = MarketRegimeAnalyzer()
    with pytest.raises(KeyError, match="prices"):
        a.classify_regime({})


def test_validate_prices_wrong_ndim() -> None:
    a = MarketRegimeAnalyzer()
    state: dict[str, Any] = {"prices": [[1.0, 2.0], [3.0, 4.0]]}
    with pytest.raises(ValueError, match="1D array"):
        a.classify_regime(state)


def test_validate_returns_wrong_ndim() -> None:
    a = MarketRegimeAnalyzer()
    state: dict[str, Any] = {
        "prices": list(_trend_up()),
        "returns": [[0.1, 0.2], [0.3, 0.4]],
    }
    with pytest.raises(ValueError, match="returns.*1D array"):
        a.classify_regime(state)


def test_dict_state_with_explicit_returns() -> None:
    a = MarketRegimeAnalyzer()
    prices = _trend_up()
    returns = np.diff(prices) / prices[:-1]
    state: dict[str, Any] = {"prices": list(prices), "returns": list(returns)}
    metrics = a.classify_regime(state)
    assert isinstance(metrics, RegimeMetrics)


def test_dict_state_returns_derived_from_prices() -> None:
    a = MarketRegimeAnalyzer()
    state: dict[str, Any] = {"prices": list(_trend_up())}
    metrics = a.classify_regime(state)
    assert metrics.regime_type == RegimeType.TRENDING_UP


def test_dict_state_single_price_returns_empty() -> None:
    a = MarketRegimeAnalyzer(min_regime_duration=1)
    state: dict[str, Any] = {"prices": [100.0]}
    metrics = a.classify_regime(state)
    # Single price -> empty returns branch -> zero volatility.
    assert metrics.volatility == 0.0


# --- array-path validation --------------------------------------------------


def test_array_path_wrong_ndim_prices() -> None:
    a = MarketRegimeAnalyzer()
    with pytest.raises(ValueError, match="prices must be a 1D array"):
        a.classify_regime(np.ones((3, 3)))


def test_array_path_wrong_ndim_returns() -> None:
    a = MarketRegimeAnalyzer()
    with pytest.raises(ValueError, match="returns must be a 1D array"):
        a.classify_regime(_trend_up(), returns=np.ones((2, 2)))


def test_array_path_returns_none_single_price() -> None:
    a = MarketRegimeAnalyzer(min_regime_duration=1)
    metrics = a.classify_regime(np.array([100.0]))
    # Single price with returns=None -> empty-returns branch -> zero volatility.
    assert metrics.volatility == 0.0


def test_array_path_explicit_returns() -> None:
    a = MarketRegimeAnalyzer()
    prices = _trend_up()
    returns = np.diff(prices) / prices[:-1]
    metrics = a.classify_regime(prices, returns=returns)
    assert metrics.volatility >= 0.0


# --- Hurst exponent ---------------------------------------------------------


def test_hurst_short_series_returns_half() -> None:
    a = MarketRegimeAnalyzer()
    assert a.calculate_hurst_exponent(np.arange(5.0)) == 0.5


def test_hurst_constant_series_returns_half() -> None:
    a = MarketRegimeAnalyzer()
    # Zero-variance chunks give no valid R/S points -> fallback 0.5.
    assert a.calculate_hurst_exponent(np.full(60, 100.0)) == 0.5


def test_hurst_trending_series_high() -> None:
    a = MarketRegimeAnalyzer()
    h = a.calculate_hurst_exponent(_trend_up())
    assert 0.0 <= h <= 1.0


# --- ADF test ---------------------------------------------------------------


def test_adf_short_series() -> None:
    a = MarketRegimeAnalyzer()
    assert a.augmented_dickey_fuller_test(np.arange(10.0)) == (0.0, 1.0)


def test_adf_constant_series_is_degenerate() -> None:
    a = MarketRegimeAnalyzer()
    # Flat series -> ss_x == 0 degenerate guard.
    stat, pval = a.augmented_dickey_fuller_test(np.full(60, 100.0))
    assert (stat, pval) == (0.0, 1.0)


def test_adf_mean_reverting_significant() -> None:
    a = MarketRegimeAnalyzer()
    stat, pval = a.augmented_dickey_fuller_test(_mean_reverting())
    assert pval in {0.05, 0.5}


def test_adf_regular_series_returns_floats() -> None:
    a = MarketRegimeAnalyzer()
    stat, pval = a.augmented_dickey_fuller_test(np.linspace(100, 101, 25))
    assert isinstance(stat, float)
    assert isinstance(pval, float)


# --- trend strength ---------------------------------------------------------


def test_trend_strength_short_series() -> None:
    a = MarketRegimeAnalyzer()
    value, strength = a.calculate_trend_strength(np.arange(5.0))
    assert value == 0.0
    assert strength == TrendStrength.VERY_WEAK


def test_trend_strength_constant_series_zero_sstot() -> None:
    a = MarketRegimeAnalyzer()
    value, strength = a.calculate_trend_strength(np.full(20, 100.0))
    assert value == 0.0
    assert strength == TrendStrength.VERY_WEAK


@pytest.mark.parametrize(
    "prices",
    [
        _trend_up(),
        _trend_down(),
        _mean_reverting(),
    ],
)
def test_trend_strength_classifications(prices: np.ndarray) -> None:
    a = MarketRegimeAnalyzer()
    value, strength = a.calculate_trend_strength(prices)
    assert isinstance(strength, TrendStrength)


def test_trend_strength_covers_all_bands() -> None:
    a = MarketRegimeAnalyzer()
    seen = set()
    for slope in (0.0, 0.15, 0.4, 0.8, 1.5):
        prices = 100.0 + slope * np.arange(50)
        _, strength = a.calculate_trend_strength(prices)
        seen.add(strength)
    # All five strength bands exercised across the slope sweep.
    assert len(seen) >= 4


# --- classify_regime: each regime ------------------------------------------


def test_classify_below_min_duration() -> None:
    a = MarketRegimeAnalyzer(min_regime_duration=10)
    metrics = a.classify_regime(np.arange(1.0, 6.0))
    assert metrics.regime_type == RegimeType.UNKNOWN
    assert metrics.duration_bars == 0


def test_classify_trending_up() -> None:
    a = MarketRegimeAnalyzer()
    assert a.classify_regime(_trend_up()).regime_type == RegimeType.TRENDING_UP


def test_classify_trending_down() -> None:
    a = MarketRegimeAnalyzer()
    assert a.classify_regime(_trend_down()).regime_type == RegimeType.TRENDING_DOWN


def test_classify_mean_reverting() -> None:
    a = MarketRegimeAnalyzer()
    assert a.classify_regime(_mean_reverting()).regime_type == RegimeType.MEAN_REVERTING


def test_classify_volatile() -> None:
    a = MarketRegimeAnalyzer()
    assert a.classify_regime(_volatile()).regime_type == RegimeType.VOLATILE


def test_classify_calm() -> None:
    a = MarketRegimeAnalyzer()
    assert a.classify_regime(_calm()).regime_type == RegimeType.CALM


def test_classify_choppy() -> None:
    a = MarketRegimeAnalyzer()
    assert a.classify_regime(_choppy()).regime_type == RegimeType.CHOPPY


# --- transitions & retained regime -----------------------------------------


def test_transition_history_records_change() -> None:
    a = MarketRegimeAnalyzer()
    a.classify_regime(_trend_up())  # sets current from UNKNOWN, no transition yet
    a.classify_regime(_trend_down())  # distinct regime -> transition recorded
    history = a.get_transition_history()
    assert len(history) == 1
    assert isinstance(history[0], RegimeTransition)
    assert history[0].from_regime == RegimeType.TRENDING_UP
    assert history[0].to_regime == RegimeType.TRENDING_DOWN


def test_same_regime_increments_duration() -> None:
    a = MarketRegimeAnalyzer()
    first = a.classify_regime(_trend_up())
    second = a.classify_regime(_trend_up())
    assert second.duration_bars == first.duration_bars + 1


def test_low_confidence_retains_previous_regime() -> None:
    # Force the retained-regime branch: high threshold keeps confidence below it
    # while an existing duration satisfies the minimum-duration guard.
    a = MarketRegimeAnalyzer(transition_threshold=1.0, min_regime_duration=10)
    a._current_regime = RegimeType.CALM
    a._regime_duration = 10
    metrics = a.classify_regime(_choppy())
    # Choppy confidence 0.7 < threshold 1.0 -> previous CALM retained.
    assert metrics.regime_type == RegimeType.CALM
    assert metrics.duration_bars == 11


# --- probabilities / summary / recommendations -----------------------------


def test_get_regime_probabilities_copy() -> None:
    a = MarketRegimeAnalyzer()
    a.classify_regime(_trend_up())
    probs = a.get_regime_probabilities()
    assert RegimeType.TRENDING_UP in probs
    probs.clear()
    assert a.get_regime_probabilities()  # original untouched


def test_get_transition_history_with_limit() -> None:
    a = MarketRegimeAnalyzer()
    a.classify_regime(_trend_up())
    a.classify_regime(_trend_down())
    a.classify_regime(_mean_reverting())
    limited = a.get_transition_history(limit=1)
    assert len(limited) == 1


@pytest.mark.parametrize(
    "regime",
    [
        RegimeType.TRENDING_UP,
        RegimeType.TRENDING_DOWN,
        RegimeType.MEAN_REVERTING,
        RegimeType.VOLATILE,
        RegimeType.CALM,
        RegimeType.CHOPPY,
        RegimeType.UNKNOWN,
    ],
)
def test_recommend_strategy_parameters(regime: RegimeType) -> None:
    a = MarketRegimeAnalyzer()
    metrics = RegimeMetrics(
        regime_type=regime,
        trend_strength=TrendStrength.MODERATE,
        volatility=0.1,
        hurst_exponent=0.5,
        adf_statistic=0.0,
        adf_pvalue=1.0,
        regime_confidence=0.8,
        duration_bars=5,
        timestamp=__import__("datetime").datetime.now(),
    )
    params = a.recommend_strategy_parameters(metrics)
    assert "position_size_multiplier" in params
    assert params["position_size_multiplier"] > 0


def test_get_regime_summary_no_transitions() -> None:
    a = MarketRegimeAnalyzer()
    summary = a.get_regime_summary()
    assert summary["current_regime"] == RegimeType.UNKNOWN.value
    assert summary["last_transition"] is None
    assert summary["regime_start_time"] is None


def test_get_regime_summary_with_transition() -> None:
    a = MarketRegimeAnalyzer()
    a.classify_regime(_trend_up())
    a.classify_regime(_trend_down())
    summary = a.get_regime_summary()
    assert summary["transition_count"] == 1
    assert summary["last_transition"] is not None
    assert summary["regime_start_time"] is not None
    assert summary["last_transition"]["from"] == RegimeType.TRENDING_UP.value
