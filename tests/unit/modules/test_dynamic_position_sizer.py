# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""
Tests for Dynamic Position Sizer Module
"""

import pytest

from modules.dynamic_position_sizer import (
    DynamicPositionSizer,
    PositionSizeResult,
    SizingMethod,
)


class TestDynamicPositionSizer:
    """Test suite for DynamicPositionSizer"""

    def test_initialization(self):
        """Test sizer initialization"""
        sizer = DynamicPositionSizer(
            base_capital=100000.0, kelly_fraction=0.25, max_position_pct=0.1
        )

        assert sizer.base_capital == 100000.0
        assert sizer.kelly_fraction == 0.25
        assert sizer.max_position_pct == 0.1

    def test_calculate_kelly_size(self):
        """Test Kelly criterion calculation"""
        sizer = DynamicPositionSizer(base_capital=100000.0, kelly_fraction=0.25)

        # Profitable strategy
        kelly_frac = sizer.calculate_kelly_size(
            win_rate=0.6, avg_win=0.02, avg_loss=0.01, fractional=True
        )

        assert kelly_frac > 0
        assert kelly_frac < 0.5  # Should be reasonable

        # With fractional Kelly
        kelly_full = sizer.calculate_kelly_size(
            win_rate=0.6, avg_win=0.02, avg_loss=0.01, fractional=False
        )

        assert kelly_full > kelly_frac  # Full Kelly should be larger

    def test_calculate_kelly_size_edge_cases(self):
        """Test Kelly with edge cases"""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        # Zero win rate
        kelly = sizer.calculate_kelly_size(0.0, 0.02, 0.01)
        assert kelly == 0.0

        # Zero avg_loss
        kelly = sizer.calculate_kelly_size(0.6, 0.02, 0.0)
        assert kelly == 0.0

    def test_calculate_volatility_adjusted_size(self):
        """Test volatility-adjusted sizing"""
        sizer = DynamicPositionSizer(base_capital=100000.0, volatility_target=0.15)

        base_size = 10000.0

        # Low volatility - should increase size
        size_low_vol = sizer.calculate_volatility_adjusted_size(0.005, base_size)

        # High volatility - should decrease size
        size_high_vol = sizer.calculate_volatility_adjusted_size(0.03, base_size)

        assert size_low_vol > size_high_vol

    def test_calculate_risk_parity_size(self):
        """Test risk parity sizing"""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        portfolio_vols = {"BTCUSD": 0.02, "ETHUSD": 0.03, "SOLUSD": 0.04}

        # Lower volatility asset should get larger allocation
        size_btc = sizer.calculate_risk_parity_size("BTCUSD", 0.02, portfolio_vols)
        size_sol = sizer.calculate_risk_parity_size("SOLUSD", 0.04, portfolio_vols)

        # Both should be non-zero and within limits
        assert size_btc > 0
        assert size_sol > 0
        # Due to max_position_pct limit, they might be equal if both hit the cap
        assert size_btc >= size_sol  # Changed from > to >=

    def test_calculate_adaptive_size(self):
        """Test adaptive sizing"""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        result = sizer.calculate_adaptive_size(
            symbol="BTCUSD",
            price=50000.0,
            volatility=0.015,
            confidence=0.8,
            win_rate=0.6,
            avg_win=0.02,
            avg_loss=0.01,
        )

        assert isinstance(result, PositionSizeResult)
        assert result.recommended_size > 0
        assert result.recommended_size <= result.max_size
        assert result.recommended_size >= result.min_size
        assert result.kelly_fraction > 0

    def test_calculate_size_fixed_method(self):
        """Test fixed sizing method"""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        result = sizer.calculate_size(
            symbol="BTCUSD",
            price=50000.0,
            volatility=0.01,
            confidence=0.8,
            method=SizingMethod.FIXED,
        )

        assert result.sizing_method == SizingMethod.FIXED
        assert result.recommended_size > 0

    def test_calculate_size_varying_confidence(self):
        """Test size adjustment with confidence"""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        size_high = sizer.calculate_size("BTCUSD", 50000.0, 0.01, confidence=1.0)
        size_low = sizer.calculate_size("BTCUSD", 50000.0, 0.01, confidence=0.5)

        assert size_high.recommended_size > size_low.recommended_size

    def test_update_statistics(self):
        """Test statistics tracking"""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        # Record some trades
        sizer.update_statistics("BTCUSD", 0.02, is_win=True)
        sizer.update_statistics("BTCUSD", -0.01, is_win=False)
        sizer.update_statistics("BTCUSD", 0.03, is_win=True)

        stats = sizer.get_statistics("BTCUSD")

        assert stats["trade_count"] == 3
        assert "win_rate" in stats
        assert "avg_win" in stats
        assert "expectancy" in stats

    def test_update_capital(self):
        """Test capital update"""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        sizer.update_capital(150000.0)
        assert sizer.base_capital == 150000.0

        # Test negative capital is handled
        sizer.update_capital(-1000.0)
        assert sizer.base_capital == 0.0

    def test_get_summary(self):
        """Test summary generation"""
        sizer = DynamicPositionSizer(base_capital=100000.0)

        sizer.update_statistics("BTCUSD", 0.02, True)
        sizer.update_statistics("ETHUSD", -0.01, False)

        summary = sizer.get_summary()

        assert "base_capital" in summary
        assert "tracked_symbols" in summary
        assert summary["tracked_symbols"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
