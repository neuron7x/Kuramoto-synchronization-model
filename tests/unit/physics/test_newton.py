# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for Newton's Laws applied to market dynamics."""

import numpy as np
import pytest

from core.physics.newton import (
    compute_acceleration,
    compute_force,
    compute_momentum,
    compute_price_acceleration,
    compute_price_velocity,
)


class TestNewtonLaws:
    """Test suite for Newton's Laws of Motion."""
    
    def test_momentum_basic(self):
        """Test basic momentum calculation p = mv."""
        mass = 100.0
        velocity = 2.0
        momentum = compute_momentum(mass, velocity)
        assert momentum == 200.0
    
    def test_momentum_zero_velocity(self):
        """Test momentum with zero velocity."""
        mass = 100.0
        velocity = 0.0
        momentum = compute_momentum(mass, velocity)
        assert momentum == 0.0
    
    def test_force_basic(self):
        """Test basic force calculation F = ma."""
        mass = 50.0
        acceleration = 4.0
        force = compute_force(mass, acceleration)
        assert force == 200.0
    
    def test_acceleration_basic(self):
        """Test acceleration calculation a = F/m."""
        force = 200.0
        mass = 50.0
        acceleration = compute_acceleration(force, mass)
        assert acceleration == 4.0
    
    def test_price_velocity_basic(self):
        """Test price velocity computation."""
        prices = np.array([100, 102, 105, 104, 107])
        velocity = compute_price_velocity(prices)
        
        # First velocity is 0, then differences
        assert velocity[0] == 0.0
        assert velocity[1] == 2.0
        assert velocity[2] == 3.0
        assert velocity[3] == -1.0
        assert velocity[4] == 3.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
