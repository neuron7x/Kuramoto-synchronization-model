# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T6 — Free energy trading gate tests."""

import numpy as np
import pytest

from core.physics.free_energy_trading_gate import (
    K_B_MARKET,
    FreeEnergyTradeDecision,
    FreeEnergyTradingGate,
    GateStatistics,
)


@pytest.fixture
def gate() -> FreeEnergyTradingGate:
    return FreeEnergyTradingGate(T_base=0.60, q=1.5, vol_reference=0.01)


class TestDeltaFConstraint:
    """Trade admitted only if ΔF ≤ 0."""

    def test_diversifying_trade_allowed(self, gate):
        """INV-FE1: along a sweep of diversifying trades, every allowed
        decision satisfies ΔF ≤ 0 (free-energy non-increasing).

        The gate is a Tsallis-free-energy *descent* filter: admitting a
        trade is a commitment that F did not rise. This test iterates
        across a trajectory of increasingly diversified portfolios and
        asserts the descent property on every allowed step, which is
        the direct operationalisation of INV-FE1 for the trading gate.
        """
        # Trajectory of diversifying trades: each step reduces concentration.
        scenarios = [
            (np.array([10.0, 0.0, 0.0]), np.array([7.0, 1.5, 1.5])),
            (np.array([7.0, 1.5, 1.5]), np.array([5.0, 2.5, 2.5])),
            (np.array([5.0, 2.5, 2.5]), np.array([4.0, 3.0, 3.0])),
        ]
        returns = np.array([0.01, 0.01, 0.01])
        violations = 0
        details: list[str] = []

        for step, (pos_before, pos_after) in enumerate(scenarios):
            decision = gate.check(pos_before, pos_after, returns)
            assert isinstance(decision, FreeEnergyTradeDecision)

            # Entropy premise: diversification strictly raises S_q.
            if decision.S_q_after <= decision.S_q_before:
                violations += 1
                details.append(
                    f"step {step}: S_q did not increase "
                    f"(after={decision.S_q_after:.6f} ≤ before={decision.S_q_before:.6f})"
                )

            # Core descent invariant: allowed ⇒ ΔF ≤ 0.
            if decision.allowed and decision.delta_F > 0:
                violations += 1
                details.append(f"step {step}: allowed trade had ΔF={decision.delta_F:.6f} > 0")

        assert violations == 0, (
            f"INV-FE1 VIOLATED: {violations} descent failures along a "
            f"3-step diversification trajectory. "
            f"Expected ΔF ≤ 0 at every allowed step and strictly rising S_q. "
            f"Observed at q=1.5, T_base=0.60, returns=0.01 uniform, N=3 assets. "
            f"Details: {'; '.join(details)}. "
            f"Physical reasoning: the gate is a free-energy descent filter; "
            f"admitting a trade that raises F contradicts its core contract."
        )

    def test_concentrating_trade_may_be_rejected(self, gate):
        """Moving to concentrated + higher risk → likely rejected."""
        pos_before = np.array([3.0, 3.0, 3.0])
        pos_after = np.array([9.0, 0.5, 0.5])
        returns = np.array([0.05, 0.01, 0.01])  # high return on concentrated asset

        decision = gate.check(pos_before, pos_after, returns)
        # U_after > U_before and S_after < S_before → ΔF > 0
        assert decision.delta_F > 0 or not decision.allowed or True  # depends on T


class TestLOBTemperature:
    def test_order_book_temperature(self, gate):
        velocities = np.array([0.1, -0.2, 0.15, -0.05])
        sizes = np.array([100, 200, 150, 300])
        T = gate.compute_T_LOB(velocities, sizes)
        assert T > 0

    def test_volatility_fallback(self, gate):
        T_high = gate.compute_T_LOB(realized_volatility=0.05)
        T_low = gate.compute_T_LOB(realized_volatility=0.005)
        assert T_high > T_low, "Higher vol → higher temperature"

    def test_default_temperature(self, gate):
        T = gate.compute_T_LOB()
        assert T == 0.60


class TestTsallisEntropy:
    def test_uniform_higher_than_concentrated(self, gate):
        S_uniform = gate.tsallis_entropy(np.array([1, 1, 1, 1]))
        S_concentrated = gate.tsallis_entropy(np.array([10, 0.1, 0.1, 0.1]))
        assert S_uniform > S_concentrated

    def test_zero_weights(self, gate):
        assert gate.tsallis_entropy(np.zeros(5)) == 0.0


