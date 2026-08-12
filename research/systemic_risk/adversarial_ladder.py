# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Adversarial ladder — hypothesis-destruction first, confirmation last.

Operational doctrine (per
``feedback_hypothesis_destruction_machine.md``):

    Don't prove Kuramoto. Build a system where Kuramoto must lose
    to everything simpler — and only if it doesn't lose, a fact
    is born.

The eight rungs (in order of stringency):

    1. Naive baselines               — simpler model wins → die
    2. Null surrogates               — destroyed marginal preserved
    3. Leakage traps                 — future-segment / lookahead
    4. Data-friction audit           — schema / IDs / calendar
    5. Parameter fragility           — sensitivity sweep
    6. Cross-implementation          — second engineer rewrites
    7. Replication                   — independent operator
    8. Prospective                   — locked detector vs next event

Each prosecutor is pre-computed *outside* this module by the
caller (so the ladder stays a pure verdict machine), then handed
to :func:`run_adversarial_ladder` as a per-prosecutor score
series. The ladder evaluates the candidate AUC against each
prosecutor's AUC on the same crisis windows and reports the
delta with a paired bootstrap CI.

**Default verdict is GUILTY.** Acquittal requires the candidate
to clear every engaged rung; even a clean acquittal is labelled
``ACQUITTED_ENGAGED`` (not ``ACQUITTED``) because the four rungs
the system cannot autonomously execute (data-friction with real
data, cross-implementation, replication, prospective) remain
``untested_rungs`` until external evidence is supplied.

Pure-function API. No I/O. Determinism via explicit ``seed``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

import numpy as np
from numpy.typing import NDArray

from .event_ledger import BankingCrisisLedger
from .falsification import (
    FalsificationConfig,
    auc_bootstrap_ci,
    auc_mann_whitney,
    run_falsification,
)

__all__ = [
    "LADDER_RUNGS",
    "LadderConfig",
    "ProsecutorScore",
    "ProsecutorOutcome",
    "LadderReport",
    "LadderVerdict",
    "ParameterFragilityReport",
    "run_adversarial_ladder",
    "parameter_fragility_audit",
    "run_null_audit",
]


LadderVerdict = Literal[
    "GUILTY",  # at least one prosecutor beat or tied the candidate
    "ACQUITTED_ENGAGED",  # candidate beat every engaged prosecutor
    "INSUFFICIENT_RUNGS",  # zero engaged prosecutors
]


# Canonical 8-rung ladder per the hypothesis-destruction-machine
# feedback memory. Rungs 4 / 6 / 7 / 8 are *structurally* outside
# the scope of any autonomous run (real-data ingest, second
# engineer, independent operator, prospective lock); they exist
# in the constant so the report can list them as ``untested_rungs``.
LADDER_RUNGS: tuple[tuple[int, str], ...] = (
    (1, "naive_baselines"),
    (2, "null_surrogates"),
    (3, "leakage_traps"),
    (4, "data_friction_audit"),
    (5, "parameter_fragility"),
    (6, "cross_implementation"),
    (7, "replication"),
    (8, "prospective"),
)


@dataclass(frozen=True, slots=True)
class LadderConfig:
    """Pre-registered ladder hyperparameters.

    Attributes
    ----------
    falsification
        Per-crisis falsification config — passed verbatim to
        :func:`run_falsification` for the candidate and each
        prosecutor.
    seed
        Root RNG seed for the paired bootstrap.
    n_bootstrap
        Stratified percentile-bootstrap iterations for the
        delta-AUC CI. Default 10000.
    confidence
        Confidence level for the delta-AUC CI. Default 0.95.
    delta_floor
        ``delta_ci_low > delta_floor`` is the survival criterion
        for one prosecutor. Default 0.0 — the candidate must
        outperform the prosecutor by a margin whose CI clears
        zero. Stricter callers may set ``delta_floor = 0.05``.
    """

    falsification: FalsificationConfig
    seed: int = 42
    n_bootstrap: int = 10_000
    confidence: float = 0.95
    delta_floor: float = 0.0

    def __post_init__(self) -> None:
        if self.n_bootstrap < 100:
            raise ValueError(f"n_bootstrap must be >= 100, got {self.n_bootstrap}")
        if not 0.0 < self.confidence < 1.0:
            raise ValueError(f"confidence must be in (0, 1), got {self.confidence}")
        if self.delta_floor < 0.0:
            raise ValueError(
                f"delta_floor must be >= 0 (a prosecutor that beats the "
                f"candidate cannot be 'survived'), got {self.delta_floor}"
            )


