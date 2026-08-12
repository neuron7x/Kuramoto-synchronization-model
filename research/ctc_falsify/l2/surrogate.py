# SPDX-License-Identifier: MIT
"""Fix #2: a single JOINTLY-matched confound surrogate.

Marginal (match-one-confound) surrogates leak — the Vinck/Schneider critique.
This destroys any true A->B phase coupling while preserving, jointly:
  * the power spectrum of B  (=> SNR / power matched by construction)
  * the amplitude envelope of B  (=> rate proxy matched)
  * signal A unchanged  (=> stimulus-locked common drive preserved)
Match quality is measured and gated (INADMISSIBLE_SURROGATE_MISMATCH).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from research.ctc_falsify.generative import TwoPopSignals
from research.ctc_falsify.l2 import config_l2 as cfg

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class SurrogateBatch:
    sig_a: FloatArray
    surrogate_b: FloatArray  # shape (n_surrogate, T)
    rate_rel_err: float
    power_rel_err: float
    matched: bool


def _phase_randomize(x: FloatArray, rng: np.random.Generator) -> FloatArray:
    """FFT phase randomization: preserves |X(f)| (power), destroys phase."""
    spec = np.fft.rfft(x)
    mag = np.abs(spec)
    rand_phase = np.exp(1j * rng.uniform(0.0, 2.0 * np.pi, size=mag.shape))
    rand_phase[0] = 1.0  # keep DC real
    surr = np.fft.irfft(mag * rand_phase, n=x.shape[0])
    return np.asarray(surr, dtype=np.float64)


def build_joint_surrogate(sig: TwoPopSignals, seed: int) -> SurrogateBatch:
    rng = np.random.default_rng(seed)
    b = sig.sig_b
    env_b = np.abs(b)
    surr = np.empty((cfg.N_SURROGATE, b.shape[0]), dtype=np.float64)
    for i in range(cfg.N_SURROGATE):
        s = _phase_randomize(b, rng)
        # Re-impose B's amplitude envelope (rate proxy) on the phase-killed signal.
        s_env = np.abs(s)
        s = s * (env_b / (s_env + 1e-12))
        surr[i] = s

    rate_obs = float(np.mean(env_b))
    rate_surr = float(np.mean(np.abs(surr)))
    power_obs = float(np.var(b))
    power_surr = float(np.mean(np.var(surr, axis=1)))
    rate_err = abs(rate_surr - rate_obs) / (abs(rate_obs) + 1e-12)
    power_err = abs(power_surr - power_obs) / (abs(power_obs) + 1e-12)
    matched = rate_err <= cfg.RATE_MATCH_TOL and power_err <= cfg.SNR_MATCH_TOL
    return SurrogateBatch(
        sig_a=sig.sig_a,
        surrogate_b=surr,
        rate_rel_err=rate_err,
        power_rel_err=power_err,
        matched=matched,
    )
