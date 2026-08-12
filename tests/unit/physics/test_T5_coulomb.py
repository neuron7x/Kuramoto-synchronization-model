# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T5 — Coulomb Electrostatic Interaction tests.

Market sign convention: same-direction OFI = attraction (flipped Coulomb).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.coulomb import CoulombInteraction


@pytest.fixture
def coulomb() -> CoulombInteraction:
    return CoulombInteraction(alpha=0.1, lookback=10)


@pytest.fixture
def distances_2x2():
    return np.array([[0.0, 0.5], [0.5, 0.0]])


class TestSameSignChargesAttract:
    """Market convention: same-sign OFI → attraction (negative force → adjacency increases)."""

    def test_same_sign_produces_negative_force(self, distances_2x2):
        """Same sign charges in market → F_market < 0 (attraction)."""
        charges = np.array([1.0, 1.0])
        forces = CoulombInteraction.compute_forces(charges, distances_2x2)
        # Market sign flip: same sign → attraction → negative F_market
        assert forces[0, 1] < 0, "Same-sign OFI should produce attraction (negative force)"


class TestOppositeSignChargesRepel:
    """Opposite OFI → repulsion (positive force → adjacency decreases)."""

    def test_opposite_sign_produces_positive_force(self, distances_2x2):
        charges = np.array([1.0, -1.0])
        forces = CoulombInteraction.compute_forces(charges, distances_2x2)
        # Market sign flip: opposite sign → repulsion → positive F_market
        assert forces[0, 1] > 0, "Opposite-sign OFI should produce repulsion"


class TestZeroChargeZeroForce:
    """Zero OFI → zero force."""

    def test_zero_charge(self, distances_2x2):
        charges = np.array([0.0, 1.0])
        forces = CoulombInteraction.compute_forces(charges, distances_2x2)
        assert forces[0, 1] == 0.0
        assert forces[1, 0] == 0.0


class TestAdjacencyUpdateBounded:
    """Updated adjacency stays in valid range [0, 1]."""

    def test_remains_in_range(self, coulomb):
        rng = np.random.default_rng(42)
        A = rng.uniform(0, 1, (5, 5))
        np.fill_diagonal(A, 0.0)
        forces = rng.uniform(-1, 1, (5, 5))
        np.fill_diagonal(forces, 0.0)

        A_new = coulomb.update_adjacency(A, forces)
        assert np.all(A_new >= 0.0), "Adjacency must be ≥ 0"
        assert np.all(A_new <= 1.0), "Adjacency must be ≤ 1"
        assert np.all(np.diag(A_new) == 0.0), "Diagonal must be zero"

    def test_repeated_updates_stable(self, coulomb):
        """100 updates should not blow up."""
        N = 5
        A = np.full((N, N), 0.5)
        np.fill_diagonal(A, 0.0)

        rng = np.random.default_rng(7)
        for _ in range(100):
            forces = rng.uniform(-1, 1, (N, N))
            np.fill_diagonal(forces, 0.0)
            A = coulomb.update_adjacency(A, forces)

        assert np.all(np.isfinite(A))
        assert np.all(A >= 0.0)
        assert np.all(A <= 1.0)


class TestChargeComputation:
    def test_positive_ofi_positive_charge(self, coulomb):
        T = 20
        ofi = np.ones((T, 2)) * 10.0  # constant positive OFI
        charges = coulomb.compute_charges(ofi)
        # Constant series → σ → 0 but clamped → large positive charge
        assert np.all(charges > 0)

    def test_forces_normalised(self, distances_2x2):
        charges = np.array([5.0, 3.0])
        forces = CoulombInteraction.compute_forces(charges, distances_2x2)
        assert np.max(np.abs(forces)) <= 1.0 + 1e-12, "Forces must be normalised to [-1, 1]"


class TestInputValidation:
    def test_alpha_bounds(self):
        with pytest.raises(ValueError):
            CoulombInteraction(alpha=0.0)
        with pytest.raises(ValueError):
            CoulombInteraction(alpha=1.5)

    def test_force_shape_mismatch(self):
        with pytest.raises(ValueError, match="must be"):
            CoulombInteraction.compute_forces(np.array([1.0, 2.0]), np.ones((3, 3)))
