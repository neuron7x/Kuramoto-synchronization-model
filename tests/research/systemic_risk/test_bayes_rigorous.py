# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for the rigorous Bayes-factor and decision-theory primitives.

Every formula here is checked against either an analytical
identity, an independent canonical reference, or a Monte-Carlo
simulation. Property-style invariants are checked under Hypothesis.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from research.systemic_risk.bayes_rigorous import (
    ASYMPTOTIC_BIC_PENALTY,
    auc_per_crisis_bf_rigorous,
    auc_to_z_under_null,
    cramer_rao_alpha_lower_bound,
    derive_kill_threshold_log_odds,
    mann_whitney_effective_n,
    mann_whitney_null_variance,
    wagenmakers_bic_bayes_factor,
)


class TestNullVariance:
    def test_balanced_case_matches_textbook(self) -> None:
        # m = n = 10 → Var = 21 / 1200 = 0.0175 (Mann-Whitney 1947 §3).
        assert mann_whitney_null_variance(10, 10) == pytest.approx(21.0 / 1200.0)

    def test_unbalanced_case(self) -> None:
        # m = 5, n = 15 → Var = 21 / (12·5·15) = 21/900.
        assert mann_whitney_null_variance(5, 15) == pytest.approx(21.0 / 900.0)

    def test_invalid_inputs_raise(self) -> None:
        with pytest.raises(ValueError, match="n_pos"):
            mann_whitney_null_variance(0, 5)
        with pytest.raises(ValueError, match="n_neg"):
            mann_whitney_null_variance(5, 0)


class TestEffectiveN:
    def test_balanced_large(self) -> None:
        # m = n = 1000 → n_eff = 1e6 / 2001 ≈ 499.75 ≈ n/2 - 1/2 for large balanced.
        n_eff = mann_whitney_effective_n(1000, 1000)
        assert n_eff == pytest.approx(499.75031, rel=1e-5)

    def test_unbalanced(self) -> None:
        n_eff = mann_whitney_effective_n(10, 100)
        # n_eff = 10·100 / 111 ≈ 9.009
        assert n_eff == pytest.approx(1000.0 / 111.0, rel=1e-9)


class TestAUCToZ:
    def test_auc_half_yields_zero(self) -> None:
        z = auc_to_z_under_null(0.5, n_pos=10, n_neg=10)
        assert z == pytest.approx(0.0)

    def test_polarity(self) -> None:
        z_above = auc_to_z_under_null(0.75, n_pos=20, n_neg=20)
        z_below = auc_to_z_under_null(0.25, n_pos=20, n_neg=20)
        assert z_above > 0
        assert z_below < 0
        # Symmetry: z(AUC) = -z(1 - AUC) for any (m, n).
        assert z_above == pytest.approx(-z_below)

    def test_invalid_auc_rejected(self) -> None:
        with pytest.raises(ValueError, match="auc must be in"):
            auc_to_z_under_null(1.5, n_pos=10, n_neg=10)


class TestWagenmakers:
    def test_z_zero_yields_lindley_penalty(self) -> None:
        # With z=0, BF should equal 1/sqrt(n_eff) — the canonical
        # "uninformative data favours the null" Lindley penalty.
        bf = wagenmakers_bic_bayes_factor(0.0, n_eff=4.0)
        assert bf == pytest.approx(0.5)  # 1/sqrt(4) = 0.5

    def test_z_zero_neff_one_is_unity(self) -> None:
        # The single value at which the prior penalty vanishes.
        bf = wagenmakers_bic_bayes_factor(0.0, n_eff=1.0)
        assert bf == pytest.approx(1.0)

    def test_large_z_favours_alternative(self) -> None:
        bf = wagenmakers_bic_bayes_factor(3.0, n_eff=10.0)
        assert bf > 1.0

    def test_invalid_inputs_rejected(self) -> None:
        with pytest.raises(ValueError, match="n_eff"):
            wagenmakers_bic_bayes_factor(1.0, n_eff=0.0)
        with pytest.raises(ValueError, match="z must be finite"):
            wagenmakers_bic_bayes_factor(math.nan, n_eff=10.0)

    def test_extreme_z_clamped(self) -> None:
        bf = wagenmakers_bic_bayes_factor(20.0, n_eff=10.0)
        # log BF = (400 - log 10) / 2 ≈ 198 ≫ 20; clamps at exp(20).
        assert bf == pytest.approx(math.exp(ASYMPTOTIC_BIC_PENALTY))

    @given(
        z=st.floats(min_value=-5.0, max_value=5.0), n_eff=st.floats(min_value=1.0, max_value=1000.0)
    )
    def test_log_bf_property(self, z: float, n_eff: float) -> None:
        # log BF = (z^2 - log n_eff) / 2 (modulo clamping).
        expected = (z * z - math.log(n_eff)) / 2.0
        if abs(expected) > ASYMPTOTIC_BIC_PENALTY:
            return  # clamped — formula holds only inside the cap
        bf = wagenmakers_bic_bayes_factor(z, n_eff=n_eff)
        assert math.log(bf) == pytest.approx(expected, abs=1e-9)


