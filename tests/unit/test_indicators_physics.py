# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
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
    """Test suite for UncertaintyQuantificationIndicator (Gabor framing)."""

    def test_basic_uncertainty(self):
        """Time-frequency product Δt·Δf is positive with renamed Gabor metadata."""
        indicator = UncertaintyQuantificationIndicator()
        prices = np.array([100, 102, 101, 103, 102, 104, 103, 105], dtype=float)

        result = indicator.transform(prices)

        # Δt·Δf is a positive feature value; metadata uses the Gabor naming.
        assert result.value > 0
        assert "time_spread" in result.metadata
        assert "freq_spread" in result.metadata

    def test_well_resolved_series_respects_gabor_bound(self):
        """A well-resolved price-like series obeys INV-GABOR1: Δt·Δf ≥ 1/(4π)."""
        indicator = UncertaintyQuantificationIndicator()
        idx = np.arange(512, dtype=float)
        env = np.exp(-((idx - 256.0) ** 2) / (2.0 * 80.0**2))
        prices = 100.0 + env * np.sin(2.0 * np.pi * 0.05 * idx)

        result = indicator.transform(prices)

        assert result.value >= (1.0 / (4.0 * np.pi)) * (1.0 - 1e-9)

    def test_uncertainty_single_price(self):
        """Single sample → degenerate 0.0, no raise (indicator stays total)."""
        indicator = UncertaintyQuantificationIndicator()
        prices = np.array([100], dtype=float)

        result = indicator.transform(prices)

        assert result.value == 0.0

    def test_uncertainty_constant_series(self):
        """Constant series has no fluctuation energy → degenerate 0.0 flagged."""
        indicator = UncertaintyQuantificationIndicator()
        prices = np.full(16, 100.0)

        result = indicator.transform(prices)

        assert result.value == 0.0
        assert result.metadata.get("degenerate") is True

    def test_uncertainty_under_resolved_window_flagged_degenerate(self):
        """Under-resolved short window → degenerate 0.0, NOT a 'max compact' value.

        A two-sample step whose fluctuation collapses power into one sample
        produces a sub-Gabor product. The indicator must surface it as
        degenerate (flagged) rather than reporting value≈0, which a position
        sizer could misread as maximal time-frequency confidence.
        """
        indicator = UncertaintyQuantificationIndicator()
        # prices = [100, 101] → fluctuation [-0.5, 0.5]: Δt collapses, sub-bound.
        prices = np.array([100.0, 101.0])

        result = indicator.transform(prices)

        assert result.value == 0.0
        assert result.metadata.get("degenerate") is True
        assert "time_spread" not in result.metadata


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
