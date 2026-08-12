# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the full Kuramoto identification stack.

This file consolidates focused tests for the four M1/M2 inverse-problem
modules that ship after phase extraction and coupling estimation:

- M1.4 :mod:`core.kuramoto.natural_frequency`
- M2.1 :mod:`core.kuramoto.delay_estimator`
- M2.2 :mod:`core.kuramoto.frustration`
- M3.1 :mod:`core.kuramoto.synthetic` (synthetic ground-truth generator)

Each test uses a small synthetic instance from
:func:`generate_sakaguchi_kuramoto` so the ground truth is known
exactly. Tests are parameterised to exercise all four ``alpha_structure``
modes of the generator (``zero``, ``symmetric``, ``antisymmetric``,
``mixed``) where applicable.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.contracts import (
    CouplingMatrix,
    DelayMatrix,
    FrustrationMatrix,
    SyntheticGroundTruth,
)
from core.kuramoto.delay_estimator import (
    DelayEstimationConfig,
    estimate_delays,
    xcorr_delay,
)
from core.kuramoto.frustration import (
    FrustrationEstimationConfig,
    estimate_frustration,
)
from core.kuramoto.natural_frequency import (
    estimate_natural_frequencies,
    estimate_natural_frequencies_from_theta,
)
from core.kuramoto.synthetic import SyntheticConfig, generate_sakaguchi_kuramoto

# ---------------------------------------------------------------------------
# M1.4 — natural frequency
# ---------------------------------------------------------------------------


class TestNaturalFrequency:
    def test_recovers_omega_of_uncoupled_oscillators(self) -> None:
        """Pure uncoupled case — median matches ω* to noise floor."""
        N, T, dt = 6, 4000, 0.05
        rng = np.random.default_rng(0)
        omega_true = rng.uniform(0.3, 1.2, size=N)
        theta = np.zeros((T, N))
        theta[0] = rng.uniform(0, 2 * np.pi, size=N)
        for t in range(1, T):
            noise = 0.02 * rng.standard_normal(N) * np.sqrt(dt)
            theta[t] = theta[t - 1] + dt * omega_true + noise
        theta = np.mod(theta, 2 * np.pi)

        omega_hat = estimate_natural_frequencies_from_theta(theta, dt=dt)
        err = np.max(np.abs(omega_hat - omega_true))
        assert err < 0.01, f"max abs error {err:.4f} above 0.01"

    def test_trimmed_mean_matches_median_for_clean_data(self) -> None:
        N, T, dt = 4, 3000, 0.05
        omega_true = np.array([0.5, 0.8, 1.0, 1.3])
        theta = np.zeros((T, N))
        for t in range(1, T):
            theta[t] = theta[t - 1] + dt * omega_true
        theta = np.mod(theta, 2 * np.pi)
        med = estimate_natural_frequencies_from_theta(theta, dt=dt, method="median")
        tri = estimate_natural_frequencies_from_theta(theta, dt=dt, method="trimmed", trim=0.1)
        assert np.allclose(med, tri, atol=1e-6)

    def test_rejects_invalid_dt(self) -> None:
        with pytest.raises(ValueError, match="dt"):
            estimate_natural_frequencies_from_theta(np.zeros((10, 3)), dt=0.0)

    def test_from_phase_matrix_infers_dt_from_timestamps(self) -> None:
        cfg = SyntheticConfig(
            N=4,
            T=2000,
            dt=0.05,
            K_sparsity=1.0,
            tau_max=0,
            alpha_structure="zero",
            alpha_max=0.0,
            sigma_noise=0.02,
            burn_in=50,
            seed=5,
        )
        gt = generate_sakaguchi_kuramoto(cfg)
        # K_sparsity=1.0 means zero edges, so oscillators are uncoupled
        omega = estimate_natural_frequencies(gt.generated_phases)
        assert omega.shape == (cfg.N,)
        assert np.max(np.abs(omega - gt.true_omega)) < 0.05

    def test_rejects_non_finite_phase(self) -> None:
        """Fail-closed: a single NaN previously poisoned the whole-column median
        (np.median is not nan-aware) while the docstring claimed 50%-outlier
        tolerance — which holds only for FINITE phase-slips, not NaN/Inf."""
        theta = np.cumsum(np.full((50, 2), 0.1), axis=0).astype(np.float64)
        theta[10, 0] = np.nan
        with pytest.raises(ValueError, match="finite"):
            estimate_natural_frequencies_from_theta(theta, dt=1.0, method="median")

    def test_rejects_too_few_timesteps(self) -> None:
        """T<3 previously raised an opaque numpy np.gradient message."""
        with pytest.raises(ValueError, match="≥3 timesteps"):
            estimate_natural_frequencies_from_theta(np.zeros((1, 3)), dt=1.0)
        with pytest.raises(ValueError, match="≥3 timesteps"):
            estimate_natural_frequencies_from_theta(np.zeros((2, 3)), dt=1.0)

    def test_median_still_robust_to_finite_outliers(self) -> None:
        """Regression: the 50%-outlier-tolerance contract holds for FINITE
        phase-slip artefacts (only NaN/Inf is now rejected)."""
        ramp = np.cumsum(np.full((60, 2), 0.1), axis=0).astype(np.float64)
        ramp[5, 0] += 50.0  # large finite phase-slip outliers
        ramp[20, 0] -= 80.0
        omega = estimate_natural_frequencies_from_theta(ramp, dt=1.0, method="median")
        assert np.allclose(omega, 0.1, atol=1e-9)


