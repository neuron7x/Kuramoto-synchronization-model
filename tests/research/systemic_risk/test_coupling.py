# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for :mod:`research.systemic_risk.coupling`."""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.coupling import (
    coupling_from_exposures,
    omega_from_volatility,
    sakaguchi_alpha_zero,
)


class TestCouplingFromExposures:
    def test_row_stochastic_default(self) -> None:
        e = np.array([[0.0, 1.0, 3.0], [2.0, 0.0, 0.0], [0.0, 0.0, 0.0]], dtype=np.float64)
        K = coupling_from_exposures(e)
        # Row 0 sums to (1+3)/4 = 1.0; row 1 → 1.0; row 2 sums stay 0.
        np.testing.assert_allclose(K.sum(axis=1), [1.0, 1.0, 0.0], atol=1e-12)
        # Asymmetric: K[0,1]=0.25, K[1,0]=1.0 ⇒ K ≠ K^T.
        assert not np.allclose(K, K.T)

    def test_zero_diagonal(self) -> None:
        e = np.eye(4, dtype=np.float64) * 5.0
        K = coupling_from_exposures(e)
        assert np.all(np.diag(K) == 0.0)

    def test_capital_weighted(self) -> None:
        e = np.array([[0.0, 4.0], [2.0, 0.0]], dtype=np.float64)
        cap = np.array([2.0, 1.0], dtype=np.float64)
        K = coupling_from_exposures(e, normalisation="capital_weighted", capital=cap)
        # Row 0: 4 / 2 = 2; row 1: 2 / 1 = 2.
        assert K[0, 1] == pytest.approx(2.0)
        assert K[1, 0] == pytest.approx(2.0)

    def test_capital_required_when_weighted(self) -> None:
        e = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float64)
        with pytest.raises(ValueError, match="capital"):
            coupling_from_exposures(e, normalisation="capital_weighted")

    def test_zero_capital_rejected(self) -> None:
        e = np.array([[0.0, 1.0], [1.0, 0.0]], dtype=np.float64)
        cap = np.array([0.0, 1.0])
        with pytest.raises(ValueError):
            coupling_from_exposures(e, normalisation="capital_weighted", capital=cap)

    def test_floor_zeros_small_entries(self) -> None:
        e = np.array([[0.0, 1.0, 100.0]] * 3, dtype=np.float64)
        np.fill_diagonal(e, 0.0)
        K = coupling_from_exposures(e, floor=0.05)
        # Row-stochastic puts ~0.0099 on the small entry → below 0.05 floor.
        assert K[0, 1] == 0.0
        # Large entry survives.
        assert K[0, 2] > 0.0

    def test_floor_inclusive_at_exact_boundary(self) -> None:
        # Documentation guarantees an *inclusive* lower bound on the
        # kept set: an entry equal to ``floor`` survives.
        e = np.array([[0.0, 0.5, 0.5], [0.5, 0.0, 0.5], [0.5, 0.5, 0.0]], dtype=np.float64)
        # Row-stochastic produces equal off-diagonal entries == 0.5.
        K = coupling_from_exposures(e, floor=0.5)
        assert K[0, 1] == 0.5, (
            f"floor inclusivity violated: entry equal to floor=0.5 "
            f"clamped to {K[0, 1]} (expected 0.5)"
        )

    def test_all_zero_row_survives_without_crash(self) -> None:
        # Bank with no outgoing exposures: row sum is zero, must
        # NOT trigger division-by-zero noise. Coupling row stays 0.
        e = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 2.0], [3.0, 4.0, 0.0]], dtype=np.float64)
        K = coupling_from_exposures(e)
        assert np.all(K[0, :] == 0.0)
        assert np.isfinite(K).all()
        # Other rows must still be row-stochastic.
        np.testing.assert_allclose(K[1, :].sum(), 1.0, atol=1e-12)
        np.testing.assert_allclose(K[2, :].sum(), 1.0, atol=1e-12)

    def test_nan_exposure_rejected(self) -> None:
        e = np.array([[0.0, np.nan], [1.0, 0.0]], dtype=np.float64)
        with pytest.raises(ValueError, match="finite"):
            coupling_from_exposures(e)

    def test_negative_exposure_rejected(self) -> None:
        with pytest.raises(ValueError):
            coupling_from_exposures(np.array([[0.0, -1.0], [-1.0, 0.0]]))

    def test_orientation_invariant_2x2(self) -> None:
        # Per the canonical orientation invariant in coupling.py:
        #   E[i, j] = i lent to j (i's exposure to j)
        #   K[i, j] = stress felt by i from j ∝ E[i, j]
        # A 2×2 directed example: bank 0 lends 9 units to bank 1,
        # bank 1 lends 1 unit to bank 0. K must reflect this
        # asymmetry without transposing.
        e = np.array([[0.0, 9.0], [1.0, 0.0]], dtype=np.float64)
        K = coupling_from_exposures(e, normalisation="raw")
        # Raw retains the magnitudes; only the diagonal is cleared.
        assert K[0, 1] == 9.0, (
            "INV-K-ORIENTATION VIOLATED: K[0,1] should encode bank 0's "
            "stress from bank 1 ∝ E[0,1]=9 (0's loan to 1); got "
            f"{K[0, 1]}. A wrong-direction transpose would give 1.0."
        )
        assert K[1, 0] == 1.0, (
            "INV-K-ORIENTATION VIOLATED: K[1,0] should encode bank 1's "
            "stress from bank 0 ∝ E[1,0]=1 (1's loan to 0); got "
            f"{K[1, 0]}. A wrong-direction transpose would give 9.0."
        )
        # Row-stochastic must also preserve orientation (now 9/9, 1/1).
        K_rs = coupling_from_exposures(e)  # default row_stochastic
        assert K_rs[0, 1] == pytest.approx(1.0), (
            f"row-stochastic orientation drift: K[0,1]={K_rs[0, 1]}, "
            f"expected 1.0 (only outgoing edge from row 0)"
        )
        assert K_rs[1, 0] == pytest.approx(1.0)


