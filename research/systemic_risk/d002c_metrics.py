# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C — Metric estimators on a Kuramoto trajectory.

Three observables computed on a :class:`KuramotoTrajectory` produced
upstream (by the C2.4 Kuramoto integrator over a
:class:`SubstrateRealization`):

  * :class:`TauOnsetMetric` — first crossing time of ``R(t) > θ`` in
    the pre-event window. Right-censored if no crossing in window.
  * :class:`AucPreEventMetric` — trapezoidal integral of ``R(t)``
    over the pre-event window. Always observed.
  * :class:`DeltaPhiSyncMetric` — first crossing time of pointwise
    phase coherence relative to a reference (substrate principal
    eigenvector by default). Right-censored if no crossing.

Right-censoring discipline
==========================
``tau_onset`` and ``phase_lag`` are time-to-event observables. If a
realisation never crosses the threshold inside the window, the
observation is right-censored at the window horizon — NOT silently
treated as ``horizon`` itself. The :func:`signal_mean` aggregator
uses the Kaplan-Meier product-limit estimator's *restricted mean
survival time*

    RMST = ∫₀^τ S(t) dt

over the window, with full censoring accounting per cohort. The
returned :class:`SignalEstimate` carries the censoring fraction
explicitly so a sweep cell with non-comparable censoring (e.g.
precursor 0% censored, null 80% censored) is visibly flagged
rather than producing a biased difference of observed means.

Strict scope
============
Pure estimators. NO Kuramoto integration. NO claim layer. NO
threshold tuning — the threshold defaults come from the locked
D-002C pre-registration; a sweep config that disagrees is caught
upstream by :func:`d002c_preregistration.validate_sweep_config`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final, Protocol

import numpy as np
from numpy.typing import NDArray

from .d002c_substrates import (
    EVENT_QUARTER,
    PRE_EVENT_START_QUARTER,
    T_HORIZON,
)

# ---------------------------------------------------------------------------
# Locked threshold defaults — read from the D-002C pre-registration YAML.
# A driver that needs to override must do so via the prereg path.
# ---------------------------------------------------------------------------
DEFAULT_TAU_ONSET_THRESHOLD_R: Final[float] = 0.50  # YAML: tau_onset.threshold_R
DEFAULT_PHASE_LAG_THRESHOLD: Final[float] = 0.50  # YAML: phase_lag


class MetricInvalid(RuntimeError):
    """Trajectory does not satisfy the metric's input contract."""


@dataclass(frozen=True)
class KuramotoTrajectory:
    """One realisation of a Kuramoto integration.

    ``R`` is the Kuramoto order parameter ``|⟨exp(i θ_j)⟩|``
    sampled at every integration step. ``theta`` is the full
    per-node phase trajectory; required for ``phase_lag`` and
    optional for the other metrics.

    ``steps_per_quarter`` is the integrator step count per quarter
    so the metric layer can map quarter-level windows to step
    indices without re-discovering the integration grid.
    """

    R: NDArray[np.float64]  # shape (T_steps,)
    theta: NDArray[np.float64] | None  # shape (T_steps, N) or None
    steps_per_quarter: int
    horizon_quarters: int = T_HORIZON

    def __post_init__(self) -> None:
        if self.R.ndim != 1:
            raise MetricInvalid(f"R must be 1-D; got shape {self.R.shape}")
        if not np.all(np.isfinite(self.R)):
            raise MetricInvalid("R contains non-finite values")
        if np.any(self.R < -1e-9) or np.any(self.R > 1.0 + 1e-9):
            raise MetricInvalid(
                f"R must lie in [0, 1]; got min={self.R.min():.4e} max={self.R.max():.4e}"
            )
        if self.steps_per_quarter < 1:
            raise MetricInvalid(f"steps_per_quarter must be >= 1; got {self.steps_per_quarter}")
        expected_steps = self.horizon_quarters * self.steps_per_quarter
        if self.R.shape[0] != expected_steps:
            raise MetricInvalid(
                f"R length {self.R.shape[0]} != "
                f"horizon_quarters * steps_per_quarter = {expected_steps}"
            )
        if self.theta is not None:
            if self.theta.ndim != 2 or self.theta.shape[0] != self.R.shape[0]:
                raise MetricInvalid(
                    f"theta must be 2-D with first axis == len(R); got {self.theta.shape}"
                )
            if not np.all(np.isfinite(self.theta)):
                raise MetricInvalid("theta contains non-finite values")

    @property
    def pre_event_slice(self) -> slice:
        """Step-index slice of the pre-event window [PRE_EVENT_START, EVENT)."""
        spq = self.steps_per_quarter
        return slice(PRE_EVENT_START_QUARTER * spq, EVENT_QUARTER * spq)


@dataclass(frozen=True)
class MetricEvaluation:
    """Single-realisation metric output."""

    metric_id: str
    value: float
    is_censored: bool
    detail: dict[str, float] = field(default_factory=dict)


class Metric(Protocol):
    """Protocol for metric estimators."""

    @property
    def id(self) -> str: ...

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation: ...