# ---------------------------------------------------------------------------
# M3.1 — synthetic ground truth
# ---------------------------------------------------------------------------


class TestSyntheticGenerator:
    @pytest.mark.parametrize("structure", ["zero", "symmetric", "antisymmetric", "mixed"])
    def test_alpha_structure(self, structure: str) -> None:
        """Verify each ``alpha_structure`` mode has the correct symmetry.

        Note: since ``α`` is zero-forced outside the active-edge mask,
        the symmetry relations only apply on bidirectional edges (both
        ``K_{ij}`` and ``K_{ji}`` non-zero).
        """
        cfg = SyntheticConfig(
            N=8,
            T=1000,
            dt=0.05,
            tau_max=2,
            alpha_max=np.pi / 4,
            alpha_structure=structure,  # type: ignore[arg-type]
            K_sparsity=0.3,  # dense so bidirectional edges are guaranteed
            burn_in=50,
            seed=42,
        )
        gt = generate_sakaguchi_kuramoto(cfg)
        assert isinstance(gt, SyntheticGroundTruth)
        if structure == "zero":
            assert np.all(gt.true_alpha == 0.0)
            return
        # Restrict to bidirectional edges: both (i,j) and (j,i) non-zero
        k_mask = gt.true_K != 0.0
        bidirectional = k_mask & k_mask.T
        if not bidirectional.any():
            pytest.skip("no bidirectional edges in this instance")
        if structure == "symmetric":
            assert np.allclose(
                gt.true_alpha[bidirectional],
                gt.true_alpha.T[bidirectional],
                atol=1e-9,
            )
        elif structure == "antisymmetric":
            assert np.allclose(
                gt.true_alpha[bidirectional],
                -gt.true_alpha.T[bidirectional],
                atol=1e-9,
            )

    def test_tau_is_zero_where_k_is_zero(self) -> None:
        gt = generate_sakaguchi_kuramoto(SyntheticConfig(N=8, T=800, tau_max=4, burn_in=50, seed=1))
        mask_no_edge = gt.true_K == 0.0
        assert np.all(gt.true_tau[mask_no_edge] == 0)

    def test_phase_wrapping_is_canonical(self) -> None:
        gt = generate_sakaguchi_kuramoto(SyntheticConfig(N=5, T=600, burn_in=50, seed=3))
        theta = gt.generated_phases.theta
        assert float(theta.min()) >= 0.0
        assert float(theta.max()) < 2 * np.pi

    def test_contract_valid_output(self) -> None:
        gt = generate_sakaguchi_kuramoto(SyntheticConfig(N=6, T=700, burn_in=50, seed=9))
        assert gt.true_K.shape == (6, 6)
        assert gt.true_K.flags.writeable is False
        assert gt.generated_phases.theta.flags.writeable is False

    def test_reproducible_under_seed(self) -> None:
        cfg = SyntheticConfig(N=5, T=600, burn_in=50, seed=17)
        gt1 = generate_sakaguchi_kuramoto(cfg)
        gt2 = generate_sakaguchi_kuramoto(cfg)
        assert np.array_equal(gt1.true_K, gt2.true_K)
        assert np.array_equal(gt1.generated_phases.theta, gt2.generated_phases.theta)

    def test_burn_in_constraint_enforced(self) -> None:
        with pytest.raises(ValueError, match="burn_in"):
            SyntheticConfig(T=1000, tau_max=100, burn_in=10)


