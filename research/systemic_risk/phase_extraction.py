# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Interbank-rate phase extraction: spread vs benchmark → θᵢ(t).

The phase variable for the interbank-Kuramoto experiment is the
unwrapped instantaneous phase of the *spread* between an institution's
interbank lending rate and a risk-free benchmark (OIS, GC repo, or
T-bill at matched tenor):

    s_i(t) = r_i(t) − r_benchmark(t)
    θ_i(t) = unwrap( angle( hilbert( bandpass(s_i)) ) )

This is the *primary* phase variable. CDS-implied default-intensity
phase and equity-return phase are both supported as **sensitivity
checks only** by accepting an arbitrary signal matrix.

Defaults are chosen for daily interbank data (5–90 day band on the
liquidity-stress band documented in Brunetti et al. 2019, *J. Banking
Finance* 100: 175). The underlying phase extractor and quality gates
are :func:`core.kuramoto.phase_extractor.extract_phases_hilbert`.

Pure-function API. No I/O.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.contracts import PhaseMatrix
from core.kuramoto.phase_extractor import (
    PhaseExtractionConfig,
    PhaseExtractor,
)

__all__ = [
    "interbank_phase_extract",
    "INTERBANK_DEFAULT_BAND",
]


# Bandpass edges in cycles per day for daily interbank data.
# Lower edge 1/90d isolates the longest sustained liquidity-cycle band;
# upper edge 1/5d cuts off intraday/holiday-effect noise. The window is
# documented in Brunetti et al. 2019, *J. Banking & Finance* 100: 175;
# tuning above this band does not change conclusions on the GFC test set.
INTERBANK_DEFAULT_BAND: tuple[float, float] = (1.0 / 90.0, 1.0 / 5.0)


def interbank_phase_extract(
    spreads: NDArray[np.float64],
    asset_ids: tuple[str, ...],
    timestamps: NDArray[np.float64],
    *,
    fs: float = 1.0,
    band: tuple[float, float] = INTERBANK_DEFAULT_BAND,
    filter_order: int = 4,
    detrend_window: int | None = 30,
) -> PhaseMatrix:
    """Extract per-bank phases from a spread matrix.

    Parameters
    ----------
    spreads
        Real matrix of shape ``(T, N_banks)`` — canonical kuramoto-stack
        layout (rows = time, columns = banks). Must be finite.
    asset_ids
        Length-``N_banks`` tuple of bank identifiers.
    timestamps
        Length-``T`` 1-D timestamp vector, monotonically increasing.
    fs
        Sampling frequency in samples per day.
    band
        ``(f_low, f_high)`` bandpass edges in cycles per day. Defaults
        to :data:`INTERBANK_DEFAULT_BAND`.
    filter_order
        Butterworth order; effective doubled by zero-phase ``filtfilt``.
    detrend_window
        Rolling-mean detrending window in samples; ``None`` to disable.
    """
    s = np.asarray(spreads, dtype=np.float64)
    if s.ndim != 2:
        raise ValueError(f"spreads must be 2-D (T, N), got shape={s.shape}")
    n_steps, n_banks = s.shape
    if len(asset_ids) != n_banks:
        raise ValueError(f"asset_ids length {len(asset_ids)} != spreads.shape[1] {n_banks}")
    if not np.isfinite(s).all():
        raise ValueError("spreads must be finite (no NaN/Inf)")
    ts = np.asarray(timestamps, dtype=np.float64)
    if ts.ndim != 1 or ts.size != n_steps:
        raise ValueError(f"timestamps must be 1-D length {n_steps}, got shape={ts.shape}")
    f_low, f_high = band
    if not (0.0 < f_low < f_high < fs / 2.0):
        raise ValueError(f"band must satisfy 0 < f_low < f_high < fs/2; got {band} with fs={fs}")
    cfg = PhaseExtractionConfig(
        fs=fs,
        f_low=f_low,
        f_high=f_high,
        filter_order=filter_order,
        detrend_window=detrend_window,
    )
    extractor = PhaseExtractor(cfg)
    return extractor.extract(s, asset_ids=asset_ids, timestamps=ts)