@dataclass(frozen=True, slots=True)
class ProsecutorScore:
    """A pre-computed prosecutor score series with rung label.

    Attributes
    ----------
    name
        Canonical prosecutor identifier — e.g. ``"naive_volatility"``,
        ``"shuffled_time_labels"``. Reused as the report key.
    rung
        Ladder rung index (1-8) per :data:`LADDER_RUNGS`.
    score
        1-D array of length matching ``len(dates)``. The
        prosecutor's analogous detector output on the same time
        grid the candidate is evaluated on.
    """

    name: str
    rung: int
    score: NDArray[np.float64]

    def __post_init__(self) -> None:
        if not 1 <= self.rung <= 8:
            raise ValueError(f"rung must be in [1, 8], got {self.rung}")
        if self.score.ndim != 1:
            raise ValueError(f"score must be 1-D, got shape={self.score.shape}")


@dataclass(frozen=True, slots=True)
class ProsecutorOutcome:
    """Per-prosecutor verdict + paired-delta evidence."""

    name: str
    rung: int
    candidate_auc: float
    prosecutor_auc: float
    delta_auc: float
    delta_ci_low: float
    delta_ci_high: float
    candidate_beat_prosecutor: bool
    n_crises_evaluated: int
    failure_reason: str | None


@dataclass(frozen=True, slots=True)
class LadderReport:
    """Composite verdict from :func:`run_adversarial_ladder`.

    Attributes
    ----------
    verdict
        ``"GUILTY"`` (≥ 1 prosecutor not beaten),
        ``"ACQUITTED_ENGAGED"`` (every engaged prosecutor lost),
        or ``"INSUFFICIENT_RUNGS"`` (no prosecutor was supplied).
        ``ACQUITTED_ENGAGED`` is the strongest verdict any
        autonomous run can emit; full ``ACQUITTED`` requires the
        4 external rungs to be cleared by separate evidence.
    outcomes
        Per-prosecutor outcomes in the order they were supplied.
    survival_paths
        Names of prosecutors the candidate beat (delta_ci_low >
        delta_floor on aggregated AUC).
    losing_paths
        Names of prosecutors the candidate lost or tied.
    lowest_rung_loss
        Smallest rung index at which the candidate was not beaten;
        ``None`` when ``verdict != "GUILTY"``.
    untested_rungs
        Rungs in 1..8 with zero prosecutors supplied. The four
        external rungs (4, 6, 7, 8) typically appear here for any
        autonomous run; their presence is the explicit reminder
        that ``ACQUITTED_ENGAGED ≠ ACQUITTED``.
    """

    verdict: LadderVerdict
    outcomes: tuple[ProsecutorOutcome, ...]
    survival_paths: tuple[str, ...]
    losing_paths: tuple[str, ...]
    lowest_rung_loss: int | None
    untested_rungs: tuple[int, ...]


# ---------------------------------------------------------------------------
# Internals — paired bootstrap on aggregated AUC
# ---------------------------------------------------------------------------


def _aggregate_aucs(
    score: NDArray[np.float64],
    dates: tuple[date, ...],
    ledger: BankingCrisisLedger,
    *,
    config: FalsificationConfig,
    country_filter: str | None,
) -> tuple[float, int]:
    """Return (mean per-crisis AUC, number of crises evaluated)."""
    report = run_falsification(score, dates, ledger, config=config, country_filter=country_filter)
    if not report.outcomes:
        return float("nan"), 0
    aucs = np.array([o.auc for o in report.outcomes], dtype=np.float64)
    return float(aucs.mean()), int(aucs.size)


