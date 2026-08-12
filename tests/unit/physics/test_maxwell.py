# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
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

        price = propagate_price_wave(initial_price, amplitude, frequency, time)
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


def test_divergence_finite_difference_boundaries() -> None:
    """`n < 2 -> zeros` and `n > 2 -> central differences` are the FD stencil boundaries.

    Under `Lt -> GtE` a real field returns all-zero divergence; under `Gt -> LtE` the interior
    points skip the central difference and stay zero. A linear ramp has constant slope
    everywhere, so its divergence must equal that slope at every point including the interior.
    """
    assert np.all(compute_market_field_divergence(np.array([42.0])) == 0.0)  # n < 2

    ramp = np.arange(5.0)  # slope 1 -> divergence 1.0 everywhere (central diff on interior)
    div = compute_market_field_divergence(ramp, dx=1.0)
    assert np.allclose(div, 1.0), f"interior central-difference divergence wrong: {div}"

    two = compute_market_field_divergence(np.array([100.0, 200.0]), dx=1.0)
    assert np.allclose(two, [100.0, 100.0])  # n == 2 forward/backward, non-zero


def test_curl_finite_difference_boundaries() -> None:
    """The curl stencil mirrors divergence: `n < 2 -> zeros`, interior uses central differences.

    A field rotating with x (Fy = x, Fx = 0) has constant curl 1.0 everywhere; under the
    mutated size guards the interior would stay 0 (Gt->LtE) or the whole field zero (Lt->GtE).
    """
    with pytest.raises(ValueError, match="same length"):
        compute_market_field_curl(np.zeros(3), np.zeros(4))

    assert np.all(compute_market_field_curl(np.array([1.0]), np.array([1.0])) == 0.0)  # n < 2

    x = np.arange(5.0)
    fx = 2.0 * x  # dFx/dy = 2 (varies -> pins the dFx/dy central-difference branch too)
    fy = x.copy()  # dFy/dx = 1  ->  curl = 1 - 2 = -1 everywhere
    curl = compute_market_field_curl(fx, fy, dx=1.0, dy=1.0)
    assert np.allclose(curl, -1.0), f"interior central-difference curl wrong: {curl}"
