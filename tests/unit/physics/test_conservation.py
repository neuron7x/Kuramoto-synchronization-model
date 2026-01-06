# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for Conservation Laws in market dynamics."""

import numpy as np
import pytest

from core.physics.conservation import (
    check_energy_conservation,
    check_momentum_conservation,
    compute_market_energy,
    compute_market_momentum,
)


class TestConservationLaws:
    """Test suite for conservation laws."""
    
    def test_energy_conservation_perfect(self):
        """Test perfect energy conservation."""
        energy_before = 100.0
        energy_after = 100.0
        conserved, change = check_energy_conservation(energy_before, energy_after)
        assert conserved is True
        assert change == 0.0
    
    def test_energy_conservation_within_tolerance(self):
        """Test energy conservation within tolerance."""
        energy_before = 100.0
        energy_after = 100.5
        conserved, change = check_energy_conservation(
            energy_before, energy_after, tolerance=0.01
        )
        assert conserved is True
        assert abs(change - 0.005) < 1e-10
    
    def test_energy_conservation_violation(self):
        """Test energy conservation violation."""
        energy_before = 100.0
        energy_after = 110.0
        conserved, change = check_energy_conservation(
            energy_before, energy_after, tolerance=0.01
        )
        assert conserved is False
        assert abs(change - 0.1) < 1e-10
    
    def test_momentum_conservation_perfect(self):
        """Test perfect momentum conservation."""
        momentum_before = 50.0
        momentum_after = 50.0
        conserved, change = check_momentum_conservation(
            momentum_before, momentum_after
        )
        assert conserved is True
        assert change == 0.0
    
    def test_market_energy_basic(self):
        """Test basic market energy computation."""
        prices = np.array([100, 102, 104])
        volumes = np.array([1.0, 1.0, 1.0])
        energy = compute_market_energy(prices, volumes)
        # Energy should be positive
        assert energy >= 0.0
    
    def test_market_momentum_basic(self):
        """Test basic market momentum computation."""
        prices = np.array([100, 102, 104])
        volumes = np.array([1.0, 1.0, 1.0])
        momentum = compute_market_momentum(prices, volumes)
        # Should compute successfully
        assert np.isfinite(momentum)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
