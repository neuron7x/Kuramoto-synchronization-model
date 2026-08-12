# SPDX-License-Identifier: MIT
"""Fail-closed adversarial audit of the phase-offset estimator.

Gates (all must pass for C4_BOUNDARY_HARDENED):

  G1 separability   : |offset| on N⁺ separates from pooled confounds with
                      Cohen's d >= D_MIN (else the C3 boundary claim was a
                      self-lie: the privileged estimator never really saw
                      the channel).
  G2 confound-reject: at the N⁺-derived decision boundary, the
                      false-positive rate on confound-only draws
                      (channel == 0) is <= FP_MAX.
  G3 sign-flip      : offset(B,A) ~ -offset(A,B) on >= SIGN_FRAC of N⁺
                      seeds (a genuinely *directed* estimator).
  G4 sweep          : with channel_strength == 0, |offset| stays below the
                      decision boundary across a common-drive sweep — the
                      estimator must not invent a channel under stronger
                      confounds.

Any failure ⇒ a scoped INADMISSIBLE that *narrows or retracts* the C3
"recoverable in principle" claim. No threshold tuning.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from research.ctc_falsify import config as cfg
from research.ctc_falsify.c4 import config_c4 as c4
from research.ctc_falsify.c4.phase_offset import offset_ab, offset_ba
from research.ctc_falsify.generative import draw_n_plus, draw_null, simulate


@dataclass(frozen=True)
class AuditResult:
    cohens_d: float
    decision_boundary: float
    confound_false_positive_rate: float
    signflip_pass_fraction: float
    sweep_false_positive_count: int
    sweep_total: int
    g1_separable: bool
    g2_confounds_rejected: bool
    g3_signflip_ok: bool
    g4_sweep_clean: bool


def _cohens_d(x: np.ndarray, y: np.ndarray) -> float:
    nx, ny = len(x), len(y)
    sp = np.sqrt(((nx - 1) * x.var(ddof=1) + (ny - 1) * y.var(ddof=1)) / (nx + ny - 2))
    return float(abs(x.mean() - y.mean()) / sp) if sp > 1e-12 else 0.0


def run_audit() -> AuditResult:
    seeds = [cfg.SEED + i for i in range(cfg.N_NULL_SEEDS)]

    nplus = np.array([abs(offset_ab(draw_n_plus(s))) for s in seeds], dtype=np.float64)
    conf = np.array(
        [abs(offset_ab(draw_null(s, fam))) for fam in cfg.NULL_FAMILIES for s in seeds],
        dtype=np.float64,
    )

    d = _cohens_d(nplus, conf)
    # Decision boundary: midpoint between the confound mean and the N⁺ mean.
    boundary = float((conf.mean() + nplus.mean()) / 2.0)
    fp_rate = float(np.mean(conf >= boundary))

    sign_ok = 0
    for s in seeds:
        sig = draw_n_plus(s)
        ab, ba = offset_ab(sig), offset_ba(sig)
        if np.sign(ab) != np.sign(ba) and abs(ab) > 1e-9:
            sign_ok += 1
    sign_frac = sign_ok / len(seeds)

    sweep_fp = 0
    sweep_total = 0
    for cd in c4.SWEEP_COMMON_DRIVE:
        for s in seeds[: c4.SWEEP_SEEDS]:
            sig = simulate(s, channel_strength=0.0, common_drive=cd, rate_mod_depth=0.0, snr=8.0)
            sweep_total += 1
            if abs(offset_ab(sig)) >= boundary:
                sweep_fp += 1

    return AuditResult(
        cohens_d=d,
        decision_boundary=boundary,
        confound_false_positive_rate=fp_rate,
        signflip_pass_fraction=sign_frac,
        sweep_false_positive_count=sweep_fp,
        sweep_total=sweep_total,
        g1_separable=d >= c4.D_MIN,
        g2_confounds_rejected=fp_rate <= c4.FP_MAX,
        g3_signflip_ok=sign_frac >= c4.SIGN_FRAC,
        g4_sweep_clean=(sweep_fp == 0),
    )


def decide(a: AuditResult) -> str:
    if not a.g1_separable:
        return c4.VERDICT_CANT_SEPARATE
    if not a.g3_signflip_ok:
        return c4.VERDICT_SIGNFLIP_BROKEN
    if not (a.g2_confounds_rejected and a.g4_sweep_clean):
        return c4.VERDICT_CONFOUND_FALSE_POSITIVE
    return c4.VERDICT_BOUNDARY_HARDENED