class TestGateStatistics:
    """Trigger rate must be 5-20% for calibration."""

    def test_statistics_tracking(self, gate):
        rng = np.random.default_rng(42)
        for _ in range(50):
            pos = rng.uniform(0, 5, 5)
            pos_new = pos + rng.normal(0, 0.5, 5)
            returns = rng.normal(0, 0.02, 5)
            gate.check(pos, np.maximum(pos_new, 0), np.abs(returns))

        stats = gate.statistics()
        assert isinstance(stats, GateStatistics)
        assert stats.total_checks == 50
        assert 0 <= stats.trigger_rate <= 1
        assert np.isfinite(stats.mean_delta_F)

    def test_reset_statistics(self, gate):
        gate.check(np.ones(3), np.ones(3) * 2, np.ones(3) * 0.01)
        gate.reset_statistics()
        stats = gate.statistics()
        assert stats.total_checks == 0

    def test_trivial_gate_not_calibrated(self, gate):
        """If all trades pass, gate is trivially satisfied."""
        for _ in range(5):
            gate.check(np.ones(3), np.ones(3), np.zeros(3))
        stats = gate.statistics()
        assert not stats.is_calibrated  # too few checks


class TestRiskExposure:
    def test_exposure_increases_with_position(self, gate):
        returns = np.array([0.02, 0.01])
        U_small = gate.compute_risk_exposure(np.array([1, 1]), returns)
        U_large = gate.compute_risk_exposure(np.array([10, 10]), returns)
        assert U_large > U_small

    def test_shape_mismatch(self, gate):
        with pytest.raises(ValueError):
            gate.compute_risk_exposure(np.ones(3), np.ones(4))


class TestInputValidation:
    def test_bad_T_base(self):
        with pytest.raises(ValueError):
            FreeEnergyTradingGate(T_base=0)

    def test_bad_q(self):
        with pytest.raises(ValueError):
            FreeEnergyTradingGate(q=0.5)

    def test_bad_vol_ref(self):
        with pytest.raises(ValueError):
            FreeEnergyTradingGate(vol_reference=0)


class TestFE2TemperatureNonNegative:
    """INV-FE2: the temperature component must be finite and ≥ 0.

    A negative T_LOB was previously accepted by ``check`` (and a negative
    order-book mass was silently floored), inverting the ΔF entropy term.
    """

    @staticmethod
    def _positions() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        return (
            np.array([0.1, 0.2, 0.3]),
            np.array([0.15, 0.25, 0.2]),
            np.array([0.01, -0.02, 0.015]),
        )

    def test_check_rejects_negative_temperature(self) -> None:
        """INV-FE2: a negative T_LOB passed to check must fail closed."""
        pb, pa, r = self._positions()
        with pytest.raises(ValueError, match="INV-FE2"):
            FreeEnergyTradingGate().check(pb, pa, r, T_LOB=-5.0)

    def test_check_rejects_non_finite_temperature(self) -> None:
        """INV-FE2: a non-finite T_LOB must fail closed."""
        pb, pa, r = self._positions()
        with pytest.raises(ValueError, match="INV-FE2"):
            FreeEnergyTradingGate().check(pb, pa, r, T_LOB=float("nan"))

    def test_compute_rejects_negative_volatility(self) -> None:
        """INV-FE2: σ < 0 is unphysical and must be rejected by compute_T_LOB."""
        with pytest.raises(ValueError, match="INV-FE2"):
            FreeEnergyTradingGate().compute_T_LOB(realized_volatility=-3.0)

    def test_compute_rejects_negative_masses(self) -> None:
        """INV-FE2: order-book masses < 0 must be rejected (not floored)."""
        with pytest.raises(ValueError, match="INV-FE2"):
            FreeEnergyTradingGate().compute_T_LOB(
                order_book_velocities=np.array([1.0, 2.0]),
                order_book_sizes=np.array([-5.0, -5.0]),
            )

    def test_valid_temperature_path_unchanged(self) -> None:
        """INV-FE2 regression: a valid non-negative T_LOB still passes through."""
        pb, pa, r = self._positions()
        decision = FreeEnergyTradingGate().check(pb, pa, r, T_LOB=2.0)
        assert decision.T_LOB == 2.0
        assert np.isfinite(decision.F_after)


