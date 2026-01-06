# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for physics-inspired market indicators."""

import numpy as np
import pytest

from core.indicators.physics import (
    EnergyConservationIndicator,
    MarketFieldDivergenceIndicator,
    MarketGravityIndicator,
    MarketMomentumIndicator,
    ThermodynamicEquilibriumIndicator,
    UncertaintyQuantificationIndicator,
)


class TestMarketMomentumIndicator:
    """Test suite for MarketMomentumIndicator."""
    
    def test_basic_momentum(self):
        """Test basic momentum calculation."""
        indicator = MarketMomentumIndicator(window=5)
        prices = np.array([100, 102, 105, 107, 110])
        
        result = indicator.transform(prices)
        
        # Momentum should be positive for increasing prices
        assert result.value != 0.0
        assert result.name == "market_momentum"
        assert "window" in result.metadata
    
    def test_momentum_with_volumes(self):
        """Test momentum with volume weights."""
        indicator = MarketMomentumIndicator(window=5)
        prices = np.array([100, 102, 105, 107, 110])
        volumes = np.array([1000, 1200, 1100, 1300, 1400])
        
        result = indicator.transform(prices, volumes=volumes)
        
        assert np.isfinite(result.value)
        assert result.metadata["has_volumes"] is True
    
    def test_momentum_empty_data(self):
        """Test momentum with empty data."""
        indicator = MarketMomentumIndicator(window=5)
        prices = np.array([])
        
        result = indicator.transform(prices)
        
        assert result.value == 0.0


class TestMarketGravityIndicator:
    """Test suite for MarketGravityIndicator."""
    
    def test_basic_gravity(self):
        """Test basic gravity calculation."""
        indicator = MarketGravityIndicator()
        prices = np.array([100, 102, 105, 103, 104])
        
        result = indicator.transform(prices)
        
        assert np.isfinite(result.value)
        assert "center_of_gravity" in result.metadata
    
    def test_gravity_with_volumes(self):
        """Test gravity with volume weights."""
        indicator = MarketGravityIndicator()
        prices = np.array([100, 102, 105])
        volumes = np.array([1000, 1500, 1200])
        
        result = indicator.transform(prices, volumes=volumes)
        
        assert np.isfinite(result.value)
        assert result.metadata["has_volumes"] is True
        assert result.metadata["center_of_gravity"] > 0


class TestEnergyConservationIndicator:
    """Test suite for EnergyConservationIndicator."""
    
    def test_basic_conservation(self):
        """Test basic energy conservation check."""
        indicator = EnergyConservationIndicator(tolerance=0.1)
        prices = np.array([100, 101, 102, 101, 100, 99, 100, 101])
        
        result = indicator.transform(prices)
        
        assert np.isfinite(result.value)
        assert "conserved" in result.metadata
        assert "energy_before" in result.metadata
        assert "energy_after" in result.metadata
    
    def test_conservation_insufficient_data(self):
        """Test with insufficient data."""
        indicator = EnergyConservationIndicator()
        prices = np.array([100, 101])
        
        result = indicator.transform(prices)
        
        assert result.value == 0.0
        assert result.metadata["insufficient_data"] is True


class TestThermodynamicEquilibriumIndicator:
    """Test suite for ThermodynamicEquilibriumIndicator."""
    
    def test_basic_equilibrium(self):
        """Test basic equilibrium detection."""
        indicator = ThermodynamicEquilibriumIndicator(window=20)
        # Generate random returns
        returns = np.random.randn(50) * 0.01
        
        result = indicator.transform(returns)
        
        assert np.isfinite(result.value)
        assert "equilibrium" in result.metadata
        assert "temperature_1" in result.metadata
        assert "temperature_2" in result.metadata
    
    def test_equilibrium_stable_regime(self):
        """Test equilibrium in stable regime."""
        indicator = ThermodynamicEquilibriumIndicator(window=10)
        # Constant volatility
        returns = np.random.randn(30) * 0.01
        
        result = indicator.transform(returns)
        
        # Should detect approximate equilibrium
        assert np.isfinite(result.value)


class TestMarketFieldDivergenceIndicator:
    """Test suite for MarketFieldDivergenceIndicator."""
    
    def test_basic_divergence(self):
        """Test basic divergence calculation."""
        indicator = MarketFieldDivergenceIndicator()
        field = np.array([100, 150, 200, 250, 300])
        
        result = indicator.transform(field)
        
        # Divergence should be positive for increasing field
        assert np.isfinite(result.value)
        assert "mean_divergence" in result.metadata
    
    def test_divergence_constant_field(self):
        """Test divergence of constant field."""
        indicator = MarketFieldDivergenceIndicator()
        field = np.array([100, 100, 100, 100])
        
        result = indicator.transform(field)
        
        # Constant field should have near-zero divergence
        assert abs(result.value) < 1e-6


class TestUncertaintyQuantificationIndicator:
    """Test suite for UncertaintyQuantificationIndicator."""
    
    def test_basic_uncertainty(self):
        """Test basic uncertainty quantification."""
        indicator = UncertaintyQuantificationIndicator()
        prices = np.array([100, 102, 101, 103, 102, 104])
        
        result = indicator.transform(prices)
        
        # Uncertainty product should be positive
        assert result.value > 0
        assert "position_uncertainty" in result.metadata
        assert "momentum_uncertainty" in result.metadata
    
    def test_uncertainty_single_price(self):
        """Test with single price."""
        indicator = UncertaintyQuantificationIndicator()
        prices = np.array([100])
        
        result = indicator.transform(prices)
        
        assert result.value == 0.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
