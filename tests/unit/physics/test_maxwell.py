# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for Maxwell's Equations in market dynamics."""

import numpy as np
import pytest

from core.physics.maxwell import (
    compute_market_field_curl,
    compute_market_field_divergence,
    propagate_price_wave,
    wave_energy,
)


class TestMaxwellEquations:
    """Test suite for Maxwell's equations."""
    
    def test_divergence_basic(self):
        """Test field divergence computation."""
        field = np.array([100, 150, 200, 180, 160])
        divergence = compute_market_field_divergence(field)
        # Divergence should have same length
        assert len(divergence) == len(field)
    
    def test_divergence_constant_field(self):
        """Test divergence of constant field is zero."""
        field = np.array([100, 100, 100, 100])
        divergence = compute_market_field_divergence(field)
        # Constant field has zero divergence
        assert np.allclose(divergence, 0.0, atol=1e-10)
    
    def test_curl_basic(self):
        """Test field curl computation."""
        field_x = np.array([1.0, 1.5, 2.0, 1.8, 1.6])
        field_y = np.array([100, 120, 110, 130, 125])
        curl = compute_market_field_curl(field_x, field_y)
        assert len(curl) == len(field_x)
    
    def test_wave_propagation_basic(self):
        """Test price wave propagation."""
        initial_price = 100.0
        amplitude = 5.0
        frequency = 0.5
        time = 0.0
        
        price = propagate_price_wave(
            initial_price, amplitude, frequency, time
        )
        # At t=0, wave should be at maximum (cos(0) = 1)
        expected = initial_price + amplitude
        assert abs(price - expected) < 1e-10
    
    def test_wave_energy_basic(self):
        """Test wave energy calculation."""
        amplitude = 5.0
        frequency = 0.5
        mass = 1000.0
        energy = wave_energy(amplitude, frequency, mass)
        # Energy should be positive
        assert energy > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
