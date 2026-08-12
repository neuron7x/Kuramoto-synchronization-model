# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for :mod:`research.systemic_risk.network_fitting`."""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.network_fitting import (
    compare_power_law_vs_exponential,
    fit_barabasi_albert,
    fit_barabasi_albert_from_topology,
    fit_exponential,
    fit_power_law,
)
from research.systemic_risk.topology import barabasi_albert_null


def _draw_power_law(n: int, alpha: float, k_min: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    u = rng.random(n)
    raw = (k_min - 0.5) * (1.0 - u) ** (1.0 / (1.0 - alpha)) + 0.5
    return np.maximum(np.rint(raw).astype(np.int64), k_min)


class TestFitPowerLaw:
    def test_recovers_alpha_on_synthetic(self) -> None:
        # Statistical: ensemble of 30 fits on synthetic α=2.5 samples.
        # The continuous-approximation MLE has known small-sample bias
        # of order 1/n for discrete data (Clauset 2009 §B). At n=2000,
        # k_min=6 the bias is ≤ 0.20 in expectation — used here as the
        # tolerance bound. Standard error of the ensemble mean is
        # σ_α/√30 ≈ 0.05.
        true_alpha = 2.5
        estimates = []
        for seed in range(30):
            sample = _draw_power_law(2000, true_alpha, 6, seed)
            estimates.append(fit_power_law(sample, k_min=6).alpha)
        mean_alpha = float(np.mean(estimates))
        assert abs(mean_alpha - true_alpha) < 0.20, (
            f"MLE-BIAS VIOLATED: mean(α̂)={mean_alpha:.4f} vs α={true_alpha} "
            f"over 30 samples of size 2000, k_min=6 (tolerance 0.20)"
        )

    def test_alpha_se_decreases_with_n(self) -> None:
        small = _draw_power_law(200, 2.5, 6, 0)
        large = _draw_power_law(2000, 2.5, 6, 0)
        small_se = fit_power_law(small, k_min=6).alpha_se
        large_se = fit_power_law(large, k_min=6).alpha_se
        assert large_se < small_se, (
            f"SE-MONOTONE VIOLATED: SE(n=2000)={large_se:.4f} >= "
            f"SE(n=200)={small_se:.4f}; expected SE ∝ 1/√n at α=2.5"
        )

    def test_ks_p_value_bracket(self) -> None:
        sample = _draw_power_law(500, 2.5, 6, 7)
        fit = fit_power_law(sample, k_min=6, n_bootstrap=200, seed=11)
        assert fit.ks_p_value is not None
        assert 0.0 < fit.ks_p_value <= 1.0

    def test_invalid_input_rejected(self) -> None:
        with pytest.raises(ValueError):
            fit_power_law(np.array([1, 2], dtype=np.int64))  # n<4
        with pytest.raises(ValueError):
            fit_power_law(np.array([-1, 2, 3, 4], dtype=np.int64))

    def test_relative_se_floor_enforced(self) -> None:
        # Tiny tail → high relative SE — must trigger the Cramér-Rao
        # floor when min_relative_se is below the floor's empirical
        # value. Concretely: at α≈2.5, n=4 the SE is 1.5/√4=0.75 and
        # σ_α/α≈0.30; tol=0.10 must reject.
        sample = np.array([6, 7, 8, 100], dtype=np.int64)
        with pytest.raises(ValueError, match="Cramér-Rao precision floor"):
            fit_power_law(sample, k_min=6, min_relative_se=0.10)


class TestFitExponential:
    def test_recovers_lambda(self) -> None:
        rng = np.random.default_rng(3)
        true_lambda = 0.4
        # Discrete shifted exponential: k = k_min + Geom(p=1-exp(-λ)).
        p = 1.0 - np.exp(-true_lambda)
        k_min = 1
        sample = (k_min + rng.geometric(p, size=2000) - 1).astype(np.int64)
        fit = fit_exponential(sample, k_min=k_min)
        assert abs(fit.lambda_ - true_lambda) < 0.1, (
            f"EXP-BIAS VIOLATED: λ̂={fit.lambda_:.4f} vs λ={true_lambda} "
            f"on synthetic n=2000, k_min={k_min}"
        )


class TestCompare:
    def test_power_law_preferred_on_power_law_sample(self) -> None:
        sample = _draw_power_law(1500, 2.4, 4, 0)
        cmp = compare_power_law_vs_exponential(sample, k_min=4)
        assert cmp.preferred == "power_law"
        assert cmp.aic_power_law < cmp.aic_exponential
        assert cmp.aic_delta > 0

    def test_exponential_preferred_on_exponential_sample(self) -> None:
        rng = np.random.default_rng(5)
        sample = (1 + rng.geometric(0.3, size=1500) - 1).astype(np.int64)
        cmp = compare_power_law_vs_exponential(sample, k_min=1)
        assert cmp.preferred == "exponential"


class TestFitBarabasiAlbert:
    def test_returns_positive_m(self) -> None:
        sample = _draw_power_law(1000, 2.5, 4, 0)
        m, fit = fit_barabasi_albert(sample)
        assert m >= 1
        assert 1.5 < fit.alpha < 4.5

    def test_seed_determinism(self) -> None:
        # Same input → same fit (no hidden randomness when n_bootstrap=0).
        sample = _draw_power_law(500, 2.5, 4, 0)
        a, fit_a = fit_barabasi_albert(sample)
        b, fit_b = fit_barabasi_albert(sample)
        assert a == b
        assert fit_a.alpha == fit_b.alpha

    def test_degenerate_constant_input_rejected(self) -> None:
        # All nodes share the same degree → no power-law tail, no
        # MLE solution. Fail-closed instead of returning a meaningless
        # m≈k/2.
        constant = np.full(20, 5, dtype=np.int64)
        with pytest.raises(ValueError, match="degenerate input"):
            fit_barabasi_albert(constant)

    def test_low_mean_degree_rejected(self) -> None:
        # <k> < 2 is incompatible with BA(m≥1) by Albert-Barabási
        # 2002 eq. 4.7. Must fail-closed.
        sparse = np.array([0, 0, 0, 1, 1, 1, 0, 0], dtype=np.int64)
        with pytest.raises(ValueError, match="BA-incompatible"):
            fit_barabasi_albert(sparse)

    def test_min_relative_se_propagates(self) -> None:
        # The validation-mode precision floor must reach the
        # underlying fit_power_law via _from_topology too.
        from research.systemic_risk.topology import barabasi_albert_null

        # n=20 BA(m=2) — n_tail too small for tight precision floor.
        topo = barabasi_albert_null(n_nodes=20, m=2, seed=0)
        with pytest.raises(ValueError, match="Cramér-Rao precision floor"):
            fit_barabasi_albert_from_topology(topo, min_relative_se=0.05)


class TestFitPowerLawValidation:
    def test_rejects_small_n(self) -> None:
        # n < MIN_TAIL_SIZE_VALIDATION must fail-closed.
        from research.systemic_risk.network_fitting import (
            MIN_TAIL_SIZE_VALIDATION,
            fit_power_law_validation,
        )

        small = _draw_power_law(MIN_TAIL_SIZE_VALIDATION - 1, 2.5, 4, 0)
        with pytest.raises(ValueError, match="validation-mode"):
            fit_power_law_validation(small)

    def test_passes_on_sufficient_sample(self) -> None:
        # Large enough sample at α=2.5 with k_min=6 clears both the
        # n=50 floor and the 10 % relative-SE precision bound.
        from research.systemic_risk.network_fitting import fit_power_law_validation

        sample = _draw_power_law(2000, 2.5, 6, 7)
        fit = fit_power_law_validation(sample, k_min=6, n_bootstrap=200, seed=11)
        assert fit.n_tail >= 50
        assert fit.alpha_se / fit.alpha <= 0.10


class TestFitBarabasiAlbertFromTopology:
    """Regression: catch the v2 in+out double-count drift on `topology.degree`.

    Reported by the Codex code-reviewer on PR #562: feeding
    ``topology.degree`` (= in + out) directly into
    :func:`fit_barabasi_albert` doubles the recovered ``m`` on
    symmetric BA-null graphs because each undirected edge is counted
    twice. :func:`fit_barabasi_albert_from_topology` resolves this by
    using ``out_degree`` consistently.
    """

    @pytest.mark.parametrize("true_m", [2, 3, 4])
    def test_recovers_generator_m_on_ba_null(self, true_m: int) -> None:
        topo = barabasi_albert_null(n_nodes=400, m=true_m, seed=true_m * 7)
        m_hat, _ = fit_barabasi_albert_from_topology(topo)
        assert abs(m_hat - true_m) <= 1, (
            f"BA-CALIBRATION VIOLATED: m̂={m_hat} from "
            f"fit_barabasi_albert_from_topology vs true m={true_m} on "
            f"barabasi_albert_null(n=400). Tolerance ±1 (finite-N)."
        )

    def test_total_degree_double_count_is_caught(self) -> None:
        # Demonstrates the original bug: feeding topology.degree (sum of
        # in+out) doubles the recovered m on symmetric graphs. The
        # _from_topology helper avoids this by using out_degree.
        topo = barabasi_albert_null(n_nodes=400, m=3, seed=11)
        m_via_total, _ = fit_barabasi_albert(topo.degree)
        m_via_topology, _ = fit_barabasi_albert_from_topology(topo)
        assert m_via_total >= 2 * m_via_topology - 1, (
            f"Expected m_via_total ≈ 2·m_via_topology on a symmetric BA "
            f"graph (in+out doubles), got m_via_total={m_via_total}, "
            f"m_via_topology={m_via_topology} at N=400, true_m=3, seed=11"
        )


class TestFitBarabasiAlbertValidationFromTopology:
    def test_rejects_small_topology(self) -> None:
        from research.systemic_risk.network_fitting import (
            fit_barabasi_albert_validation_from_topology,
        )
        from research.systemic_risk.topology import barabasi_albert_null

        topo = barabasi_albert_null(n_nodes=20, m=2, seed=0)
        with pytest.raises(ValueError, match="validation-mode BA fit"):
            fit_barabasi_albert_validation_from_topology(topo)

    def test_passes_on_sufficient_topology(self) -> None:
        from research.systemic_risk.network_fitting import (
            fit_barabasi_albert_validation_from_topology,
        )
        from research.systemic_risk.topology import barabasi_albert_null

        # n=3000: auto-selected k_min ≈ 25 leaves n_tail ≈ 56 ≥ 50
        # AND rel_se ≈ 0.086 ≤ 0.10 — both validation floors cleared.
        topo = barabasi_albert_null(n_nodes=3000, m=3, seed=42)
        m_hat, fit = fit_barabasi_albert_validation_from_topology(topo)
        assert m_hat >= 1
        assert fit.n_tail >= 50
        assert fit.alpha_se / fit.alpha <= 0.10
