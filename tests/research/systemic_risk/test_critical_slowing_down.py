# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""CSD indicator tests — leakage, edge cases, constant policy."""

from __future__ import annotations

import numpy as np
import pytest

from research.systemic_risk.critical_slowing_down import (
    CSDConfig,
    compute_csd_indicators,
)


class TestCSDConfig:
    def test_window_too_small_rejected(self) -> None:
        with pytest.raises(ValueError, match="window must be >= 3"):
            CSDConfig(window=2, min_periods=2)

    def test_min_periods_too_small_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_periods must be >= 3"):
            CSDConfig(window=10, min_periods=2)

    def test_min_periods_exceeds_window_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"min_periods.*<= window"):
            CSDConfig(window=5, min_periods=10)

    def test_lag_zero_rejected(self) -> None:
        with pytest.raises(ValueError, match="lag must be >= 1"):
            CSDConfig(window=10, min_periods=5, lag=0)

    def test_lag_exceeds_min_periods_rejected(self) -> None:
        with pytest.raises(ValueError, match=r"lag.*<.*min_periods"):
            CSDConfig(window=10, min_periods=5, lag=5)

    def test_ddof_must_be_less_than_min_periods(self) -> None:
        # Codex audit P0: ddof >= min_periods leaves the rolling
        # variance with 0 degrees of freedom on the smallest
        # evaluated window → silent NaN. Fail-closed instead.
        with pytest.raises(ValueError, match=r"ddof.*< min_periods"):
            CSDConfig(window=10, min_periods=5, ddof=5)

    def test_ddof_less_than_min_periods_accepted(self) -> None:
        cfg = CSDConfig(window=10, min_periods=5, ddof=4)
        assert cfg.ddof == 4

    def test_ddof_zero_accepted(self) -> None:
        cfg = CSDConfig(window=10, min_periods=5, ddof=0)
        assert cfg.ddof == 0


class TestCSDIndicatorContracts:
    def test_rejects_2d(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10)
        with pytest.raises(ValueError, match="1-D"):
            compute_csd_indicators(np.zeros((10, 3)), cfg)

    def test_rejects_empty(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10)
        with pytest.raises(ValueError, match="non-empty"):
            compute_csd_indicators(np.zeros(0), cfg)

    def test_rejects_nan_internal(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10)
        x = np.arange(20, dtype=np.float64)
        x[5] = np.nan
        with pytest.raises(ValueError, match="finite"):
            compute_csd_indicators(x, cfg)

    def test_rejects_inf(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10)
        x = np.arange(20, dtype=np.float64)
        x[5] = np.inf
        with pytest.raises(ValueError, match="finite"):
            compute_csd_indicators(x, cfg)

    def test_output_length_matches_input(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10)
        x = np.arange(50, dtype=np.float64)
        out = compute_csd_indicators(x, cfg)
        assert out.variance.shape == x.shape
        assert out.lag1_autocorr.shape == x.shape
        assert out.skewness.shape == x.shape
        assert out.valid_count.shape == x.shape

    def test_insufficient_prefix_is_nan(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10)
        x = np.arange(50, dtype=np.float64)
        out = compute_csd_indicators(x, cfg)
        # Indices 0..min_periods-2 have insufficient window.
        assert np.all(np.isnan(out.variance[: cfg.min_periods - 1]))
        assert np.all(np.isfinite(out.variance[cfg.min_periods - 1 :]))

    def test_valid_count_grows(self) -> None:
        cfg = CSDConfig(window=10, min_periods=5)
        x = np.arange(15, dtype=np.float64)
        out = compute_csd_indicators(x, cfg)
        # Valid count is monotone non-decreasing up to window then constant.
        assert out.valid_count[0] == 1
        assert out.valid_count[4] == 5
        assert out.valid_count[9] == 10
        assert out.valid_count[14] == 10  # capped at window


class TestNoLookaheadLeakage:
    def test_csd_has_no_lookahead_leakage(self) -> None:
        # The protocol's load-bearing rail: mutating future
        # observations must not change any past indicator.
        x = np.arange(100, dtype=np.float64)
        cfg = CSDConfig(window=10, min_periods=10)
        base = compute_csd_indicators(x, cfg)
        x_changed = x.copy()
        x_changed[80:] = 10_000.0
        changed = compute_csd_indicators(x_changed, cfg)
        # Indices [0, 79] use only past + present ≤ 79; cannot
        # depend on indices 80+. Bit-identical (incl. NaN matches).
        np.testing.assert_array_equal(base.variance[:80], changed.variance[:80])
        np.testing.assert_array_equal(base.lag1_autocorr[:80], changed.lag1_autocorr[:80])
        np.testing.assert_array_equal(base.skewness[:80], changed.skewness[:80])


class TestConstantPolicy:
    def test_nan_policy_default(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10)
        x = np.full(20, 3.14, dtype=np.float64)
        out = compute_csd_indicators(x, cfg)
        # Constant series → variance == 0, lag1/skew NaN by default.
        valid = np.isfinite(out.variance) & (out.valid_count >= cfg.min_periods)
        assert np.all(out.variance[valid] == 0.0)
        assert np.all(np.isnan(out.lag1_autocorr[valid]))
        assert np.all(np.isnan(out.skewness[valid]))

    def test_zero_policy(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10, constant_policy="zero")
        x = np.full(20, 1.5, dtype=np.float64)
        out = compute_csd_indicators(x, cfg)
        valid = out.valid_count >= cfg.min_periods
        assert np.all(out.lag1_autocorr[valid] == 0.0)
        assert np.all(out.skewness[valid] == 0.0)

    def test_raise_policy(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10, constant_policy="raise")
        x = np.full(20, 1.5, dtype=np.float64)
        with pytest.raises(ValueError, match="degenerate window"):
            compute_csd_indicators(x, cfg)


class TestSkewnessZeroVariancePolicy:
    def test_zero_variance_yields_nan_under_default(self) -> None:
        cfg = CSDConfig(window=10, min_periods=10)
        x = np.full(20, 5.0)
        out = compute_csd_indicators(x, cfg)
        # Skew defined positions are all NaN under default policy.
        defined = out.valid_count >= cfg.min_periods
        assert np.all(np.isnan(out.skewness[defined]))


class TestRisingIndicatorsOnSyntheticBifurcation:
    def test_indicators_finite_on_simple_drift(self) -> None:
        # Synthetic series with growing variance; indicators must
        # produce finite values past the warmup.
        rng = np.random.default_rng(0)
        n = 300
        sigmas = np.linspace(0.1, 1.0, n)
        x = rng.standard_normal(n) * sigmas
        cfg = CSDConfig(window=30, min_periods=30)
        out = compute_csd_indicators(x, cfg)
        finite_var = out.variance[~np.isnan(out.variance)]
        assert finite_var.size > 0
        assert np.all(finite_var >= 0.0)
