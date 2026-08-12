"""Tests for the regime detection module."""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.killtest import FeatureFrame, run_killtest
from research.microstructure.regime import regime_mask_from_score, rolling_corr_regime


def _make_features(n_rows: int, n_sym: int, seed: int, correlation: float) -> FeatureFrame:
    """Generate a synthetic FeatureFrame with controllable cross-asset correlation.

    Each symbol's 1-sec log-return is `correlation * shared + sqrt(1-ρ²) * idio`,
    so the per-period cross-asset correlation is approximately `correlation`.
    """
    rng = np.random.default_rng(seed)
    shared = rng.normal(0.0, 1.0, size=n_rows)
    mid = np.zeros((n_rows, n_sym), dtype=np.float64)
    ofi = rng.normal(0.0, 1.0, size=(n_rows, n_sym))
    qi = rng.uniform(-1.0, 1.0, size=(n_rows, n_sym))
    noise = np.sqrt(max(0.0, 1.0 - correlation * correlation))
    for k in range(n_sym):
        idio = rng.normal(0.0, 1.0, size=n_rows)
        ret = 0.001 * (correlation * shared + noise * idio)
        mid[:, k] = 100.0 + (k + 1) + ret.cumsum()
    return FeatureFrame(
        timestamps_ms=np.arange(n_rows, dtype=np.int64) * 1000,
        symbols=tuple(f"SYM{k}" for k in range(n_sym)),
        mid=mid,
        ofi=ofi,
        queue_imbalance=qi,
    )


def test_rolling_corr_regime_shape_and_warmup() -> None:
    features = _make_features(1200, 6, seed=42, correlation=0.5)
    score = rolling_corr_regime(features, window_rows=300)
    assert score.shape == (features.n_rows,)
    assert np.all(np.isnan(score[:300]))
    assert np.isfinite(score[300:]).sum() > 0


def test_rolling_corr_regime_high_vs_low() -> None:
    """High-ρ regime must yield a higher mean score than a low-ρ regime."""
    high = rolling_corr_regime(_make_features(800, 6, seed=1, correlation=0.8), window_rows=200)
    low = rolling_corr_regime(_make_features(800, 6, seed=1, correlation=0.05), window_rows=200)
    high_mean = float(np.nanmean(high))
    low_mean = float(np.nanmean(low))
    assert (
        high_mean > low_mean + 0.1
    ), f"high-ρ score {high_mean:.3f} must exceed low-ρ score {low_mean:.3f} by > 0.1"


def test_rolling_corr_regime_rejects_small_window() -> None:
    features = _make_features(400, 4, seed=0, correlation=0.3)
    with pytest.raises(ValueError):
        rolling_corr_regime(features, window_rows=10)


def test_rolling_corr_regime_rejects_single_symbol() -> None:
    features = _make_features(400, 1, seed=0, correlation=0.3)
    with pytest.raises(ValueError):
        rolling_corr_regime(features, window_rows=100)


def test_regime_mask_from_score_handles_nan() -> None:
    score = np.array([0.1, np.nan, 0.4, 0.6, np.nan, 0.3], dtype=np.float64)
    mask = regime_mask_from_score(score, threshold=0.35)
    assert mask.dtype == bool
    assert mask.tolist() == [False, False, True, True, False, False]


def test_run_killtest_rejects_wrong_mask_shape() -> None:
    features = _make_features(1500, 6, seed=42, correlation=0.5)
    bad = np.ones(features.n_rows + 1, dtype=bool)
    with pytest.raises(ValueError):
        run_killtest(features, regime_mask=bad)


def test_run_killtest_with_trivial_mask_matches_unmasked() -> None:
    """Passing an all-True mask must produce the same verdict as passing no mask."""
    features = _make_features(1500, 6, seed=42, correlation=0.5)
    unmasked = run_killtest(features, seed=42)
    full_mask = np.ones(features.n_rows, dtype=bool)
    masked = run_killtest(features, regime_mask=full_mask, seed=42)
    assert unmasked.verdict == masked.verdict
    if np.isfinite(unmasked.ic_signal) and np.isfinite(masked.ic_signal):
        assert abs(unmasked.ic_signal - masked.ic_signal) < 1e-9
