# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Invariant tests for :mod:`research.systemic_risk.early_warning`.

Physics anchors:
* INV-K1: ``0 <= R(t) <= 1`` for any phases (universal).
* INV-K5: ``<R> ~ O(1/sqrt(N))`` for incoherent phases (statistical).
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.contracts import PhaseMatrix
from research.systemic_risk.early_warning import (
    EarlyWarningConfig,
    compute_early_warning,
    kuramoto_order_parameter,
)


class TestKuramotoOrderParameter:
    def test_inv_k1_universal_bounds_random_phases(self) -> None:
        # INV-K1: R ∈ [0, 1] for any phases. Canonical layout (T, N).
        rng = np.random.default_rng(42)
        for _ in range(20):
            t, n = int(rng.integers(20, 200)), int(rng.integers(2, 50))
            phases = rng.uniform(-np.pi, np.pi, size=(t, n))
            r = kuramoto_order_parameter(phases)
            assert np.all(r >= 0.0) and np.all(r <= 1.0 + 1e-12), (
                f"INV-K1 VIOLATED: R out of [0,1]; "
                f"min={r.min():.6f}, max={r.max():.6f} "
                f"at N={n}, T={t}"
            )

    def test_inv_k5_incoherent_finite_size(self) -> None:
        # INV-K5: <R> ~ 1/sqrt(N) under uniform phases. Use C=3/sqrt(N) bound.
        rng = np.random.default_rng(7)
        n = 100
        t = 1000
        ensemble = []
        for _ in range(50):
            phases = rng.uniform(-np.pi, np.pi, size=(t, n))
            ensemble.append(float(kuramoto_order_parameter(phases).mean()))
        mean_r = float(np.mean(ensemble))
        bound = 3.0 / np.sqrt(n)
        assert mean_r < bound, (
            f"INV-K5 VIOLATED: <R>={mean_r:.4f} >= ε=3/√N={bound:.4f} "
            f"expected R→O(1/√N) for incoherent phases. "
            f"At N={n}, T={t}, n_seeds=50"
        )

    def test_perfect_coherence_yields_R_one(self) -> None:
        t, n = 100, 20
        phases = np.zeros((t, n), dtype=np.float64)
        r = kuramoto_order_parameter(phases)
        assert np.allclose(r, 1.0, atol=1e-12), (
            f"INV-K1 VIOLATED: identical phases must give R=1; got max diff "
            f"{float(np.abs(r - 1.0).max()):.2e} at N={n}, T={t}"
        )

    def test_rejects_1d_input(self) -> None:
        with pytest.raises(ValueError):
            kuramoto_order_parameter(np.zeros(10, dtype=np.float64))


class TestEarlyWarningConfig:
    @pytest.mark.parametrize("window", [0, 1, 3])
    def test_inv_ew1_small_window_rejected(self, window: int) -> None:
        with pytest.raises(ValueError, match="INV-EW1"):
            EarlyWarningConfig(window=window)

    @pytest.mark.parametrize("frac", [0.4, 0.0, 1.5])
    def test_inv_ew2_bad_fraction_rejected(self, frac: float) -> None:
        with pytest.raises(ValueError, match="INV-EW2"):
            EarlyWarningConfig(min_window_fraction=frac)


class TestComputeEarlyWarning:
    def _make_phase_matrix(self, n: int, t: int, seed: int) -> PhaseMatrix:
        rng = np.random.default_rng(seed)
        # PhaseMatrix.theta is (T, N), wrapped to [0, 2π) per its contract.
        theta = rng.uniform(0.0, 2.0 * np.pi, size=(t, n)).astype(np.float64)
        # Guard against the open upper edge with a safety nudge.
        theta = np.minimum(theta, np.nextafter(2.0 * np.pi, 0.0))
        ts = np.arange(t, dtype=np.float64)
        return PhaseMatrix(
            theta=theta,
            timestamps=ts,
            asset_ids=tuple(f"b{i}" for i in range(n)),
            extraction_method="hilbert",
            frequency_band=(0.01, 0.2),
        )

    def test_features_are_nan_at_start_then_finite(self) -> None:
        pm = self._make_phase_matrix(n=10, t=100, seed=42)
        cfg = EarlyWarningConfig(window=20)
        result = compute_early_warning(pm, cfg)
        assert np.all(np.isnan(result.R_level[: cfg.window - 1]))
        assert np.all(np.isfinite(result.R_level[cfg.window - 1 :]))
        assert np.all(np.isfinite(result.R_var[cfg.window - 1 :]))
        assert np.all(np.isfinite(result.R_slope[cfg.window - 1 :]))

    def test_inv_k1_R_in_bounds(self) -> None:
        pm = self._make_phase_matrix(n=30, t=200, seed=11)
        cfg = EarlyWarningConfig(window=30)
        result = compute_early_warning(pm, cfg)
        assert np.all(result.R >= 0.0) and np.all(result.R <= 1.0 + 1e-12)

    def test_score_non_negative(self) -> None:
        pm = self._make_phase_matrix(n=20, t=200, seed=3)
        result = compute_early_warning(pm, EarlyWarningConfig(window=30))
        finite = result.score[np.isfinite(result.score)]
        assert finite.size > 0
        assert np.all(finite >= 0.0)

    def test_T_shorter_than_window_rejected(self) -> None:
        pm = self._make_phase_matrix(n=5, t=10, seed=0)
        with pytest.raises(ValueError, match="shorter than window"):
            compute_early_warning(pm, EarlyWarningConfig(window=30))
