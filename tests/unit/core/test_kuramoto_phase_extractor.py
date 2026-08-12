# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ``core.kuramoto.phase_extractor`` (protocol M1.2).

Acceptance criteria from KURAMOTO_NETWORK_ENGINE_METHODOLOGY.md:

- V1 synthetic sinusoid: extracted phase matches φ₀ + 2πft within ±0.01 rad.
- Quality gates Q1-Q3 produce sensible scores on clean and degraded inputs.
- PhaseExtractor returns a contract-compliant :class:`PhaseMatrix`.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.kuramoto.contracts import PhaseMatrix
from core.kuramoto.phase_extractor import (
    OptionalDependencyError,
    PhaseExtractionConfig,
    PhaseExtractor,
    cross_method_agreement,
    extract_phases_hilbert,
)

# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfig:
    def test_rejects_negative_fs(self) -> None:
        with pytest.raises(ValueError, match="fs"):
            PhaseExtractionConfig(fs=-1.0)

    def test_rejects_inverted_band(self) -> None:
        with pytest.raises(ValueError, match="f_low"):
            PhaseExtractionConfig(fs=1.0, f_low=0.3, f_high=0.1)

    def test_rejects_above_nyquist(self) -> None:
        with pytest.raises(ValueError, match="Nyquist"):
            PhaseExtractionConfig(fs=1.0, f_low=0.2, f_high=0.6)


# ---------------------------------------------------------------------------
# V1 — synthetic sinusoid recovery (primary acceptance test)
# ---------------------------------------------------------------------------