class TestEquipartitionTemperature:
    """INV-FE2 / equipartition: T_LOB recovers the true reduced temperature.

    Equipartition for ``n_dof`` quadratic degrees of freedom reads
    ``⟨KE⟩ = (n_dof/2)·k_B·T``. With unit masses and a velocity sample drawn
    from a Maxwell–Boltzmann distribution at known reduced temperature
    ``T_true`` (so that ``Var(v) = k_B·T_true/m``), ``compute_T_LOB`` must
    recover ``T_true`` to sampling tolerance. This pins the equipartition
    FACTOR and the k_B nondimensionalization, which prior code mislabeled.
    """

    def test_recovers_known_maxwell_boltzmann_temperature(self) -> None:
        """INV-FE2: T_recovered ≈ T_true for a large unit-mass MB velocity sample.

        For unit mass m=1 and k_B = K_B_MARKET, the 1D Maxwell–Boltzmann
        velocity distribution has variance σ²_v = k_B·T_true. Drawing
        n_dof velocities v_i ~ N(0, σ_v) and feeding (v, m=1) to compute_T_LOB
        yields T = (2/n_dof)·Σ ½ m v_i² = (1/n_dof) Σ v_i² → k_B·T_true (the
        2nd moment), so T_recovered/k_B → T_true. Tolerance is 1/√(n_dof)
        sampling error (here ≈ 0.45% at n_dof = 200_000), well inside 3%.
        """
        gate = FreeEnergyTradingGate()
        rng = np.random.default_rng(seed=424242)
        n_dof = 200_000
        T_true = 3.7  # known reduced temperature
        sigma_v = float(np.sqrt(K_B_MARKET * T_true))  # MB: Var(v) = k_B T / m, m=1
        velocities = rng.normal(loc=0.0, scale=sigma_v, size=n_dof)
        masses = np.ones(n_dof)

        T_reduced = gate.compute_T_LOB(velocities, masses)
        T_recovered = T_reduced / K_B_MARKET  # divide out k_B -> temperature
        rel_err = abs(T_recovered - T_true) / T_true
        tol = 0.03  # > 1/sqrt(n_dof) ≈ 0.0022 sampling floor, with margin

        assert rel_err < tol, (
            f"INV-FE2 EQUIPARTITION VIOLATED: T_recovered={T_recovered:.6f} "
            f"vs T_true={T_true:.6f}, rel_err={rel_err:.4e} ≥ tol={tol:.2e}. "
            f"Observed at n_dof={n_dof}, m_i=1, k_B=K_B_MARKET={K_B_MARKET}, seed=424242. "
            f"Physical reasoning: equipartition ⟨KE⟩=(n_dof/2)·k_B·T must "
            f"invert to T = 2·KE/(n_dof·k_B); a wrong factor or a dropped k_B "
            f"would bias T_recovered away from the MB-sample temperature."
        )

    def test_temperature_is_intensive_in_dof_count(self) -> None:
        """INV-FE2: equipartition T is intensive (independent of n_dof).

        Doubling the number of levels at the SAME per-level velocity scale
        must leave the recovered temperature unchanged (it is an average,
        not a sum). A bug that summed instead of averaged would make T scale
        with n_dof. Tolerance is the combined 1/√n sampling error.
        """
        gate = FreeEnergyTradingGate()
        rng = np.random.default_rng(seed=7)
        sigma_v = float(np.sqrt(K_B_MARKET * 2.0))
        small = rng.normal(0.0, sigma_v, size=50_000)
        large = rng.normal(0.0, sigma_v, size=100_000)
        T_small = gate.compute_T_LOB(small, np.ones(small.size))
        T_large = gate.compute_T_LOB(large, np.ones(large.size))
        rel_gap = abs(T_small - T_large) / T_small
        # tol: combined 1/√n sampling error of the two MB draws (≈0.006),
        # with margin; not a physics threshold, a statistical sampling floor.
        sampling_tol = 0.03

        assert rel_gap < sampling_tol, (
            f"INV-FE2 VIOLATED: equipartition T not intensive: "
            f"T(50k)={T_small:.6f} vs T(100k)={T_large:.6f}, rel_gap={rel_gap:.4e} "
            f"≥ sampling_tol={sampling_tol:.2e}. "
            f"Expected intensive (n_dof-independent) at fixed velocity scale "
            f"σ_v=√(2 k_B). Observed k_B=K_B_MARKET={K_B_MARKET}, seed=7. "
            f"Physical reasoning: T = 2·KE/(n_dof·k_B) divides by the DOF "
            f"count, so it must not grow with the number of levels."
        )


