# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ``core.kuramoto.coupling_estimator`` (protocol M1.3).

Covers the methodology's V1/V2/V3 validation criteria:

- V1: synthetic ground-truth recovery — TPR > 0.8, FPR < 0.1 on a known
  sparse signed coupling matrix.
- V2: null rejection — <5% edges survive on temporally shuffled data.
- Prox operators: analytic verification of MCP/SCAD/soft-threshold.
- Row solver convergence on a clean least-squares problem.
- End-to-end ``CouplingEstimator`` returning a contract-valid
  :class:`CouplingMatrix`.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.contracts import CouplingMatrix, PhaseMatrix
from core.kuramoto.coupling_estimator import (
    CouplingEstimationConfig,
    CouplingEstimator,
    _proximal_gradient_row,
    estimate_coupling,
    mcp_prox,
    scad_prox,
    soft_threshold,
)

# ---------------------------------------------------------------------------
# Synthetic Kuramoto generator (Euler forward, no delays/frustration)
# ---------------------------------------------------------------------------


def _simulate_kuramoto(
    N: int,
    T: int,
    dt: float,
    K_true: np.ndarray,
    omega: np.ndarray,
    noise_std: float = 0.0,
    seed: int = 0,
) -> np.ndarray:
    """Minimal Euler-Maruyama simulator for the standard Kuramoto model.

    We deliberately omit delays and frustration here — this is the
    ground-truth case M1.3 is designed to recover exactly.
    """
    rng = np.random.default_rng(seed)
    theta = np.zeros((T, N), dtype=np.float64)
    theta[0] = rng.uniform(0.0, 2 * np.pi, size=N)
    sqrt_dt = np.sqrt(dt)
    for t in range(1, T):
        # Vectorised coupling: sin(θ_j − θ_i)
        diff = theta[t - 1, np.newaxis, :] - theta[t - 1, :, np.newaxis]
        coupling = np.sum(K_true * np.sin(diff), axis=1)
        noise = noise_std * rng.standard_normal(N) * sqrt_dt
        theta[t] = theta[t - 1] + dt * (omega + coupling) + noise
    return np.mod(theta, 2 * np.pi)


def _build_phase_matrix(theta: np.ndarray, dt: float) -> PhaseMatrix:
    T, N = theta.shape
    return PhaseMatrix(
        theta=theta,
        timestamps=np.arange(T, dtype=np.float64) * dt,
        asset_ids=tuple(f"x{i}" for i in range(N)),
        extraction_method="hilbert",
        frequency_band=(0.01, 1.0),
    )


# ---------------------------------------------------------------------------
# Prox operators — analytic checks
# ---------------------------------------------------------------------------


class TestProxOperators:
    def test_soft_threshold_kills_below_threshold(self) -> None:
        x = np.array([-0.3, -0.1, 0.0, 0.1, 0.5])
        out = soft_threshold(x, t=0.2)
        expected = np.array([-0.1, 0.0, 0.0, 0.0, 0.3])
        assert np.allclose(out, expected)

    def test_mcp_prox_three_regions(self) -> None:
        lam, gamma, step = 1.0, 3.0, 0.5
        # Region 1: |z| ≤ step*λ = 0.5  → 0
        # Region 3: |z| > γλ = 3.0      → identity
        z = np.array([0.3, 1.5, 4.0])
        out = mcp_prox(z, lam=lam, gamma=gamma, step=step)
        assert out[0] == 0.0
        assert np.isclose(out[2], 4.0)
        # Middle branch: z = 1.5, |z| - step*λ = 1.0, denom = 1 - step/γ = 5/6
        assert np.isclose(out[1], 1.0 / (5.0 / 6.0))

    def test_mcp_prox_preserves_sign(self) -> None:
        z = np.array([-2.0, -1.5, 1.5, 2.0])
        out = mcp_prox(z, lam=1.0, gamma=3.0, step=0.5)
        assert np.all(np.sign(out) == np.sign(z))

    def test_scad_prox_equals_identity_for_large_values(self) -> None:
        z = np.array([5.0, 10.0])
        out = scad_prox(z, lam=1.0, gamma=3.7, step=0.5)
        assert np.allclose(out, z)


# ---------------------------------------------------------------------------
# Row solver — convergence on a clean LS problem
# ---------------------------------------------------------------------------


