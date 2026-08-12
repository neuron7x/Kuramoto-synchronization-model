# SPDX-License-Identifier: MIT
"""The *standard* CTC analysis pipeline, emulated faithfully (and naively).

This is intentionally the pipeline CTC papers use: band-limit to gamma,
take the analytic phase, compute pairwise PLV and magnitude-squared
coherence, threshold at canonical values. The instrument's whole point is
to see whether THIS pipeline mislabels confounds as CTC-positive.

The readout is computed from the signals only — it never touches the
ground-truth ``channel_strength``; that independence is asserted in tests
and guarded by the INADMISSIBLE_CIRCULAR_PIPELINE gate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.signal import butter, coherence, hilbert, sosfiltfilt

from research.ctc_falsify import config as cfg
from research.ctc_falsify.generative import TwoPopSignals

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class CTCReadout:
    plv: float
    coherence: float
    ctc_positive: bool  # the pipeline's canonical-threshold verdict


def _bandpass(x: FloatArray) -> FloatArray:
    fs = 1.0 / cfg.DT
    lo = (cfg.F0 - cfg.GAMMA_BAND_HALFWIDTH) / (fs / 2.0)
    hi = (cfg.F0 + cfg.GAMMA_BAND_HALFWIDTH) / (fs / 2.0)
    sos = butter(4, [lo, hi], btype="band", output="sos")
    return np.asarray(sosfiltfilt(sos, x), dtype=np.float64)


def _plv(sig_a: FloatArray, sig_b: FloatArray) -> float:
    pa = np.angle(hilbert(_bandpass(sig_a)))
    pb = np.angle(hilbert(_bandpass(sig_b)))
    return float(np.abs(np.exp(1j * (pa - pb)).mean()))


def _gamma_coherence(sig_a: FloatArray, sig_b: FloatArray) -> float:
    fs = 1.0 / cfg.DT
    freqs, cxy = coherence(sig_a, sig_b, fs=fs, nperseg=512)
    band = (freqs >= cfg.F0 - cfg.GAMMA_BAND_HALFWIDTH) & (
        freqs <= cfg.F0 + cfg.GAMMA_BAND_HALFWIDTH
    )
    if not band.any():
        return 0.0
    return float(np.asarray(cxy, dtype=np.float64)[band].mean())


def run_standard_pipeline(sig: TwoPopSignals) -> CTCReadout:
    """Apply the canonical PLV+coherence CTC readout to a signal pair."""
    plv = _plv(sig.sig_a, sig.sig_b)
    coh = _gamma_coherence(sig.sig_a, sig.sig_b)
    positive = plv >= cfg.CANON_PLV and coh >= cfg.CANON_COH
    return CTCReadout(plv=plv, coherence=coh, ctc_positive=positive)
