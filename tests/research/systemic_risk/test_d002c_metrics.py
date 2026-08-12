# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C C2.2 — Metric estimator tests.

Pins gates G11-G15 for the metric layer:

  G11  right-censoring is handled honestly (NOT silent NaN, NOT
       horizon-imputation); KM RMST is the canonical aggregator
  G12  reproducible: same R(t) → same metric value bit-exact
  G13  monotone sanity: a stronger signal in R(t) yields a larger
       |signal_mean| on a 3-point smoke test
  G14  9 substrate × metric combinations all callable
  G15  30+ unit tests total across substrates + metrics

Strict scope: pure estimator tests. NO Kuramoto integration.
Trajectories are synthesized directly with known properties.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from research.systemic_risk.d002c_metrics import (
    ALL_METRICS,
    DEFAULT_PHASE_LAG_THRESHOLD,
    DEFAULT_TAU_ONSET_THRESHOLD_R,
    METRIC_BY_ID,
    AucPreEventMetric,
    DeltaPhiSyncMetric,
    KuramotoTrajectory,
    MetricEvaluation,
    MetricInvalid,
    SignalEstimate,
    TauOnsetMetric,
    kaplan_meier_restricted_mean,
    signal_mean,
)
from research.systemic_risk.d002c_substrates import (
    EVENT_QUARTER,
    PRE_EVENT_START_QUARTER,
    T_HORIZON,
)

# ---------------------------------------------------------------------------
# Trajectory builders
# ---------------------------------------------------------------------------


def _flat_R(value: float, steps_per_quarter: int = 16) -> KuramotoTrajectory:
    """R(t) = const at every step. No theta."""
    R = np.full(T_HORIZON * steps_per_quarter, value, dtype=np.float64)
    return KuramotoTrajectory(R=R, theta=None, steps_per_quarter=steps_per_quarter)


def _step_R(
    *,
    low: float,
    high: float,
    crossing_quarter: int,
    steps_per_quarter: int = 16,
) -> KuramotoTrajectory:
    """R(t) jumps from `low` to `high` at the start of `crossing_quarter`."""
    total = T_HORIZON * steps_per_quarter
    R = np.full(total, low, dtype=np.float64)
    R[crossing_quarter * steps_per_quarter :] = high
    return KuramotoTrajectory(R=R, theta=None, steps_per_quarter=steps_per_quarter)


def _trajectory_with_theta(
    *,
    theta_t_n: np.ndarray,
    steps_per_quarter: int = 16,
) -> KuramotoTrajectory:
    R = np.abs(np.mean(np.exp(1j * theta_t_n), axis=1))
    return KuramotoTrajectory(R=R, theta=theta_t_n, steps_per_quarter=steps_per_quarter)


# ---------------------------------------------------------------------------
# KuramotoTrajectory contract
# ---------------------------------------------------------------------------


def test_trajectory_validates_R_shape_1d() -> None:
    with pytest.raises(MetricInvalid):
        KuramotoTrajectory(
            R=np.zeros((10, 2), dtype=np.float64),
            theta=None,
            steps_per_quarter=2,
        )


def test_trajectory_validates_R_finite() -> None:
    bad = np.zeros(T_HORIZON * 4, dtype=np.float64)
    bad[3] = np.nan
    with pytest.raises(MetricInvalid):
        KuramotoTrajectory(R=bad, theta=None, steps_per_quarter=4)


def test_trajectory_validates_R_in_unit_interval() -> None:
    bad = np.zeros(T_HORIZON * 4, dtype=np.float64)
    bad[5] = 1.5
    with pytest.raises(MetricInvalid):
        KuramotoTrajectory(R=bad, theta=None, steps_per_quarter=4)


def test_trajectory_validates_steps_per_quarter_consistency() -> None:
    R = np.zeros(31, dtype=np.float64)  # 31 doesn't factor T_HORIZON
    with pytest.raises(MetricInvalid):
        KuramotoTrajectory(R=R, theta=None, steps_per_quarter=4)