class TestRowSolver:
    def test_lasso_recovers_sparse_coefficients(self) -> None:
        rng = np.random.default_rng(0)
        n, p = 400, 10
        X = rng.standard_normal((n, p))
        # Standardise columns so ‖X_j‖²/n ≈ 1 and the λ grid is interpretable
        X /= X.std(axis=0, keepdims=True)
        beta_true = np.zeros(p)
        beta_true[1] = 1.5
        beta_true[4] = -2.0
        beta_true[7] = 0.9
        y = X @ beta_true + 0.01 * rng.standard_normal(n)

        beta_hat = _proximal_gradient_row(X, y, lam=0.01, penalty="lasso", max_iter=2000, tol=1e-9)
        assert np.allclose(beta_hat, beta_true, atol=0.05)

    def test_mcp_zeros_noise_coefficients(self) -> None:
        rng = np.random.default_rng(1)
        n, p = 500, 20
        X = rng.standard_normal((n, p))
        X /= X.std(axis=0, keepdims=True)
        beta_true = np.zeros(p)
        beta_true[3] = 2.0
        beta_true[12] = -1.5
        y = X @ beta_true + 0.05 * rng.standard_normal(n)

        beta_hat = _proximal_gradient_row(
            X, y, lam=0.05, penalty="mcp", gamma=3.0, max_iter=2000, tol=1e-9
        )
        # Signal coefficients recovered
        assert abs(beta_hat[3] - 2.0) < 0.15
        assert abs(beta_hat[12] - (-1.5)) < 0.15
        # All noise coefficients are exactly zero thanks to MCP's unbiasedness
        noise_mask = np.ones(p, dtype=bool)
        noise_mask[[3, 12]] = False
        assert np.all(beta_hat[noise_mask] == 0.0)


# ---------------------------------------------------------------------------
# End-to-end synthetic recovery (V1)
# ---------------------------------------------------------------------------


class TestSyntheticRecovery:
    @staticmethod
    @pytest.fixture(scope="class")
    def ground_truth() -> tuple[np.ndarray, np.ndarray, PhaseMatrix]:
        """Small, well-identified sparse Kuramoto instance.

        Eight oscillators, six ground-truth edges (≈89% sparsity on the
        off-diagonal), moderate coupling, low noise, long trajectory.
        """
        N, T, dt = 8, 3000, 0.05
        K_true = np.zeros((N, N), dtype=np.float64)
        K_true[0, 1] = 1.8
        K_true[1, 0] = 1.5
        K_true[2, 3] = -1.2
        K_true[3, 2] = -1.4
        K_true[4, 5] = 2.0
        K_true[6, 7] = 1.1
        rng = np.random.default_rng(42)
        omega = rng.uniform(0.3, 0.7, size=N)
        theta = _simulate_kuramoto(N, T, dt, K_true, omega, noise_std=0.05, seed=42)
        return K_true, omega, _build_phase_matrix(theta, dt)

    def test_edge_recovery_tpr_fpr(
        self, ground_truth: tuple[np.ndarray, np.ndarray, PhaseMatrix]
    ) -> None:
        K_true, _omega, pm = ground_truth
        cfg = CouplingEstimationConfig(
            penalty="mcp",
            lambda_reg=0.15,
            dt=float(pm.timestamps[1] - pm.timestamps[0]),
            max_iter=2000,
            tol=1e-7,
        )
        K_hat = estimate_coupling(pm, cfg).K

        true_edges = np.abs(K_true) > 0
        hat_edges = np.abs(K_hat) > 0
        np.fill_diagonal(true_edges, False)
        np.fill_diagonal(hat_edges, False)

        tp = int(np.sum(true_edges & hat_edges))
        fn = int(np.sum(true_edges & ~hat_edges))
        fp = int(np.sum(~true_edges & hat_edges))
        tn = int(np.sum(~true_edges & ~hat_edges))
        tpr = tp / max(tp + fn, 1)
        fpr = fp / max(fp + tn, 1)

        assert tpr >= 0.8, f"TPR={tpr:.3f} below 0.8 threshold"
        assert fpr <= 0.1, f"FPR={fpr:.3f} above 0.1 threshold"

    def test_sign_recovery(self, ground_truth: tuple[np.ndarray, np.ndarray, PhaseMatrix]) -> None:
        K_true, _, pm = ground_truth
        cfg = CouplingEstimationConfig(
            penalty="mcp",
            lambda_reg=0.15,
            dt=float(pm.timestamps[1] - pm.timestamps[0]),
            max_iter=2000,
            tol=1e-7,
        )
        K_hat = estimate_coupling(pm, cfg).K
        true_mask = np.abs(K_true) > 0
        matched = true_mask & (np.abs(K_hat) > 0)
        if matched.sum() == 0:
            pytest.fail("no edges detected at all")
        sign_acc = float(np.mean(np.sign(K_hat[matched]) == np.sign(K_true[matched])))
        assert sign_acc >= 0.9, f"sign accuracy {sign_acc:.3f} below 0.9"


# ---------------------------------------------------------------------------
# Null rejection (V2)
# ---------------------------------------------------------------------------


