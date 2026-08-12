"""Spectral analysis of the κ_min cross-sectional signal.

Three measures:

    S1  Welch power spectral density (segment-averaged periodogram).
        Scipy-backed when available; explicit Hann+FFT fallback.

    S2  Dominant period. The frequency bin with peak power above the
        broadband trend is converted to period (= 1/f). For a noise-
        dominated signal this can be arbitrary; for a regime-cycling
        signal it identifies the dominant cycle.

    S3  Redness slope β. Log-log regression of log(P) on log(f):
            log P(f) ≈ α − β · log(f)
        β ≈ 0  → white noise      (memoryless, unpredictable)
        β ≈ 1  → pink / 1/f noise
        β ≈ 2  → red / Brownian    (random-walk-like)
        β > 0  is a necessary condition for persistence but not
        sufficient for predictability.

All pure. Deterministic. Scipy dependency for Welch; fallback pure-NumPy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

DEFAULT_SEGMENT_SEC: Final[int] = 600  # 10-min Welch segments on 1-sec grid
DEFAULT_PEAK_MIN_PERIOD_SEC: Final[float] = 30.0


@dataclass(frozen=True)
class SpectralReport:
    frequencies_hz: tuple[float, ...]
    psd: tuple[float, ...]
    dominant_period_sec: float | None
    dominant_peak_power: float | None
    redness_slope_beta: float
    redness_intercept: float
    regime_verdict: str  # "WHITE" | "PINK" | "RED" | "INCONCLUSIVE"


def _welch_psd(
    signal: NDArray[np.float64],
    *,
    fs_hz: float,
    segment_len: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Welch PSD via scipy.signal if present; pure-NumPy Hann+FFT fallback."""
    try:
        from scipy.signal import welch

        freq, psd = welch(
            signal,
            fs=fs_hz,
            nperseg=segment_len,
            noverlap=segment_len // 2,
            window="hann",
            detrend="constant",
            return_onesided=True,
            scaling="density",
        )
        return np.asarray(freq, dtype=np.float64), np.asarray(psd, dtype=np.float64)
    except Exception:
        # Fallback: non-overlapping Hann + FFT
        n = signal.size
        if segment_len > n:
            segment_len = n
        window = np.hanning(segment_len)
        n_segments = max(1, n // segment_len)
        psd_stack: list[NDArray[np.float64]] = []
        for i in range(n_segments):
            seg = signal[i * segment_len : (i + 1) * segment_len]
            if seg.size < segment_len:
                break
            seg = seg - float(np.mean(seg))
            seg = seg * window
            spec = np.fft.rfft(seg)
            psd_seg = (np.abs(spec) ** 2) / (fs_hz * float(np.sum(window**2)))
            # correct one-sided scaling
            if segment_len % 2 == 0:
                psd_seg[1:-1] *= 2.0
            else:
                psd_seg[1:] *= 2.0
            psd_stack.append(psd_seg.astype(np.float64))
        if not psd_stack:
            return np.array([], dtype=np.float64), np.array([], dtype=np.float64)
        avg = np.mean(np.stack(psd_stack, axis=0), axis=0)
        freqs = np.fft.rfftfreq(segment_len, d=1.0 / fs_hz)
        return freqs.astype(np.float64), avg


def spectral_report(
    signal: NDArray[np.float64],
    *,
    fs_hz: float = 1.0,
    segment_sec: int = DEFAULT_SEGMENT_SEC,
    peak_min_period_sec: float = DEFAULT_PEAK_MIN_PERIOD_SEC,
) -> SpectralReport:
    """Compute Welch PSD, identify dominant period, fit redness slope.

    Signal assumed sampled at `fs_hz` Hz (default 1 Hz on our 1-sec grid).
    Dominant peak requires period >= `peak_min_period_sec` (to avoid
    Nyquist edge picking up measurement noise).
    """
    x = np.asarray(signal, dtype=np.float64)
    x = x[np.isfinite(x)]
    if x.size < 256:
        return SpectralReport(
            frequencies_hz=(),
            psd=(),
            dominant_period_sec=None,
            dominant_peak_power=None,
            redness_slope_beta=float("nan"),
            redness_intercept=float("nan"),
            regime_verdict="INCONCLUSIVE",
        )
    segment_len = int(segment_sec * fs_hz)
    segment_len = min(segment_len, x.size)
    freq, psd = _welch_psd(x, fs_hz=fs_hz, segment_len=segment_len)

    # Drop DC bin (freq=0) for peak and log-log fit.
    mask = freq > 0.0
    if int(mask.sum()) < 10:
        return SpectralReport(
            frequencies_hz=tuple(float(f) for f in freq.tolist()),
            psd=tuple(float(p) for p in psd.tolist()),
            dominant_period_sec=None,
            dominant_peak_power=None,
            redness_slope_beta=float("nan"),
            redness_intercept=float("nan"),
            regime_verdict="INCONCLUSIVE",
        )

    f_pos = freq[mask]
    p_pos = psd[mask]

    # Dominant peak search: largest PSD bin meeting min-period constraint.
    max_freq_for_peak = 1.0 / max(peak_min_period_sec, 1e-12)
    peak_mask = f_pos <= max_freq_for_peak
    if int(peak_mask.sum()) == 0:
        dom_period: float | None = None
        dom_power: float | None = None
    else:
        sub_f = f_pos[peak_mask]
        sub_p = p_pos[peak_mask]
        idx = int(np.argmax(sub_p))
        dom_period = float(1.0 / sub_f[idx]) if sub_f[idx] > 0 else None
        dom_power = float(sub_p[idx])

    # Redness slope via OLS on log-log. Exclude bins with P=0.
    valid = (p_pos > 0) & (f_pos > 0)
    if int(valid.sum()) < 5:
        beta = float("nan")
        intercept = float("nan")
        verdict = "INCONCLUSIVE"
    else:
        log_f = np.log(f_pos[valid])
        log_p = np.log(p_pos[valid])
        slope, intercept_val = np.polyfit(log_f, log_p, 1)
        beta = float(-slope)  # slope is negative for 1/f^β noise
        intercept = float(intercept_val)
        if abs(beta) < 0.3:
            verdict = "WHITE"
        elif 0.3 <= beta < 1.3:
            verdict = "PINK"
        elif beta >= 1.3:
            verdict = "RED"
        else:
            verdict = "INCONCLUSIVE"

    return SpectralReport(
        frequencies_hz=tuple(float(f) for f in freq.tolist()),
        psd=tuple(float(p) for p in psd.tolist()),
        dominant_period_sec=dom_period,
        dominant_peak_power=dom_power,
        redness_slope_beta=beta,
        redness_intercept=intercept,
        regime_verdict=verdict,
    )
