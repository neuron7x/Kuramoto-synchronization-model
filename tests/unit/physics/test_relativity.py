# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for Relativity in market dynamics."""

import numpy as np
import pytest

from core.physics.relativity import (
    compute_relative_time,
    lorentz_factor,
    lorentz_transform,
    relativistic_momentum,
    velocity_addition,
)


class TestRelativity:
    """Test suite for relativistic effects."""
    
    def test_lorentz_factor_zero_velocity(self):
        """Test Lorentz factor at zero velocity."""
        velocity = 0.0
        gamma = lorentz_factor(velocity)
        # At v=0, gamma should be 1
        assert abs(gamma - 1.0) < 1e-10
    
    def test_lorentz_factor_half_speed(self):
        """Test Lorentz factor at half maximum velocity."""
        velocity = 0.5
        gamma = lorentz_factor(velocity, c=1.0)
        expected = 1.0 / np.sqrt(1.0 - 0.25)
        assert abs(gamma - expected) < 1e-10
    
    def test_lorentz_transform_identity(self):
        """Test Lorentz transform at zero velocity."""
        position = 10.0
        time = 1.0
        velocity = 0.0
        
        pos_prime, t_prime = lorentz_transform(position, time, velocity)
        # At v=0, coordinates should be unchanged
        assert abs(pos_prime - position) < 1e-10
        assert abs(t_prime - time) < 1e-10
    
    def test_relativistic_momentum_classical_limit(self):
        """Test relativistic momentum approaches classical at low velocity."""
        mass = 100.0
        velocity = 0.01  # 1% of max
        
        p_rel = relativistic_momentum(mass, velocity, c=1.0)
        p_classical = mass * velocity
        
        # Should be very close at low velocity
        assert abs(p_rel - p_classical) / p_classical < 0.01
    
    def test_velocity_addition_classical_limit(self):
        """Test velocity addition in classical limit."""
        v1 = 0.01
        v2 = 0.01
        v_combined = velocity_addition(v1, v2, c=1.0)
        
        # At low velocities, should be approximately classical
        classical = v1 + v2
        assert abs(v_combined - classical) / classical < 0.01
    
    def test_velocity_addition_speed_limit(self):
        """Test velocity addition respects speed limit."""
        c = 1.0
        v1 = 0.9 * c
        v2 = 0.9 * c
        v_combined = velocity_addition(v1, v2, c)
        
        # Combined velocity should not exceed c
        assert v_combined < c
    
    def test_time_dilation_basic(self):
        """Test time dilation effect."""
        proper_time = 1.0
        velocity = 0.6
        dilated_time = compute_relative_time(proper_time, velocity, c=1.0)
        
        # Moving clocks run slower (dilated time > proper time)
        assert dilated_time > proper_time


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