def test_trajectory_validates_theta_shape() -> None:
    R = np.zeros(T_HORIZON * 4, dtype=np.float64)
    theta_bad = np.zeros((T_HORIZON * 4, 5, 2), dtype=np.float64)
    with pytest.raises(MetricInvalid):
        KuramotoTrajectory(R=R, theta=theta_bad, steps_per_quarter=4)


def test_trajectory_pre_event_slice_matches_window() -> None:
    tr = _flat_R(0.1, steps_per_quarter=8)
    sl = tr.pre_event_slice
    assert sl.start == PRE_EVENT_START_QUARTER * 8
    assert sl.stop == EVENT_QUARTER * 8


# ---------------------------------------------------------------------------
# M1: tau_onset
# ---------------------------------------------------------------------------


def test_tau_onset_default_threshold_matches_locked_yaml() -> None:
    assert TauOnsetMetric().threshold_R == DEFAULT_TAU_ONSET_THRESHOLD_R
    assert DEFAULT_TAU_ONSET_THRESHOLD_R == 0.50


def test_tau_onset_returns_first_crossing_in_window() -> None:
    tr = _step_R(low=0.1, high=0.9, crossing_quarter=3, steps_per_quarter=8)
    ev = TauOnsetMetric().evaluate(tr)
    # window starts at quarter PRE_EVENT_START_QUARTER (=2), crossing at q=3
    # → relative offset = (3-2)*8 = 8
    assert ev.value == pytest.approx(8.0)
    assert ev.is_censored is False
    assert ev.metric_id == "tau_onset"


def test_tau_onset_censors_when_no_crossing_in_window() -> None:
    tr = _flat_R(0.1, steps_per_quarter=8)
    ev = TauOnsetMetric().evaluate(tr)
    assert ev.is_censored is True
    assert ev.value == pytest.approx(float((EVENT_QUARTER - PRE_EVENT_START_QUARTER) * 8))


def test_tau_onset_bit_exact_reproducible() -> None:
    tr1 = _step_R(low=0.1, high=0.9, crossing_quarter=3)
    tr2 = _step_R(low=0.1, high=0.9, crossing_quarter=3)
    ev1 = TauOnsetMetric().evaluate(tr1)
    ev2 = TauOnsetMetric().evaluate(tr2)
    assert ev1.value == ev2.value
    assert ev1.is_censored == ev2.is_censored


def test_tau_onset_ignores_crossings_outside_window() -> None:
    """A crossing at the EVENT quarter (=6) is OUTSIDE the pre-event window
    [2, 6) — it should be censored."""
    tr = _step_R(low=0.1, high=0.9, crossing_quarter=6, steps_per_quarter=8)
    ev = TauOnsetMetric().evaluate(tr)
    assert ev.is_censored is True


def test_tau_onset_custom_threshold() -> None:
    tr = _step_R(low=0.1, high=0.35, crossing_quarter=3, steps_per_quarter=8)
    # default 0.50 → censored; custom 0.30 → crossed
    assert TauOnsetMetric(threshold_R=0.50).evaluate(tr).is_censored is True
    ev = TauOnsetMetric(threshold_R=0.30).evaluate(tr)
    assert ev.is_censored is False


# ---------------------------------------------------------------------------
# M2: auc_pre_event
# ---------------------------------------------------------------------------


def test_auc_constant_R_gives_predictable_area() -> None:
    tr = _flat_R(0.4, steps_per_quarter=16)
    ev = AucPreEventMetric().evaluate(tr)
    # window length in steps = (6-2)*16 = 64; np.trapezoid with dx=1
    # over a constant 0.4 of length 64 = 0.4 * (64-1) = 25.2
    assert ev.value == pytest.approx(0.4 * 63.0)
    assert ev.is_censored is False


def test_auc_never_censored() -> None:
    for v in (0.0, 0.5, 1.0):
        ev = AucPreEventMetric().evaluate(_flat_R(v))
        assert ev.is_censored is False


