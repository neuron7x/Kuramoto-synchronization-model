# SPDX-License-Identifier: MIT
"""L2 fail-closed verdict logic.

Pre-data decision order:

  V1  Surrogate must jointly match rate AND power on every validation draw,
      else INADMISSIBLE_SURROGATE_MISMATCH  (fix #2).
  V2  Positive control (known-routing N+) standardized residual must exceed
      NPLUS_RESIDUAL_MIN_Z AND confound-only residual must stay below
      CONFOUND_RESIDUAL_MAX_Z, else INADMISSIBLE_NPLUS_INSITU_BLIND
      (fix #3 — a blind estimator may never license a kill).
  V3  No real paired dataset is bound → INADMISSIBLE_NO_PAIRED_DATA
      (the designed pre-data success).

KILLED_SCOPED / SURVIVED_INITIAL are reachable only with a bound dataset
(C3): symmetric thresholds (fix #8), P-replication gate (fix #5),
power/MDE gate (fix #7), Holm multiplicity (fix #6).
"""

from __future__ import annotations

from dataclasses import dataclass

from research.ctc_falsify import config as l1
from research.ctc_falsify.generative import draw_n_plus, draw_null
from research.ctc_falsify.l2 import config_l2 as cfg
from research.ctc_falsify.l2.residual import standardized_residual


@dataclass(frozen=True)
class L2SelfValidation:
    surrogate_all_matched: bool
    mean_nplus_residual_z: float
    max_confound_residual_z: float
    nplus_recovered: bool
    confounds_not_flagged: bool
    n_validation_seeds: int
    worst_rate_rel_err: float
    worst_power_rel_err: float


def run_self_validation() -> L2SelfValidation:
    """In-silico proof that the L2 estimator is not blind, BEFORE any data."""
    seeds = [l1.SEED + i for i in range(cfg.N_VALIDATION_SEEDS)]

    nplus_z: list[float] = []
    rate_err: list[float] = []
    power_err: list[float] = []
    all_matched = True
    for s in seeds:
        r = standardized_residual(draw_n_plus(s), s)
        nplus_z.append(r.residual_z)
        rate_err.append(r.rate_rel_err)
        power_err.append(r.power_rel_err)
        all_matched = all_matched and r.matched

    confound_z: list[float] = []
    for fam in l1.NULL_FAMILIES:
        for s in seeds:
            r = standardized_residual(draw_null(s, fam), s)
            confound_z.append(r.residual_z)
            rate_err.append(r.rate_rel_err)
            power_err.append(r.power_rel_err)
            all_matched = all_matched and r.matched

    mean_nplus = float(sum(nplus_z) / len(nplus_z))
    max_conf = max(confound_z)
    return L2SelfValidation(
        surrogate_all_matched=all_matched,
        mean_nplus_residual_z=mean_nplus,
        max_confound_residual_z=max_conf,
        nplus_recovered=mean_nplus >= cfg.NPLUS_RESIDUAL_MIN_Z,
        confounds_not_flagged=max_conf <= cfg.CONFOUND_RESIDUAL_MAX_Z,
        n_validation_seeds=len(seeds),
        worst_rate_rel_err=max(rate_err),
        worst_power_rel_err=max(power_err),
    )


def decide_l2(v: L2SelfValidation, *, real_dataset_bound: bool = False) -> str:
    if not v.surrogate_all_matched:
        return cfg.VERDICT_INADMISSIBLE_SURROGATE_MISMATCH
    if not (v.nplus_recovered and v.confounds_not_flagged):
        return cfg.VERDICT_INADMISSIBLE_NPLUS_INSITU_BLIND
    if not real_dataset_bound:
        return cfg.VERDICT_INADMISSIBLE_NO_PAIRED_DATA
    raise NotImplementedError("real-data residual test is C3; no dataset is bound")
