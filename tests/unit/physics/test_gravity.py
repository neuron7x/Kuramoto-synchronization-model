# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for Universal Gravitation in market dynamics."""

import numpy as np
import pytest

from core.physics.gravity import (
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
        expected = 1.0 * (100.0 * 50.0) / (10.0**2)
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


def test_compute_market_gravity_guards_and_self_exclusion() -> None:
    """The N-body sum guards: empty -> empty, length mismatch -> raise, and i != j (no self-pull).

    Under the mutated comparisons an empty input proceeds into an error, a length mismatch is
    accepted, and (critically) `i != j -> i == j` sums each body's pull on ITSELF at zero
    distance -> a non-finite gravity. A two-body field must be finite and non-zero.
    """
    import numpy as np

    from core.physics.gravity import compute_market_gravity

    assert compute_market_gravity(np.array([]), np.array([])).size == 0  # n == 0 branch

    with pytest.raises(ValueError, match="same length"):
        compute_market_gravity(np.array([100.0, 101.0]), np.array([1.0]))  # size != n

    gravity = compute_market_gravity(np.array([100.0, 105.0]), np.array([10.0, 10.0]))
    assert gravity.shape == (2,)
    assert np.all(np.isfinite(gravity)), "self-pull (i == j) at zero distance made gravity non-finite"
    assert np.any(gravity != 0.0)


def test_gravity_center_volume_weighted_unless_volumeless() -> None:
    """`if total_volume == 0: return mean(prices)` -- fall back to unweighted only with no volume.

    Under `Eq -> NotEq` a real volume profile is discarded for the plain mean, and a
    volumeless series divides by zero. The volume-weighted centre must differ from the mean
    when the volume is lopsided.
    """
    import numpy as np

    from core.physics.gravity import market_gravity_center

    prices = np.array([100.0, 200.0])
    weighted = market_gravity_center(prices, np.array([9.0, 1.0]))  # mass at 100
    assert weighted == pytest.approx(110.0), "volume weighting was discarded for the plain mean"

    volumeless = market_gravity_center(prices, np.array([0.0, 0.0]))
    assert volumeless == pytest.approx(150.0)  # falls back to unweighted mean
