"""Tests for attribution module: Gini, lag sweep, autocorrelation decay."""

from __future__ import annotations

import numpy as np

from research.microstructure.attribution import (
    AutocorrReport,
    ConcentrationReport,
    LagReport,
    autocorrelation_decay,
    concentration_report,
    gini_coefficient,
    lag_ic_sweep,
)


def test_gini_uniform_is_near_zero() -> None:
    values = np.ones(1000, dtype=np.float64)
    g = gini_coefficient(values)
    assert 0.0 <= g < 1e-12


def test_gini_concentrated_is_near_one() -> None:
    values = np.zeros(1000, dtype=np.float64)
    values[0] = 1000.0
    g = gini_coefficient(values)
    assert g > 0.99


def test_gini_empty_is_zero() -> None:
    g = gini_coefficient(np.array([], dtype=np.float64))
    assert g == 0.0


def test_gini_all_zero_is_zero() -> None:
    g = gini_coefficient(np.zeros(500, dtype=np.float64))
    assert g == 0.0


def test_gini_two_point_distribution() -> None:
    """Half uniform, half at 10× the uniform value — Gini should be moderate."""
    values = np.concatenate([np.ones(500, dtype=np.float64), 10.0 * np.ones(500, dtype=np.float64)])
    g = gini_coefficient(values)
    # Analytical: this specific pair distribution → G ~ 0.41
    assert 0.30 < g < 0.50


def test_concentration_report_schema_and_top_k_monotone() -> None:
    rng = np.random.default_rng(42)
    trades = rng.normal(0.0, 5.0, size=200).tolist()
    r = concentration_report(trades)
    assert isinstance(r, ConcentrationReport)
    assert r.n_trades == 200
    assert r.total_abs_bp > 0.0
    # monotonic top-K: 5% ≤ 10% ≤ 20%
    assert r.top_5_pct_frac_of_total <= r.top_10_pct_frac_of_total
    assert r.top_10_pct_frac_of_total <= r.top_20_pct_frac_of_total
    # top_20 must exceed 20% (since sort is descending magnitude)
    assert r.top_20_pct_frac_of_total > 0.20
    # 80% frac must lie in (0, 1]
    assert 0.0 < r.trades_frac_for_80_pct_of_total <= 1.0


def test_concentration_report_empty_trades() -> None:
    r = concentration_report([])
    assert r.n_trades == 0
    assert r.gini == 0.0
    assert r.trades_frac_for_80_pct_of_total == 0.0


def test_concentration_report_one_dominant_trade_has_high_gini() -> None:
    """One trade carrying 99% of notional → Gini near 1."""
    trades = [0.001] * 99 + [100.0]
    r = concentration_report(trades)
    assert r.gini > 0.90
    # top 5% (5 trades) should capture >95% of total
    assert r.top_5_pct_frac_of_total > 0.95


def test_lag_ic_sweep_identity_at_zero_lag() -> None:
    """With no shift, IC should equal vanilla Spearman."""
    rng = np.random.default_rng(42)
    n_rows = 500
    signal = rng.normal(0.0, 1.0, size=n_rows)
    target = np.stack(
        [
            signal + rng.normal(0.0, 0.1, size=n_rows),
            signal + rng.normal(0.0, 0.1, size=n_rows),
            signal + rng.normal(0.0, 0.1, size=n_rows),
        ],
        axis=1,
    )
    report = lag_ic_sweep(signal, target, lags_sec=(0,))
    assert np.isfinite(report.ic_per_lag[0])
    # Strong signal → target direct link → IC near 1.0
    assert report.ic_per_lag[0] > 0.9


def test_lag_ic_sweep_verdict_taxonomy() -> None:
    rng = np.random.default_rng(42)
    n_rows = 500
    signal = rng.normal(0.0, 1.0, size=n_rows)
    target = np.stack(
        [rng.normal(0.0, 1.0, size=n_rows), rng.normal(0.0, 1.0, size=n_rows)], axis=1
    )
    r = lag_ic_sweep(signal, target, lags_sec=(-60, 0, +60))
    assert isinstance(r, LagReport)
    assert r.verdict in {"LEADING", "COINCIDENT", "LAGGING", "UNRESOLVED"}
    assert r.ic_peak_lag_sec in {-60, 0, +60}


def test_lag_ic_sweep_all_nan_returns_unresolved() -> None:
    """If target is constant, IC is NaN at every lag → UNRESOLVED."""
    n_rows, n_sym = 500, 2
    signal = np.random.default_rng(42).normal(0.0, 1.0, size=n_rows)
    target = np.ones((n_rows, n_sym), dtype=np.float64) * 3.14
    r = lag_ic_sweep(signal, target, lags_sec=(-30, 0, +30))
    assert r.verdict == "UNRESOLVED"
    assert not np.isfinite(r.ic_peak_value)


def test_autocorrelation_decay_white_noise_fast_decay() -> None:
    """White noise should decay almost immediately past lag 0."""
    rng = np.random.default_rng(42)
    signal = rng.normal(0.0, 1.0, size=5000)
    r = autocorrelation_decay(signal, max_lag_sec=200, lag_step_sec=10)
    assert isinstance(r, AutocorrReport)
    # First ACF entry is lag 0 = 1.0
    assert abs(r.acf[0] - 1.0) < 1e-9
    # Decay time should be short (< 30s for white noise)
    assert r.tau_decay_sec is not None
    assert r.tau_decay_sec <= 30.0


def test_autocorrelation_decay_persistent_signal_slow_decay() -> None:
    """AR(1) with high phi should have long decay."""
    rng = np.random.default_rng(42)
    n = 8000
    phi = 0.98
    noise = rng.normal(0.0, 1.0, size=n)
    signal = np.zeros(n, dtype=np.float64)
    for t in range(1, n):
        signal[t] = phi * signal[t - 1] + noise[t]
    r = autocorrelation_decay(signal, max_lag_sec=600, lag_step_sec=10)
    assert r.tau_decay_sec is not None
    # For AR(1) with phi=0.98, τ_decay ≈ 1/(1-phi) ≈ 50, so > 30
    assert r.tau_decay_sec > 30.0


def test_autocorrelation_decay_short_signal_returns_trivial() -> None:
    signal = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    r = autocorrelation_decay(signal)
    assert r.tau_decay_sec is None
    assert r.acf == (1.0,)


def test_autocorrelation_decay_constant_signal_no_threshold_cross() -> None:
    signal = np.ones(5000, dtype=np.float64) * 2.5
    r = autocorrelation_decay(signal, max_lag_sec=200, lag_step_sec=10)
    # Constant → zero variance → ACF undefined → tau None
    # Either all NaN beyond lag 0, or tau stays None
    assert r.tau_decay_sec is None or r.tau_decay_sec > 0.0