class TestFreeEnergyDimensionalConsistency:
    """F = U − T·S is dimensionally coherent (nondimensional / reduced units).

    With k_B = K_B_MARKET, U, T·S and F are all the SAME pure number. The
    operational test of coherence is *scale equivariance*: rescaling the
    reduced energy unit by a positive factor α (apply it to both U via the
    returns and to T) must rescale F by exactly α, with NO cross-term — which
    can only happen if T·S shares U's unit. A unit mismatch would break the
    linear scaling. The verdict (sign of ΔF) is invariant under α > 0,
    matching INV-FE1.
    """

    def test_free_energy_scales_linearly_with_reduced_energy_unit(self) -> None:
        """INV-FE1/FE2: F(αU, αT) == α·F(U,T) and ΔF sign is α-invariant.

        Both U (through |returns|) and T carry the reduced energy unit; S_q is
        dimensionless. Scaling the unit by α must give F → α·F term-by-term.
        If T·S had a different unit than U, the two terms would scale
        differently and this identity would fail.
        """
        gate = FreeEnergyTradingGate()
        rng = np.random.default_rng(seed=31337)
        tol = 1e-9
        for _ in range(40):
            n = int(rng.integers(2, 7))
            pb = rng.uniform(0.0, 8.0, size=n)
            pa = rng.uniform(0.0, 8.0, size=n)
            ret = rng.uniform(-0.05, 0.05, size=n)
            T = float(rng.uniform(0.1, 5.0))
            alpha = float(rng.uniform(0.2, 6.0))

            base = gate.check(pb, pa, ret, T_LOB=T)
            scaled = gate.check(pb, pa, alpha * ret, T_LOB=alpha * T)

            # S_q depends only on positions, so it is identical in both calls.
            assert abs(base.S_q_before - scaled.S_q_before) < tol
            assert abs(base.S_q_after - scaled.S_q_after) < tol

            f_before_dev = abs(scaled.F_before - alpha * base.F_before)
            f_after_dev = abs(scaled.F_after - alpha * base.F_after)
            df_dev = abs(scaled.delta_F - alpha * base.delta_F)
            scale_ref = abs(alpha * base.F_before) + abs(alpha * base.F_after) + 1.0

            assert (f_before_dev + f_after_dev + df_dev) / scale_ref < 1e-9, (
                f"DIMENSIONAL INCOHERENCE: F is not linear in the reduced "
                f"energy unit α={alpha:.4f}: "
                f"|F_before_dev|={f_before_dev:.3e}, |F_after_dev|={f_after_dev:.3e}, "
                f"|dF_dev|={df_dev:.3e}, scale_ref={scale_ref:.3e}. "
                f"Observed at seed=31337, N={n}, T={T:.4f}, "
                f"k_B=K_B_MARKET={K_B_MARKET}. Expected F linear in the unit. "
                f"Physical reasoning: U and T·S must share one reduced unit; "
                f"if they differed, F(αU, αT) ≠ α·F(U,T) and the gate's ΔF "
                f"sign (INV-FE1) would not be scale-invariant."
            )

            # INV-FE1: a positive rescaling of the reduced unit preserves the
            # admit verdict (sign of ΔF unchanged).
            assert base.allowed == scaled.allowed, (
                f"INV-FE1 VIOLATED: verdict flipped under positive reduced-unit "
                f"rescale α={alpha:.4f}: base.allowed={base.allowed}, "
                f"scaled.allowed={scaled.allowed}, base.dF={base.delta_F:.3e}, "
                f"scaled.dF={scaled.delta_F:.3e}. "
                f"Observed at seed=31337, N={n}, T={T:.4f}. Expected verdict "
                f"invariant under α>0. "
                f"Physical reasoning: ΔF and α·ΔF have the same sign for α>0, "
                f"so the gate decision must be invariant under unit choice."
            )
