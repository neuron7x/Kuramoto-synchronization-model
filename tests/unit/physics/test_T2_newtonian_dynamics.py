# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T2 — Newtonian Inertial Dynamics tests.

Falsifying tests for F=ma dynamics and TACL free energy gate.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.newtonian_dynamics import FreeEnergyGate, NewtonianPriceDynamics


@pytest.fixture
def dynamics() -> NewtonianPriceDynamics:
    return NewtonianPriceDynamics(ema_span=20, dt=1.0)


class TestAccelerationZeroForBalancedOrderflow:
    """If net OFI = 0, acceleration must be zero."""

    def test_balanced_ofi(self, dynamics):
        ofi = np.array([100.0, -50.0, -50.0])  # sum = 0
        force = dynamics.compute_force(ofi)
        assert force == 0.0
        accel = dynamics.compute_acceleration(force, 1000.0)
        assert accel == 0.0

    def test_empty_ofi(self, dynamics):
        force = dynamics.compute_force(np.array([]))
        assert force == 0.0


class TestMassScaling:
    """High volume asset has lower acceleration for same force."""

    def test_higher_mass_lower_acceleration(self, dynamics):
        force = 100.0
        mass_high = dynamics.compute_mass(np.full(30, 10000.0))
        mass_low = dynamics.compute_mass(np.full(30, 100.0))
        a_high = dynamics.compute_acceleration(force, mass_high)
        a_low = dynamics.compute_acceleration(force, mass_low)
        assert abs(a_high) < abs(a_low), "Higher mass → lower acceleration"

    def test_mass_positive(self, dynamics):
        mass = dynamics.compute_mass(np.array([0.0, 0.0, 0.0]))
        assert mass > 0, "Mass must be positive (clamped)"


class TestEulerIntegration:
    """Euler integration preserves basic physics."""

    def test_zero_acceleration_constant_velocity(self):
        p, v = NewtonianPriceDynamics.euler_step(100.0, 1.0, 0.0, dt=1.0)
        assert p == 101.0  # p + v*dt
        assert v == 1.0  # unchanged

    def test_positive_acceleration_increases_velocity(self):
        p, v = NewtonianPriceDynamics.euler_step(100.0, 0.0, 2.0, dt=1.0)
        assert v == 2.0  # v + a*dt
        assert p == 101.0  # p + 0*1 + 0.5*2*1²

    def test_step_method_integrates_correctly(self, dynamics):
        vol_hist = np.full(30, 500.0)
        ofi = np.array([50.0])
        new_p, new_v, accel = dynamics.step(100.0, 0.0, vol_hist, ofi)
        assert accel > 0, "Positive OFI → positive acceleration"
        assert new_p > 100.0, "Price should increase"


class TestFreeEnergyGate:
    """TACL free energy constraint: dF = dU - T·dS ≤ 0."""

    def test_rejects_positive_dF(self):
        gate = FreeEnergyGate(T=0.60)
        # dU = 1.0, dS = 0.0 → dF = 1.0 > 0 → reject
        assert gate.gate(dU=1.0, dS=0.0) is False

    def test_allows_negative_dF(self):
        gate = FreeEnergyGate(T=0.60)
        # dU = -1.0, dS = 1.0 → dF = -1.0 - 0.6 = -1.6 → allow
        assert gate.gate(dU=-1.0, dS=1.0) is True

    def test_allows_zero_dF(self):
        gate = FreeEnergyGate(T=0.60)
        # dU = 0.6, dS = 1.0 → dF = 0.6 - 0.6 = 0.0 → allow (≤ 0)
        assert gate.gate(dU=0.6, dS=1.0) is True

    def test_rejects_position_increase_when_dF_positive(self):
        gate = FreeEnergyGate(T=0.60)
        # Scenario: increasing concentration (dS < 0) while losing money (dU > 0)
        assert gate.gate(dU=0.5, dS=-0.5) is False

    def test_temperature_must_be_positive(self):
        with pytest.raises(ValueError, match="> 0"):
            FreeEnergyGate(T=0.0)

    def test_free_energy_change_value(self):
        gate = FreeEnergyGate(T=0.60)
        dF = gate.free_energy_change(dU=1.0, dS=2.0)
        assert abs(dF - (1.0 - 0.60 * 2.0)) < 1e-12