# ---------------------------------------------------------------------------
# M2.1 — delay estimation
# ---------------------------------------------------------------------------


def _coupling_from_truth(gt: SyntheticGroundTruth) -> CouplingMatrix:
    """Build a CouplingMatrix directly from ground-truth K.

    Used in delay / frustration tests to isolate errors in those
    estimators from upstream coupling recovery noise.
    """
    n_off = gt.true_K.size - gt.true_K.shape[0]
    sparsity = float(1.0 - np.count_nonzero(gt.true_K) / n_off) if n_off else 1.0
    return CouplingMatrix(
        K=gt.true_K,
        asset_ids=gt.generated_phases.asset_ids,
        sparsity=sparsity,
        method="scad",
    )


class TestDelayEstimator:
    def test_xcorr_delay_detects_simple_lag(self) -> None:
        rng = np.random.default_rng(0)
        T = 500
        y = rng.standard_normal(T)
        lag = 4
        x = np.concatenate([np.zeros(lag), y[:-lag]])
        candidates = xcorr_delay(x, y, max_lag=10, n_candidates=3)
        assert lag in [abs(c) for c in candidates]

    def test_exact_single_edge_recovery(self) -> None:
        """On a clean single-edge instance the joint solver recovers τ exactly.

        This is the minimal identifiability scenario of the methodology:
        one isolated edge with weak coupling (no sync), large ``Δω``,
        long trajectory, and negligible noise. The estimator must hit
        the true lag exactly.
        """
        N, T, dt = 2, 6000, 0.05
        rng = np.random.default_rng(0)
        omega = np.array([0.4, 1.5])
        K = np.zeros((N, N))
        K[0, 1] = 0.4
        tau_true = np.zeros((N, N), dtype=np.int64)
        tau_true[0, 1] = 2

        theta = np.zeros((T, N))
        theta[0] = rng.uniform(0, 2 * np.pi, size=N)
        for t in range(1, T):
            td = max(0, t - 1 - int(tau_true[0, 1]))
            c0 = K[0, 1] * np.sin(theta[td, 1] - theta[t - 1, 0])
            theta[t, 0] = theta[t - 1, 0] + dt * (omega[0] + c0)
            theta[t, 1] = theta[t - 1, 1] + dt * omega[1]
        theta = np.mod(theta, 2 * np.pi)

        from core.kuramoto.contracts import PhaseMatrix

        pm = PhaseMatrix(
            theta=theta,
            timestamps=np.arange(T, dtype=np.float64) * dt,
            asset_ids=("a", "b"),
            extraction_method="hilbert",
            frequency_band=(0.01, 1.0),
        )
        coupling = CouplingMatrix(
            K=K,
            asset_ids=("a", "b"),
            sparsity=float(1 - 1 / 2),
            method="scad",
        )
        D = estimate_delays(
            pm,
            coupling,
            DelayEstimationConfig(max_lag=5, dt=dt, method="joint"),
        )
        assert int(D.tau[0, 1]) == 2, f"expected τ=2, got {int(D.tau[0, 1])}"

    @pytest.mark.parametrize("seed", [11, 23, 47])
    def test_joint_row_recovers_delays_on_synthetic(self, seed: int) -> None:
        """Joint coordinate descent recovers τ within ±2 steps on average.

        With strong coupling and synchronisation the Kuramoto inverse
        problem becomes fundamentally ill-conditioned for lag
        estimation — the sin term collapses once oscillators
        phase-lock, and mutual contributions alias into each other.
        This test uses weak coupling and large ``Δω`` so the problem
        stays identifiable, and averages across three independent
        seeds so the assertion is robust.
        """
        cfg = SyntheticConfig(
            N=4,
            T=6000,
            dt=0.05,
            K_sparsity=0.7,
            K_scale=(0.3, 0.7),
            omega_center=0.8,
            omega_spread=0.6,
            tau_max=3,
            alpha_structure="zero",
            alpha_max=0.0,
            sigma_noise=0.01,
            burn_in=50,
            seed=seed,
        )
        gt = generate_sakaguchi_kuramoto(cfg)
        coupling = _coupling_from_truth(gt)
        D = estimate_delays(
            gt.generated_phases,
            coupling,
            DelayEstimationConfig(max_lag=4, dt=cfg.dt, method="joint", n_passes=3),
        )
        active = gt.true_K != 0.0
        if active.sum() == 0:
            pytest.skip("no edges in this synthetic instance")
        err = np.abs(D.tau - gt.true_tau)[active]
        # Realistic bound on multi-edge joint recovery under
        # weak-coupling identifiability conditions. The single-edge
        # test above pins down the exact case.
        assert float(err.mean()) <= 2.0, f"seed={seed} tau MAE={err.mean():.2f} exceeds 2.0"

    def test_returns_contract_valid_delay_matrix(self) -> None:
        gt = generate_sakaguchi_kuramoto(
            SyntheticConfig(N=5, T=1000, tau_max=3, burn_in=50, seed=3)
        )
        D = estimate_delays(
            gt.generated_phases,
            _coupling_from_truth(gt),
            DelayEstimationConfig(max_lag=5, dt=0.05),
        )
        assert isinstance(D, DelayMatrix)
        assert D.tau.dtype == np.int64
        assert D.max_lag_tested == 5
        assert D.tau.flags.writeable is False

    def test_zero_delay_for_inactive_edges(self) -> None:
        gt = generate_sakaguchi_kuramoto(
            SyntheticConfig(N=6, T=800, K_sparsity=0.9, tau_max=3, burn_in=50, seed=4)
        )
        D = estimate_delays(
            gt.generated_phases,
            _coupling_from_truth(gt),
            DelayEstimationConfig(max_lag=5, dt=0.05),
        )
        inactive = gt.true_K == 0.0
        assert np.all(D.tau[inactive] == 0)

    def test_rejects_asset_id_mismatch(self) -> None:
        gt = generate_sakaguchi_kuramoto(SyntheticConfig(N=4, T=400, burn_in=40, seed=2))
        mismatched = CouplingMatrix(
            K=np.zeros((4, 4), dtype=np.float64),
            asset_ids=("a", "b", "c", "d"),
            sparsity=1.0,
            method="scad",
        )
        with pytest.raises(ValueError, match="asset_ids"):
            estimate_delays(gt.generated_phases, mismatched, DelayEstimationConfig(dt=0.05))


