# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Instantaneous-phase extraction for the NetworkKuramotoEngine (protocol M1.2).

This module turns a matrix of financial log-returns (or any band-limited
signal) into a canonical :class:`~core.kuramoto.contracts.PhaseMatrix`
suitable for the downstream sparse-regression identification step.

The methodology specifies three pipelines in order of increasing cost and
time-frequency resolution:

1. **Bandpass + Hilbert** — primary method, depends only on ``scipy``.
   Butterworth zero-phase filter followed by the analytic signal.
2. **CEEMDAN + Hilbert** — validation method, requires optional ``PyEMD``.
   Used to cross-check Hilbert in non-stationary regimes.
3. **Synchrosqueezed CWT** — gold-standard time-frequency reassignment,
   requires optional ``ssqueezepy``.

Only method (1) is hard-required. (2) and (3) raise a clear
``OptionalDependencyError`` when invoked without the backing package,
so the primary Hilbert path always works on a bare scipy install.

Quality gates (Q1-Q4 from the methodology) are applied after extraction
and returned as diagnostics on ``PhaseMatrix.quality_scores``. Q4 is only
computable when two methods have been run on the same input.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Final

import numpy as np
from scipy.signal import butter, filtfilt, hilbert

from .contracts import PhaseMatrix

__all__ = [
    "PhaseExtractionConfig",
    "PhaseExtractor",
    "OptionalDependencyError",
    "extract_phases_hilbert",
    "cross_method_agreement",
]

logger = logging.getLogger(__name__)

_TWO_PI: Final[float] = 2.0 * np.pi


