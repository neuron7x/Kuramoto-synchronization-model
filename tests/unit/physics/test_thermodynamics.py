# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unit tests for Thermodynamics in market dynamics."""

import numpy as np
import pytest

from core.physics.thermodynamics import (
    boltzmann_entropy,
    compute_free_energy,
    compute_market_temperature,
    is_thermodynamic_equilibrium,
)


class TestThermodynamics:
    """Test suite for thermodynamic laws."""
    
    def test_boltzmann_entropy_uniform(self):
        """Test entropy for uniform distribution."""
        # Uniform distribution has maximum entropy
        probs = np.array([0.25, 0.25, 0.25, 0.25])
        entropy = boltzmann_entropy(probs)
        # Should be positive
        assert entropy > 0
    
    def test_boltzmann_entropy_certain(self):
        """Test entropy for certain outcome."""
        # Certain outcome has zero entropy
        probs = np.array([1.0, 0.0, 0.0, 0.0])
        entropy = boltzmann_entropy(probs)
        assert abs(entropy) < 1e-10
    
    def test_market_temperature_basic(self):
        """Test market temperature calculation."""
        volatility = 0.02  # 2% volatility
        temp = compute_market_temperature(volatility)
        # Temperature should be positive
        assert temp > 0
    
    def test_market_temperature_scaling(self):
        """Test temperature scales with volatility squared."""
        vol1 = 0.01
        vol2 = 0.02
        temp1 = compute_market_temperature(vol1)
        temp2 = compute_market_temperature(vol2)
        # Doubling volatility should quadruple temperature
        assert abs(temp2 - 4 * temp1) < 1e-6
    
    def test_free_energy_basic(self):
        """Test Helmholtz free energy calculation."""
        internal_energy = 100.0
        temperature = 300.0
        entropy = 0.5
        free_energy = compute_free_energy(internal_energy, temperature, entropy)
        expected = 100.0 - 300.0 * 0.5
        assert abs(free_energy - expected) < 1e-10
    
    def test_thermal_equilibrium_same_temp(self):
        """Test equilibrium detection for same temperature."""
        temp1 = 300.0
        temp2 = 300.0
        assert is_thermodynamic_equilibrium(temp1, temp2)
    
    def test_thermal_equilibrium_within_tolerance(self):
        """Test equilibrium within tolerance."""
        temp1 = 300.0
        temp2 = 310.0
        # Within 5% tolerance
        assert is_thermodynamic_equilibrium(temp1, temp2, tolerance=0.05)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