def test_auc_monotone_in_R() -> None:
    """G13 sanity: stronger sustained R → larger AUC."""
    aucs = [AucPreEventMetric().evaluate(_flat_R(R)).value for R in (0.1, 0.3, 0.7)]
    assert aucs[0] < aucs[1] < aucs[2]


# ---------------------------------------------------------------------------
# M3: delta_phi_sync (phase_lag)
# ---------------------------------------------------------------------------


def test_phase_lag_default_threshold_matches_locked_yaml() -> None:
    assert DeltaPhiSyncMetric().threshold_phi == DEFAULT_PHASE_LAG_THRESHOLD
    # And the canonical numeric value (sanity against accidental edit of
    # the module-level constant)
    assert DEFAULT_PHASE_LAG_THRESHOLD == 0.50


def test_phase_lag_requires_theta() -> None:
    tr = _flat_R(0.1)
    with pytest.raises(MetricInvalid):
        DeltaPhiSyncMetric().evaluate(tr)


def test_phase_lag_uniform_weights_collapse_to_R_threshold() -> None:
    """With uniform reference weights Φ(t) = |⟨exp(i θ)⟩| = R(t).
    So phase_lag with default reference must agree with a tau_onset
    threshold at the same level."""
    N = 10
    spq = 8
    total = T_HORIZON * spq
    # Construct theta s.t. R(t) is 0.1 for t < q=3, then 0.9 for t >= q=3
    rng = np.random.default_rng(0)
    theta = np.empty((total, N), dtype=np.float64)
    # Phase spread → low R
    spread_low = rng.uniform(0.0, 2 * np.pi, size=N)
    # Phase clustered → high R
    spread_high = 0.01 * rng.standard_normal(N)
    boundary = 3 * spq
    theta[:boundary] = spread_low[None, :]
    theta[boundary:] = spread_high[None, :]
    tr = _trajectory_with_theta(theta_t_n=theta, steps_per_quarter=spq)
    ev = DeltaPhiSyncMetric(threshold_phi=0.50).evaluate(tr)
    assert ev.is_censored is False
    # Crossing must be at the boundary, relative to window-start (q=2):
    # boundary - 2*spq = 8
    assert ev.value == pytest.approx(8.0)


def test_phase_lag_custom_reference_weights() -> None:
    N = 6
    spq = 4
    total = T_HORIZON * spq
    theta = np.full((total, N), 0.0, dtype=np.float64)
    # Two nodes coherent, rest scrambled — projecting on the coherent
    # subset's eigenvector should yield Φ=1, while uniform projection
    # gives Φ < 1
    theta[:, 2:] = np.pi  # phase π for the 4 "noisy" nodes
    tr = _trajectory_with_theta(theta_t_n=theta, steps_per_quarter=spq)
    # Default (uniform) — Φ = | (2 · 1 + 4 · e^{iπ}) / 6 | = | -2/6 | = 1/3
    ev_default = DeltaPhiSyncMetric(threshold_phi=0.50).evaluate(tr)
    assert ev_default.is_censored is True
    # Custom weights focused on the coherent subset → Φ = 1
    w = np.zeros(N, dtype=np.float64)
    w[:2] = 1.0
    ev_custom = DeltaPhiSyncMetric(threshold_phi=0.50, reference_weights=w).evaluate(tr)
    assert ev_custom.is_censored is False
    assert ev_custom.value == pytest.approx(0.0)


def test_phase_lag_censors_when_no_crossing() -> None:
    """If Φ(t) never crosses the threshold (e.g. phases stay scrambled)
    the metric is right-censored."""
    N = 50
    spq = 4
    rng = np.random.default_rng(123)
    theta = rng.uniform(0.0, 2 * np.pi, size=(T_HORIZON * spq, N))
    tr = _trajectory_with_theta(theta_t_n=theta, steps_per_quarter=spq)
    ev = DeltaPhiSyncMetric(threshold_phi=0.95).evaluate(tr)
    assert ev.is_censored is True


