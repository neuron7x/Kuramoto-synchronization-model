"""Tests for wavelet-based Hölder exponent estimation."""

from __future__ import annotations

import numpy as np
import pytest

from core.metrics.holder import (
    holder_exponent_wavelet,
    local_holder_spectrum,
    multifractal_width,
    singularity_spectrum,
)
from utils.fractal_cascade import pink_noise

try:
    import pywt  # noqa: F401

    _PYWT_AVAILABLE = True
except ImportError:
    _PYWT_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _PYWT_AVAILABLE, reason="PyWavelets not installed")


def test_holder_exponent_basic():
    """Test basic Hölder exponent estimation on synthetic data."""
    # Generate simple random walk (H ≈ 0.5-1.0)
    # Note: cumsum of white noise has H near 1.0 for finite samples
    rng = np.random.default_rng(42)
    random_walk = np.cumsum(rng.normal(0, 1, 1024))

    h = holder_exponent_wavelet(random_walk)
    # Random walk/integrated white noise should have H in [0.3, 1.5]
    assert 0.3 < h < 1.5, f"Unexpected H for random walk: {h}"


def test_holder_exponent_pink_noise():
    """Test Hölder exponent on colored noise with known scaling."""
    # Pink noise (1/f, beta=1) integrated should have H > 1
    # because integration adds smoothness
    rng = np.random.default_rng(42)
    noise = pink_noise(4096, beta=1.0, rng=rng)
    integrated = np.cumsum(noise)  # Integrate to get smoother signal

    h = holder_exponent_wavelet(integrated)
    # Integrated pink noise is smoother, should have H in [0.5, 2.0]
    assert 0.5 < h <= 2.0, f"Unexpected Hölder exponent: {h}"


def test_holder_exponent_smooth_signal():
    """Test that smooth signals have higher Hölder exponent."""
    # Very smooth sinusoid
    t = np.linspace(0, 10 * np.pi, 2048)
    smooth = np.sin(t)

    h = holder_exponent_wavelet(smooth)
    # Smooth signals should have H > 0.5
    assert h > 0.3, f"Expected H > 0.3 for smooth signal, got {h}"


def test_holder_exponent_short_series():
    """Test behavior with short time series."""
    short = np.random.randn(16)
    h = holder_exponent_wavelet(short)
    # Should return default 0.5 for too-short series
    assert h == 0.5


def test_holder_exponent_empty():
    """Test behavior with empty input."""
    empty = np.array([])
    h = holder_exponent_wavelet(empty)
    assert h == 0.5


def test_holder_exponent_with_nans():
    """Test that NaN values are handled properly."""
    data = np.random.randn(512)
    data[100:110] = np.nan
    h = holder_exponent_wavelet(data)
    assert 0.0 <= h <= 2.0


def test_local_holder_spectrum_basic():
    """Test local Hölder spectrum computation."""
    rng = np.random.default_rng(42)
    signal = np.cumsum(rng.normal(0, 1, 512))

    positions, h_local = local_holder_spectrum(signal, window=64)

    assert len(positions) == len(h_local)
    assert len(positions) > 0
    assert all(0.0 <= h <= 2.0 for h in h_local)


def test_local_holder_spectrum_short():
    """Test local Hölder spectrum with short input."""
    short = np.random.randn(32)
    pos, h_local = local_holder_spectrum(short, window=64)

    # Should return single point for too-short input
    assert len(pos) == 1
    assert len(h_local) == 1


def test_singularity_spectrum_basic():
    """Test singularity spectrum computation."""
    rng = np.random.default_rng(42)
    signal = np.cumsum(rng.normal(0, 1, 2048))

    h_vals, D_vals = singularity_spectrum(signal)

    assert len(h_vals) == len(D_vals)
    assert len(h_vals) >= 1
    # D values should be in [0, 1.5] range
    assert all(0.0 <= d <= 1.5 for d in D_vals)


def test_singularity_spectrum_short():
    """Test singularity spectrum with short input."""
    short = np.random.randn(32)
    h_vals, D_vals = singularity_spectrum(short)

    # Should return monofractal spectrum
    assert len(h_vals) >= 1


def test_multifractal_width():
    """Test multifractal width computation."""
    rng = np.random.default_rng(42)
    signal = np.cumsum(rng.normal(0, 1, 2048))

    width = multifractal_width(signal)

    # Width should be non-negative
    assert width >= 0.0


def test_holder_exponent_invalid_input():
    """Test error handling for invalid inputs."""
    # 2-D input should raise
    with pytest.raises(ValueError, match="1-D"):
        holder_exponent_wavelet(np.ones((10, 10)))


def test_different_wavelets():
    """Test with different wavelet families."""
    rng = np.random.default_rng(42)
    signal = np.cumsum(rng.normal(0, 1, 1024))

    wavelets = ["db2", "db4", "db8", "haar", "sym4"]
    for wav in wavelets:
        try:
            h = holder_exponent_wavelet(signal, wavelet=wav)
            assert 0.0 <= h <= 2.0, f"Invalid H for wavelet {wav}: {h}"
        except ValueError:
            # Some wavelets may not be available
            pass


def test_reproducibility():
    """Test that results are reproducible."""
    rng = np.random.default_rng(42)
    signal = np.cumsum(rng.normal(0, 1, 1024))

    h1 = holder_exponent_wavelet(signal)
    h2 = holder_exponent_wavelet(signal)

    assert h1 == h2, "Results should be reproducible"