# ---------------------------------------------------------------------------
# M1: tau_onset
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TauOnsetMetric:
    """First time R(t) crosses ``threshold_R`` in the pre-event window.

    Returns:
      * value = first crossing step index relative to window start
      * is_censored = True if R never crosses in window
      * detail.R_max_in_window, detail.window_steps
    """

    threshold_R: float = DEFAULT_TAU_ONSET_THRESHOLD_R

    @property
    def id(self) -> str:
        return "tau_onset"

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation:
        sl = trajectory.pre_event_slice
        R_win = trajectory.R[sl]
        window_steps = R_win.shape[0]
        crossings = np.flatnonzero(R_win > self.threshold_R)
        if crossings.size == 0:
            value = float(window_steps)
            censored = True
        else:
            value = float(crossings[0])
            censored = False
        return MetricEvaluation(
            metric_id=self.id,
            value=value,
            is_censored=censored,
            detail={
                "R_max_in_window": float(R_win.max()),
                "window_steps": float(window_steps),
                "threshold_R": float(self.threshold_R),
            },
        )


# ---------------------------------------------------------------------------
# M2: auc_pre_event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AucPreEventMetric:
    """Trapezoidal AUC of R(t) over the pre-event window. Always observed."""

    @property
    def id(self) -> str:
        return "sync_auc"

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation:
        sl = trajectory.pre_event_slice
        R_win = trajectory.R[sl]
        # Uniform step grid; dt = 1 step
        auc = float(np.trapezoid(R_win, dx=1.0))
        return MetricEvaluation(
            metric_id=self.id,
            value=auc,
            is_censored=False,
            detail={
                "R_max_in_window": float(R_win.max()),
                "R_mean_in_window": float(R_win.mean()),
                "window_steps": float(R_win.shape[0]),
            },
        )


# ---------------------------------------------------------------------------
# M3: delta_phi_sync (phase_lag) — pointwise phase coherence to a reference
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeltaPhiSyncMetric:
    """First time the pointwise phase coherence

        Φ(t) = | (1/N) Σ_j w_j · exp(i θ_j(t)) |

    crosses ``threshold_phi`` in the pre-event window. The reference
    weight vector ``w`` defaults to uniform (which collapses to the
    standard Kuramoto order parameter R(t)); the sweep runner passes
    the substrate principal eigenvector to project on a structurally
    motivated direction.
    """

    threshold_phi: float = DEFAULT_PHASE_LAG_THRESHOLD
    reference_weights: NDArray[np.float64] | None = None

    @property
    def id(self) -> str:
        return "phase_lag"

    def evaluate(self, trajectory: KuramotoTrajectory) -> MetricEvaluation:
        if trajectory.theta is None:
            raise MetricInvalid("phase_lag requires per-node phases (theta)")
        theta = trajectory.theta
        N = theta.shape[1]
        if self.reference_weights is None:
            w = np.full(N, 1.0 / float(N), dtype=np.float64)
        else:
            w = np.asarray(self.reference_weights, dtype=np.float64)
            if w.shape != (N,):
                raise MetricInvalid(f"reference_weights must have shape ({N},); got {w.shape}")
            wnorm = float(np.linalg.norm(w, ord=1))
            if not np.isfinite(wnorm) or wnorm == 0.0:
                raise MetricInvalid("reference_weights must be finite and sum to nonzero L1")
            w = w / wnorm
        # Φ(t) = | Σ_j w_j exp(i θ_j(t)) |
        proj = np.exp(1j * theta) @ w
        phi = np.abs(proj)
        sl = trajectory.pre_event_slice
        phi_win = phi[sl]
        window_steps = phi_win.shape[0]
        crossings = np.flatnonzero(phi_win > self.threshold_phi)
        if crossings.size == 0:
            value = float(window_steps)
            censored = True
        else:
            value = float(crossings[0])
            censored = False
        return MetricEvaluation(
            metric_id=self.id,
            value=value,
            is_censored=censored,
            detail={
                "phi_max_in_window": float(phi_win.max()),
                "window_steps": float(window_steps),
                "threshold_phi": float(self.threshold_phi),
            },
        )


# ---------------------------------------------------------------------------
# Cohort-level signal aggregation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalEstimate:
    """Cohort-level signal: mean(precursor) - mean(null) of the metric.

    For right-censored metrics the means are *restricted-mean survival
    times* from a Kaplan-Meier product-limit estimator over the
    pre-event window. Censoring fractions are reported per cohort
    so a downstream consumer can flag non-comparable cells (e.g.
    precursor 0% censored vs null 80% censored — the comparison
    of observed means would be biased).
    """

    metric_id: str
    signal_mean: float
    mean_precursor: float
    mean_null: float
    censoring_fraction_precursor: float
    censoring_fraction_null: float
    n_precursor: int
    n_null: int
    method: str  # "observed_mean" | "km_restricted_mean"


