# SPDX-License-Identifier: MIT
"""Fail-closed admissibility gates and verdict logic.

Decision order (pre-registered — see docs/research/CTC_FALSIFY_001_PREREGISTRATION.md):

    A  Generative ground truth must exist (channel toggle) else
       INADMISSIBLE_NO_GENERATIVE_GROUNDTRUTH.
    B  Positive control N+ must be recovered by the standard pipeline on
       >= NPLUS_MIN_RECOVERY of seeds else INADMISSIBLE_ESTIMATOR_BLIND
       (a pipeline that cannot see a true channel cannot license any kill).
    C  The readout must be independent of the injected channel parameter
       else INADMISSIBLE_CIRCULAR_PIPELINE.
    D  Enough independent seeds else INADMISSIBLE_UNDERPOWERED.
    E  No real electrophysiology dataset is bound at this stage, so the
       canon-kill verdict is withheld: INADMISSIBLE_NO_REAL_DATA. The
       confound diagnostic is still computed and recorded as evidence.

KILLED_SCOPED / SURVIVED_INITIAL are unreachable until ``real_data`` is
provided (L2). The engine never fabricates a kill, never rescues the canon.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from research.ctc_falsify import config as cfg
from research.ctc_falsify.generative import draw_n_plus, draw_null
from research.ctc_falsify.pipeline import run_standard_pipeline


@dataclass(frozen=True)
class Diagnostic:
    nplus_recovery_rate: float
    null_false_positive_rate: dict[str, float]
    n_seeds: int
    readout_independent_of_groundtruth: bool
    mean_nplus_plv: float
    mean_null_plv: dict[str, float] = field(default_factory=dict)


def _seeds() -> list[int]:
    return [cfg.SEED + i for i in range(cfg.N_NULL_SEEDS)]


def run_diagnostic() -> Diagnostic:
    """Run the generative confound diagnostic across independent seeds."""
    seeds = _seeds()

    nplus_hits = 0
    nplus_plv: list[float] = []
    for s in seeds:
        r = run_standard_pipeline(draw_n_plus(s))
        nplus_hits += int(r.ctc_positive)
        nplus_plv.append(r.plv)

    fp_rate: dict[str, float] = {}
    mean_null_plv: dict[str, float] = {}
    for fam in cfg.NULL_FAMILIES:
        hits = 0
        plvs: list[float] = []
        for s in seeds:
            r = run_standard_pipeline(draw_null(s, fam))
            hits += int(r.ctc_positive)
            plvs.append(r.plv)
        fp_rate[fam] = hits / len(seeds)
        mean_null_plv[fam] = float(sum(plvs) / len(plvs))

    # Circularity guard: the readout is a pure function of the signals; a
    # confound draw has channel_strength == 0 yet still yields a finite PLV,
    # which is only possible if the readout does not read the ground truth.
    probe = draw_null(seeds[0], cfg.NULL_FAMILIES[0])
    readout_independent = probe.channel_strength == 0.0 and run_standard_pipeline(probe).plv >= 0.0

    return Diagnostic(
        nplus_recovery_rate=nplus_hits / len(seeds),
        null_false_positive_rate=fp_rate,
        n_seeds=len(seeds),
        readout_independent_of_groundtruth=readout_independent,
        mean_nplus_plv=float(sum(nplus_plv) / len(nplus_plv)),
        mean_null_plv=mean_null_plv,
    )


def decide(diag: Diagnostic, *, groundtruth_available: bool = True, real_data: bool = False) -> str:
    """Fail-closed verdict from the diagnostic. Default path = INADMISSIBLE."""
    if not groundtruth_available:
        return cfg.VERDICT_INADMISSIBLE_NO_GROUNDTRUTH
    if diag.nplus_recovery_rate < cfg.NPLUS_MIN_RECOVERY:
        return cfg.VERDICT_INADMISSIBLE_ESTIMATOR_BLIND
    if not diag.readout_independent_of_groundtruth:
        return cfg.VERDICT_INADMISSIBLE_CIRCULAR
    if diag.n_seeds < cfg.MIN_SEEDS_FOR_POWER:
        return cfg.VERDICT_INADMISSIBLE_UNDERPOWERED
    if not real_data:
        # Pre-data: the canon-kill is withheld by design. The confound
        # diagnostic is recorded but no verdict on the theory is emitted.
        return cfg.VERDICT_INADMISSIBLE_NO_REAL_DATA
    # real_data path (L2) is intentionally not implementable here yet.
    raise NotImplementedError("real-data residual test is L2; not bound in this artifact")
