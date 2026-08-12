# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for SerotoninODE — 5-HT dynamics with Lyapunov stability.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import pytest

from core.neuro.serotonin_ode import SerotoninODE, SerotoninODEParams


@pytest.fixture
def params() -> SerotoninODEParams:
    return SerotoninODEParams()


@pytest.fixture
def ode(params: SerotoninODEParams) -> SerotoninODE:
    return SerotoninODE(params)


# ── Steady state convergence ─────────────────────────────────────────


@pytest.mark.L3
class TestSteadyState:
    """Under zero stress, level should converge to baseline."""

    def test_converges_to_baseline(self, params: SerotoninODEParams) -> None:
        """INV-5HT1: zero-stress trajectory converges to baseline (Lyapunov stability)."""
        ode = SerotoninODE(params, level=0.8, desensitization=0.0)
        for _ in range(5000):
            ode.step(stress=0.0, dt=0.1)
        assert ode.level == pytest.approx(params.baseline, abs=0.02)

    def test_low_start_converges_up(self, params: SerotoninODEParams) -> None:
        """INV-5HT1: low initial level converges up to baseline under zero stress."""
        ode = SerotoninODE(params, level=0.05, desensitization=0.0)
        for _ in range(5000):
            ode.step(stress=0.0, dt=0.1)
        assert ode.level == pytest.approx(params.baseline, abs=0.02)


# ── Stress response ─────────────────────────────────────────────────


@pytest.mark.L3
class TestStressResponse:
    """High stress input should increase 5-HT level."""

    def test_stress_raises_level(self, params: SerotoninODEParams) -> None:
        """INV-5HT3: higher stress input produces higher serotonin level."""
        ode = SerotoninODE(params, level=params.baseline)
        for _ in range(100):
            ode.step(stress=1.0, dt=0.1)
        assert ode.level > params.baseline


# ── Desensitisation ──────────────────────────────────────────────────


@pytest.mark.L3
class TestDesensitisation:
    """Sustained stress → desensitisation → moderation of level."""

    def test_sustained_stress_increases_desens(self, params: SerotoninODEParams) -> None:
        """INV-5HT4: sustained stress builds receptor desensitisation."""
        ode = SerotoninODE(params, level=params.baseline)
        # Drive level above threshold with stress
        for _ in range(500):
            ode.step(stress=1.0, dt=0.1)
        assert ode.desensitization > 0.0

    def test_desens_moderates_level(self, params: SerotoninODEParams) -> None:
        """Level with desens should be lower than without (after sustained stress).

        Use moderate stress (0.3) to keep both ODE variants below the
        clamp at 1.0 so the desensitisation effect is observable.
        """
        # With desensitisation (default, but amplified eta for clearer effect)
        params_with = SerotoninODEParams(eta=0.05, delta=0.1)
        ode_with = SerotoninODE(params_with, level=params_with.baseline)
        for _ in range(3000):
            ode_with.step(stress=0.3, dt=0.1)

        # Without desensitisation (eta=0 → no desens buildup)
        params_no = SerotoninODEParams(eta=0.0, delta=0.1)
        ode_without = SerotoninODE(params_no, level=params_no.baseline)
        for _ in range(3000):
            ode_without.step(stress=0.3, dt=0.1)

        assert ode_with.level < ode_without.level


# ── RK4 accuracy ─────────────────────────────────────────────────────