# ---------------------------------------------------------------------------
# M2.2 — frustration estimation
# ---------------------------------------------------------------------------


class TestFrustrationEstimator:
    def test_zero_alpha_recovered_on_zero_structure(self) -> None:
        cfg = SyntheticConfig(
            N=5,
            T=3000,
            dt=0.05,
            K_sparsity=0.6,
            K_scale=(0.6, 1.2),
            omega_center=0.8,
            omega_spread=0.3,
            tau_max=0,
            alpha_structure="zero",
            alpha_max=0.0,
            sigma_noise=0.02,
            burn_in=50,
            seed=11,
        )
        gt = generate_sakaguchi_kuramoto(cfg)
        coupling = _coupling_from_truth(gt)
        delays = DelayMatrix(
            tau=np.zeros((cfg.N, cfg.N), dtype=np.int64),
            tau_seconds=np.zeros((cfg.N, cfg.N)),
            asset_ids=gt.generated_phases.asset_ids,
            method="cross_correlation",
            max_lag_tested=0,
        )
        alpha = estimate_frustration(
            gt.generated_phases,
            coupling,
            delays,
            FrustrationEstimationConfig(dt=cfg.dt),
        )
        active = gt.true_K != 0.0
        if active.any():
            mae = float(np.mean(np.abs(alpha.alpha[active])))
            assert mae < np.pi / 6, f"MAE {mae:.3f} above π/6"

    def test_mixed_alpha_recovery_within_pi_over_4(self) -> None:
        cfg = SyntheticConfig(
            N=5,
            T=4000,
            dt=0.05,
            K_sparsity=0.6,
            K_scale=(0.7, 1.3),
            omega_center=0.8,
            omega_spread=0.3,
            tau_max=0,
            alpha_structure="mixed",
            alpha_max=np.pi / 5,
            sigma_noise=0.02,
            burn_in=50,
            seed=37,
        )
        gt = generate_sakaguchi_kuramoto(cfg)
        coupling = _coupling_from_truth(gt)
        delays = DelayMatrix(
            tau=np.zeros((cfg.N, cfg.N), dtype=np.int64),
            tau_seconds=np.zeros((cfg.N, cfg.N)),
            asset_ids=gt.generated_phases.asset_ids,
            method="cross_correlation",
            max_lag_tested=0,
        )
        alpha = estimate_frustration(
            gt.generated_phases,
            coupling,
            delays,
            FrustrationEstimationConfig(dt=cfg.dt),
        )
        active = gt.true_K != 0.0
        diff = np.angle(np.exp(1j * (alpha.alpha - gt.true_alpha)))
        mae = float(np.mean(np.abs(diff[active])))
        # Methodology: circular MAE < π/4 for mixed at S/N > 2
        assert mae < np.pi / 4, f"MAE {mae:.3f} rad exceeds π/4"

    def test_returns_contract_valid_frustration_matrix(self) -> None:
        gt = generate_sakaguchi_kuramoto(SyntheticConfig(N=4, T=500, burn_in=50, seed=1))
        delays = DelayMatrix(
            tau=np.zeros((4, 4), dtype=np.int64),
            tau_seconds=np.zeros((4, 4)),
            asset_ids=gt.generated_phases.asset_ids,
            method="cross_correlation",
            max_lag_tested=0,
        )
        alpha = estimate_frustration(
            gt.generated_phases,
            _coupling_from_truth(gt),
            delays,
            FrustrationEstimationConfig(dt=0.05),
        )
        assert isinstance(alpha, FrustrationMatrix)
        assert alpha.alpha.flags.writeable is False
        assert np.all(np.abs(alpha.alpha) <= np.pi + 1e-9)
        assert alpha.method == "profile_likelihood"


