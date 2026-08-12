# SPDX-License-Identifier: MIT
"""Physics-grounded generative ground truth.

Two Sakaguchi-Kuramoto oscillator populations emit LFP-like mean-field
signals. The *only* mechanism that constitutes genuine CTC routing is a
directed A->B phase coupling (``channel``). Confounds (common drive, rate
envelope, low SNR) are injected with ``channel == 0`` so any "CTC-positive"
readout on them is, by construction, a false positive.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from research.ctc_falsify import config as cfg

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class TwoPopSignals:
    """Mean-field LFP-like signals of the two populations and the ground truth."""

    sig_a: FloatArray
    sig_b: FloatArray
    channel_strength: float  # ground-truth directed A->B coupling (0 == no channel)


def _mean_field(theta: FloatArray) -> float:
    """Real part of the Kuramoto order parameter (LFP-like proxy)."""
    return float(np.cos(theta).mean())


def simulate(
    seed: int,
    *,
    channel_strength: float,
    common_drive: float,
    rate_mod_depth: float,
    snr: float,
) -> TwoPopSignals:
    """Integrate the two-population model and return mean-field signals.

    Parameters
    ----------
    channel_strength : genuine directed A->B phase coupling (the CTC mechanism)
    common_drive     : amplitude of a *shared* stochastic input (N1 confound)
    rate_mod_depth   : depth of a slow envelope correlated across A,B (N2)
    snr              : additive-noise signal-to-noise ratio (N3 when low)
    """
    rng = np.random.default_rng(seed)
    n = cfg.N_OSC
    omega = 2.0 * np.pi * rng.normal(cfg.F0, cfg.FREQ_SIGMA, size=(2, n))
    theta = rng.uniform(-np.pi, np.pi, size=(2, n))

    w0 = 2.0 * np.pi * cfg.F0
    sig_a = np.empty(cfg.T_STEPS, dtype=np.float64)
    sig_b = np.empty(cfg.T_STEPS, dtype=np.float64)

    # Slow envelope shared by both populations (rate/amplitude confound).
    t = np.arange(cfg.T_STEPS) * cfg.DT
    env_freq = 4.0  # Hz, slow co-modulation
    envelope = 1.0 + rate_mod_depth * np.sin(2.0 * np.pi * env_freq * t + rng.uniform(0, np.pi))

    for k in range(cfg.T_STEPS):
        mean_a = np.angle(np.exp(1j * theta[0]).mean())
        mean_b = np.angle(np.exp(1j * theta[1]).mean())

        shared = common_drive * rng.normal(0.0, 1.0) * np.sqrt(cfg.DT)

        # Population A: intra coupling only (the "sender").
        coup_a = cfg.K_INTRA * np.sin(mean_a - theta[0] - cfg.SAKAGUCHI_LAG)
        dtheta_a = (omega[0] + coup_a) * cfg.DT + shared
        # Population B: intra coupling + directed channel from A (the CTC term).
        coup_b = cfg.K_INTRA * np.sin(mean_b - theta[1] - cfg.SAKAGUCHI_LAG)
        chan = channel_strength * cfg.K_INTRA * np.sin(mean_a - theta[1])
        dtheta_b = (omega[1] + coup_b + chan) * cfg.DT + shared

        theta[0] = theta[0] + dtheta_a
        theta[1] = theta[1] + dtheta_b

        sig_a[k] = envelope[k] * _mean_field(theta[0])
        sig_b[k] = envelope[k] * _mean_field(theta[1])

    if snr > 0.0:
        noise_scale = float(np.std(sig_a)) / snr
        sig_a = sig_a + rng.normal(0.0, noise_scale, size=cfg.T_STEPS)
        sig_b = sig_b + rng.normal(0.0, noise_scale, size=cfg.T_STEPS)

    _ = w0  # carrier reference retained for documentation parity
    return TwoPopSignals(sig_a=sig_a, sig_b=sig_b, channel_strength=channel_strength)


def draw_n_plus(seed: int) -> TwoPopSignals:
    """Positive control: a genuine phase-gated channel, no heavy confound."""
    return simulate(
        seed,
        channel_strength=cfg.CHANNEL_STRENGTH_TRUE,
        common_drive=0.05,
        rate_mod_depth=0.0,
        snr=8.0,
    )


def draw_null(seed: int, family: str) -> TwoPopSignals:
    """Confound-only draw (channel_strength == 0 by construction)."""
    if family == "N1_COMMON_DRIVE":
        return simulate(
            seed, channel_strength=0.0, common_drive=cfg.COMMON_DRIVE, rate_mod_depth=0.0, snr=8.0
        )
    if family == "N2_RATE":
        return simulate(
            seed,
            channel_strength=0.0,
            common_drive=0.05,
            rate_mod_depth=cfg.RATE_MOD_DEPTH,
            snr=8.0,
        )
    if family == "N3_SNR":
        return simulate(
            seed,
            channel_strength=0.0,
            common_drive=0.05,
            rate_mod_depth=0.0,
            snr=cfg.SNR_LOW,
        )
    raise ValueError(f"unknown null family: {family!r}")