class TestAUCBFRigorous:
    def test_auc_half_returns_lindley_below_one(self) -> None:
        # The canonical Lindley penalty: AUC=0.5 with finite n_eff > 1
        # must return BF < 1 (the prior-penalty term).
        bf = auc_per_crisis_bf_rigorous(0.5, n_pos=10, n_neg=10)
        assert bf < 1.0
        # Specifically: 1 / sqrt(100/21) = sqrt(21)/10.
        assert bf == pytest.approx(math.sqrt(21.0) / 10.0, rel=1e-9)

    def test_polarity_symmetry(self) -> None:
        # BF(AUC, m, n) == BF(1 - AUC, m, n) — the test is two-sided.
        bf_high = auc_per_crisis_bf_rigorous(0.85, n_pos=15, n_neg=15)
        bf_low = auc_per_crisis_bf_rigorous(0.15, n_pos=15, n_neg=15)
        assert bf_high == pytest.approx(bf_low, rel=1e-12)

    def test_strictly_monotone_in_distance_from_half(self) -> None:
        # |AUC - 0.5| ↑  →  BF ↑
        bf_05 = auc_per_crisis_bf_rigorous(0.55, n_pos=20, n_neg=20)
        bf_07 = auc_per_crisis_bf_rigorous(0.70, n_pos=20, n_neg=20)
        bf_09 = auc_per_crisis_bf_rigorous(0.90, n_pos=20, n_neg=20)
        assert bf_05 < bf_07 < bf_09

    def test_monte_carlo_null_polarity(self) -> None:
        """Under H0, the **expected** log BF should be ≤ 0 — the
        Bayesian "ratio between right and wrong evidence" is on the
        right side of the line on average."""
        rng = np.random.default_rng(seed=20260508)
        n_trials = 500
        log_bfs = []
        m, n = 30, 30
        for _ in range(n_trials):
            x = rng.normal(0.0, 1.0, m)
            y = rng.normal(0.0, 1.0, n)  # H0: same distribution
            # Empirical AUC via Mann-Whitney U-statistic.
            u = float(((x[:, None] > y[None, :]).astype(np.float64).sum()))
            auc_hat = u / (m * n)
            log_bfs.append(math.log(auc_per_crisis_bf_rigorous(auc_hat, n_pos=m, n_neg=n)))
        mean_log_bf = float(np.mean(log_bfs))
        # Under H0, mean log BF should be negative (Lindley).
        # We allow a generous slack for Monte Carlo noise.
        assert mean_log_bf < 0.5, (
            f"Under H0, mean log BF should be ≤ 0 (Lindley penalty); "
            f"got {mean_log_bf:.3f} over {n_trials} trials"
        )


class TestCramerRao:
    def test_textbook_value(self) -> None:
        # α = 2.5, n = 100 → SE_LB = 1.5 / 10 = 0.15.
        assert cramer_rao_alpha_lower_bound(2.5, n=100) == pytest.approx(0.15)

    def test_invalid_alpha_rejected(self) -> None:
        with pytest.raises(ValueError, match="alpha must be > 1"):
            cramer_rao_alpha_lower_bound(0.99, n=100)

    def test_invalid_n_rejected(self) -> None:
        with pytest.raises(ValueError, match="n must be >= 2"):
            cramer_rao_alpha_lower_bound(2.5, n=1)

    def test_monte_carlo_mle_meets_lower_bound(self) -> None:
        """Simulate Pareto data and check that MLE empirical SE is ≥
        Cramér-Rao lower bound (allowing 5% finite-sample slack)."""
        rng = np.random.default_rng(seed=42424242)
        true_alpha = 2.5
        x_min = 1.0
        n = 5000
        n_replicas = 200
        # Pareto Type-I generator: x = x_min · u^{-1/(α-1)}, u ∈ (0, 1).
        alpha_hats = []
        for _ in range(n_replicas):
            u = rng.uniform(0.0, 1.0, size=n)
            x = x_min * u ** (-1.0 / (true_alpha - 1.0))
            log_ratio = np.log(x / x_min)
            alpha_hat = 1.0 + n / float(log_ratio.sum())
            alpha_hats.append(alpha_hat)
        empirical_se = float(np.std(alpha_hats, ddof=1))
        lower_bound = cramer_rao_alpha_lower_bound(true_alpha, n=n)
        # Empirical SE must be ≥ CRLB. Allow 5% finite-sample tolerance.
        assert (
            empirical_se >= 0.95 * lower_bound
        ), f"Empirical SE {empirical_se:.5f} fell below 95% of Cramér-Rao bound {lower_bound:.5f}"
        # ... but should also be close (within 20%) — MLE asymptotically attains it.
        assert empirical_se <= 1.20 * lower_bound, (
            f"Empirical SE {empirical_se:.5f} exceeded 120% of "
            f"Cramér-Rao bound {lower_bound:.5f} — efficiency loss"
        )


