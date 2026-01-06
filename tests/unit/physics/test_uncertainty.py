# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for Heisenberg's Uncertainty Principle in market dynamics."""

import numpy as np
import pytest

from core.physics.uncertainty import (
    check_uncertainty_principle,
    heisenberg_uncertainty,
    information_limit,
    minimum_uncertainty_product,
    optimal_measurement_tradeoff,
    position_momentum_uncertainty,
)


class TestUncertaintyPrinciple:
    """Test suite for Heisenberg's Uncertainty Principle."""
    
    def test_heisenberg_uncertainty_basic(self):
        """Test basic uncertainty product calculation."""
        delta_x = 0.1
        delta_p = 0.2
        product = heisenberg_uncertainty(delta_x, delta_p)
        assert abs(product - 0.02) < 1e-10
    
    def test_minimum_uncertainty_product(self):
        """Test minimum uncertainty product."""
        min_product = minimum_uncertainty_product(hbar=1.0)
        expected = 0.5  # h_bar / 2
        assert abs(min_product - expected) < 1e-10
    
    def test_check_uncertainty_principle_valid(self):
        """Test uncertainty principle with valid uncertainties."""
        delta_x = 1.0
        delta_p = 1.0
        hbar = 1.0
        
        valid, factor = check_uncertainty_principle(delta_x, delta_p, hbar)
        # Product = 1.0, minimum = 0.5, so valid
        assert valid is True
        assert factor >= 1.0
    
    def test_check_uncertainty_principle_violation(self):
        """Test uncertainty principle violation detection."""
        delta_x = 0.1
        delta_p = 0.1
        hbar = 1.0
        
        valid, factor = check_uncertainty_principle(delta_x, delta_p, hbar)
        # Product = 0.01, minimum = 0.5, so violated
        assert valid is False
        assert factor < 1.0
    
    def test_position_momentum_uncertainty(self):
        """Test uncertainty computation from data."""
        prices = np.array([100, 102, 101, 103, 102, 104])
        velocities = np.diff(prices)
        
        delta_x, delta_p, product = position_momentum_uncertainty(
            prices, velocities
        )
        
        # Uncertainties should be positive
        assert delta_x > 0
        assert delta_p > 0
        assert product > 0
    
    def test_optimal_measurement_tradeoff(self):
        """Test optimal uncertainty allocation."""
        budget = 1.0
        hbar = 1.0
        
        dx_opt, dp_opt = optimal_measurement_tradeoff(budget, hbar)
        
        # Optimal split should be equal
        assert abs(dx_opt - dp_opt) < 1e-10
        
        # Product should satisfy uncertainty principle
        product = dx_opt * dp_opt
        min_product = minimum_uncertainty_product(hbar)
        assert product >= min_product - 1e-10
    
    def test_information_limit_basic(self):
        """Test information limit calculation."""
        measurement_time = 1.0
        hbar = 1.0
        
        limit = information_limit(measurement_time, hbar)
        
        # Limit should be positive and finite
        assert limit > 0
        assert np.isfinite(limit)
    
    def test_information_limit_zero_time(self):
        """Test information limit with zero measurement time."""
        measurement_time = 0.0
        limit = information_limit(measurement_time)
        
        # Infinite limit for zero time
        assert limit == float('inf')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
