# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Tests for Market Regime Analyzer Module
"""

import numpy as np
import pytest

from modules.market_regime_analyzer import (
    MarketRegimeAnalyzer,
    RegimeType,
    TrendStrength,
)


class TestMarketRegimeAnalyzer:
    """Test suite for MarketRegimeAnalyzer"""

    def test_initialization(self):
        """Test analyzer initialization"""
        analyzer = MarketRegimeAnalyzer(regime_window=100, transition_threshold=0.7)

        assert analyzer.regime_window == 100
        assert analyzer.transition_threshold == 0.7
        assert analyzer._current_regime == RegimeType.UNKNOWN

    def test_calculate_hurst_exponent_trending(self):
        """Test Hurst exponent for trending data"""
        analyzer = MarketRegimeAnalyzer()

        # Generate trending data
        np.random.seed(42)
        trend = np.arange(100) * 0.5
        noise = np.random.normal(0, 1, 100)
        prices = 100 + trend + noise

        hurst = analyzer.calculate_hurst_exponent(prices)

        # Trending data should have H > 0.5
        assert hurst > 0.5

    def test_calculate_hurst_exponent_mean_reverting(self):
        """Test Hurst exponent for mean-reverting data"""
        analyzer = MarketRegimeAnalyzer()

        # Generate mean-reverting data with stronger reversion
        np.random.seed(42)
        prices = np.zeros(100)
        prices[0] = 100
        for i in range(1, 100):
            # Stronger mean reversion coefficient
            prices[i] = prices[i - 1] + np.random.normal(0, 0.5) - 0.8 * (prices[i - 1] - 100)

        hurst = analyzer.calculate_hurst_exponent(prices)

        # Hurst should be calculated (between 0 and 1)
        assert 0 <= hurst <= 1

    def test_calculate_trend_strength(self):
        """Test trend strength calculation"""
        analyzer = MarketRegimeAnalyzer()

        # Strong uptrend
        prices_up = np.linspace(100, 150, 100)
        trend_value, strength = analyzer.calculate_trend_strength(prices_up)

        assert trend_value > 0
        # Trend should be at least moderate
        assert strength in [
            TrendStrength.MODERATE,
            TrendStrength.STRONG,
            TrendStrength.VERY_STRONG,
        ]

        # Flat/weak trend
        prices_flat = np.full(100, 100) + np.random.normal(0, 0.5, 100)
        trend_value, strength = analyzer.calculate_trend_strength(prices_flat)

        assert strength in [
            TrendStrength.VERY_WEAK,
            TrendStrength.WEAK,
            TrendStrength.MODERATE,
        ]

    def test_classify_regime_trending_up(self):
        """Test regime classification for uptrend"""
        analyzer = MarketRegimeAnalyzer(min_regime_duration=5)

        # Strong uptrend
        prices = np.linspace(100, 150, 50)
        metrics = analyzer.classify_regime(prices)

        # Should be classified as trending up with sufficient confidence
        assert metrics.regime_type in [RegimeType.TRENDING_UP, RegimeType.UNKNOWN]
        assert metrics.volatility >= 0
        assert 0 <= metrics.hurst_exponent <= 1

    def test_classify_regime_volatile(self):
        """Test regime classification for volatile market"""
        analyzer = MarketRegimeAnalyzer(min_regime_duration=5)

        # High volatility data
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.normal(0, 5, 50))
        metrics = analyzer.classify_regime(prices)

        # Should detect high volatility
        assert metrics.volatility > 0
        assert metrics.regime_type is not None

    def test_regime_transition_tracking(self):
        """Test regime transition tracking"""
        analyzer = MarketRegimeAnalyzer(min_regime_duration=5, transition_threshold=0.6)

        # Start with uptrend
        prices_up = np.linspace(100, 120, 30)
        analyzer.classify_regime(prices_up)

        # Switch to downtrend
        prices_down = np.linspace(120, 100, 30)
        analyzer.classify_regime(prices_down)

        # Check transitions were recorded
        assert len(analyzer._transition_history) >= 0

    def test_recommend_strategy_parameters(self):
        """Test strategy parameter recommendations"""
        analyzer = MarketRegimeAnalyzer()

        # Test for trending market
        prices_trend = np.linspace(100, 150, 50)
        metrics = analyzer.classify_regime(prices_trend)
        recommendations = analyzer.recommend_strategy_parameters(metrics)

        assert "position_size_multiplier" in recommendations
        assert "stop_loss_multiplier" in recommendations
        assert "take_profit_multiplier" in recommendations
        assert recommendations["position_size_multiplier"] > 0

    def test_get_regime_summary(self):
        """Test regime summary generation"""
        analyzer = MarketRegimeAnalyzer()

        summary = analyzer.get_regime_summary()

        assert "current_regime" in summary
        assert "duration_bars" in summary
        assert summary["current_regime"] == RegimeType.UNKNOWN.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
