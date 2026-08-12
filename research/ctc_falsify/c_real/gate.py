# SPDX-License-Identifier: MIT
"""Fail-closed C-real decision logic (pre-data).

Decision order, all pre-registered:

  A  No paired LFP+spike dataset bound  -> INADMISSIBLE_NO_PAIRED_DATA.
  B  No INDEPENDENT routing-ON/OFF label (attention/opto/microstim)
     -> INADMISSIBLE_NO_INDEPENDENT_ROUTING_LABEL  (real data has no
     toggle GT; a self-derived label is circular — the C4 lesson).
  C  Descriptive P (coherence↔behaviour) does not replicate on the bound
     dataset -> INADMISSIBLE_DATASET_UNSUITABLE.
  D  Power below MDE -> INADMISSIBLE_UNDERPOWERED.
  E  Terminal (only here): the two pre-stated forecast branches —
       SURVIVED_INITIAL  iff the C5 cross-spectral discriminant OOS-AUC
         >= AUC_SUPPORT_MIN on routing-ON vs OFF, above the
         jointly-matched confound surrogate, Holm-corrected;
       KILLED_SCOPED     iff OOS-AUC <= AUC_CHANCE_HI with the
         independent control present (variant A: standard CTC evidence
         is estimand-limited / phenomenon absent at this scope).

Pre-data, only Step A is reachable: the designed INADMISSIBLE_NO_PAIRED_DATA.
KILLED_SCOPED / SURVIVED_INITIAL require a bound dataset (C-real-data),
never this prereg artifact.
"""

from __future__ import annotations

from research.ctc_falsify.c_real import config_c_real as cr


def decide(
    *,
    dataset_bound: bool = False,
    independent_label: bool = False,
    p_replicates: bool = False,
    powered: bool = False,
    oos_auc: float | None = None,
) -> str:
    if not dataset_bound:
        return cr.VERDICT_NO_PAIRED_DATA
    if not independent_label:
        return cr.VERDICT_NO_INDEPENDENT_LABEL
    if not p_replicates:
        return cr.VERDICT_DATASET_UNSUITABLE
    if not powered:
        return cr.VERDICT_UNDERPOWERED
    if oos_auc is None:
        raise NotImplementedError("C-real-data residual test is the next layer; not bound here")
    if oos_auc >= cr.AUC_SUPPORT_MIN:
        return cr.VERDICT_SURVIVED_INITIAL
    if oos_auc <= cr.AUC_CHANCE_HI:
        return cr.VERDICT_KILLED_SCOPED
    raise NotImplementedError("AUC in the inconclusive band — needs richer pre-registered probe")
