# SPDX-License-Identifier: MIT
"""C3: time-reversed-surrogate directed residual estimator (v2).

The v1 phase-randomization estimator was blind (it destroyed the legitimate
channel phase along with the confound). v2 instead uses a TIME-REVERSED
surrogate (Schreiber-Schmitz): time reversal preserves the power spectrum,
autocorrelation, amplitude distribution and any shared (common-drive)
structure EXACTLY, but flips the sign of a directed phase lag — so a true
causal A->B channel survives as a directed-asymmetry residual while
confound-only (zero-lag / symmetric) signals collapse to ~0.

Directed statistic: the Phase-Slope Index (Nolte 2008) over the gamma band,
which is antisymmetric under time reversal of one channel.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import csd

from research.ctc_falsify import config as l1
from research.ctc_falsify.generative import TwoPopSignals
from research.ctc_falsify.l2 import config_l2 as cfg

_FS: float = 1.0 / l1.DT
_GAMMA_LO: float = l1.F0 - l1.GAMMA_BAND_HALFWIDTH
_GAMMA_HI: float = l1.F0 + l1.GAMMA_BAND_HALFWIDTH


@dataclass(frozen=True)
class ResidualV2:
    residual_z: float
    psi_observed: float
    surrogate_mean_abs: float
    surrogate_std_abs: float


def _phase_slope_index(a: np.ndarray, b: np.ndarray) -> float:
    """PSI over the gamma band. Sign/magnitude is directional and flips
    under time reversal of one channel."""
    freqs, pxy = csd(a, b, fs=_FS, nperseg=cfg.PSI_NPERSEG)
    coh = pxy / (np.abs(pxy) + 1e-18)  # unit complex coherency proxy
    band = (freqs >= _GAMMA_LO) & (freqs <= _GAMMA_HI)
    idx = np.where(band)[0]
    if idx.size < 2:
        return 0.0
    val = 0.0
    for j in range(idx.size - 1):
        f0, f1 = idx[j], idx[j + 1]
        val += float(np.imag(np.conj(coh[f0]) * coh[f1]))
    return val


def time_reversed_surrogates(sig: TwoPopSignals, seed: int) -> np.ndarray:
    """Time-reversed B with random circular shift per surrogate.

    Time reversal kills directed phase; the circular shift (spectrum- and
    autocorrelation-preserving) provides an ensemble for standardization
    without re-introducing a directed relationship.
    """
    rng = np.random.default_rng(seed)
    b_rev = sig.sig_b[::-1].copy()
    n = b_rev.shape[0]
    out = np.empty((cfg.N_SURROGATE, n), dtype=np.float64)
    for i in range(cfg.N_SURROGATE):
        shift = int(rng.integers(1, n))
        out[i] = np.roll(b_rev, shift)
    return out


def directed_residual_v2(sig: TwoPopSignals, seed: int) -> ResidualV2:
    psi_obs = _phase_slope_index(sig.sig_a, sig.sig_b)
    surr = time_reversed_surrogates(sig, seed)
    psi_surr = np.array(
        [abs(_phase_slope_index(sig.sig_a, surr[i])) for i in range(surr.shape[0])],
        dtype=np.float64,
    )
    mu = float(psi_surr.mean())
    sd = float(psi_surr.std(ddof=1))
    z = (abs(psi_obs) - mu) / sd if sd > 1e-18 else 0.0
    return ResidualV2(
        residual_z=float(z),
        psi_observed=float(psi_obs),
        surrogate_mean_abs=mu,
        surrogate_std_abs=sd,
    )