class OptionalDependencyError(ImportError):
    """Raised when a phase-extraction backend needs a missing optional package."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PhaseExtractionConfig:
    """Hyperparameters for phase extraction.

    Attributes
    ----------
    fs : float
        Sampling frequency in samples per unit time (``1.0`` for daily
        bars, ``390.0`` for minute bars on a 6.5h trading day, etc.).
    f_low, f_high : float
        Passband edges in the **same units as ``fs``** (i.e. cycles per
        unit time). The defaults ``(0.05, 0.2)`` cycles/day isolate a
        5–20-day oscillation band for daily data.
    filter_order : int
        Butterworth filter order. Order 4 with zero-phase ``filtfilt``
        gives an effective order of 8 and a steep rolloff without phase
        distortion.
    detrend_window : int | None
        Rolling-mean window for detrending. ``None`` disables detrending
        (useful for unit-tests on perfectly stationary synthetic signals).
        Default ``250`` matches the approximate number of trading days
        per year for daily data.
    min_amplitude_ratio : float
        Q1 gate: the fraction ``A_i(t) / median(A_i)`` below which a
        sample is flagged as unreliable (phase is undefined for
        near-zero amplitude).
    max_lowamp_fraction : float
        Q1 gate: maximum tolerated fraction of low-amplitude samples
        per asset before the asset is flagged.
    max_nan_fraction : float
        Q3 gate: maximum tolerated NaN fraction per asset.
    """

    fs: float = 1.0
    f_low: float = 0.05
    f_high: float = 0.2
    filter_order: int = 4
    detrend_window: int | None = 250
    min_amplitude_ratio: float = 0.1
    max_lowamp_fraction: float = 0.2
    max_nan_fraction: float = 0.05

    def __post_init__(self) -> None:
        if self.fs <= 0:
            raise ValueError(f"fs must be > 0; got {self.fs}")
        if not 0 <= self.f_low < self.f_high:
            raise ValueError(f"need 0 ≤ f_low < f_high; got ({self.f_low}, {self.f_high})")
        if self.f_high >= 0.5 * self.fs:
            raise ValueError(f"f_high={self.f_high} must be < Nyquist=fs/2={0.5 * self.fs}")
        if self.filter_order < 1:
            raise ValueError("filter_order must be ≥ 1")


# ---------------------------------------------------------------------------
# Low-level primitives
# ---------------------------------------------------------------------------


def _rolling_mean(x: np.ndarray, window: int) -> np.ndarray:
    """NaN-safe centred rolling mean via cumulative sum.

    The signal is reflected at the boundaries so that the output has the
    same length as the input and the edges are not biased toward zero.
    """
    if window <= 1:
        return np.zeros_like(x)
    pad = window // 2
    xp = np.pad(x, pad, mode="reflect")
    cs = np.cumsum(np.insert(xp, 0, 0.0))
    out = (cs[window:] - cs[:-window]) / float(window)
    # Trim to original length (cumsum output length = len(xp) - window + 1)
    # Align centre: take the middle len(x) samples
    start = (len(out) - len(x)) // 2
    return np.asarray(out[start : start + len(x)], dtype=np.float64)


def _bandpass(x: np.ndarray, cfg: PhaseExtractionConfig) -> np.ndarray:
    """Zero-phase Butterworth bandpass filter."""
    nyq = 0.5 * cfg.fs
    low = cfg.f_low / nyq
    high = cfg.f_high / nyq
    b, a = butter(cfg.filter_order, [low, high], btype="bandpass")
    # filtfilt requires ``len(x) > padlen`` (default padlen = 3*max(len(a),len(b)))
    padlen = 3 * max(len(a), len(b))
    if x.shape[0] <= padlen:
        raise ValueError(
            f"signal length {x.shape[0]} too short for filter order "
            f"{cfg.filter_order} (need > {padlen})"
        )
    return np.asarray(filtfilt(b, a, x, axis=0), dtype=np.float64)


def _detrend(x: np.ndarray, window: int | None) -> np.ndarray:
    if window is None or window <= 1:
        return np.asarray(x - np.mean(x, axis=0, keepdims=True), dtype=np.float64)
    # Column-wise rolling-mean detrend
    out = np.empty_like(x)
    for i in range(x.shape[1]):
        out[:, i] = x[:, i] - _rolling_mean(x[:, i], window)
    return out


def _wrap_phase(theta: np.ndarray) -> np.ndarray:
    """Wrap phase to [0, 2π)."""
    return np.asarray(np.mod(theta, _TWO_PI), dtype=np.float64)


def _fill_short_nan_gaps(x: np.ndarray, max_nan_fraction: float) -> np.ndarray:
    """Linearly interpolate per-column non-finite gaps within tolerance.

    Zero-phase ``filtfilt`` and the Hilbert transform smear a single NaN across
    the entire column, so the advertised ``max_nan_fraction`` tolerance is
    unenforceable unless the gaps are filled *before* filtering. For each column
    whose non-finite fraction is in ``(0, max_nan_fraction]`` we linearly
    interpolate the missing samples (a logged short-gap repair). Columns with no
    gaps are returned untouched (bit-identical), and columns whose non-finite
    fraction *exceeds* the tolerance are left as-is so they surface NaN output
    and are flagged by the Q3 quality diagnostic rather than silently repaired.
    """
    if bool(np.all(np.isfinite(x))):
        return x  # clean input — bit-identical, the common path
    out = x.copy()
    n_rows = x.shape[0]
    rows = np.arange(n_rows, dtype=np.float64)
    for col in range(x.shape[1]):
        finite = np.isfinite(out[:, col])
        n_finite = int(finite.sum())
        nan_fraction = 1.0 - n_finite / n_rows
        # bounds: only short gaps (≤ max_nan_fraction, ≥2 anchors) are repaired;
        # larger gaps stay NaN for the Q3 diagnostic to flag (no silent repair).
        if nan_fraction == 0.0 or nan_fraction > max_nan_fraction or n_finite < 2:
            continue
        out[:, col] = np.interp(rows, rows[finite], out[finite, col])
    return out


# ---------------------------------------------------------------------------
# Primary method — Bandpass + Hilbert
# ---------------------------------------------------------------------------


def extract_phases_hilbert(
    signal: np.ndarray,
    cfg: PhaseExtractionConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Bandpass + Hilbert phase extraction.

    Parameters
    ----------
    signal
        Input matrix of shape ``(T, N)``: log-returns, detrended
        log-prices, or any real-valued band-limited series.
    cfg
        Extraction configuration.

    Returns
    -------
    theta : np.ndarray
        Wrapped instantaneous phase, shape ``(T, N)``, dtype ``float64``,
        range ``[0, 2π)``.
    amplitude : np.ndarray
        Envelope ``|z_i(t)|``, shape ``(T, N)``, dtype ``float64``.
    """
    if signal.ndim != 2:
        raise ValueError(f"signal must be 2-D (T,N); got {signal.ndim}-D")
    x = np.asarray(signal, dtype=np.float64)
    # Repair short non-finite gaps BEFORE filtering so a few missing samples do
    # not smear across the whole column under filtfilt/Hilbert (delivers the
    # advertised max_nan_fraction tolerance; clean input is unchanged).
    x = _fill_short_nan_gaps(x, cfg.max_nan_fraction)
    x = _detrend(x, cfg.detrend_window)
    x = _bandpass(x, cfg)
    z = hilbert(x, axis=0)
    theta = _wrap_phase(np.angle(z).astype(np.float64))
    amplitude = np.abs(z).astype(np.float64)
    return theta, amplitude


