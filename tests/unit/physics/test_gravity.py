# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for Universal Gravitation in market dynamics."""

import numpy as np
import pytest

from core.physics.gravity import (
    compute_market_gravity,
    gravitational_force,
    gravitational_potential,
    market_gravity_center,
)


class TestGravitation:
    """Test suite for gravitational laws."""
    
    def test_gravitational_force_basic(self):
        """Test basic gravitational force calculation."""
        mass1 = 100.0
        mass2 = 50.0
        distance = 10.0
        force = gravitational_force(mass1, mass2, distance)
        expected = 1.0 * (100.0 * 50.0) / (10.0 ** 2)
        assert abs(force - expected) < 1e-10
    
    def test_gravitational_force_inverse_square(self):
        """Test inverse square law."""
        mass1 = 100.0
        mass2 = 50.0
        d1 = 10.0
        d2 = 20.0
        
        f1 = gravitational_force(mass1, mass2, d1)
        f2 = gravitational_force(mass1, mass2, d2)
        
        # Force at 2x distance should be 1/4 of original
        assert abs(f2 - f1 / 4.0) < 1e-10
    
    def test_gravitational_potential_basic(self):
        """Test gravitational potential energy."""
        mass = 100.0
        distance = 10.0
        potential = gravitational_potential(mass, distance)
        expected = -1.0 * 100.0 / 10.0
        assert abs(potential - expected) < 1e-10
    
    def test_market_gravity_center_uniform(self):
        """Test center of gravity with uniform volumes."""
        prices = np.array([100, 110, 120])
        center = market_gravity_center(prices)
        # Should be simple average
        assert abs(center - 110.0) < 1e-10
    
    def test_market_gravity_center_weighted(self):
        """Test center of gravity with volume weights."""
        prices = np.array([100, 110, 120])
        volumes = np.array([1, 2, 1])
        center = market_gravity_center(prices, volumes)
        # VWAP: (100*1 + 110*2 + 120*1) / 4 = 440/4 = 110
        assert abs(center - 110.0) < 1e-10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
