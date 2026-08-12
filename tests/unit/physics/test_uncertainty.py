# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the Gabor time-frequency uncertainty limit (INV-GABOR1).

INV-GABOR1 (algebraic, ANCHORED — Gabor 1946 / Folland-Sitaram 1997):
    Δt · Δf ≥ 1/(4π) for every finite-energy sampled signal, with equality
    (saturation) for a Gaussian envelope. 1/(4π) is an exact mathematical
    constant — there is no Planck constant and no fabricated ℏ/2.

These tests replace the previous "Heisenberg ΔxΔp ≥ ℏ/2" suite, which
asserted properties of a classical std-product dressed as quantum mechanics
(category error: price and its first difference are jointly observable).
"""

import math

import numpy as np
import pytest

from core.physics.uncertainty import (
    GABOR_LIMIT,
    check_gabor_limit,
    gabor_lower_bound,
    time_frequency_spread,
)


class TestGaborConstant:
    """The bound is the exact mathematical constant 1/(4π), not a physical ℏ."""

    def test_bound_is_one_over_four_pi(self):
        """INV-GABOR1: the bound is exact 1/(4π), not a fabricated ℏ/2."""
        bound = gabor_lower_bound()
        expected = 1.0 / (4.0 * math.pi)
        # It must equal 1/(4π) AND must NOT be the old fabricated ℏ/2 = 0.5.
        assert abs(bound - expected) < 1e-15, (
            f"INV-GABOR1 VIOLATED: gabor_lower_bound()={bound:.18f} "
            f"!= 1/(4π)={expected:.18f}; the constant must be exact 1/(4π). "
            f"diff={abs(bound - expected):.3e} with expected=1/(4π), tol=1e-15"
        )
        assert abs(bound - 0.5) > 0.4, (
            f"INV-GABOR1 VIOLATED: bound={bound:.6f} coincides with the old "
            f"fabricated ℏ/2=0.5; the Gabor limit must NOT be a Planck-constant "
            f"artifact. expected bound ≈ 0.0796, observed={bound:.6f} with hbar=0"
        )
        assert bound == expected, (
            f"INV-GABOR1 VIOLATED: bound={bound!r} must equal 1/(4π)={expected!r} "
            f"exactly (strict identity). observed={bound!r} with constant=1/(4pi)"
        )

    def test_module_constant_matches_accessor(self):
        """INV-GABOR1: GABOR_LIMIT constant and accessor are one source of truth."""
        for label, value in (("GABOR_LIMIT", GABOR_LIMIT), ("accessor", gabor_lower_bound())):
            assert value == GABOR_LIMIT, (
                f"INV-GABOR1 VIOLATED: {label}={value!r} != GABOR_LIMIT={GABOR_LIMIT!r}; "
                f"constant and accessor must be a single source of truth. "
                f"observed={value!r}, expected GABOR_LIMIT with label={label}"
            )


def _gaussian_envelope(n: int, center: float, sigma: float) -> np.ndarray:
    """Gaussian window exp(-(idx-center)²/(2σ²)) of length n."""
    idx = np.arange(n, dtype=float)
    return np.exp(-((idx - center) ** 2) / (2.0 * sigma**2))


class TestGaborLimitUniversal:
    """INV-GABOR1: Δt·Δf ≥ 1/(4π) for well-resolved signals (universal sweep).

    Scope is the well-resolved regime (time-localized, band-limited away from
    Nyquist) where the discrete second-moment estimator faithfully realizes the
    continuous Gabor bound. See INV-GABOR1 scope note: the naive estimator can
    dip below 1/(4π) for under-resolved/near-Nyquist short noise, so the sweep
    deliberately does NOT include that regime — asserting a false universal
    floor would be dishonest.
    """

    def test_gaussian_windowed_band_limited_respect_bound(self):
        """INV-GABOR1: 200 well-resolved Gaussian-windowed signals satisfy Δt·Δf ≥ 1/(4π)."""
        rng = np.random.default_rng(42)
        bound = GABOR_LIMIT
        violations: list[tuple[int, float]] = []
        for trial in range(200):
            n = int(rng.integers(256, 1024))
            sigma = float(rng.uniform(n * 0.08, n * 0.25))
            center = float(rng.uniform(n * 0.4, n * 0.6))
            env = _gaussian_envelope(n, center, sigma)
            freq = float(rng.uniform(0.02, 0.15))
            phase = float(rng.uniform(0.0, 2.0 * math.pi))
            signal = env * (1.0 + 0.5 * np.sin(2.0 * math.pi * freq * np.arange(n) + phase))
            dt, df, product = time_frequency_spread(signal)
            assert dt >= 0.0 and df >= 0.0
            if product < bound * (1.0 - 1e-9):
                violations.append((trial, product))
        assert not violations, (
            f"INV-GABOR1 VIOLATED: {len(violations)} of 200 well-resolved signals "
            f"fell below the Gabor bound. "
            f"Required Δt·Δf ≥ 1/(4π)={bound:.6f} for well-resolved signals. "
            f"first_violation={violations[0] if violations else None}. "
            f"seed=42, n∈[256,1024], Gaussian-windowed band-limited"
        )

    def test_noisy_sinusoid_in_window_respects_bound(self):
        """INV-GABOR1: well-resolved noisy windowed sinusoids stay above 1/(4π)."""
        rng = np.random.default_rng(7)
        bound = GABOR_LIMIT
        for trial in range(50):
            n = int(rng.integers(256, 768))
            idx = np.arange(n, dtype=float)
            env = _gaussian_envelope(n, n / 2.0, n * 0.18)
            freq = float(rng.uniform(0.02, 0.12))
            phase = float(rng.uniform(0.0, 2.0 * math.pi))
            noise = 0.05 * rng.standard_normal(n)
            signal = env * (np.sin(2.0 * math.pi * freq * idx + phase) + noise)
            dt, df, product = time_frequency_spread(signal)
            ok, factor = check_gabor_limit(dt, df)
            assert ok and product >= bound * (1.0 - 1e-9), (
                f"INV-GABOR1 VIOLATED: windowed sinusoid trial {trial} gave "
                f"Δt·Δf={product:.6f} < 1/(4π)={bound:.6f}. "
                f"Well-resolved oscillatory signals must stay above the bound. "
                f"slack_factor={factor:.4f}. "
                f"freq={freq:.4f}, n={n}, seed=7"
            )

    def test_lowpass_smoothed_noise_respects_bound(self):
        """INV-GABOR1: band-limited (lowpass-smoothed) noise respects Δt·Δf ≥ 1/(4π)."""
        rng = np.random.default_rng(99)
        bound = GABOR_LIMIT
        kernel = np.exp(-((np.arange(-20, 21, dtype=float)) ** 2) / (2.0 * 6.0**2))
        kernel /= kernel.sum()
        for trial in range(50):
            n = int(rng.integers(256, 1024))
            raw = rng.standard_normal(n)
            signal = np.convolve(raw, kernel, mode="same")
            _, _, product = time_frequency_spread(signal)
            assert product >= bound * (1.0 - 1e-9), (
                f"INV-GABOR1 VIOLATED: lowpass-smoothed noise trial {trial} gave "
                f"Δt·Δf={product:.6f} < 1/(4π)={bound:.6f}. "
                f"Band-limited (well-resolved) noise must respect the bound. "
                f"product/bound={product / bound:.4f}. "
                f"n={n}, seed=99, Gaussian lowpass sigma=6"
            )


class TestGaussianSaturation:
    """INV-GABOR1 equality: a Gaussian envelope SATURATES Δt·Δf → 1/(4π)."""

    def test_gaussian_envelope_saturates_bound(self):
        """INV-GABOR1: a Gaussian envelope saturates the bound to ≈1/(4π)."""
        # Wide Gaussian, well inside the window so truncation is negligible.
        # Sweep the center so saturation is verified as translation-invariant.
        n = 4096
        sigma = 200.0
        idx = np.arange(n, dtype=float)
        bound = GABOR_LIMIT
        for center in (n / 2.0, n * 0.45, n * 0.55):
            gaussian = np.exp(-((idx - center) ** 2) / (2.0 * sigma**2))
            dt, df, product = time_frequency_spread(gaussian)
            np.testing.assert_allclose(
                product,
                bound,
                atol=2e-3,
                err_msg=(
                    f"INV-GABOR1 SATURATION VIOLATED: Gaussian envelope gave "
                    f"Δt·Δf={product:.8f}, expected ≈1/(4π)={bound:.8f}. "
                    f"A Gaussian is the unique minimizer that hits equality. "
                    f"Δt={dt:.4f}, Δf={df:.6f}. "
                    f"n={n}, sigma={sigma}, center={center}"
                ),
            )

    def test_narrower_gaussian_also_saturates(self):
        """INV-GABOR1: Gaussian saturation is scale-invariant in σ (Δt∝σ, Δf∝1/σ)."""
        # Saturation is scale-invariant: Δt scales as σ, Δf as 1/σ, product fixed.
        n = 8192
        bound = GABOR_LIMIT
        for sigma in (120.0, 250.0, 400.0):
            idx = np.arange(n, dtype=float)
            gaussian = np.exp(-((idx - n / 2.0) ** 2) / (2.0 * sigma**2))
            _, _, product = time_frequency_spread(gaussian)
            np.testing.assert_allclose(
                product,
                bound,
                atol=2e-3,
                err_msg=(
                    f"INV-GABOR1 SATURATION VIOLATED: Gaussian sigma={sigma} gave "
                    f"Δt·Δf={product:.8f}, expected ≈1/(4π)={bound:.8f}. "
                    f"Saturation must be scale-invariant in sigma. "
                    f"diff={abs(product - bound):.3e}. "
                    f"n={n}"
                ),
            )


class TestContractViolations:
    """INV-GABOR1 fail-closed: degenerate input → ValueError (no silent repair)."""

    def test_size_shape_finiteness_violations_raise(self):
        """INV-GABOR1 fail-closed: empty/single/non-finite/non-1-D input → ValueError."""
        bad_inputs: list[tuple[np.ndarray, str]] = [
            (np.array([]), "empty"),
            (np.array([3.14]), "single sample"),
            (np.array([1.0, 2.0, np.nan, 4.0]), "NaN"),
            (np.array([1.0, np.inf, 3.0]), "Inf"),
            (np.ones((4, 4)), "2-D"),
        ]
        for bad, label in bad_inputs:
            with pytest.raises(ValueError) as exc_info:
                time_frequency_spread(bad)
            assert "INV-GABOR1" in str(exc_info.value), (
                f"INV-GABOR1 VIOLATED: {label} input did not raise an "
                f"INV-GABOR1-tagged ValueError. "
                f"Fail-closed contract: degenerate input must raise, never repair. "
                f"got message='{exc_info.value}'. "
                f"with label={label}, shape={getattr(bad, 'shape', None)}"
            )

    def test_constant_signal_raises(self):
        """INV-GABOR1 fail-closed: constant (zero-variance) signal → ValueError."""
        for constant in (0.0, 5.0, -3.0, 1e6):
            with pytest.raises(ValueError) as exc_info:
                time_frequency_spread(np.full(64, constant))
            assert "constant" in str(exc_info.value), (
                f"INV-GABOR1 VIOLATED: constant signal value={constant} did not "
                f"raise the constant-input ValueError. "
                f"A flat signal has zero variance and must be rejected. "
                f"Fail-closed: refuse to report a spurious localization. "
                f"got message='{exc_info.value}' with value={constant}, N=64"
            )

    def test_under_resolved_window_below_bound_raises(self):
        """INV-GABOR1 fail-closed: a sub-bound (under-resolved) window → ValueError.

        The Gabor limit is a theorem; a discrete product below 1/(4π) can only
        mean an under-resolved / near-Nyquist window (power collapsed into one
        sample or bin), never a sub-bound discovery. Returning it would let a
        short-window caller misread a degenerate window as a maximally compact,
        maximally confident measurement — so it must fail-closed, not repair.
        """
        bound = gabor_lower_bound()
        # Non-constant 2-sample windows whose power collapses below the theorem.
        under_resolved: list[tuple[np.ndarray, str]] = [
            (np.array([0.0, 1.0]), "two-sample step (Δt→0)"),
            (np.array([1.0, 1.0001]), "near-constant ramp"),
            (np.array([1.0, 2.0]), "two-sample ramp (ratio 0.75)"),
        ]
        for sig, label in under_resolved:
            with pytest.raises(ValueError) as exc_info:
                time_frequency_spread(sig)
            msg = str(exc_info.value)
            assert "INV-GABOR1" in msg and "1/(4π)" in msg, (
                f"INV-GABOR1 VIOLATED: under-resolved window ({label}) did not "
                f"fail-closed with a sub-bound ValueError. "
                f"A discrete Δt·Δf below 1/(4π)={bound:.6f} is an under-resolution "
                f"artefact, never a measurement. "
                f"Fail-closed: refuse to report it. "
                f"got message='{msg}' for signal={sig.tolist()}"
            )

    def test_check_rejects_invalid_spreads(self):
        """INV-GABOR1 fail-closed: negative or non-finite spread → ValueError."""
        invalid_pairs: list[tuple[float, float, str]] = [
            (-1.0, 0.1, "≥ 0"),
            (0.1, -2.0, "≥ 0"),
            (float("inf"), 0.1, "finite"),
            (0.1, float("nan"), "finite"),
        ]
        for dt, df, expected in invalid_pairs:
            with pytest.raises(ValueError) as exc_info:
                check_gabor_limit(dt, df)
            assert expected in str(exc_info.value), (
                f"INV-GABOR1 VIOLATED: check_gabor_limit(Δt={dt}, Δf={df}) did not "
                f"raise the expected '{expected}' ValueError. "
                f"A second moment must not be negative or non-finite. "
                f"Fail-closed comparator: no silent acceptance. "
                f"got message='{exc_info.value}' with dt={dt}, df={df}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
