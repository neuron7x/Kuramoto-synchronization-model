# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T4 — Free-energy-analog risk gate tests (Lyapunov control objective).

Shannon/Tsallis entropy, Ricci temperature coupling, and the control
objective F = U − T·S. F is a Lyapunov candidate the gate drives down, NOT
a conserved/second-law quantity — see TestSecondLawDoesNotHold.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.physics.thermodynamic_risk import ThermodynamicRiskGate


@pytest.fixture
def gate() -> ThermodynamicRiskGate:
    return ThermodynamicRiskGate(q=1.5, T_base=0.60)


class TestEntropyIncreasesWithDiversification:
    """More diversified portfolios have higher entropy."""

    def test_uniform_higher_than_concentrated(self, gate):
        uniform = np.array([0.25, 0.25, 0.25, 0.25])
        concentrated = np.array([0.97, 0.01, 0.01, 0.01])

        S_uniform = gate.shannon_entropy(uniform)
        S_concentrated = gate.shannon_entropy(concentrated)
        assert S_uniform > S_concentrated

    def test_tsallis_uniform_higher_than_concentrated(self, gate):
        uniform = np.array([0.25, 0.25, 0.25, 0.25])
        concentrated = np.array([0.97, 0.01, 0.01, 0.01])

        S_uniform = gate.tsallis_entropy(uniform)
        S_concentrated = gate.tsallis_entropy(concentrated)
        assert S_uniform > S_concentrated

    def test_shannon_maximum_for_uniform(self, gate):
        """Maximum entropy for N assets = ln(N)."""
        N = 4
        uniform = np.ones(N) / N
        S = gate.shannon_entropy(uniform)
        assert abs(S - np.log(N)) < 1e-10


class TestFreeEnergyGateBlocksConcentration:
    """Gate must block moves that increase concentration when dU > 0."""

    def test_blocks_concentration_increase(self, gate):
        # dU > 0 (losing money), dS < 0 (concentrating)
        assert gate.gate(dU=0.5, dS=-0.1, kappa_min=0.0) == False  # noqa: E712

    def test_allows_diversification_with_small_loss(self, gate):
        # dU slightly positive, dS large positive → dF < 0
        assert gate.gate(dU=0.1, dS=1.0, kappa_min=0.0) == True  # noqa: E712


class TestRicciTemperatureCouplingSign:
    """T_eff = T_base · exp(-κ_min): sign convention correct."""

    def test_negative_curvature_raises_temperature(self, gate):
        T_neg = gate.ricci_temperature(kappa_min=-1.0)
        T_zero = gate.ricci_temperature(kappa_min=0.0)
        assert T_neg > T_zero, "Negative curvature → higher temperature"

    def test_positive_curvature_lowers_temperature(self, gate):
        T_pos = gate.ricci_temperature(kappa_min=1.0)
        T_zero = gate.ricci_temperature(kappa_min=0.0)
        assert T_pos < T_zero, "Positive curvature → lower temperature"

    def test_zero_curvature_returns_base(self, gate):
        T = gate.ricci_temperature(kappa_min=0.0)
        assert abs(T - 0.60) < 1e-12


class TestLyapunovStabilityNumerical:
    """F is a CONTROL Lyapunov candidate, not a conserved/monotone law.

    This is a CONDITIONAL property test: F decreases monotonically ONLY in
    the constructed admissible regime (dU ≤ 0 AND dS ≥ 0). It does NOT
    assert a second law — dS ≥ 0 here is an imposed scenario, not a
    guarantee about portfolio entropy. The companion test
    TestSecondLawDoesNotHold proves the unconstrained case.
    """

    def test_free_energy_monotone_decreasing_in_admissible_regime(self, gate):
        rng = np.random.default_rng(42)
        F_values = []
        U = 1.0
        S = 0.5

        for _ in range(1000):
            # Constructed admissible regime: Kelly-bounded dU ≤ 0 ...
            dU = -abs(rng.normal(0, 0.01))
            # ... and dS ≥ 0 IMPOSED here (not a law — see companion test).
            dS = abs(rng.normal(0, 0.005))
            U += dU
            S += dS
            F = gate.free_energy(U, gate.T_base, S)
            F_values.append(F)

        F_arr = np.array(F_values)
        diffs = np.diff(F_arr)
        # F non-increasing ONLY because we imposed dU≤0 ∧ dS≥0 above.
        assert np.all(diffs <= 1e-10), (
            f"Free energy increased at {np.sum(diffs > 1e-10)} steps "
            f"(max increase: {np.max(diffs):.6e})"
        )