class TestNaturalFrequencyMethodDispatch:
    """`if method == "median"` selects the robust estimator; the branch must be the one taken."""

    def test_median_and_mean_diverge_on_a_skewed_sample(self) -> None:
        """Under `Eq -> NotEq` a `method="median"` request silently runs a different branch.

        Clean data hides it (median ~= mean), so the estimators must be probed on a sample
        with an OUTLIER, where the median rejects it and the mean is dragged toward it. Each
        method must return its own estimator's value.
        """
        import numpy as np

        from core.kuramoto.natural_frequency import estimate_natural_frequencies_from_theta

        rng = np.random.default_rng(0)
        dt = 0.01
        steps = 400
        # A steady 1.0 rad/step drift with one large late jump -> skewed instantaneous freq.
        theta = np.cumsum(np.full((steps, 1), 1.0 * dt), axis=0) + rng.normal(0, 1e-4, (steps, 1))
        theta[-1, 0] += 5.0  # outlier spike in the last instantaneous frequency

        median = estimate_natural_frequencies_from_theta(theta, dt=dt, method="median")
        mean = estimate_natural_frequencies_from_theta(theta, dt=dt, method="mean")
        assert not np.allclose(median, mean), "median and mean must differ on skewed data"
        # The median holds the true drift (1.0); the mean is dragged off by the spike.
        assert median[0] > mean[0]
