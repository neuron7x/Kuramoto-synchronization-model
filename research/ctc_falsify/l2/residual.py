# SPDX-License-Identifier: MIT
"""Fix #1: standardized residual estimand (not a difference of point estimates).

residual_z = (SFC_obs - mean(SFC_surrogate)) / std(SFC_surrogate)

SFC = the same gamma PLV the standard CTC pipeline uses (L1 pipeline), so the
residual asks exactly: what is left after the jointly-matched confound null is
subtracted, in surrogate-standardized units.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import hilbert

from research.ctc_falsify.generative import TwoPopSignals
from research.ctc_falsify.l2.surrogate import build_joint_surrogate
from research.ctc_falsify.pipeline import _bandpass


@dataclass(frozen=True)
class ResidualResult:
    residual_z: float
    sfc_observed: float
    surrogate_mean: float
    surrogate_std: float
    matched: bool
    rate_rel_err: float
    power_rel_err: float


def _plv_pair(a: np.ndarray, b: np.ndarray) -> float:
    pa = np.angle(hilbert(_bandpass(np.asarray(a, dtype=np.float64))))
    pb = np.angle(hilbert(_bandpass(np.asarray(b, dtype=np.float64))))
    return float(np.abs(np.exp(1j * (pa - pb)).mean()))


def standardized_residual(sig: TwoPopSignals, seed: int) -> ResidualResult:
    batch = build_joint_surrogate(sig, seed)
    sfc_obs = _plv_pair(sig.sig_a, sig.sig_b)
    surr_sfc = np.array(
        [_plv_pair(batch.sig_a, batch.surrogate_b[i]) for i in range(batch.surrogate_b.shape[0])],
        dtype=np.float64,
    )
    mu = float(surr_sfc.mean())
    sd = float(surr_sfc.std(ddof=1))
    z = (sfc_obs - mu) / sd if sd > 1e-12 else 0.0
    return ResidualResult(
        residual_z=float(z),
        sfc_observed=sfc_obs,
        surrogate_mean=mu,
        surrogate_std=sd,
        matched=batch.matched,
        rate_rel_err=batch.rate_rel_err,
        power_rel_err=batch.power_rel_err,
    )