# ---------------------------------------------------------------------------
# Optional: CEEMDAN + Hilbert
# ---------------------------------------------------------------------------


def extract_phases_ceemdan(
    signal: np.ndarray,
    cfg: PhaseExtractionConfig,
    trials: int = 100,
    epsilon: float = 0.1,
) -> tuple[np.ndarray, np.ndarray]:
    """CEEMDAN decomposition + Hilbert on band-matched IMFs.

    Raises :class:`OptionalDependencyError` if ``PyEMD`` is not installed.
    """
    try:
        from PyEMD import CEEMDAN  # type: ignore[import-not-found,unused-ignore]
    except ImportError as exc:  # pragma: no cover - exercised only without PyEMD
        raise OptionalDependencyError(
            "CEEMDAN requires the optional 'EMD-signal' package (pip install EMD-signal)"
        ) from exc

    if signal.ndim != 2:
        raise ValueError(f"signal must be 2-D (T,N); got {signal.ndim}-D")
    x = np.asarray(signal, dtype=np.float64)
    T, N = x.shape
    theta = np.empty_like(x)
    amplitude = np.empty_like(x)
    f_centre = 0.5 * (cfg.f_low + cfg.f_high)

    for i in range(N):
        ceemdan = CEEMDAN(trials=trials, epsilon=epsilon)
        imfs = ceemdan(x[:, i])  # shape (K, T)
        # Select IMFs whose dominant frequency falls inside the band
        selected = []
        for imf in imfs:
            z_imf = hilbert(imf)
            inst_phase = np.unwrap(np.angle(z_imf))
            inst_freq = np.gradient(inst_phase) * cfg.fs / _TWO_PI
            median_freq = float(np.median(inst_freq))
            if cfg.f_low <= median_freq <= cfg.f_high:
                selected.append(imf)
        if not selected:
            # Fallback: keep IMF closest to band centre by median freq
            freqs = [
                float(np.median(np.gradient(np.unwrap(np.angle(hilbert(imf)))) * cfg.fs / _TWO_PI))
                for imf in imfs
            ]
            idx = int(np.argmin(np.abs(np.asarray(freqs) - f_centre)))
            selected = [imfs[idx]]
        x_band = np.sum(selected, axis=0)
        z = hilbert(x_band)
        theta[:, i] = _wrap_phase(np.angle(z))
        amplitude[:, i] = np.abs(z)

    return theta, amplitude


# ---------------------------------------------------------------------------
# Optional: Synchrosqueezed CWT
# ---------------------------------------------------------------------------


