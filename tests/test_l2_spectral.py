"""Tests for spectral analysis module."""

from __future__ import annotations

import numpy as np

from research.microstructure.spectral import (
    SpectralReport,
    spectral_report,
)


def test_spectral_white_noise_returns_white_verdict() -> None:
    rng = np.random.default_rng(42)
    x = rng.normal(0.0, 1.0, size=8000)
    r = spectral_report(x, fs_hz=1.0, segment_sec=500)
    assert isinstance(r, SpectralReport)
    assert r.regime_verdict in {"WHITE", "INCONCLUSIVE"}
    assert abs(r.redness_slope_beta) < 0.5


def test_spectral_random_walk_returns_red_verdict() -> None:
    """Cumulative-sum noise has 1/f² power spectrum → β ≈ 2 → RED."""
    rng = np.random.default_rng(42)
    inc = rng.normal(0.0, 1.0, size=8000)
    x = np.cumsum(inc)
    r = spectral_report(x, fs_hz=1.0, segment_sec=500)
    assert r.regime_verdict == "RED"
    assert r.redness_slope_beta > 1.3


def test_spectral_pink_noise_returns_pink_verdict() -> None:
    """Build approximate 1/f noise via inverse FFT of A(f) ∝ 1/√f."""
    rng = np.random.default_rng(42)
    n = 8000
    freqs = np.fft.rfftfreq(n, d=1.0)
    # Guard against divide-by-zero at the DC bin by setting f→NaN there then
    # zeroing the amplitude; keeps the test warning-free.
    with np.errstate(divide="ignore", invalid="ignore"):
        amps = np.where(freqs > 0, 1.0 / np.sqrt(np.where(freqs > 0, freqs, 1.0)), 0.0)
    phases = rng.uniform(0.0, 2.0 * np.pi, size=amps.size)
    spec = amps * np.exp(1j * phases)
    x = np.fft.irfft(spec, n=n).astype(np.float64)
    r = spectral_report(x, fs_hz=1.0, segment_sec=500)
    assert r.regime_verdict in {"PINK", "RED"}
    assert 0.5 < r.redness_slope_beta < 1.8


def test_spectral_short_signal_returns_inconclusive() -> None:
    x = np.arange(100, dtype=np.float64)
    r = spectral_report(x, fs_hz=1.0, segment_sec=60)
    assert r.regime_verdict == "INCONCLUSIVE"
    assert r.dominant_period_sec is None


def test_spectral_sinusoid_finds_correct_period() -> None:
    """Pure sine at period=120s should yield dominant_period_sec ≈ 120."""
    n = 16000
    period = 120
    t = np.arange(n, dtype=np.float64)
    x = np.sin(2.0 * np.pi * t / period) + 0.05 * np.random.default_rng(42).normal(0.0, 1.0, size=n)
    r = spectral_report(x, fs_hz=1.0, segment_sec=1200, peak_min_period_sec=10.0)
    assert r.dominant_period_sec is not None
    # Frequency resolution is limited by segment length; accept ±20 % tolerance.
    assert abs(r.dominant_period_sec - period) < 30.0


def test_spectral_constant_signal_returns_some_verdict() -> None:
    """Constant signal after mean-detrend is numerically zero; the log-log fit
    operates on floating-point round-off noise and can yield any verdict.
    Test contract: pipeline must not crash and must return a valid verdict
    label."""
    x = np.ones(5000, dtype=np.float64) * 2.71
    r = spectral_report(x, fs_hz=1.0, segment_sec=300)
    assert r.regime_verdict in {"WHITE", "PINK", "RED", "INCONCLUSIVE"}


def test_spectral_report_schema_complete() -> None:
    rng = np.random.default_rng(42)
    x = rng.normal(0.0, 1.0, size=5000)
    r = spectral_report(x, fs_hz=1.0, segment_sec=300)
    assert isinstance(r.frequencies_hz, tuple)
    assert isinstance(r.psd, tuple)
    assert len(r.frequencies_hz) == len(r.psd)
    assert np.isfinite(r.redness_slope_beta) or r.regime_verdict == "INCONCLUSIVE"
    assert r.regime_verdict in {"WHITE", "PINK", "RED", "INCONCLUSIVE"}