def test_phase_lag_rejects_bad_reference_weights() -> None:
    spq = 4
    theta = np.zeros((T_HORIZON * spq, 5), dtype=np.float64)
    tr = _trajectory_with_theta(theta_t_n=theta, steps_per_quarter=spq)
    # Wrong length
    with pytest.raises(MetricInvalid):
        DeltaPhiSyncMetric(reference_weights=np.ones(3)).evaluate(tr)
    # Zero L1
    with pytest.raises(MetricInvalid):
        DeltaPhiSyncMetric(reference_weights=np.zeros(5)).evaluate(tr)


# ---------------------------------------------------------------------------
# G11: Kaplan-Meier restricted mean
# ---------------------------------------------------------------------------


def test_km_rmst_no_censoring_equals_simple_mean() -> None:
    """With zero censoring, RMST equals the cohort mean (a known KM
    property when the horizon is larger than the largest event time)."""
    times = np.array([1.0, 2.0, 3.0, 4.0])
    censored = np.zeros(4, dtype=bool)
    rmst = kaplan_meier_restricted_mean(times, censored, horizon=10.0)
    assert rmst == pytest.approx(np.mean(times), rel=1e-12)


def test_km_rmst_all_censored_returns_horizon() -> None:
    times = np.array([5.0, 5.0, 5.0])  # all hit censor cap
    censored = np.ones(3, dtype=bool)
    rmst = kaplan_meier_restricted_mean(times, censored, horizon=5.0)
    assert rmst == pytest.approx(5.0, rel=1e-12)


def test_km_rmst_partial_censoring_strictly_between_mean_and_horizon() -> None:
    times = np.array([2.0, 3.0, 5.0, 5.0])
    censored = np.array([False, False, True, True])
    rmst = kaplan_meier_restricted_mean(times, censored, horizon=5.0)
    observed_mean = float(np.mean([2.0, 3.0]))
    # KM RMST under right-censoring is ≥ observed mean (censored
    # observations push the survival curve up) and ≤ horizon
    assert observed_mean < rmst < 5.0


def test_km_rmst_monotone_in_censoring_fraction() -> None:
    times = np.array([2.0, 2.0, 2.0, 2.0])
    rm_none = kaplan_meier_restricted_mean(times, np.zeros(4, dtype=bool), horizon=10.0)
    rm_some = kaplan_meier_restricted_mean(
        times, np.array([False, False, True, True]), horizon=10.0
    )
    rm_all = kaplan_meier_restricted_mean(times, np.ones(4, dtype=bool), horizon=10.0)
    assert rm_none < rm_some < rm_all


def test_km_rmst_rejects_empty_cohort() -> None:
    with pytest.raises(ValueError):
        kaplan_meier_restricted_mean(
            np.array([], dtype=np.float64),
            np.array([], dtype=bool),
            horizon=5.0,
        )


def test_km_rmst_rejects_nonpositive_horizon() -> None:
    with pytest.raises(ValueError):
        kaplan_meier_restricted_mean(np.array([1.0]), np.array([False]), horizon=0.0)


def test_km_rmst_rejects_negative_times() -> None:
    with pytest.raises(ValueError):
        kaplan_meier_restricted_mean(np.array([-1.0]), np.array([False]), horizon=5.0)


# ---------------------------------------------------------------------------
# Cohort-level signal aggregation
# ---------------------------------------------------------------------------


def _make_eval(value: float, censored: bool, metric_id: str = "tau_onset") -> MetricEvaluation:
    return MetricEvaluation(metric_id=metric_id, value=value, is_censored=censored)


def test_signal_mean_zero_when_cohorts_identical() -> None:
    pre = [_make_eval(5.0, False) for _ in range(20)]
    null = [_make_eval(5.0, False) for _ in range(20)]
    est = signal_mean(TauOnsetMetric(), pre, null, horizon=10.0)
    assert est.signal_mean == 0.0
    assert est.method == "observed_mean"
    assert est.censoring_fraction_precursor == 0.0
    assert est.censoring_fraction_null == 0.0