class TestSecondLawDoesNotHold:
    """Falsification: portfolio entropy is NOT governed by a second law.

    A rebalance toward concentration lowers entropy (dS < 0), so the
    free-energy-analog F is not monotone in general. The gate's contract
    is a control objective that PENALISES such moves, not a law that
    forbids dS < 0 as input. These tests pin the honest framing so the
    removed "second-law analog" claim cannot silently return.
    """

    def test_concentration_lowers_entropy(self, gate):
        uniform = np.array([0.25, 0.25, 0.25, 0.25])
        concentrated = np.array([0.97, 0.01, 0.01, 0.01])
        dS = gate.shannon_entropy(concentrated) - gate.shannon_entropy(uniform)
        assert dS < 0.0, (
            "Concentration must lower portfolio entropy (dS<0); a "
            "'second law' dS>=0 is false for this quantity. "
            f"dS={dS:.6f}, S_uniform=ln4={np.log(4):.6f}"
        )

    def test_free_energy_rises_under_concentration(self, gate):
        # Same scalar dU, opposite-sign dS: concentration (dS<0) yields a
        # STRICTLY LARGER F than diversification (dS>0). If F were governed
        # by a second law this could not happen.
        dU = 0.0
        T = gate.T_base
        F_concentrate = gate.free_energy(dU, T, -0.3)
        F_diversify = gate.free_energy(dU, T, +0.3)
        assert F_concentrate > F_diversify, (
            f"F under concentration ({F_concentrate:.4f}) must exceed F "
            f"under diversification ({F_diversify:.4f}) — no monotone law."
        )

    def test_gate_accepts_negative_dS_as_free_input(self, gate):
        # The gate must handle dS<0 without error and penalise it: with
        # dU=0 a concentrating move (dS<0 → dF>0) is rejected, while a
        # diversifying move (dS>0 → dF<0) is admitted.
        assert gate.gate(dU=0.0, dS=-0.2, kappa_min=0.0) is False
        assert gate.gate(dU=0.0, dS=+0.2, kappa_min=0.0) is True


class TestTsallisProperties:
    def test_tsallis_zero_for_single_asset(self, gate):
        """Single asset → S_q = 0 (no diversification)."""
        S = gate.tsallis_entropy(np.array([1.0]))
        assert abs(S) < 1e-10

    def test_tsallis_non_negative(self, gate):
        """Tsallis entropy is non-negative for valid weights."""
        rng = np.random.default_rng(7)
        for _ in range(50):
            w = rng.uniform(0, 1, 10)
            S = gate.tsallis_entropy(w)
            assert S >= -1e-12

    def test_zero_weights_return_zero(self, gate):
        S = gate.tsallis_entropy(np.array([0.0, 0.0]))
        assert S == 0.0


class TestGateWithDetails:
    def test_returns_all_fields(self, gate):
        result = gate.gate_with_details(dU=0.1, dS=0.5, kappa_min=-0.5)
        assert "allowed" in result
        assert "dF" in result
        assert "T_eff" in result
        assert result["kappa_min"] == -0.5


class TestInputValidation:
    def test_q_must_be_positive(self):
        with pytest.raises(ValueError):
            ThermodynamicRiskGate(q=0)

    def test_q_cannot_be_one(self):
        with pytest.raises(ValueError, match="degenerates"):
            ThermodynamicRiskGate(q=1.0)

    def test_T_base_must_be_positive(self):
        with pytest.raises(ValueError):
            ThermodynamicRiskGate(T_base=0)


def test_free_energy_admissibility_boundary(gate) -> None:
    """`return dF <= 0.0` -- the gate admits a position update iff free energy does not rise.

    Under `LtE -> Gt` the admissibility inverts: an energy-INCREASING update (dF > 0) is
    admitted and an energy-lowering one is blocked -- the opposite of the control objective
    (INV-FE: F non-increasing under admissible updates). Pinned on both sides of zero.
    """
    # dS = 0 so dF = dU exactly; sign of dU is the sign of dF.
    assert gate.gate(dU=-1.0, dS=0.0, kappa_min=0.0) is True  # dF = -1 <= 0 -> admit
    assert gate.gate(dU=1.0, dS=0.0, kappa_min=0.0) is False  # dF = +1  > 0 -> block
    assert gate.gate_with_details(dU=1.0, dS=0.0, kappa_min=0.0)["allowed"] is False
