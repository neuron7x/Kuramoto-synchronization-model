# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integration tests for physics-inspired trading framework."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from numpy.typing import NDArray

from backtest.physics_validation import PhysicsBacktestValidator
from core.indicators.physics import (
    EnergyConservationIndicator,
    MarketGravityIndicator,
    MarketMomentumIndicator,
    ThermodynamicEquilibriumIndicator,
    UncertaintyQuantificationIndicator,
)
from core.physics import (
    check_proxy_drift,
    compute_market_gravity,
    compute_momentum,
    compute_price_velocity,
    compute_volatility_energy_proxy,
)


class TestPhysicsIntegration:
    """Integration tests for physics framework."""

    @pytest.fixture
    def sample_data(self) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
        """Generate sample data for testing."""
        np.random.seed(42)
        prices = np.linspace(100, 120, 50) + np.random.randn(50) * 2
        volumes = 1000 + np.random.randn(50) * 100
        volumes = np.abs(volumes)
        returns = np.diff(prices) / prices[:-1]
        return prices, volumes, returns

    def test_end_to_end_momentum_strategy(self, sample_data: Any) -> None:
        """Test end-to-end momentum strategy."""
        prices, volumes, _ = sample_data

        # Compute velocity
        velocity = compute_price_velocity(prices)

        # Compute momentum (smoke check — direct compute_momentum call must produce finite output)
        momentum = compute_momentum(volumes[1:], velocity[1:])
        assert np.all(np.isfinite(momentum))

        # Use momentum indicator
        indicator = MarketMomentumIndicator(window=20)
        result = indicator.transform(prices, volumes=volumes)

        # Should produce valid momentum
        assert np.isfinite(result.value)
        assert "window" in result.metadata

    def test_end_to_end_gravity_strategy(self, sample_data: Any) -> None:
        """Test end-to-end gravity strategy."""
        prices, volumes, _ = sample_data

        # Compute gravity field (smoke check — direct compute_market_gravity call must produce finite output)
        gravity = compute_market_gravity(prices, volumes)
        assert np.all(np.isfinite(gravity))

        # Use gravity indicator
        indicator = MarketGravityIndicator()
        result = indicator.transform(prices, volumes=volumes)

        # Should compute center of gravity
        assert np.isfinite(result.value)
        assert "center_of_gravity" in result.metadata
        assert result.metadata["center_of_gravity"] > 0

    def test_conservation_checks_in_backtest(self, sample_data: Any) -> None:
        """Test conservation checks during backtesting."""
        prices, volumes, _ = sample_data

        # Split data into before/after
        mid = len(prices) // 2
        prices1 = prices[:mid]
        prices2 = prices[mid:]
        volumes1 = volumes[:mid]
        volumes2 = volumes[mid:]

        # Compute energies
        energy1 = compute_volatility_energy_proxy(prices1, volumes1)
        energy2 = compute_volatility_energy_proxy(prices2, volumes2)

        # Check conservation
        conserved, change = check_proxy_drift(energy1, energy2, tolerance=0.2)

        # Should compute without errors
        assert isinstance(conserved, bool)
        assert np.isfinite(change)

    def test_physics_backtest_validator(self, sample_data: Any) -> None:
        """Test physics validator in backtest context."""
        prices, volumes, _ = sample_data

        validator = PhysicsBacktestValidator(energy_tolerance=0.2, momentum_tolerance=0.2)

        # Simulate multiple timesteps
        for t in range(10, len(prices) - 10):
            prices_before = prices[t - 10 : t]
            prices_after = prices[t : t + 10]
            volumes_before = volumes[t - 10 : t]
            volumes_after = volumes[t : t + 10]

            result = validator.check_timestep(
                timestep=t,
                prices_before=prices_before,
                prices_after=prices_after,
                volumes_before=volumes_before,
                volumes_after=volumes_after,
            )

            assert "energy_conserved" in result
            assert "momentum_conserved" in result

        metrics = validator.get_metrics()
        assert metrics.total_timesteps > 0

    def test_multi_indicator_regime_detection(self, sample_data: Any) -> None:
        """Test combining multiple indicators for regime detection."""
        prices, volumes, returns = sample_data

        # Energy conservation
        conservation_ind = EnergyConservationIndicator(tolerance=0.15)
        cons_result = conservation_ind.transform(prices, volumes=volumes)

        # Thermodynamic equilibrium
        equilibrium_ind = ThermodynamicEquilibriumIndicator(window=15)
        eq_result = equilibrium_ind.transform(returns)

        # Both should produce valid results
        assert np.isfinite(cons_result.value)
        assert np.isfinite(eq_result.value)

        # Metadata should be present
        assert "conserved" in cons_result.metadata
        assert "equilibrium" in eq_result.metadata

        # Determine regime
        stable_regime = cons_result.metadata["conserved"] and eq_result.metadata["equilibrium"]

        # Should be deterministic
        assert isinstance(stable_regime, bool)

    def test_uncertainty_based_position_sizing(self, sample_data: Any) -> None:
        """Test using uncertainty for position sizing."""
        prices, _, _ = sample_data

        # Compute uncertainty
        uncertainty_ind = UncertaintyQuantificationIndicator()
        result = uncertainty_ind.transform(prices)

        # Position size inversely proportional to uncertainty
        max_position = 100.0
        uncertainty_product = result.value

        # Avoid division by zero
        if uncertainty_product > 0:
            position_size = max_position / (1.0 + uncertainty_product)
        else:
            position_size = max_position

        # Should produce valid position size
        assert 0 <= position_size <= max_position
        assert np.isfinite(position_size)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