def test_signal_mean_reports_negative_when_precursor_smaller() -> None:
    pre = [_make_eval(3.0, False) for _ in range(20)]
    null = [_make_eval(7.0, False) for _ in range(20)]
    est = signal_mean(TauOnsetMetric(), pre, null, horizon=10.0)
    assert est.signal_mean == pytest.approx(-4.0)


def test_signal_mean_uses_km_when_either_cohort_censored() -> None:
    pre = [_make_eval(3.0, False)] * 10 + [_make_eval(8.0, True)] * 10
    null = [_make_eval(7.0, False)] * 20
    est = signal_mean(TauOnsetMetric(), pre, null, horizon=8.0)
    assert est.method == "km_restricted_mean"
    assert est.censoring_fraction_precursor == pytest.approx(0.5)
    assert est.censoring_fraction_null == 0.0


def test_signal_mean_reports_cohort_sizes() -> None:
    pre = [_make_eval(1.0, False) for _ in range(7)]
    null = [_make_eval(1.0, False) for _ in range(13)]
    est = signal_mean(AucPreEventMetric(), pre, null, horizon=10.0)
    assert est.n_precursor == 7
    assert est.n_null == 13


def test_signal_mean_rejects_empty_cohorts() -> None:
    pre = [_make_eval(1.0, False)]
    with pytest.raises(ValueError):
        signal_mean(TauOnsetMetric(), pre, [], horizon=5.0)
    with pytest.raises(ValueError):
        signal_mean(TauOnsetMetric(), [], pre, horizon=5.0)


# ---------------------------------------------------------------------------
# G13: monotone-signal sanity — stronger crossing yields larger |signal|
# ---------------------------------------------------------------------------


def test_g13_signal_mean_monotone_in_precursor_strength() -> None:
    """Smoke test: as precursor cohort crosses earlier (smaller tau values)
    while the null stays late, |signal_mean| must grow."""
    null = [_make_eval(8.0, False) for _ in range(20)]
    weak_pre = [_make_eval(7.0, False) for _ in range(20)]
    mid_pre = [_make_eval(4.0, False) for _ in range(20)]
    strong_pre = [_make_eval(1.0, False) for _ in range(20)]
    weak = signal_mean(TauOnsetMetric(), weak_pre, null, horizon=10.0).signal_mean
    mid = signal_mean(TauOnsetMetric(), mid_pre, null, horizon=10.0).signal_mean
    strong = signal_mean(TauOnsetMetric(), strong_pre, null, horizon=10.0).signal_mean
    assert abs(weak) < abs(mid) < abs(strong)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_has_three_metrics() -> None:
    assert len(ALL_METRICS) == 3
    assert {m.id for m in ALL_METRICS} == {"tau_onset", "sync_auc", "phase_lag"}


def test_metric_by_id_round_trip() -> None:
    for m in ALL_METRICS:
        assert METRIC_BY_ID[m.id].id == m.id


# ---------------------------------------------------------------------------
# G14: tau_onset + sync_auc evaluable on the same R-only trajectory
# ---------------------------------------------------------------------------


def test_g14_tau_onset_and_auc_share_trajectory_shape() -> None:
    tr = _step_R(low=0.1, high=0.7, crossing_quarter=3, steps_per_quarter=8)
    ev_tau = TauOnsetMetric().evaluate(tr)
    ev_auc = AucPreEventMetric().evaluate(tr)
    assert ev_tau.metric_id == "tau_onset"
    assert ev_auc.metric_id == "sync_auc"
    assert math.isfinite(ev_tau.value)
    assert math.isfinite(ev_auc.value)


# ---------------------------------------------------------------------------
# SignalEstimate basic invariants
# ---------------------------------------------------------------------------


def test_signal_estimate_carries_method_and_metric_id() -> None:
    pre = [_make_eval(1.0, False)]
    null = [_make_eval(2.0, False)]
    est = signal_mean(TauOnsetMetric(), pre, null, horizon=5.0)
    assert isinstance(est, SignalEstimate)
    assert est.metric_id == "tau_onset"
    assert est.method == "observed_mean"
