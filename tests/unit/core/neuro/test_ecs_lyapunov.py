# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for ECS Lyapunov regulator — homeostatic stability guarantees."""

import pytest

from core.neuro.ecs_lyapunov import ECSLyapunovRegulator
from core.neuro.signal_bus import NeuroSignalBus

pytestmark = pytest.mark.L3


@pytest.fixture
def bus():
    return NeuroSignalBus()


@pytest.fixture
def reg(bus):
    return ECSLyapunovRegulator(bus)


class TestLyapunovDescent:
    """Lyapunov function V must decrease monotonically."""

    def test_V_decreases_under_constant_stress(self, reg):
        """Under constant stress, after initial transient V should decrease."""
        stress = 0.5
        # Let transient settle
        for _ in range(50):
            reg.step(stress, dt=0.5)
        # Now measure monotonic descent
        prev_V = reg._lyapunov(reg.free_energy, reg.compensatory_factor, reg.stress_integral)
        violations = 0
        for _ in range(200):
            result = reg.step(stress, dt=0.5)
            if result["lyapunov_V"] > prev_V + 1e-10:
                violations += 1
            prev_V = result["lyapunov_V"]
        assert violations == 0, f"V increased {violations} times (should be monotone)"

    def test_stability_guarantee_1000_steps(self, reg):
        """dV/dt <= 0 for all steps once the system has settled.

        Note: when V is near zero and external stress injects energy,
        V must increase initially. The Lyapunov guarantee applies to
        the *autonomous* dynamics; here we verify that once V is
        non-trivial, the correction mechanism prevents runaway growth.
        """
        # Warm up with constant stress to build up state
        for _ in range(100):
            reg.step(0.5, dt=0.5)

        # Now run with same constant stress — V should not increase
        prev_V = reg._lyapunov(reg.free_energy, reg.compensatory_factor, reg.stress_integral)
        violations = 0
        for i in range(1000):
            result = reg.step(0.5, dt=0.5)
            if result["lyapunov_V"] > prev_V + 1e-8:
                violations += 1
            prev_V = result["lyapunov_V"]
        assert violations == 0, f"V increased {violations} times after settling"


class TestFreeEnergyConvergence:
    """FE should converge toward target (0) when stress is removed."""

    def test_converges_to_target(self, reg):
        """After stress removal, FE should converge toward 0."""
        # Apply stress
        for _ in range(100):
            reg.step(1.0, dt=0.5)
        fe_after_stress = abs(reg.free_energy)
        assert fe_after_stress > 0.01, "FE should be non-zero under stress"

        # Remove stress, let recover
        for _ in range(2000):
            reg.step(0.0, dt=0.5)
        assert abs(reg.free_energy) < fe_after_stress, "FE should decrease after stress removal"

    def test_recovery_after_stress_removal(self, reg):
        """FE returns toward baseline after stress spike."""
        # Baseline
        for _ in range(50):
            reg.step(0.0, dt=0.5)
        baseline_fe = abs(reg.free_energy)

        # Spike
        for _ in range(30):
            reg.step(2.0, dt=0.5)
        spike_fe = abs(reg.free_energy)
        assert spike_fe > baseline_fe + 0.01

        # Recover
        for _ in range(2000):
            reg.step(0.0, dt=0.5)
        recovered_fe = abs(reg.free_energy)
        assert recovered_fe < spike_fe, "FE should recover after stress removal"


class TestCompensatoryFactor:
    """Compensatory factor adapts to counteract stress."""

    def test_cf_adapts_under_stress(self, reg):
        """CF should grow when FE is above target."""
        for _ in range(500):
            reg.step(1.0, dt=0.5)
        assert (
            abs(reg.compensatory_factor) > 1e-4
        ), f"CF should adapt to counteract sustained stress, got {reg.compensatory_factor}"


class TestRiskMultiplier:
    """Risk multiplier mapping from free energy."""

    def test_bounds(self, reg):
        """Multiplier always in [0.1, 1.0]."""
        # At rest
        m = reg.get_risk_multiplier()
        assert 0.1 <= m <= 1.0

        # Under stress
        for _ in range(100):
            reg.step(5.0, dt=0.5)
        m = reg.get_risk_multiplier()
        assert 0.1 <= m <= 1.0

    def test_stress_spike_decreases_multiplier(self, reg):
        """High FE → lower risk multiplier."""
        m_rest = reg.get_risk_multiplier()
        for _ in range(100):
            reg.step(3.0, dt=0.5)
        m_stress = reg.get_risk_multiplier()
        assert m_stress < m_rest, "Stress should lower risk multiplier"

    def test_zero_fe_gives_max_multiplier(self, reg):
        """FE = 0 → multiplier = 1.0."""
        reg.free_energy = 0.0
        assert reg.get_risk_multiplier() == 1.0


class TestBusPublishing:
    """ECS publishes free energy to bus."""

    def test_publishes_fe_to_bus(self, bus, reg):
        reg.step(1.0, dt=0.5)
        snapshot = bus.snapshot()
        assert snapshot.ecs_free_energy >= 0.0
