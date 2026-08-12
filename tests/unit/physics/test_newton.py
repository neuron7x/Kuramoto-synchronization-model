# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for Newton's Laws applied to market dynamics."""

import numpy as np
import pytest

from core.physics.newton import (
    compute_acceleration,
    compute_force,
    compute_momentum,
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


def test_acceleration_mass_guard_protects_only_near_zero() -> None:
    """`np.where(np.abs(mass) < 1e-10, 1e-10, mass)` divides by real mass, guards only ~0.

    Under `Lt -> GtE` the where inverts: every real mass is replaced by 1e-10 (F=ma explodes)
    while a genuinely zero mass passes through to a divide-by-zero. A normal mass must give the
    exact Newtonian acceleration.
    """
    import numpy as np

    from core.physics.newton import compute_acceleration

    assert compute_acceleration(10.0, 2.0) == pytest.approx(5.0)  # F/m, not F/1e-10 (scalar path)
    assert np.isfinite(compute_acceleration(1.0, 0.0))  # near-zero scalar mass stays finite

    # Array path (np.where): a real mass must divide, only the ~0 entry is protected.
    accel = compute_acceleration(np.array([10.0, 1.0]), np.array([2.0, 0.0]))
    assert accel[0] == pytest.approx(5.0), "array-mass path replaced a real mass with 1e-10"
    assert np.isfinite(accel[1])


def test_price_acceleration_zero_below_two_velocity_points() -> None:
    """`if velocity.size < 2: return zeros` -- acceleration needs two velocities to difference.

    Under `Lt -> GtE` a well-resolved series returns all-zero acceleration (a flat, false
    calm), and a too-short one is differenced into a shape error. A rising-then-turning price
    path must produce a non-zero acceleration.
    """
    import numpy as np

    from core.physics.newton import compute_price_acceleration

    prices = np.array([100.0, 102.0, 105.0, 104.0, 108.0])
    accel = compute_price_acceleration(prices)
    assert np.any(accel != 0.0), "a curved price path must have non-zero acceleration"