class TestOmegaFromVolatility:
    def test_finite_output(self) -> None:
        rng = np.random.default_rng(0)
        log_returns = rng.standard_normal((500, 8))
        omega = omega_from_volatility(log_returns)
        assert omega.shape == (8,)
        assert np.all(np.isfinite(omega))
        assert np.all(omega > 0.0)

    def test_high_vol_higher_omega(self) -> None:
        rng = np.random.default_rng(0)
        low = rng.standard_normal((1000, 4)) * 0.1
        high = rng.standard_normal((1000, 4)) * 1.0
        ω_low = omega_from_volatility(low)
        ω_high = omega_from_volatility(high)
        assert float(ω_high.mean()) > float(ω_low.mean())

    def test_invalid_fs_rejected(self) -> None:
        with pytest.raises(ValueError):
            omega_from_volatility(np.zeros((10, 3)), fs=0.0)

    def test_single_observation_rejected(self) -> None:
        # Regression: Codex flagged that std(ddof=1) on T=1 returns NaN
        # silently. The validator must fail-closed on T < 2.
        with pytest.raises(ValueError, match="at least 2 time samples"):
            omega_from_volatility(np.zeros((1, 4)))

    def test_zero_observations_rejected(self) -> None:
        with pytest.raises(ValueError, match="at least 2 time samples"):
            omega_from_volatility(np.zeros((0, 4)))

    def test_inf_input_rejected(self) -> None:
        bad = np.zeros((10, 3), dtype=np.float64)
        bad[5, 1] = np.inf
        with pytest.raises(ValueError, match="finite"):
            omega_from_volatility(bad)

    def test_zero_variance_returns_zero_omega(self) -> None:
        # Constant series → σ=0 → ω=0. Caller-detectable, no NaN
        # leakage. The downstream Kuramoto solver receives explicit
        # zero (a degenerate but well-defined oscillator) instead of
        # an undefined value.
        omega = omega_from_volatility(np.full((10, 3), 0.123, dtype=np.float64))
        assert np.all(omega == 0.0)
        assert np.all(np.isfinite(omega))


class TestSakaguchiAlphaZero:
    def test_shape_and_values(self) -> None:
        a = sakaguchi_alpha_zero(5)
        assert a.shape == (5, 5)
        assert np.all(a == 0.0)

    def test_invalid_n_rejected(self) -> None:
        with pytest.raises(ValueError):
            sakaguchi_alpha_zero(0)
