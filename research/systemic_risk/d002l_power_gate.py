"""D-002L-P2 pre-outcome statistical power gate.

This module is intentionally confirmatory-outcome blind. It consumes:
1. a source-complete D002L-P1 Treasury exposure registry;
2. a P1 execution status that must be TERMINAL_PASS for scientific execution;
3. calibration-only residual noise metadata; and
4. an external literature effect-prior artifact.

The P2 design-rank check uses only pre-outcome/exogenous regressors. The locked
lagged-spread control is unavailable until P3 outcome ingestion and MUST be
rechecked in the full P4 design. P2 never loads confirmatory TGCR/IOER/IORB.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
from scipy.stats import nct, t

SCHEMA_VERSION = "D002L-P2-POWER-GATE-v1"
CALIBRATION_END = date(2018, 12, 31)
CONFIRMATORY_START = date(2019, 1, 1)
CONFIRMATORY_END = date(2026, 8, 20)
TARGET_POWER = 0.80
ALPHA = 0.05
MIN_EFFECTIVE_CLUSTERS = 20


class D002LPowerError(ValueError):
    """Fail-closed D-002L-P2 power-gate error."""


@dataclass(frozen=True)
class PowerPoint:
    n: int
    rank: int
    df: int
    clusters: int
    residualized_x_ss: float
    standard_error_beta: float
    noncentrality: float
    power: float


def _load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise D002LPowerError(f"INVALID_JSON_ARTIFACT:{path}:{exc}") from exc
    if not isinstance(obj, dict):
        raise D002LPowerError(f"JSON_ARTIFACT_NOT_OBJECT:{path}")
    return obj


def validate_p1_status_authority(status: Mapping[str, Any]) -> None:
    """Reject P2 before reading downstream artifacts unless P1 itself is authoritative."""
    if status.get("node_id") != "D002L-P1":
        raise D002LPowerError("P1_STATUS_WRONG_NODE")
    if status.get("status") != "TERMINAL_PASS":
        raise D002LPowerError("P1_NOT_TERMINAL_PASS")
    if status.get("decision") != "D002L_EXPOSURE_REGISTRY_SOURCE_COMPLETE":
        raise D002LPowerError("P1_WRONG_DECISION")
    if status.get("lineage_advance_allowed") is not True:
        raise D002LPowerError("P1_LINEAGE_ADVANCE_NOT_AUTHORIZED")
    if status.get("source_authenticity_for_lineage_advance") is not True:
        raise D002LPowerError("P1_SOURCE_AUTHENTICITY_NOT_ESTABLISHED")
    if status.get("confirmatory_outcomes_ingested") is not False:
        raise D002LPowerError("P1_OUTCOME_FIREWALL_BREACHED")


def validate_p1_registry_authority(registry: Mapping[str, Any]) -> None:
    """Validate the source-complete P1 registry boundary after P1 status passes."""
    if registry.get("node_id") != "D002L-P1":
        raise D002LPowerError("P1_REGISTRY_WRONG_NODE")
    if registry.get("confirmatory_outcomes_ingested") is not False:
        raise D002LPowerError("P1_REGISTRY_OUTCOME_FIREWALL_BREACHED")
    if registry.get("next_phase_authorized") != "D002L-P2":
        raise D002LPowerError("P1_REGISTRY_DOES_NOT_AUTHORIZE_P2")


def validate_p1_authority(status: Mapping[str, Any], registry: Mapping[str, Any]) -> None:
    """P2 is illegal until both P1 status and registry are authoritative."""
    validate_p1_status_authority(status)
    validate_p1_registry_authority(registry)


def validate_calibration_noise(artifact: Mapping[str, Any]) -> float:
    """Accept only calibration-period noise; never confirmatory observations."""
    required = {
        "schema_version",
        "study_id",
        "use",
        "period_start",
        "period_end",
        "sigma_residual_bps",
        "week_cluster_design_effect",
        "confirmatory_observations_used",
    }
    missing = sorted(required - set(artifact))
    if missing:
        raise D002LPowerError(f"CALIBRATION_NOISE_FIELDS_MISSING:{missing}")
    if artifact["study_id"] != "D-002L":
        raise D002LPowerError("CALIBRATION_NOISE_WRONG_STUDY")
    if artifact["use"] != "POWER_ONLY":
        raise D002LPowerError("CALIBRATION_NOISE_WRONG_USE")
    try:
        start = date.fromisoformat(str(artifact["period_start"]))
        end = date.fromisoformat(str(artifact["period_end"]))
        sigma = float(artifact["sigma_residual_bps"])
        design_effect = float(artifact["week_cluster_design_effect"])
    except (TypeError, ValueError) as exc:
        raise D002LPowerError("CALIBRATION_NOISE_INVALID_VALUE") from exc
    if end > CALIBRATION_END:
        raise D002LPowerError("CALIBRATION_NOISE_LEAKS_POST_CALIBRATION_PERIOD")
    if end < start:
        raise D002LPowerError("CALIBRATION_NOISE_PERIOD_REVERSED")
    if artifact["confirmatory_observations_used"] not in (0, False):
        raise D002LPowerError("CONFIRMATORY_OUTCOMES_USED_IN_POWER_NOISE")
    if not math.isfinite(sigma) or sigma <= 0:
        raise D002LPowerError("CALIBRATION_SIGMA_MUST_BE_POSITIVE_FINITE")
    if not math.isfinite(design_effect) or design_effect < 1.0:
        raise D002LPowerError("WEEK_CLUSTER_DESIGN_EFFECT_MUST_BE_FINITE_GE_1")
    return sigma * math.sqrt(design_effect)


def conservative_effect_prior(artifact: Mapping[str, Any]) -> dict[str, Any]:
    """Apply the preregistered 50%-shrink / 95%-CI-bound rule."""
    if artifact.get("study_id") != "D-002L":
        raise D002LPowerError("EFFECT_PRIOR_WRONG_STUDY")
    if artifact.get("source_role") != "EXTERNAL_DESIGN_AND_POWER_PRIOR_ONLY":
        raise D002LPowerError("EFFECT_PRIOR_WRONG_SOURCE_ROLE")
    if artifact.get("confirmatory_outcomes_used") not in (0, False):
        raise D002LPowerError("CONFIRMATORY_OUTCOMES_USED_IN_EFFECT_PRIOR")
    try:
        point = float(artifact["published_point_estimate_bps_per_100bn"])
    except (KeyError, TypeError, ValueError) as exc:
        raise D002LPowerError("EFFECT_PRIOR_POINT_ESTIMATE_INVALID") from exc
    if not math.isfinite(point) or point <= 0:
        raise D002LPowerError("EFFECT_PRIOR_POINT_ESTIMATE_MUST_BE_POSITIVE_FINITE")
    half_point = 0.5 * point

    lower = artifact.get("published_ci95_lower_bps_per_100bn")
    upper = artifact.get("published_ci95_upper_bps_per_100bn")
    if lower is None or upper is None:
        chosen = half_point
        quality = "PARTIAL"
        ci_bound = None
    else:
        try:
            lo = float(lower)
            hi = float(upper)
        except (TypeError, ValueError) as exc:
            raise D002LPowerError("EFFECT_PRIOR_CI_INVALID") from exc
        if not (math.isfinite(lo) and math.isfinite(hi) and lo <= hi):
            raise D002LPowerError("EFFECT_PRIOR_CI_INVALID")
        ci_bound = max(0.0, lo)
        chosen = min(half_point, ci_bound)
        quality = "FULL"
    if chosen <= 0:
        raise D002LPowerError("CONSERVATIVE_EFFECT_PRIOR_COLLAPSES_TO_ZERO")
    return {
        "published_point_estimate_bps_per_100bn": point,
        "half_point_estimate_bps_per_100bn": half_point,
        "ci95_positive_lower_bound_bps_per_100bn": ci_bound,
        "chosen_beta_prior_bps_per_100bn": chosen,
        "prior_quality": quality,
        "rule": "min(0.5*published_point_estimate, positive_95pct_lower_bound_if_available)",
    }


def _is_month_end(d: date) -> float:
    from datetime import timedelta
    return float((d + timedelta(days=1)).month != d.month)


def _is_quarter_end(d: date) -> float:
    return float(_is_month_end(d) and d.month in {3, 6, 9, 12})


def _week_key(d: date) -> tuple[int, int]:
    iso = d.isocalendar()
    return int(iso.year), int(iso.week)


def confirmatory_events(registry: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    events = registry.get("events")
    if not isinstance(events, list):
        raise D002LPowerError("P1_EVENTS_NOT_LIST")
    out: list[Mapping[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            raise D002LPowerError("P1_EVENT_NOT_OBJECT")
        if event.get("partition") != "CONFIRMATORY_RETROSPECTIVE_EXPOSURE_ONLY":
            continue
        if event.get("eligible") is not True:
            continue
        d = date.fromisoformat(str(event["settlement_date"]))
        if not (CONFIRMATORY_START <= d <= CONFIRMATORY_END):
            raise D002LPowerError("CONFIRMATORY_EVENT_DATE_OUTSIDE_LOCKED_PERIOD")
        out.append(event)
    out.sort(key=lambda e: str(e["settlement_date"]))
    if not out:
        raise D002LPowerError("ZERO_ELIGIBLE_CONFIRMATORY_EVENTS_AT_P2")
    return out


def exogenous_design(events: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray, list[date]]:
    """Build pre-outcome design: intercept, x_coupon, b_bill, calendar controls."""
    rows: list[list[float]] = []
    x: list[float] = []
    dates: list[date] = []
    for event in events:
        d = date.fromisoformat(str(event["settlement_date"]))
        try:
            coupon = float(event["x_t_scaled_100bn"])
            bill = float(event["b_t_scaled_100bn"])
        except (KeyError, TypeError, ValueError) as exc:
            raise D002LPowerError("P1_EXPOSURE_VALUE_INVALID") from exc
        if not (math.isfinite(coupon) and math.isfinite(bill)):
            raise D002LPowerError("P1_EXPOSURE_VALUE_NONFINITE")
        dow = d.weekday()
        if dow >= 5:
            raise D002LPowerError("SETTLEMENT_DATE_ON_WEEKEND")
        dummies = [float(dow == k) for k in (1, 2, 3, 4)]
        rows.append([1.0, coupon, bill, *dummies, _is_month_end(d), _is_quarter_end(d)])
        x.append(coupon)
        dates.append(d)
    return np.asarray(rows, dtype=float), np.asarray(x, dtype=float), dates


def _power_for_events(
    events: Sequence[Mapping[str, Any]], *, sigma_bps: float, beta_prior_bps_per_100bn: float
) -> PowerPoint:
    X, x, dates = exogenous_design(events)
    n = int(X.shape[0])
    rank = int(np.linalg.matrix_rank(X))
    if rank < X.shape[1]:
        raise D002LPowerError(f"DESIGN_MATRIX_RANK_DEFICIENT:rank={rank}:columns={X.shape[1]}")
    if n <= rank:
        raise D002LPowerError(f"NONPOSITIVE_RESIDUAL_DF:n={n}:rank={rank}")
    Z = np.delete(X, 1, axis=1)
    coef, *_ = np.linalg.lstsq(Z, x, rcond=None)
    x_resid = x - Z @ coef
    sxx = float(x_resid @ x_resid)
    if not math.isfinite(sxx) or sxx <= 0:
        raise D002LPowerError("EXPOSURE_VARIANCE_NONPOSITIVE_AFTER_NUISANCE_RESIDUALIZATION")
    df = n - rank
    se_beta = sigma_bps / math.sqrt(sxx)
    ncp = beta_prior_bps_per_100bn / se_beta
    crit = float(t.ppf(1.0 - ALPHA / 2.0, df))
    power = float(nct.sf(crit, df, ncp) + nct.cdf(-crit, df, ncp))
    if not math.isfinite(power) or not (0.0 <= power <= 1.0):
        raise D002LPowerError("POWER_NUMERIC_NONFINITE_OR_OUT_OF_RANGE")
    clusters = len({_week_key(d) for d in dates})
    return PowerPoint(n, rank, df, clusters, sxx, se_beta, ncp, power)


def evaluate_power(
    registry: Mapping[str, Any], calibration_noise: Mapping[str, Any], effect_prior: Mapping[str, Any]
) -> dict[str, Any]:
    """Evaluate preregistered P2 power without loading confirmatory outcomes."""
    sigma_effective = validate_calibration_noise(calibration_noise)
    prior = conservative_effect_prior(effect_prior)
    beta = float(prior["chosen_beta_prior_bps_per_100bn"])
    events = confirmatory_events(registry)
    point = _power_for_events(events, sigma_bps=sigma_effective, beta_prior_bps_per_100bn=beta)

    n_min: int | None = None
    for k in range(1, len(events) + 1):
        try:
            p = _power_for_events(events[:k], sigma_bps=sigma_effective, beta_prior_bps_per_100bn=beta)
        except D002LPowerError:
            continue
        if p.clusters >= MIN_EFFECTIVE_CLUSTERS and p.power >= TARGET_POWER:
            n_min = k
            break

    refusal_reasons: list[str] = []
    if point.power < TARGET_POWER:
        refusal_reasons.append("POWER_BELOW_0_80")
    if point.clusters < MIN_EFFECTIVE_CLUSTERS:
        refusal_reasons.append("EFFECTIVE_CLUSTER_COUNT_BELOW_20")
    if n_min is None:
        refusal_reasons.append("NO_OBSERVED_PREFIX_REACHES_POWER_AND_CLUSTER_GATE")

    return {
        "schema_version": SCHEMA_VERSION,
        "study_id": "D-002L",
        "node_id": "D002L-P2",
        "phase_contract": "power_gate_before_confirmatory_outcome_ingestion",
        "status": "TERMINAL_PASS" if not refusal_reasons else "TERMINAL_REFUSED",
        "decision": "POWER_GATE_PASS" if not refusal_reasons else "POWER_GATE_REFUSED_UNDERPOWERED_OR_INVALID_DESIGN",
        "alpha_two_sided": ALPHA,
        "target_power": TARGET_POWER,
        "minimum_effective_clusters": MIN_EFFECTIVE_CLUSTERS,
        "eligible_confirmatory_event_count": point.n,
        "effective_cluster_count": point.clusters,
        "preoutcome_design_rank": point.rank,
        "preoutcome_design_columns": 9,
        "residual_df": point.df,
        "residualized_coupon_exposure_ss": point.residualized_x_ss,
        "sigma_residual_bps_calibration_only": float(calibration_noise["sigma_residual_bps"]),
        "week_cluster_design_effect_calibration_only": float(calibration_noise["week_cluster_design_effect"]),
        "effective_sigma_bps_for_power": sigma_effective,
        "standard_error_beta_prior_design": point.standard_error_beta,
        "noncentrality": point.noncentrality,
        "power": point.power,
        "computed_n_min_observed_prefix": n_min,
        "effect_prior": prior,
        "refusal_reasons": refusal_reasons,
        "confirmatory_outcomes_ingested": False,
        "full_design_with_lagged_spread_checked": False,
        "full_design_recheck_required_at": "D002L-P4",
        "canonical_run_authorized": False,
        "next_legal_node": "D002L-P3" if not refusal_reasons else None,
        "claim_boundary": (
            "Power/design adequacy only. No confirmatory TGCR/IOER/IORB observations are loaded; "
            "no beta is fit; no empirical association, causality, prediction, alpha, or GeoSync claim is established."
        ),
    }


def execute_power_gate(
    p1_status: Mapping[str, Any],
    registry: Mapping[str, Any],
    calibration_noise: Mapping[str, Any],
    effect_prior: Mapping[str, Any],
) -> dict[str, Any]:
    validate_p1_authority(p1_status, registry)
    return evaluate_power(registry, calibration_noise, effect_prior)


def execute_from_paths(status_path: Path, registry_path: Path, noise_path: Path, prior_path: Path) -> dict[str, Any]:
    status = _load_json(status_path)
    validate_p1_status_authority(status)
    registry = _load_json(registry_path)
    validate_p1_registry_authority(registry)
    return evaluate_power(registry, _load_json(noise_path), _load_json(prior_path))