def kaplan_meier_restricted_mean(
    times: NDArray[np.float64],
    censored: NDArray[np.bool_],
    horizon: float,
) -> float:
    """Kaplan-Meier restricted mean survival time over [0, horizon].

    Product-limit estimator (Kaplan-Meier 1958):

        S(t) = ∏_{t_i ≤ t, observed} (1 - d_i / n_i)

    where ``d_i`` is the count of *observed* events at distinct event
    time ``t_i`` and ``n_i`` is the at-risk count just before ``t_i``.
    The restricted mean is

        RMST(τ) = ∫₀^τ S(t) dt

    discretised over the sorted event times.

    Convention: an "event" here is a threshold *crossing* (R > θ).
    ``censored=True`` means no crossing observed within ``[0, horizon)``;
    such a realisation does NOT contribute an event time, only to the
    at-risk denominator.
    """
    times = np.asarray(times, dtype=np.float64)
    censored = np.asarray(censored, dtype=bool)
    if times.shape != censored.shape:
        raise ValueError(f"times {times.shape} and censored {censored.shape} shape mismatch")
    if times.size == 0:
        raise ValueError("kaplan_meier_restricted_mean: empty cohort")
    if horizon <= 0.0:
        raise ValueError(f"horizon must be > 0; got {horizon}")
    if np.any(~np.isfinite(times)) or np.any(times < 0.0):
        raise ValueError("times must be finite and >= 0")
    # Clip event times to the horizon (no events beyond the window are
    # observable by construction)
    t_clip = np.minimum(times, horizon)
    # Sort by event time
    order = np.argsort(t_clip, kind="stable")
    t_sorted = t_clip[order]
    c_sorted = censored[order]
    n_total = t_sorted.size
    # Sweep
    S = 1.0
    rmst = 0.0
    prev_t = 0.0
    i = 0
    while i < n_total:
        t_i = float(t_sorted[i])
        # contribution to RMST up to t_i at the current S level
        rmst += S * (t_i - prev_t)
        # find tied block
        j = i
        d_i = 0  # observed events at t_i
        while j < n_total and t_sorted[j] == t_i:
            if not c_sorted[j]:
                d_i += 1
            j += 1
        n_i = n_total - i  # at-risk count just before t_i
        if d_i > 0 and n_i > 0:
            S *= 1.0 - d_i / float(n_i)
        prev_t = t_i
        i = j
    # tail from prev_t to horizon (only contributes if some realisations
    # extended past the last event time — their censoring keeps S > 0)
    rmst += S * (horizon - prev_t)
    return float(rmst)


def signal_mean(
    metric: Metric,
    evaluations_precursor: list[MetricEvaluation],
    evaluations_null: list[MetricEvaluation],
    *,
    horizon: float,
) -> SignalEstimate:
    """Aggregate per-realisation evaluations into a cohort signal.

    Right-censored metrics (``tau_onset``, ``phase_lag``) use
    Kaplan-Meier RMST. Non-censored metrics (``sync_auc``) use the
    simple cohort mean.
    """
    if not evaluations_precursor:
        raise ValueError("signal_mean: empty precursor cohort")
    if not evaluations_null:
        raise ValueError("signal_mean: empty null cohort")

    def _cohort(evals: list[MetricEvaluation]) -> tuple[float, float, str]:
        any_censored = any(e.is_censored for e in evals)
        if any_censored:
            times = np.array([e.value for e in evals], dtype=np.float64)
            censored = np.array([e.is_censored for e in evals], dtype=bool)
            return (
                kaplan_meier_restricted_mean(times, censored, horizon=horizon),
                float(np.mean(censored)),
                "km_restricted_mean",
            )
        values = np.array([e.value for e in evals], dtype=np.float64)
        return float(values.mean()), 0.0, "observed_mean"

    mu_p, c_p, method_p = _cohort(evaluations_precursor)
    mu_n, c_n, method_n = _cohort(evaluations_null)
    # If one cohort is censored and the other isn't, the comparable
    # method is still km_restricted_mean — fall back to that for both.
    method = (
        "km_restricted_mean" if "km_restricted_mean" in (method_p, method_n) else "observed_mean"
    )
    return SignalEstimate(
        metric_id=metric.id,
        signal_mean=mu_p - mu_n,
        mean_precursor=mu_p,
        mean_null=mu_n,
        censoring_fraction_precursor=c_p,
        censoring_fraction_null=c_n,
        n_precursor=len(evaluations_precursor),
        n_null=len(evaluations_null),
        method=method,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


ALL_METRICS: Final[tuple[Metric, ...]] = (
    TauOnsetMetric(),
    AucPreEventMetric(),
    DeltaPhiSyncMetric(),
)

METRIC_BY_ID: Final[dict[str, Metric]] = {m.id: m for m in ALL_METRICS}


__all__ = [
    "DEFAULT_TAU_ONSET_THRESHOLD_R",
    "DEFAULT_PHASE_LAG_THRESHOLD",
    "MetricInvalid",
    "KuramotoTrajectory",
    "MetricEvaluation",
    "Metric",
    "TauOnsetMetric",
    "AucPreEventMetric",
    "DeltaPhiSyncMetric",
    "SignalEstimate",
    "kaplan_meier_restricted_mean",
    "signal_mean",
    "ALL_METRICS",
    "METRIC_BY_ID",
]