class TestSyntheticRecovery:
    def _build_signal(
        self,
        T: int = 4000,
        fs: float = 10.0,
        f: float = 1.0,
        phi0: float = 0.7,
        noise: float = 0.0,
        seed: int = 0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Generate a clean sinusoid plus optional Gaussian noise."""
        rng = np.random.default_rng(seed)
        t = np.arange(T) / fs
        true_phase = np.mod(phi0 + 2 * np.pi * f * t, 2 * np.pi)
        x = np.sin(phi0 + 2 * np.pi * f * t)
        if noise > 0:
            x = x + noise * rng.standard_normal(T)
        return x[:, None], true_phase

    @staticmethod
    def _circular_mae(a: np.ndarray, b: np.ndarray) -> float:
        """Mean absolute circular difference in radians."""
        d = np.angle(np.exp(1j * (a - b)))
        return float(np.mean(np.abs(d)))

    @staticmethod
    def _aligned_circular_residual(extracted: np.ndarray, true_phase: np.ndarray) -> np.ndarray:
        """Circular residual after removing the global constant offset.

        Hilbert(sin(φ)) introduces a fixed −π/2 shift, and different
        extraction backends use different reference conventions. We
        measure recovery *up to a constant offset* by subtracting the
        circular mean of the phase difference.
        """
        diff = np.angle(np.exp(1j * (extracted - true_phase)))
        mean_offset = np.angle(np.mean(np.exp(1j * diff)))
        return np.angle(np.exp(1j * (diff - mean_offset)))

    def test_clean_sinusoid_recovery(self) -> None:
        T, fs, f = 4000, 10.0, 1.0
        phi0 = 0.7
        signal, true_phase = self._build_signal(T=T, fs=fs, f=f, phi0=phi0)

        cfg = PhaseExtractionConfig(
            fs=fs,
            f_low=0.5,
            f_high=1.5,
            detrend_window=None,
        )
        theta, amplitude = extract_phases_hilbert(signal, cfg)

        assert theta.shape == (T, 1)
        assert theta.dtype == np.float64
        assert float(theta.min()) >= 0.0
        assert float(theta.max()) < 2 * np.pi
        assert np.all(amplitude > 0)

        # Ignore filter transients (first / last 10%)
        edge = T // 10
        residual = self._aligned_circular_residual(theta[edge:-edge, 0], true_phase[edge:-edge])
        mse = float(np.mean(residual**2))
        assert mse < 0.01, f"phase recovery MSE {mse:.6f} exceeds 0.01 rad²"
        mae = float(np.mean(np.abs(residual)))
        assert mae < 0.1

    def test_noisy_sinusoid_recovery(self) -> None:
        T, fs, f = 4000, 10.0, 1.0
        signal, true_phase = self._build_signal(T=T, fs=fs, f=f, phi0=0.3, noise=0.15, seed=1)
        cfg = PhaseExtractionConfig(fs=fs, f_low=0.5, f_high=1.5, detrend_window=None)
        theta, _ = extract_phases_hilbert(signal, cfg)
        edge = T // 10
        residual = self._aligned_circular_residual(theta[edge:-edge, 0], true_phase[edge:-edge])
        mae = float(np.mean(np.abs(residual)))
        assert mae < 0.2, f"noisy recovery MAE {mae:.4f} too large"

    def test_instantaneous_frequency_matches_ground_truth(self) -> None:
        T, fs, f = 4000, 10.0, 1.0
        signal, _ = self._build_signal(T=T, fs=fs, f=f)
        cfg = PhaseExtractionConfig(fs=fs, f_low=0.5, f_high=1.5, detrend_window=None)
        theta, _ = extract_phases_hilbert(signal, cfg)
        unwrapped = np.unwrap(theta[:, 0])
        inst_freq = np.gradient(unwrapped) * fs / (2 * np.pi)
        edge = T // 10
        mean_freq = float(np.mean(inst_freq[edge:-edge]))
        assert abs(mean_freq - f) < 0.02


# ---------------------------------------------------------------------------
# PhaseExtractor high-level API
# ---------------------------------------------------------------------------


class TestPhaseExtractorAPI:
    @pytest.fixture()
    def signal_3assets(self) -> tuple[np.ndarray, np.ndarray]:
        rng = np.random.default_rng(7)
        T, fs = 2000, 10.0
        t = np.arange(T) / fs
        phases0 = np.array([0.0, 0.5, 1.2])
        x = np.stack(
            [
                np.sin(2 * np.pi * 1.0 * t + phases0[0]) + 0.05 * rng.standard_normal(T),
                np.sin(2 * np.pi * 1.0 * t + phases0[1]) + 0.05 * rng.standard_normal(T),
                np.sin(2 * np.pi * 1.0 * t + phases0[2]) + 0.05 * rng.standard_normal(T),
            ],
            axis=1,
        )
        return x, t

    def test_extract_returns_valid_phase_matrix(
        self, signal_3assets: tuple[np.ndarray, np.ndarray]
    ) -> None:
        x, t = signal_3assets
        extractor = PhaseExtractor(
            PhaseExtractionConfig(fs=10.0, f_low=0.5, f_high=1.5, detrend_window=None)
        )
        pm = extractor.extract(
            signal=x,
            asset_ids=("A", "B", "C"),
            timestamps=t,
            method="hilbert",
        )
        assert isinstance(pm, PhaseMatrix)
        assert pm.theta.shape == (x.shape[0], 3)
        assert pm.extraction_method == "hilbert"
        assert pm.frequency_band == (0.5, 1.5)
        assert pm.quality_scores is not None
        # Q3 should be zero on finite input
        assert pm.quality_scores["Q3_nan_fraction_max"] == 0.0
        # Returned theta must be immutable
        assert pm.theta.flags.writeable is False

    def test_rejects_unknown_method(self, signal_3assets: tuple[np.ndarray, np.ndarray]) -> None:
        x, t = signal_3assets
        extractor = PhaseExtractor(
            PhaseExtractionConfig(fs=10.0, f_low=0.5, f_high=1.5, detrend_window=None)
        )
        with pytest.raises(ValueError, match="Unknown method"):
            extractor.extract(x, ("A", "B", "C"), t, method="magic")

    def test_ceemdan_raises_without_pyemd(
        self, signal_3assets: tuple[np.ndarray, np.ndarray]
    ) -> None:
        pytest.importorskip
        try:
            import PyEMD  # noqa: F401
        except ImportError:
            pass
        else:
            pytest.skip("PyEMD installed; this test only runs without it")
        x, t = signal_3assets
        extractor = PhaseExtractor(
            PhaseExtractionConfig(fs=10.0, f_low=0.5, f_high=1.5, detrend_window=None)
        )
        with pytest.raises(OptionalDependencyError):
            extractor.extract(x, ("A", "B", "C"), t, method="ceemdan")

    def test_extract_with_validation_survives_missing_validator(
        self, signal_3assets: tuple[np.ndarray, np.ndarray]
    ) -> None:
        """If CEEMDAN is unavailable, extract_with_validation must still
        return the primary result and flag Q4 as unavailable rather than
        raising — the pipeline cannot hard-fail on an optional backend."""
        try:
            import PyEMD  # noqa: F401

            has_pyemd = True
        except ImportError:
            has_pyemd = False
        x, t = signal_3assets
        extractor = PhaseExtractor(
            PhaseExtractionConfig(fs=10.0, f_low=0.5, f_high=1.5, detrend_window=None)
        )
        pm, q4 = extractor.extract_with_validation(
            signal=x,
            asset_ids=("A", "B", "C"),
            timestamps=t,
            primary="hilbert",
            validator="ceemdan",
        )
        assert isinstance(pm, PhaseMatrix)
        if has_pyemd:
            assert "Q4_mean_abs_diff" in q4
        else:
            assert q4 == {"Q4_unavailable": 1.0}


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------


class TestQualityGates:
    def test_q1_flags_low_amplitude_asset(self) -> None:
        """A signal with a large quiet gap should trip the Q1 gate.

        Construction: ~70% of samples carry a unit-amplitude sinusoid,
        the middle ~30% carry a near-silent version (1e-4). The median
        amplitude is dominated by the high-amplitude majority, so the
        quiet window falls below ``0.1 * median`` and should push
        ``Q1_low_amp_fraction_max`` above the default 0.2 threshold.
        """
        T, fs = 2000, 10.0
        t = np.arange(T) / fs
        envelope = np.ones(T)
        envelope[int(0.35 * T) : int(0.65 * T)] = 1e-4  # 30% quiet window
        x = (envelope * np.sin(2 * np.pi * 1.0 * t))[:, None]
        cfg = PhaseExtractionConfig(fs=fs, f_low=0.5, f_high=1.5, detrend_window=None)
        extractor = PhaseExtractor(cfg)
        pm = extractor.extract(x, ("A",), t, method="hilbert")
        assert pm.quality_scores is not None
        assert pm.quality_scores["Q1_low_amp_fraction_max"] > 0.2

    def test_q3_all_zero_nan_on_finite_input(self) -> None:
        T, fs = 2000, 10.0
        t = np.arange(T) / fs
        x = np.sin(2 * np.pi * 1.0 * t)[:, None]
        cfg = PhaseExtractionConfig(fs=fs, f_low=0.5, f_high=1.5, detrend_window=None)
        pm = PhaseExtractor(cfg).extract(x, ("A",), t, method="hilbert")
        assert pm.quality_scores is not None
        assert pm.quality_scores["Q3_nan_fraction_max"] == 0.0


# ---------------------------------------------------------------------------
# Cross-method agreement helper
# ---------------------------------------------------------------------------


class TestCrossMethodAgreement:
    def test_identical_inputs_give_zero_diff(self) -> None:
        theta = np.mod(np.linspace(0, 10 * np.pi, 200), 2 * np.pi).reshape(-1, 1)
        q4 = cross_method_agreement(theta, theta)
        assert q4["Q4_mean_abs_diff"] == pytest.approx(0.0, abs=1e-12)
        assert q4["Q4_frac_gt_pi_over_4"] == 0.0

    def test_pi_offset_gives_pi_diff(self) -> None:
        theta_a = np.zeros((100, 1))
        theta_b = np.full((100, 1), np.pi)
        q4 = cross_method_agreement(theta_a, theta_b)
        assert q4["Q4_mean_abs_diff"] == pytest.approx(np.pi, abs=1e-9)
        assert q4["Q4_frac_gt_pi_over_4"] == 1.0

    def test_shape_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="shape mismatch"):
            cross_method_agreement(np.zeros((10, 2)), np.zeros((10, 3)))


class TestNanGapTolerance:
    """The advertised ``max_nan_fraction`` tolerance must be real: a few missing
    samples must not smear across the whole column under filtfilt/Hilbert.

    Reproduces a latent defect — a single NaN previously poisoned the entire
    column (100% loss) because the Q3 gate ran AFTER filtering. Short gaps
    (≤ tolerance) are now interpolated before filtering; larger gaps stay NaN
    for Q3 to flag; clean input is bit-identical.
    """

    @staticmethod
    def _band_signal(n_rows: int = 400, n_cols: int = 2) -> np.ndarray:
        rng = np.random.default_rng(0)
        t = np.arange(n_rows)
        base = np.sin(2.0 * np.pi * 0.05 * t)[:, None] * np.ones((1, n_cols))
        return base + 0.01 * rng.standard_normal((n_rows, n_cols))

    def test_clean_input_is_bit_identical(self) -> None:
        cfg = PhaseExtractionConfig()
        signal = self._band_signal()
        theta_a, _ = extract_phases_hilbert(signal, cfg)
        theta_b, _ = extract_phases_hilbert(signal.copy(), cfg)
        assert np.array_equal(theta_a, theta_b)
        assert np.all(np.isfinite(theta_a))

    def test_small_gap_within_tolerance_is_repaired(self) -> None:
        """≤ max_nan_fraction NaNs → finite phase (was all-NaN before)."""
        cfg = PhaseExtractionConfig()  # default max_nan_fraction = 0.05
        signal = self._band_signal()
        signal[50:60, 0] = np.nan  # 10/400 = 2.5% ≤ 5%
        theta, _ = extract_phases_hilbert(signal, cfg)
        assert np.all(np.isfinite(theta[:, 0]))
        assert np.all(np.isfinite(theta[:, 1]))

    def test_large_gap_left_for_q3_and_neighbours_unaffected(self) -> None:
        """> max_nan_fraction NaNs → that column stays NaN (Q3 flags it) while a
        clean neighbour column is unaffected — no silent whole-matrix repair."""
        cfg = PhaseExtractionConfig()
        signal = self._band_signal()
        signal[50:130, 0] = np.nan  # 80/400 = 20% > 5%
        theta, _ = extract_phases_hilbert(signal, cfg)
        assert np.all(np.isnan(theta[:, 0]))
        assert np.all(np.isfinite(theta[:, 1]))