@pytest.mark.L3
class TestRK4Accuracy:
    """RK4 should be more accurate than Euler for the same step size."""

    def test_rk4_vs_euler(self) -> None:
        # Use short integration (5 time units) so we compare transient
        # behaviour, not the converged steady state.
        params = SerotoninODEParams()
        T = 5.0
        dt_coarse = 0.5
        n_coarse = int(T / dt_coarse)

        # Reference: RK4 with very fine step
        dt_fine = 0.0001
        n_fine = int(T / dt_fine)
        ref = SerotoninODE(params, level=0.1, desensitization=0.0)
        for _ in range(n_fine):
            ref.step(stress=0.5, dt=dt_fine)
        ref_level = ref.level

        # RK4 with coarse step
        rk4 = SerotoninODE(params, level=0.1, desensitization=0.0)
        for _ in range(n_coarse):
            rk4.step(stress=0.5, dt=dt_coarse)

        # Euler with same coarse step
        euler = SerotoninODE(params, level=0.1, desensitization=0.0)
        for _ in range(n_coarse):
            level, desens = euler.level, euler.desensitization
            dl, dd = euler._derivatives(level, desens, 0.5)
            euler.level = max(0.0, min(1.0, level + dt_coarse * dl))
            euler.desensitization = max(0.0, desens + dt_coarse * dd)

        rk4_err = abs(rk4.level - ref_level)
        euler_err = abs(euler.level - ref_level)
        assert (
            rk4_err < euler_err
        ), f"RK4 error {rk4_err:.6e} should be < Euler error {euler_err:.6e}"


# ── Lyapunov stability ──────────────────────────────────────────────


@pytest.mark.L3
class TestLyapunovStability:
    """Lyapunov function V should decrease monotonically for convergent trajectories."""

    def test_verify_lyapunov_normal_trajectory(self, params: SerotoninODEParams) -> None:
        """INV-5HT1: Lyapunov function V non-increasing along zero-stress trajectory."""
        # Use params without desensitisation coupling for clean Lyapunov
        # (desens introduces cross-term that can cause small V bumps)
        clean_params = SerotoninODEParams(eta=0.0, delta=0.0)
        ode = SerotoninODE(clean_params, level=0.8, desensitization=0.0)
        trajectory: list[tuple[float, float]] = [(ode.level, ode.desensitization)]
        for _ in range(2000):
            ode.step(stress=0.0, dt=0.1)
            trajectory.append((ode.level, ode.desensitization))
        assert ode.verify_lyapunov(trajectory)

    def test_lyapunov_monotonicity(self, params: SerotoninODEParams) -> None:
        """INV-5HT1: V(t+1) ≤ V(t) + eps for every step of the trajectory."""
        # Use params without desensitisation for monotonic V decrease
        clean_params = SerotoninODEParams(eta=0.0, delta=0.0)
        ode = SerotoninODE(clean_params, level=0.8, desensitization=0.0)
        trajectory: list[tuple[float, float]] = [(ode.level, ode.desensitization)]
        for _ in range(2000):
            ode.step(stress=0.0, dt=0.1)
            trajectory.append((ode.level, ode.desensitization))

        # V should decrease over time
        v_values = [ode._lyapunov(*s) for s in trajectory]
        for i in range(1, len(v_values)):
            assert v_values[i] <= v_values[i - 1] + 1e-12

    def test_short_trajectory_passes(self, ode: SerotoninODE) -> None:
        assert ode.verify_lyapunov([])
        assert ode.verify_lyapunov([(0.3, 0.0)])


# ── Boundedness ──────────────────────────────────────────────────────


@pytest.mark.L3
class TestBoundedness:
    """Level should stay in [0, 1] for any reasonable input."""

    @pytest.mark.parametrize("stress", [0.0, 0.5, 1.0, 2.0, 5.0])
    def test_level_bounded(self, params: SerotoninODEParams, stress: float) -> None:
        """INV-5HT2: s(t) ∈ [0, 1] for every step under varied stress."""
        ode = SerotoninODE(params, level=0.5)
        for _ in range(1000):
            ode.step(stress=stress, dt=0.1)
            assert 0.0 <= ode.level <= 1.0, f"Level {ode.level} out of [0,1]"

    def test_desens_non_negative(self, params: SerotoninODEParams) -> None:
        """INV-5HT6: desensitisation non-negative under all conditions."""
        ode = SerotoninODE(params, level=0.1, desensitization=0.0)
        for _ in range(500):
            ode.step(stress=0.0, dt=0.1)
            assert ode.desensitization >= 0.0