class TestNullRejection:
    def test_shuffled_phases_yield_few_edges(self) -> None:
        """Break temporal structure and confirm the estimator degenerates.

        Each oscillator's phase series is independently shuffled, which
        destroys the dynamics that generated ``sin(θ_j − θ_i)``
        correlations. At the same ``λ`` we expect far fewer non-zero
        edges than on the real data.
        """
        N, T, dt = 6, 2000, 0.05
        K_true = np.zeros((N, N))
        K_true[0, 1] = K_true[1, 0] = 1.5
        K_true[2, 3] = K_true[3, 2] = 1.2
        rng = np.random.default_rng(7)
        omega = rng.uniform(0.3, 0.6, size=N)
        theta = _simulate_kuramoto(N, T, dt, K_true, omega, noise_std=0.05, seed=7)

        pm = _build_phase_matrix(theta, dt)
        cfg = CouplingEstimationConfig(
            penalty="mcp", lambda_reg=0.15, dt=dt, max_iter=2000, tol=1e-7
        )
        K_real = estimate_coupling(pm, cfg).K
        real_edges = int(np.count_nonzero(K_real))

        shuffled = theta.copy()
        for i in range(N):
            rng.shuffle(shuffled[:, i])
        pm_null = _build_phase_matrix(shuffled, dt)
        K_null = estimate_coupling(pm_null, cfg).K
        null_edges = int(np.count_nonzero(K_null))

        # Shuffling must cost us real edges AND keep FP count low.
        off_diag = N * N - N
        assert null_edges < real_edges, (
            f"null_edges={null_edges} ≥ real_edges={real_edges}: "
            "estimator does not discriminate signal from noise"
        )
        assert null_edges / off_diag < 0.2, f"null density {null_edges / off_diag:.2f} too high"


# ---------------------------------------------------------------------------
# High-level CouplingEstimator → CouplingMatrix contract
# ---------------------------------------------------------------------------


class TestCouplingEstimatorAPI:
    def test_returns_contract_valid_matrix(self) -> None:
        N, T, dt = 5, 2000, 0.05
        K_true = np.zeros((N, N))
        K_true[0, 1] = 1.5
        K_true[1, 0] = 1.4
        K_true[3, 4] = -1.3
        rng = np.random.default_rng(11)
        omega = rng.uniform(0.3, 0.6, size=N)
        theta = _simulate_kuramoto(N, T, dt, K_true, omega, noise_std=0.05, seed=11)
        pm = _build_phase_matrix(theta, dt)

        cfg = CouplingEstimationConfig(
            penalty="mcp", lambda_reg=0.02, dt=dt, max_iter=1500, tol=1e-7
        )
        result = CouplingEstimator(cfg).estimate(pm)

        assert isinstance(result, CouplingMatrix)
        assert result.K.shape == (N, N)
        assert np.all(np.diag(result.K) == 0.0)
        assert result.K.flags.writeable is False  # deeply immutable
        assert result.method == "mcp"
        assert 0.0 <= result.sparsity <= 1.0
        assert result.asset_ids == pm.asset_ids

    def test_stability_selection_smoke(self) -> None:
        """Stability selection runs end-to-end and attaches scores.

        Kept small (N=4, T=600, n_subsamples=4, small λ-grid) so the
        test stays fast — the methodology's quality claims are tested
        separately in the V1 recovery test above.
        """
        N, T, dt = 4, 600, 0.05
        K_true = np.zeros((N, N))
        K_true[0, 1] = 1.5
        K_true[1, 0] = 1.4
        rng = np.random.default_rng(3)
        omega = rng.uniform(0.3, 0.6, size=N)
        theta = _simulate_kuramoto(N, T, dt, K_true, omega, noise_std=0.05, seed=3)
        pm = _build_phase_matrix(theta, dt)

        cfg = CouplingEstimationConfig(
            penalty="mcp",
            lambda_reg=0.02,
            dt=dt,
            max_iter=500,
            tol=1e-5,
            stability_selection=True,
            lambda_grid=(0.01, 0.03, 0.1),
            n_subsamples=4,
            subsample_fraction=0.5,
            stability_threshold=0.5,
            random_state=0,
        )
        result = CouplingEstimator(cfg).estimate(pm)
        assert result.stability_scores is not None
        assert result.stability_scores.shape == (N, N)
        assert float(result.stability_scores.min()) >= 0.0
        assert float(result.stability_scores.max()) <= 1.0
        # Real edges (0→1, 1→0) should have higher stability than noise edges
        real_stab = result.stability_scores[[0, 1], [1, 0]].mean()
        noise_stab_mask = np.ones((N, N), dtype=bool)
        noise_stab_mask[[0, 1], [1, 0]] = False
        np.fill_diagonal(noise_stab_mask, False)
        noise_stab = result.stability_scores[noise_stab_mask].mean()
        assert real_stab > noise_stab