def extract_phases_ssq_cwt(
    signal: np.ndarray,
    cfg: PhaseExtractionConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Synchrosqueezed CWT + ridge extraction (gold-standard).

    Raises :class:`OptionalDependencyError` if ``ssqueezepy`` is not installed.
    """
    try:
        from ssqueezepy import ssq_cwt  # type: ignore[import-not-found,unused-ignore]
        from ssqueezepy.ridge_extraction import (  # type: ignore[import-not-found,unused-ignore]
            extract_ridges,
        )
    except ImportError as exc:  # pragma: no cover
        raise OptionalDependencyError(
            "SSQ-CWT requires the optional 'ssqueezepy' package (pip install ssqueezepy)"
        ) from exc

    if signal.ndim != 2:
        raise ValueError(f"signal must be 2-D (T,N); got {signal.ndim}-D")
    x = np.asarray(signal, dtype=np.float64)
    T, N = x.shape
    theta = np.empty_like(x)
    amplitude = np.empty_like(x)

    for i in range(N):
        Tx, _Wx, ssq_freqs, *_ = ssq_cwt(x[:, i], fs=cfg.fs)
        # Restrict to the target band
        band_mask = (ssq_freqs >= cfg.f_low) & (ssq_freqs <= cfg.f_high)
        if not np.any(band_mask):
            raise ValueError(
                f"No SSQ frequencies in band ({cfg.f_low}, {cfg.f_high}) for asset {i}"
            )
        Tx_band = Tx[band_mask]
        ridge = extract_ridges(np.abs(Tx_band), penalty=2.0, n_ridges=1)
        ridge_idx = np.asarray(ridge).reshape(-1)
        reconstructed = Tx_band[ridge_idx, np.arange(T)]
        theta[:, i] = _wrap_phase(np.angle(reconstructed))
        amplitude[:, i] = np.abs(reconstructed)

    return theta, amplitude


# ---------------------------------------------------------------------------
# Quality gates
# ---------------------------------------------------------------------------


def _quality_gates(
    theta: np.ndarray,
    amplitude: np.ndarray,
    cfg: PhaseExtractionConfig,
) -> dict[str, float]:
    """Compute Q1-Q3 quality diagnostics.

    Q1 — low-amplitude fraction per asset (phase undefined where
         ``A_i(t) < min_amplitude_ratio · median(A_i)``).
    Q2 — frequency stability: fraction of samples with instantaneous
         frequency outside ``3σ`` of the band centre.
    Q3 — NaN coverage per asset.
    """
    T, N = theta.shape
    scores: dict[str, float] = {}

    # Q3: NaN fraction (compute first so Q1/Q2 can short-circuit)
    nan_frac = np.mean(np.isnan(theta), axis=0)
    scores["Q3_nan_fraction_max"] = float(np.max(nan_frac))
    scores["Q3_assets_failed"] = float(np.sum(nan_frac > cfg.max_nan_fraction))

    # Q1: low-amplitude fraction
    med_amp = np.median(amplitude, axis=0)
    med_amp = np.where(med_amp > 0, med_amp, 1.0)  # guard div-by-zero
    low_amp = amplitude < (cfg.min_amplitude_ratio * med_amp[np.newaxis, :])
    low_amp_frac = np.mean(low_amp, axis=0)
    scores["Q1_low_amp_fraction_max"] = float(np.max(low_amp_frac))
    scores["Q1_assets_failed"] = float(np.sum(low_amp_frac > cfg.max_lowamp_fraction))

    # Q2: frequency stability (on unwrapped phase)
    theta_unwrapped = np.unwrap(theta, axis=0)
    inst_freq = np.gradient(theta_unwrapped, axis=0) * cfg.fs / _TWO_PI
    f_centre = 0.5 * (cfg.f_low + cfg.f_high)
    f_std = np.std(inst_freq, axis=0)
    out_of_band = np.mean(np.abs(inst_freq - f_centre) > 3.0 * np.maximum(f_std, 1e-12), axis=0)
    scores["Q2_out_of_band_fraction_max"] = float(np.max(out_of_band))

    return scores


def cross_method_agreement(
    theta_a: np.ndarray,
    theta_b: np.ndarray,
) -> dict[str, float]:
    """Q4: agreement between two extraction methods.

    Returns both the circular mean absolute error of ``Δθ`` per asset
    and the fraction of samples with ``|Δθ| > π/4`` — the methodology
    requires the latter to be below 20%.
    """
    if theta_a.shape != theta_b.shape:
        raise ValueError(f"shape mismatch: {theta_a.shape} vs {theta_b.shape}")
    # Circular difference in [-π, π]
    diff = np.angle(np.exp(1j * (theta_a - theta_b)))
    abs_diff = np.abs(diff)
    return {
        "Q4_mean_abs_diff": float(np.mean(abs_diff)),
        "Q4_frac_gt_pi_over_4": float(np.mean(abs_diff > np.pi / 4)),
    }


# ---------------------------------------------------------------------------
# High-level extractor
# ---------------------------------------------------------------------------


class PhaseExtractor:
    """High-level interface exposing the three extraction pipelines.

    Example
    -------
    >>> cfg = PhaseExtractionConfig(fs=1.0, f_low=0.05, f_high=0.2)
    >>> extractor = PhaseExtractor(cfg)
    >>> pm = extractor.extract(
    ...     signal=log_returns,
    ...     asset_ids=("AAPL", "MSFT", "GOOG"),
    ...     timestamps=ts,
    ...     method="hilbert",
    ... )
    >>> pm.theta.shape
    (T, 3)
    """

    def __init__(self, config: PhaseExtractionConfig | None = None) -> None:
        self.config = config or PhaseExtractionConfig()

    def extract(
        self,
        signal: np.ndarray,
        asset_ids: tuple[str, ...],
        timestamps: np.ndarray,
        method: str = "hilbert",
    ) -> PhaseMatrix:
        """Run one of the three extraction pipelines and return a
        validated :class:`PhaseMatrix`.

        Parameters
        ----------
        signal
            ``(T, N)`` matrix of real-valued band-limited observations.
        asset_ids
            Column labels, length ``N``, unique.
        timestamps
            Monotonic time vector of length ``T``.
        method
            One of ``{"hilbert", "ceemdan", "ssq_cwt"}``.
        """
        if method == "hilbert":
            theta, amplitude = extract_phases_hilbert(signal, self.config)
        elif method == "ceemdan":
            theta, amplitude = extract_phases_ceemdan(signal, self.config)
        elif method == "ssq_cwt":
            theta, amplitude = extract_phases_ssq_cwt(signal, self.config)
        else:
            raise ValueError(f"Unknown method '{method}'; expected hilbert|ceemdan|ssq_cwt")

        quality = _quality_gates(theta, amplitude, self.config)

        if quality["Q1_assets_failed"] > 0:
            logger.warning(
                "Phase extraction Q1 gate: %d asset(s) exceeded low-amplitude fraction %.2f",
                int(quality["Q1_assets_failed"]),
                self.config.max_lowamp_fraction,
            )
        if quality["Q3_assets_failed"] > 0:
            logger.warning(
                "Phase extraction Q3 gate: %d asset(s) exceeded NaN fraction %.2f",
                int(quality["Q3_assets_failed"]),
                self.config.max_nan_fraction,
            )

        return PhaseMatrix(
            theta=theta,
            timestamps=np.asarray(timestamps),
            asset_ids=tuple(asset_ids),
            extraction_method=method,
            frequency_band=(self.config.f_low, self.config.f_high),
            amplitude=amplitude,
            quality_scores=quality,
        )

    def extract_with_validation(
        self,
        signal: np.ndarray,
        asset_ids: tuple[str, ...],
        timestamps: np.ndarray,
        primary: str = "hilbert",
        validator: str = "ceemdan",
    ) -> tuple[PhaseMatrix, dict[str, float]]:
        """Extract via ``primary`` and cross-validate with ``validator``.

        Returns the primary :class:`PhaseMatrix` and a dict of Q4
        agreement metrics. If the validator backend is missing, Q4
        returns ``{"Q4_unavailable": 1.0}`` and a warning is logged
        instead of raising — the primary result is still returned.
        """
        primary_pm = self.extract(signal, asset_ids, timestamps, method=primary)
        try:
            validator_pm = self.extract(signal, asset_ids, timestamps, method=validator)
        except OptionalDependencyError as exc:
            logger.warning("Q4 cross-validation skipped: %s", exc)
            return primary_pm, {"Q4_unavailable": 1.0}
        q4 = cross_method_agreement(primary_pm.theta, validator_pm.theta)
        return primary_pm, q4