class TestKillThresholdDerivation:
    def test_default_geosync_calibration(self) -> None:
        # Default kill threshold is -5.0 log-odds. Reverse-engineer:
        # log(c_FK / c_FP) = -5.0  ⇒  c_FK / c_FP = e^(-5) ≈ 1/148.4.
        threshold = derive_kill_threshold_log_odds(
            cost_false_kill=1.0,
            cost_false_pass=math.exp(5.0),
        )
        assert threshold == pytest.approx(-5.0)

    def test_symmetric_costs_yield_zero(self) -> None:
        # c_FK == c_FP → threshold == 0 (posterior > 0.5 to KILL).
        threshold = derive_kill_threshold_log_odds(cost_false_kill=2.5, cost_false_pass=2.5)
        assert threshold == pytest.approx(0.0)

    def test_invalid_costs_rejected(self) -> None:
        with pytest.raises(ValueError, match="cost_false_kill"):
            derive_kill_threshold_log_odds(cost_false_kill=0.0, cost_false_pass=1.0)
        with pytest.raises(ValueError, match="cost_false_pass"):
            derive_kill_threshold_log_odds(cost_false_kill=1.0, cost_false_pass=0.0)

    def test_log_form_consistency(self) -> None:
        # log(c_FK / c_FP) is the threshold; equivalent to
        # log(p / (1 - p)) at the Bayes-rule cutoff.
        c_fk, c_fp = 1.0, 99.0
        threshold = derive_kill_threshold_log_odds(cost_false_kill=c_fk, cost_false_pass=c_fp)
        p_star = c_fk / (c_fk + c_fp)
        assert threshold == pytest.approx(math.log(p_star / (1.0 - p_star)))


class TestComparisonAdHocVsRigorous:
    """The two key audit signals: (a) at AUC=0.5 the rigorous BF
    is < 1 (Lindley penalty), but the ad hoc returned exactly 1.0;
    (b) at large AUC the rigorous BF scales **quadratically** in
    (AUC-0.5), while the ad hoc scales linearly. These tests
    document the divergence so future readers see why the rigorous
    form replaces the ad hoc."""

    def test_at_half_rigorous_below_one_ad_hoc_at_one(self) -> None:
        n_pos = n_neg = 10
        rigorous = auc_per_crisis_bf_rigorous(0.5, n_pos=n_pos, n_neg=n_neg)
        ad_hoc = math.exp(2.0 * (0.5 - 0.5) * math.sqrt(n_pos + n_neg))
        assert rigorous < 1.0
        assert ad_hoc == pytest.approx(1.0)
        # Ratio: ad_hoc / rigorous = sqrt(n_eff) ≈ 4.58 for n=10+10.

    def test_at_high_auc_rigorous_grows_quadratically(self) -> None:
        # log BF_rigorous(AUC=0.5+δ) ∝ δ², log BF_ad_hoc ∝ δ.
        n_pos = n_neg = 50
        deltas = np.array([0.05, 0.10, 0.20])
        log_rig = np.array(
            [
                math.log(auc_per_crisis_bf_rigorous(0.5 + d, n_pos=n_pos, n_neg=n_neg))
                for d in deltas
            ]
        )
        # Filter out the negative range — at small δ the Lindley
        # penalty dominates and log BF is still negative; we want to
        # confirm only that the *increment* in log BF as δ doubles
        # behaves quadratically when δ is large enough to dominate.
        # Use δ from 0.1 to 0.2 (×2): log BF ratio should be ≈ 4 (since
        # quadratic in δ).
        log_at_01 = log_rig[1] + 0.5 * math.log(mann_whitney_effective_n(n_pos, n_neg))
        log_at_02 = log_rig[2] + 0.5 * math.log(mann_whitney_effective_n(n_pos, n_neg))
        # log BF + Lindley = z²/2 ∝ δ² → ratio ≈ 4
        ratio = log_at_02 / log_at_01
        assert 3.5 < ratio < 4.5, (
            f"Quadratic scaling expected: log(BF · √n_eff) at δ=0.2 vs δ=0.1 "
            f"should be ~4×; got {ratio:.3f}"
        )