def _paired_delta_bootstrap(
    candidate_score: NDArray[np.float64],
    prosecutor_score: NDArray[np.float64],
    dates: tuple[date, ...],
    ledger: BankingCrisisLedger,
    *,
    config: LadderConfig,
    country_filter: str | None,
) -> tuple[float, float, float, float, float, int]:
    """Paired bootstrap of (candidate_AUC − prosecutor_AUC) per crisis.

    Returns
    -------
    (candidate_mean_auc, prosecutor_mean_auc, delta, ci_low, ci_high, n_crises)
    """
    cand_mean, n_crises = _aggregate_aucs(
        candidate_score,
        dates,
        ledger,
        config=config.falsification,
        country_filter=country_filter,
    )
    prose_mean, n_crises_p = _aggregate_aucs(
        prosecutor_score,
        dates,
        ledger,
        config=config.falsification,
        country_filter=country_filter,
    )
    if n_crises == 0 or n_crises_p == 0:
        return (
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            float("nan"),
            min(n_crises, n_crises_p),
        )
    # Per-crisis paired bootstrap: resample (candidate_outcome,
    # prosecutor_outcome) jointly across the crisis index.
    cand_report = run_falsification(
        candidate_score,
        dates,
        ledger,
        config=config.falsification,
        country_filter=country_filter,
    )
    prose_report = run_falsification(
        prosecutor_score,
        dates,
        ledger,
        config=config.falsification,
        country_filter=country_filter,
    )
    # Align by crisis label so the bootstrap is paired correctly.
    by_label_cand = {o.label: o.auc for o in cand_report.outcomes}
    by_label_prose = {o.label: o.auc for o in prose_report.outcomes}
    common_labels = sorted(set(by_label_cand) & set(by_label_prose))
    if not common_labels:
        return (cand_mean, prose_mean, float("nan"), float("nan"), float("nan"), 0)
    cand_arr = np.array([by_label_cand[lbl] for lbl in common_labels], dtype=np.float64)
    prose_arr = np.array([by_label_prose[lbl] for lbl in common_labels], dtype=np.float64)
    rng = np.random.default_rng(config.seed)
    n = cand_arr.size
    deltas = np.empty(config.n_bootstrap, dtype=np.float64)
    for b in range(config.n_bootstrap):
        idx = rng.integers(0, n, size=n)
        deltas[b] = float(cand_arr[idx].mean() - prose_arr[idx].mean())
    alpha = (1.0 - config.confidence) / 2.0
    ci_low = float(np.quantile(deltas, alpha))
    ci_high = float(np.quantile(deltas, 1.0 - alpha))
    return (
        float(cand_arr.mean()),
        float(prose_arr.mean()),
        float(cand_arr.mean() - prose_arr.mean()),
        ci_low,
        ci_high,
        int(n),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_adversarial_ladder(
    candidate_score: NDArray[np.float64],
    dates: tuple[date, ...],
    ledger: BankingCrisisLedger,
    *,
    prosecutors: tuple[ProsecutorScore, ...],
    config: LadderConfig,
    country_filter: str | None = None,
) -> LadderReport:
    """Evaluate the candidate against every supplied prosecutor.

    Default verdict is ``GUILTY`` — the candidate must outperform
    *every* engaged prosecutor on aggregated AUC with a paired
    bootstrap CI lower bound clearing ``config.delta_floor``.

    Parameters
    ----------
    candidate_score
        1-D early-warning score, length ``len(dates)``.
    dates
        Strictly-increasing tuple of calendar dates.
    ledger
        :class:`BankingCrisisLedger` (synthetic or real).
    prosecutors
        Tuple of :class:`ProsecutorScore` — one per prosecutor.
    config
        :class:`LadderConfig` with embedded
        :class:`FalsificationConfig`.
    country_filter
        Optional ISO-3 country code; restricts evaluation to that
        country's events.
    """
    if candidate_score.ndim != 1:
        raise ValueError(f"candidate_score must be 1-D, got shape={candidate_score.shape}")
    n_engaged = len(prosecutors)
    engaged_rungs = {p.rung for p in prosecutors}
    untested = tuple(rung for rung, _ in LADDER_RUNGS if rung not in engaged_rungs)
    outcomes: list[ProsecutorOutcome] = []
    for p in prosecutors:
        if p.score.size != candidate_score.size:
            outcomes.append(
                ProsecutorOutcome(
                    name=p.name,
                    rung=p.rung,
                    candidate_auc=float("nan"),
                    prosecutor_auc=float("nan"),
                    delta_auc=float("nan"),
                    delta_ci_low=float("nan"),
                    delta_ci_high=float("nan"),
                    candidate_beat_prosecutor=False,
                    n_crises_evaluated=0,
                    failure_reason=(
                        f"prosecutor score length {p.score.size} != "
                        f"candidate length {candidate_score.size}"
                    ),
                )
            )
            continue
        cand_auc, prose_auc, delta, ci_low, ci_high, n_cr = _paired_delta_bootstrap(
            candidate_score,
            p.score,
            dates,
            ledger,
            config=config,
            country_filter=country_filter,
        )
        if n_cr == 0 or not np.isfinite(ci_low):
            outcomes.append(
                ProsecutorOutcome(
                    name=p.name,
                    rung=p.rung,
                    candidate_auc=cand_auc,
                    prosecutor_auc=prose_auc,
                    delta_auc=delta,
                    delta_ci_low=ci_low,
                    delta_ci_high=ci_high,
                    candidate_beat_prosecutor=False,
                    n_crises_evaluated=n_cr,
                    failure_reason=(
                        "no crises evaluable on common labels — prosecutor cannot be tested"
                    ),
                )
            )
            continue
        beat = ci_low > config.delta_floor
        outcomes.append(
            ProsecutorOutcome(
                name=p.name,
                rung=p.rung,
                candidate_auc=cand_auc,
                prosecutor_auc=prose_auc,
                delta_auc=delta,
                delta_ci_low=ci_low,
                delta_ci_high=ci_high,
                candidate_beat_prosecutor=beat,
                n_crises_evaluated=n_cr,
                failure_reason=None,
            )
        )
    survival = tuple(o.name for o in outcomes if o.candidate_beat_prosecutor)
    losing = tuple(o.name for o in outcomes if not o.candidate_beat_prosecutor)
    lowest_loss: int | None
    if losing:
        lowest_loss = min(o.rung for o in outcomes if not o.candidate_beat_prosecutor)
    else:
        lowest_loss = None
    if n_engaged == 0:
        verdict: LadderVerdict = "INSUFFICIENT_RUNGS"
    elif losing:
        verdict = "GUILTY"
    else:
        verdict = "ACQUITTED_ENGAGED"
    return LadderReport(
        verdict=verdict,
        outcomes=tuple(outcomes),
        survival_paths=survival,
        losing_paths=losing,
        lowest_rung_loss=lowest_loss,
        untested_rungs=untested,
    )


# ---------------------------------------------------------------------------
# Rung 5 — parameter fragility audit
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ParameterFragilityReport:
    """Sensitivity sweep over a single config knob.

    Attributes
    ----------
    parameter
        Name of the swept axis (e.g. ``"pre_event_window_days"``).
    values
        Swept values in the order they were evaluated.
    aucs
        Mean per-crisis AUC at each swept value.
    verdicts
        Per-value falsification verdict
        (``HARD_FAIL`` / ``HARD_PASS`` / ``UNDECIDED``).
    auc_min, auc_max
        Min / max mean AUC over the sweep.
    auc_range
        ``auc_max - auc_min``. Wider range = more fragile.
    fragile
        ``True`` when ``auc_range >= fragility_tolerance`` —
        candidate's verdict depends on parameter choice, so the
        single-point AUC is *not* representative.
    """

    parameter: str
    values: tuple[float, ...]
    aucs: tuple[float, ...]
    verdicts: tuple[str, ...]
    auc_min: float
    auc_max: float
    auc_range: float
    fragile: bool


def parameter_fragility_audit(
    score: NDArray[np.float64],
    dates: tuple[date, ...],
    ledger: BankingCrisisLedger,
    *,
    base_config: FalsificationConfig,
    parameter: str,
    sweep: tuple[float, ...],
    fragility_tolerance: float = 0.05,
    country_filter: str | None = None,
) -> ParameterFragilityReport:
    """Sweep one config knob and report verdict stability.

    The sweep replaces ``base_config`` field ``parameter`` with each
    value in ``sweep`` and re-runs :func:`run_falsification`. The
    audit is fragile when the AUC range across the sweep meets or
    exceeds ``fragility_tolerance``.

    Why this exists: a single-point HARD_PASS is not evidence if a
    1-day change in ``pre_event_window_days`` flips the verdict.
    Reporting the sweep is the only honest answer.
    """
    if not sweep:
        raise ValueError("sweep must be non-empty")
    if fragility_tolerance < 0:
        raise ValueError(f"fragility_tolerance must be >= 0, got {fragility_tolerance}")
    # Validate the parameter NAME up-front so the unknown-field
    # raise is not swallowed by the per-value sweep wrapper below.
    _config_with_override(base_config, parameter, sweep[0])
    aucs: list[float] = []
    verdicts: list[str] = []
    for value in sweep:
        try:
            new_cfg = _config_with_override(base_config, parameter, value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid sweep value {value} for {parameter!r}") from exc
        report = run_falsification(
            score, dates, ledger, config=new_cfg, country_filter=country_filter
        )
        if report.outcomes:
            mean_auc = float(np.mean([o.auc for o in report.outcomes]))
        else:
            mean_auc = float("nan")
        aucs.append(mean_auc)
        verdicts.append(report.verdict)
    finite_aucs = [a for a in aucs if np.isfinite(a)]
    auc_min = min(finite_aucs) if finite_aucs else float("nan")
    auc_max = max(finite_aucs) if finite_aucs else float("nan")
    auc_range = auc_max - auc_min if finite_aucs else float("nan")
    fragile = bool(np.isfinite(auc_range) and auc_range >= fragility_tolerance)
    return ParameterFragilityReport(
        parameter=parameter,
        values=tuple(float(v) for v in sweep),
        aucs=tuple(aucs),
        verdicts=tuple(verdicts),
        auc_min=auc_min,
        auc_max=auc_max,
        auc_range=auc_range,
        fragile=fragile,
    )


def _config_with_override(
    base: FalsificationConfig, name: str, value: float
) -> FalsificationConfig:
    """Return a new FalsificationConfig with one field overridden.

    Validates against the field set of FalsificationConfig — no
    silent extra-field acceptance.
    """
    int_fields = {
        "pre_event_window_days",
        "null_window_count",
        "min_distance_from_event_days",
        "n_permutations",
        "n_bootstrap",
    }
    float_fields = {
        "fail_auc",
        "ci_floor_tol",
        "pass_auc_ci_low",
        "pass_alpha",
    }
    sweep_eligible = sorted(int_fields | float_fields)
    if name not in int_fields and name not in float_fields:
        raise ValueError(
            f"unknown FalsificationConfig field {name!r}; sweep-eligible: {sweep_eligible}"
        )
    kwargs: dict[str, int | float] = {
        "pre_event_window_days": base.pre_event_window_days,
        "null_window_count": base.null_window_count,
        "min_distance_from_event_days": base.min_distance_from_event_days,
        "n_permutations": base.n_permutations,
        "n_bootstrap": base.n_bootstrap,
        "confidence": base.confidence,
        "fail_auc": base.fail_auc,
        "ci_floor_tol": base.ci_floor_tol,
        "pass_auc_ci_low": base.pass_auc_ci_low,
        "pass_alpha": base.pass_alpha,
        "seed": base.seed,
    }
    if name in int_fields:
        kwargs[name] = int(value)
    else:
        kwargs[name] = float(value)
    return FalsificationConfig(**kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Composed null audit (closes the PATH B deferral on PR #562)
# ---------------------------------------------------------------------------


def run_null_audit(
    candidate_score: NDArray[np.float64],
    null_scores: tuple[tuple[str, NDArray[np.float64]], ...],
    dates: tuple[date, ...],
    ledger: BankingCrisisLedger,
    *,
    config: LadderConfig,
    country_filter: str | None = None,
) -> LadderReport:
    """Six-baseline null audit composed over the adversarial ladder.

    Closes the PATH B deferral declared in
    ``research/systemic_risk/null_models.py``: this is the
    promised executable orchestrator. It is a thin wrapper over
    :func:`run_adversarial_ladder` that pins each null surrogate to
    rung 2.

    The six canonical null surrogates the caller is expected to
    pre-compute and supply (in any order):

    1. ``shuffled_time_labels``        — score, score-replacing
    2. ``random_exposure_weights``     — score derived from
                                          weight-shuffled topology
    3. ``static_topology_baseline``    — score from time-mean adj
    4. ``linear_correlation_surrogate`` — score, non-Kuramoto
    5. ``permuted_crisis_dates``       — score unchanged but
                                          ledger swapped — engage
                                          via a separate ladder run
                                          on the permuted ledger
    6. ``degree_preserving_randomization`` — score from rewired adj

    Inputs and outputs of each surrogate stay the responsibility
    of the caller; this function does not invent them. It simply
    raises every supplied surrogate to rung-2 and applies the
    paired-bootstrap delta verdict.

    Parameters
    ----------
    candidate_score
        Length-T 1-D candidate score series.
    null_scores
        Tuple of ``(name, score_series)`` pairs. Names should map
        to the six surrogate identifiers above; the function does
        NOT enforce the six-name set, so a partial audit on any
        subset is allowed (the report's ``untested_rungs`` will
        document the remaining ladder rungs as usual).
    dates, ledger, config, country_filter
        Same semantics as :func:`run_adversarial_ladder`.
    """
    prosecutors = tuple(
        ProsecutorScore(name=name, rung=2, score=np.asarray(score, dtype=np.float64))
        for name, score in null_scores
    )
    return run_adversarial_ladder(
        candidate_score,
        dates,
        ledger,
        prosecutors=prosecutors,
        config=config,
        country_filter=country_filter,
    )


# Suppress unused-symbol warnings — these are part of the public API.
_ = (auc_bootstrap_ci, auc_mann_whitney)