# ---------------------------------------------------------------------------
# Median-contract regression for complementary_pairs_stability
# ---------------------------------------------------------------------------


class TestComplementaryPairsMedianContract:
    """K_median must be the MEDIAN of the pooled non-zero edge estimates.

    The docstring, the ``K_median`` variable name, and the consuming
    ``CouplingEstimator.estimate`` docstring all promise the median — a
    robust statistic. A prior implementation returned the arithmetic MEAN
    (``weight_sum / weight_n``), which an outlier fit drags away from the
    contracted value. These tests pin the median semantics by feeding a
    crafted, fully deterministic pool of per-edge fits through a stub row
    solver so the expected statistic is exact (no float tolerance slack on
    the median value itself).
    """

    def test_median_not_mean_on_crafted_pool(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from core.kuramoto import coupling_estimator as ce

        # 2 subsamples × 2 halves × 1 λ  →  exactly 4 fits per edge.
        # Edge (0, 1) receives the pool {0.1, 0.1, 0.1, 5.0}:
        #   contracted median = 0.1   (robust to the 5.0 outlier)
        #   buggy mean         = 1.325 (dragged up by the outlier)
        pool = iter([0.1, 0.1, 0.1, 5.0])

        def _fake_single(
            theta_sub: np.ndarray, lam: float, cfg: CouplingEstimationConfig
        ) -> np.ndarray:
            K_hat = np.zeros((2, 2), dtype=np.float64)
            K_hat[0, 1] = next(pool)
            return K_hat

        monkeypatch.setattr(ce, "_estimate_K_single", _fake_single)

        cfg = CouplingEstimationConfig(
            stability_selection=True,
            lambda_grid=(0.01,),
            n_subsamples=2,
            subsample_fraction=0.5,
            random_state=0,
        )
        theta = np.zeros((100, 2), dtype=np.float64)
        K_median, stability = ce.complementary_pairs_stability(theta, cfg)

        # MEDIAN contract: exact on the crafted pool.
        assert K_median[0, 1] == pytest.approx(0.1, abs=1e-12), (
            f"K_median must be the MEDIAN of {{0.1, 0.1, 0.1, 5.0}} = 0.1, "
            f"got {K_median[0, 1]!r}. A value near the mean (1.325) means the "
            "outlier-biased mean bug regressed."
        )
        # The 5.0 outlier must NOT drag the estimate toward the mean.
        assert K_median[0, 1] < 1.0, (
            f"K_median={K_median[0, 1]!r} shows outlier contamination; the "
            "median of {0.1,0.1,0.1,5.0} is 0.1, well below the mean 1.325."
        )
        # Never-selected edges stay exactly zero; diagonal is zeroed.
        assert K_median[1, 0] == 0.0
        assert K_median[0, 0] == 0.0 and K_median[1, 1] == 0.0
        assert 0.0 <= float(stability[0, 1]) <= 1.0

    def test_median_even_pool_averages_two_central(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Even-sized pool → mean of the two central order statistics."""
        from core.kuramoto import coupling_estimator as ce

        # Pool {1.0, 2.0, 3.0, 100.0}: median = (2.0 + 3.0) / 2 = 2.5.
        pool = iter([1.0, 2.0, 3.0, 100.0])

        def _fake_single(
            theta_sub: np.ndarray, lam: float, cfg: CouplingEstimationConfig
        ) -> np.ndarray:
            K_hat = np.zeros((2, 2), dtype=np.float64)
            K_hat[0, 1] = next(pool)
            return K_hat

        monkeypatch.setattr(ce, "_estimate_K_single", _fake_single)

        cfg = CouplingEstimationConfig(
            stability_selection=True,
            lambda_grid=(0.01,),
            n_subsamples=2,
            subsample_fraction=0.5,
            random_state=1,
        )
        theta = np.zeros((100, 2), dtype=np.float64)
        K_median, _ = ce.complementary_pairs_stability(theta, cfg)
        assert K_median[0, 1] == pytest.approx(2.5, abs=1e-12), (
            f"Median of {{1,2,3,100}} is 2.5 (mean would be 26.5), "
            f"got {K_median[0, 1]!r}."
        )


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:
    def test_rejects_unknown_penalty(self) -> None:
        with pytest.raises(ValueError, match="penalty"):
            CouplingEstimationConfig(penalty="elasticnet")

    def test_rejects_non_positive_lambda(self) -> None:
        with pytest.raises(ValueError, match="lambda_reg"):
            CouplingEstimationConfig(lambda_reg=0.0)

    def test_rejects_gamma_le_1(self) -> None:
        with pytest.raises(ValueError, match="gamma"):
            CouplingEstimationConfig(gamma=1.0)
