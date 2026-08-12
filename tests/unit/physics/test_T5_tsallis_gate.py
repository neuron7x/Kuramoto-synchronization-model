# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""T5 — Tsallis entropy risk gate tests (MLE-fitted q, GoF-gated).

q is estimated by maximum-likelihood on the Student-t equivalence
q = (ν + 3) / (ν + 1) (Souza & Tsallis 1997; Tsallis 2009 Ch. 4), NOT by
kurtosis moment-matching. The fit is goodness-of-fit gated by a
Kolmogorov-Smirnov test: a sample that is not a q-Gaussian fails closed to
the conservative fallback. These tests pin both the anchored fit and the
fail-closed behaviour.
"""

import numpy as np
import pytest

from core.physics.tsallis_gate import TsallisGateResult, TsallisRegime, TsallisRiskGate


def _q_from_nu(nu: float) -> float:
    """q = (ν + 3) / (ν + 1) — the Student-t ↔ q-Gaussian map."""
    return (nu + 3.0) / (nu + 1.0)


@pytest.fixture
def gate() -> TsallisRiskGate:
    return TsallisRiskGate(window=30, q_normal=1.35, q_crisis=1.55)


class TestQEstimation:
    """q estimated by MLE on the Student-t equivalence q=(ν+3)/(ν+1)."""

    def test_gaussian_returns_near_1(self):
        """Gaussian ⟹ ν → large ⟹ q → 1 (Gaussian limit of q-Gaussian).

        Unlike the legacy kurtosis estimator (which mapped κ≈0 to q≈5/3),
        the MLE recovers the true tail index: a Gaussian is the ν→∞ limit
        of the t-family, so q must collapse toward 1.
        """
        rng = np.random.default_rng(42)
        returns = rng.normal(0, 0.01, 10000)
        q = TsallisRiskGate.estimate_q(returns)
        # At N=10000 the fitted ν is large; q sits just above 1.0. We bound
        # well below the NORMAL cutoff 1.35 — a Gaussian cannot be crisis.
        assert 1.0 <= q < 1.10, (
            f"INV-HPC2: Gaussian q={q:.4f} not in [1.0, 1.10). "
            f"Expected q→1 (ν→∞ limit). N=10000, seed=42. "
            f"MLE t-equivalence q=(ν+3)/(ν+1)."
        )

    def test_heavy_tails_higher_q(self):
        """Heavy tails ⟹ smaller ν ⟹ higher q than a Gaussian sample."""
        rng = np.random.default_rng(42)
        normal = rng.normal(0, 0.01, 1000)
        heavy = rng.standard_t(3, 1000) * 0.01  # t-distribution, heavy tails

        q_normal = TsallisRiskGate.estimate_q(normal)
        q_heavy = TsallisRiskGate.estimate_q(heavy)
        assert q_heavy > q_normal, (
            f"INV-HPC2: q_heavy={q_heavy:.4f} !> q_normal={q_normal:.4f}. "
            f"Expected heavier tails → smaller ν → higher q. "
            f"N=1000, seed=42. MLE Student-t fit."
        )

    def test_known_q_recovery_student_t(self):
        """ANCHORED: MLE recovers a KNOWN q from a Student-t with known ν.

        Generate t(ν) samples with ν ∈ {3, 5, 8, 30}; the true Tsallis
        index is q* = (ν+3)/(ν+1). At N=20000 the MLE recovers q* to a
        tight statistical tolerance. This is the falsifiable anchor of the
        whole change: a broken/moment-match estimator misses these targets.
        """
        for df, tol in ((3, 0.02), (5, 0.03), (8, 0.03), (30, 0.02)):
            rng = np.random.default_rng(7)
            sample = rng.standard_t(df, 20000)
            q_hat = TsallisRiskGate.estimate_q(sample)
            q_true = _q_from_nu(float(df))
            assert abs(q_hat - q_true) < tol, (
                f"INV-HPC2: recovered q={q_hat:.4f} vs true q*={q_true:.4f} "
                f"(ν={df}) exceeds tol={tol}. "
                f"N=20000, seed=7. MLE must recover the known tail index; "
                f"a kurtosis moment-match would fail here (κ diverges)."
            )

    def test_constant_returns_q_1(self):
        """No variance → q = 1.0 (Gaussian limit, degenerate fit)."""
        returns = np.zeros(100)
        q = TsallisRiskGate.estimate_q(returns)
        assert q == 1.0, (
            f"INV-HPC2: zero-variance q={q} != 1.0. "
            f"Expected degenerate Gaussian limit. N=100, all-zero."
        )

    def test_insufficient_data(self):
        q = TsallisRiskGate.estimate_q(np.array([0.01, 0.02]))
        assert q == 1.0, (
            f"INV-HPC2: insufficient-data q={q} != 1.0. "
            f"Expected Gaussian-limit fallback for N<4. N=2."
        )


class TestGoodnessOfFitFailClosed:
    """A non-q-Gaussian sample must fail closed — no confident regime."""

    def test_bimodal_fails_closed(self):
        """FAIL-CLOSED: a clearly bimodal sample is not a q-Gaussian.

        gof_passed must be False, and the gate must emit the conservative
        fallback (q=1.5, ELEVATED, multiplier 0.25) — NOT a confident
        q-derived regime. This is the verdict-flip guard: an unfitted
        sample can never drive a confident position decision.
        """
        rng = np.random.default_rng(1)
        bimodal = np.concatenate(
            [rng.normal(-5.0, 0.3, 500), rng.normal(5.0, 0.3, 500)]
        )
        gate = TsallisRiskGate(window=2000, min_observations=20, gof_alpha=0.05)
        result = gate.evaluate(bimodal)
        assert result.gof_passed is False, (
            f"INV-HPC2 fail-closed: bimodal gof_passed={result.gof_passed} "
            f"(gof_p={result.gof_pvalue:.2e}) must be False. "
            f"N=1000, seed=1. A two-mode mixture is not a q-Gaussian."
        )
        assert result.regime == TsallisRegime.ELEVATED, (
            f"INV-HPC2 fail-closed: bimodal regime={result.regime.value} "
            f"must be conservative ELEVATED fallback, not q-derived. "
            f"N=1000, seed=1, gof_p={result.gof_pvalue:.2e}."
        )
        assert result.position_multiplier == 0.25, (
            f"INV-FE2 fail-closed: bimodal multiplier="
            f"{result.position_multiplier} must be conservative 0.25. "
            f"N=1000, seed=1. No confident sizing from an unfitted sample."
        )

    def test_strong_skew_fails_closed(self):
        """FAIL-CLOSED: a strongly skewed (exponential) sample is not q-Gaussian."""
        rng = np.random.default_rng(2)
        skewed = rng.exponential(1.0, 1000) - 1.0
        gate = TsallisRiskGate(window=2000, min_observations=20, gof_alpha=0.05)
        result = gate.evaluate(skewed)
        assert result.gof_passed is False, (
            f"INV-HPC2 fail-closed: skewed gof_passed={result.gof_passed} "
            f"(gof_p={result.gof_pvalue:.2e}) must be False. "
            f"N=1000, seed=2. A skewed exponential is not a symmetric q-Gaussian."
        )
        assert result.position_multiplier == 0.25, (
            f"INV-FE2 fail-closed: skewed multiplier="
            f"{result.position_multiplier} must be conservative 0.25. "
            f"N=1000, seed=2, gof_p={result.gof_pvalue:.2e}."
        )

    def test_clean_t_passes_gof(self):
        """A clean Student-t sample passes GoF and emits a q-derived regime."""
        rng = np.random.default_rng(11)
        clean = rng.standard_t(5, 400) * 0.01
        gate = TsallisRiskGate(window=2000, min_observations=20, gof_alpha=0.05)
        result = gate.evaluate(clean)
        assert result.gof_passed is True, (
            f"INV-HPC2: clean t(5) gof_passed={result.gof_passed} "
            f"(gof_p={result.gof_pvalue:.3f}) must be True. "
            f"N=400, seed=11. A genuine t-sample must not fail closed."
        )
        assert result.gof_pvalue >= 0.05, (
            f"INV-HPC2: clean t(5) gof_p={result.gof_pvalue:.3f} < alpha 0.05. "
            f"N=400, seed=11."
        )


class TestRegimeClassification:
    def test_normal_regime(self, gate):
        assert gate.classify_regime(1.2) == TsallisRegime.NORMAL

    def test_elevated_regime(self, gate):
        assert gate.classify_regime(1.45) == TsallisRegime.ELEVATED

    def test_crisis_regime(self, gate):
        assert gate.classify_regime(1.60) == TsallisRegime.CRISIS


class TestPositionMultiplier:
    """f(q) = max(0, 1 - (q - 1.35) / 0.20)."""

    def test_full_position_in_normal(self, gate):
        assert gate.position_multiplier(1.20) == 1.0

    def test_zero_position_in_crisis(self, gate):
        assert gate.position_multiplier(1.55) == 0.0
        assert gate.position_multiplier(2.0) == 0.0

    def test_half_position_midway(self, gate):
        mult = gate.position_multiplier(1.45)
        assert abs(mult - 0.5) < 1e-10

    def test_monotone_decreasing(self, gate):
        q_values = np.linspace(1.0, 2.0, 20)
        mults = [gate.position_multiplier(q) for q in q_values]
        for i in range(1, len(mults)):
            assert mults[i] <= mults[i - 1] + 1e-12


class TestGateEvaluation:
    def test_normal_market_full_position(self):
        # Full position requires a sample large enough to TRUST the q-MLE
        # (>= n_mle_trust). At the default tiny window the small-N guard
        # correctly refuses full position; see TestSmallNFailClosed.
        gate = TsallisRiskGate(window=400, q_normal=1.35, q_crisis=1.55)
        rng = np.random.default_rng(42)
        returns = rng.normal(0, 0.005, 400)  # low vol Gaussian, N >= trust
        result = gate.evaluate(returns)
        assert isinstance(result, TsallisGateResult)
        assert result.regime is TsallisRegime.NORMAL, (
            f"INV-FE2: a trustworthy Gaussian sample is NORMAL regime. "
            f"regime={result.regime}, q={result.q:.4f}, n={result.window_returns}."
        )
        assert result.position_multiplier == pytest.approx(1.0, abs=1e-9), (
            f"NORMAL regime grants full position. "
            f"mult={result.position_multiplier}, q={result.q:.4f}."
        )
        assert result.gof_passed is True, (
            f"INV-HPC2: a Gaussian sample (N>=trust) must fit. "
            f"gof_passed={result.gof_passed}, gof_p={result.gof_pvalue:.3f}."
        )

    def test_history_recorded(self, gate):
        rng = np.random.default_rng(42)
        returns = rng.normal(0, 0.01, 60)
        gate.evaluate(returns)
        gate.evaluate(returns)
        assert len(gate.history) == 2

    def test_2d_returns(self, gate):
        """Cross-sectional returns should work."""
        rng = np.random.default_rng(42)
        returns = rng.normal(0, 0.01, (60, 5))
        result = gate.evaluate(returns)
        assert isinstance(result, TsallisGateResult)

    def test_evaluate_prices(self, gate):
        rng = np.random.default_rng(42)
        prices = 100 + np.cumsum(rng.normal(0, 1, 100))
        result = gate.evaluate_prices(prices)
        assert isinstance(result, TsallisGateResult)


class TestDrawdownReduction:
    """Gate should reduce exposure during crisis-like returns."""

    def test_crisis_returns_reduce_position(self, gate):
        rng = np.random.default_rng(42)
        # Simulate crisis: heavy-tailed returns with high kurtosis.
        # t(2.5) is a genuine q-Gaussian-family sample (it passes GoF), so
        # the gate emits a CONFIDENT crisis regime — not a fail-closed one.
        crisis = rng.standard_t(2.5, 200) * 0.05
        result = gate.evaluate(crisis)
        assert result.position_multiplier < 1.0, (
            f"INV-FE2: crisis multiplier={result.position_multiplier} "
            f"must be < 1.0. q={result.q:.4f}, gof_p={result.gof_pvalue:.3f}, "
            f"N=30 (window), seed=42. Heavy tails → high q → reduced position."
        )


class TestInputValidation:
    def test_bad_window(self):
        with pytest.raises(ValueError):
            TsallisRiskGate(window=1)

    def test_bad_q_order(self):
        with pytest.raises(ValueError):
            TsallisRiskGate(q_normal=1.55, q_crisis=1.35)

    def test_bad_gof_alpha(self):
        with pytest.raises(ValueError):
            TsallisRiskGate(gof_alpha=0.0)
        with pytest.raises(ValueError):
            TsallisRiskGate(gof_alpha=1.0)

    def test_insufficient_prices(self, gate):
        with pytest.raises(ValueError):
            gate.evaluate_prices(np.array([100.0]))


class TestSmallNFailClosed:
    """Small-N MLE escape must fail CLOSED (one-directional, demote-only).

    scipy.stats.t.fit escapes to the Gaussian limit on a genuine heavy-tailed
    sample at small N (ν_fit ~ 1e11), reading as q≈1 / NORMAL / full position —
    a fail-OPEN: a pre-crisis heavy tail sized at full exposure. The trust
    floor (n_mle_trust) + degenerate-escape detector close this by refusing a
    LESS-conservative-than-fallback sizing when the sample is untrustworthy.
    A confident CRISIS read is NEVER weakened.
    """

    def test_heavy_tail_small_n_never_full_position(self):
        # INV-FE2 fail-closed: a genuine Student-t(ν∈{3,5}) heavy tail at the
        # default window (N=60 < n_mle_trust) must NEVER be classified
        # NORMAL/full-position via the optimiser escape, across many seeds.
        gate = TsallisRiskGate(window=60, q_normal=1.35, q_crisis=1.55)
        offenders = []
        for nu in (3.0, 5.0):
            for seed in range(30):
                rng = np.random.default_rng(1000 + seed)
                returns = rng.standard_t(nu, size=60) * 0.01
                r = gate.evaluate(returns)
                if r.regime is TsallisRegime.NORMAL or r.position_multiplier >= 1.0:
                    offenders.append((nu, seed, r.regime.value, r.position_multiplier))
        assert not offenders, (
            "INV-FE2 fail-OPEN: heavy-tail t(nu) at N=60 granted NORMAL/full "
            "position via small-N MLE escape. The trust floor must demote it. "
            f"n_mle_trust=250, window=60. "
            f"{len(offenders)} offending (nu,seed,regime,mult): {offenders[:5]}"
        )

    def test_gaussian_large_n_keeps_full_position(self):
        # No over-conservatism at scale: a true Gaussian at N >= n_mle_trust
        # still earns NORMAL / full position.
        gate = TsallisRiskGate(window=600, q_normal=1.35, q_crisis=1.55)
        rng = np.random.default_rng(7)
        returns = rng.normal(0, 0.01, 600)
        r = gate.evaluate(returns)
        assert r.regime is TsallisRegime.NORMAL and r.position_multiplier == pytest.approx(
            1.0, abs=1e-9
        ), (
            "A trustworthy (N>=trust) Gaussian must keep full position. "
            f"regime={r.regime}, mult={r.position_multiplier}, q={r.q:.4f}, "
            f"n={r.window_returns}, n_mle_trust=250"
        )

    def test_gaussian_small_n_demoted_to_conservative(self):
        # Honest small-N behaviour: a Gaussian below the trust floor cannot be
        # PROVEN Gaussian, so it is demoted to the conservative fallback
        # (not full position) rather than fail-OPEN.
        gate = TsallisRiskGate(window=60, q_normal=1.35, q_crisis=1.55)
        rng = np.random.default_rng(7)
        returns = rng.normal(0, 0.01, 60)
        r = gate.evaluate(returns)
        assert r.position_multiplier <= 0.25 + 1e-12, (
            "INV-FE2: a sub-trust-floor sample must not grant more than the "
            "conservative fallback. "
            f"mult={r.position_multiplier}, regime={r.regime}, n={r.window_returns}, "
            f"n_mle_trust=250"
        )

    def test_crisis_preserved_at_any_n(self):
        # The guard is demote-only: a genuine crisis heavy tail (low ν) still
        # cuts exposure to <= the conservative fallback at small N — the guard
        # must not WEAKEN a crisis read up toward full position.
        gate = TsallisRiskGate(window=60, q_normal=1.35, q_crisis=1.55)
        cut = 0
        for seed in range(30):
            rng = np.random.default_rng(2000 + seed)
            returns = rng.standard_t(2.2, size=60) * 0.02
            r = gate.evaluate(returns)
            # Whether the fit resolves CRISIS or the guard demotes, exposure is
            # never more generous than the conservative fallback for a genuine
            # very-heavy tail; crisis fits must reach <= fallback.
            assert r.position_multiplier <= 0.25 + 1e-12, (
                "INV-FE2: very-heavy tail t(2.2) at N=60 must not exceed the "
                f"conservative fallback. mult={r.position_multiplier}, "
                f"regime={r.regime}, seed={seed}"
            )
            if r.position_multiplier == 0.0:
                cut += 1
        assert cut >= 1, (
            "At least some t(2.2) windows should resolve to a hard CRISIS "
            f"(multiplier 0.0); the guard must not mask all crises. cut={cut}/30"
        )
