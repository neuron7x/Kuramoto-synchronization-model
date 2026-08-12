# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002K-P3 high-SNR event-transition metric definitions.

This module gives the K-P0-locked primary endpoint
``pre_post_standardized_mean_shift`` its full *executable* mathematical
contract and defines the K-P0-listed secondary *exploratory-only*
battery. It is a metric-DEFINITION layer, not a scoring pipeline.

Why high-SNR (the D-002H / D-002I lesson)
-----------------------------------------
D-002H / D-002I diagnosed multiplicity inflation: spreading the
confirmatory signal across many endpoints destroys statistical power.
D-002K answers with **exactly one** confirmatory endpoint
(``pre_post_standardized_mean_shift``, locked in K-P0 and immutable
here); every other metric is ``exploratory_only`` and may never enter
the Bonferroni denominator or be promoted to primary without a fresh
D-002L pre-registration.

What this module IS / IS NOT
----------------------------
* IS: pure-numpy deterministic metric functions + a crisis-vs-placebo
  contrast helper, unit-testable on tiny synthetic arrays for
  *definitional correctness only*.
* IS NOT: a scoring run. No data ingestion. No file read of any ingested
  or real market series. No model fit. No canonical-run authorization.
* IS NOT: a numeric decision threshold. The threshold VALUE is
  power-gate territory (a later D-002K P-power phase). This module locks
  *what* is measured and *how*, never the cut value.

Fail-closed discipline (GeoSync physics contract)
-------------------------------------------------
The primary metric raises ``ValueError`` on degenerate inputs
(``sigma == 0`` baseline, insufficient pre/post length, non-finite
input). There is **no silent numeric repair** — a degenerate baseline is
an honest error, not a quantity to clamp away. There is no ``np.clip`` /
``max(0, .)`` / ``min(1, .)`` of any physical quantity in this module;
the only bounds are fail-closed input guards, each commented inline.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Locked identifiers (K-P0 / K-P1 coupling — do NOT tune after scoring)
# ---------------------------------------------------------------------------

#: The single confirmatory endpoint id, locked in K-P0
#: (``d002k_primary_metric_contract_v1.json::primary_metric_id``). This
#: string MUST equal that lock; no swap, no second confirmatory metric.
PRIMARY_METRIC_ID: str = "pre_post_standardized_mean_shift"

#: The six K-P0-listed secondary metrics. ALL exploratory_only; NONE
#: confirmatory; NONE enters the Bonferroni denominator.
SECONDARY_METRIC_IDS: tuple[str, ...] = (
    "max_zscore",
    "area_under_stress_curve",
    "recovery_half_life",
    "slope_into_crisis",
    "volatility_ratio",
    "persistence_above_threshold",
)

#: The six K-P1 observable families (from
#: ``source_observable_contract_v1.json``). Every metric maps to >=1.
K_P1_OBSERVABLE_FAMILIES: tuple[str, ...] = (
    "level_shift",
    "spread_widening",
    "volatility_burst",
    "recovery_time",
    "transition_steepness",
    "stress_persistence",
)


# ---------------------------------------------------------------------------
# Shared fail-closed input helpers (no silent repair)
# ---------------------------------------------------------------------------


def _as_finite_1d(series: Sequence[float] | NDArray[np.float64], name: str) -> NDArray[np.float64]:
    """Coerce *series* to a finite 1-D float64 array or fail closed.

    Raises:
        ValueError: non-1-D input, empty input, or any NaN/Inf element.
            Fail-closed: a non-finite event series is an honest error,
            never a value to silently repair.
    """
    arr = np.asarray(series, dtype=np.float64)
    if arr.ndim != 1:
        msg = f"{name} must be 1-D, got ndim={arr.ndim}"
        raise ValueError(msg)
    if arr.size == 0:
        msg = f"{name} must be non-empty"
        raise ValueError(msg)
    if not np.all(np.isfinite(arr)):
        msg = f"{name} contains NaN/Inf; fail-closed (no silent repair)"
        raise ValueError(msg)
    return arr


def _split_pre_post(
    series: Sequence[float] | NDArray[np.float64],
    onset_idx: int,
    pre_len: int,
    post_len: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return ``(pre_window, post_window)`` slices relative to crisis onset.

    The pre-window is the ``pre_len`` samples ending just before
    ``onset_idx`` (the locked matched pre-window baseline); the
    post-window is the ``post_len`` samples starting at ``onset_idx``
    (the locked in-crisis window). Fail-closed on any geometry that
    cannot honestly support both windows — no truncation, no padding.

    Raises:
        ValueError: non-int args, non-positive lengths, onset out of
            range, or insufficient samples for either window.
    """
    arr = _as_finite_1d(series, "series")
    if not isinstance(onset_idx, int) or not isinstance(pre_len, int):
        msg = "onset_idx and pre_len must be int"
        raise ValueError(msg)
    if not isinstance(post_len, int):
        msg = "post_len must be int"
        raise ValueError(msg)
    if pre_len <= 0 or post_len <= 0:
        msg = f"pre_len={pre_len} and post_len={post_len} must both be > 0"
        raise ValueError(msg)
    # bounds: fail-closed window-geometry guard (NOT a physical clamp).
    # An out-of-range onset or a window that runs off either edge is a
    # short-window error; we raise rather than truncate/pad silently.
    if onset_idx < pre_len:
        msg = f"insufficient pre-window: onset_idx={onset_idx} < pre_len={pre_len}"
        raise ValueError(msg)
    if onset_idx + post_len > arr.size:
        msg = (
            f"insufficient post-window: onset_idx={onset_idx} + "
            f"post_len={post_len} > len={arr.size}"
        )
        raise ValueError(msg)
    pre = arr[onset_idx - pre_len : onset_idx]
    post = arr[onset_idx : onset_idx + post_len]
    return pre, post


def _baseline_mu_sigma(pre: NDArray[np.float64]) -> tuple[float, float]:
    """Return ``(mu_pre, sigma_pre)`` with sample std (ddof=1, K-P0 lock).

    Raises:
        ValueError: ``pre`` has < 2 samples (sample std undefined) or
            ``sigma_pre == 0`` (degenerate constant baseline). Fail-
            closed: a zero-variance baseline is a real error, not a
            quantity to clamp to epsilon.
    """
    if pre.size < 2:
        msg = f"pre-window needs >= 2 samples for ddof=1 std, got {pre.size}"
        raise ValueError(msg)
    mu = float(np.mean(pre))
    # ddof=1: degrees of freedom fixed at pre-registration (K-P0 step 4).
    sigma = float(np.std(pre, ddof=1))
    if sigma == 0.0:
        msg = "degenerate baseline: sigma_pre == 0; fail-closed (no silent repair)"
        raise ValueError(msg)
    return mu, sigma


# ---------------------------------------------------------------------------
# PRIMARY confirmatory endpoint (K-P0 lock — immutable definition)
# ---------------------------------------------------------------------------


def pre_post_standardized_mean_shift(
    series: Sequence[float] | NDArray[np.float64],
    onset_idx: int,
    pre_len: int,
    post_len: int,
) -> float:
    """K-P0-locked PRIMARY CONFIRMATORY endpoint (Cohen's-d form).

    Definition (verbatim K-P0 ``computation_steps``): take the locked
    pre-window baseline segment and the locked in-crisis segment of the
    K-P1 funding-stress observable series; ``mu_pre = mean(pre)``,
    ``mu_in = mean(post)``, ``sigma_pre = std(pre, ddof=1)``; the metric
    is ``(mu_in - mu_pre) / sigma_pre`` — a single standardized scalar.

    This is the ONLY confirmatory endpoint of D-002K and is byte-locked
    by K-P0: no swap, no second confirmatory metric, no post-hoc primary.

    Deterministic: pure arithmetic on the input slice; identical inputs
    yield bit-identical output. Fail-closed on degenerate baseline
    (``sigma_pre == 0``), short pre/post window, or non-finite input —
    GeoSync physics discipline forbids silent repair.

    Args:
        series: 1-D event observable series (synthetic in tests; a real
            ingested series is NOT read by this module).
        onset_idx: index of crisis onset (first in-crisis sample).
        pre_len: locked pre-window baseline length (samples).
        post_len: locked in-crisis window length (samples).

    Returns:
        The standardized mean shift as a float.

    Raises:
        ValueError: any contract violation (see module docstring).
    """
    pre, post = _split_pre_post(series, onset_idx, pre_len, post_len)
    mu_pre, sigma_pre = _baseline_mu_sigma(pre)
    mu_in = float(np.mean(post))
    return (mu_in - mu_pre) / sigma_pre


# ---------------------------------------------------------------------------
# SECONDARY exploratory battery (ALL exploratory_only; NONE confirmatory)
# ---------------------------------------------------------------------------


def max_zscore(
    series: Sequence[float] | NDArray[np.float64],
    onset_idx: int,
    pre_len: int,
    post_len: int,
) -> float:
    """EXPLORATORY ONLY. Peak in-crisis z-score vs the pre-window baseline.

    z-standardize the post-window with the pre-window ``(mu, sigma)``;
    return ``max(post_z)``. Exploratory descriptor of transition
    sharpness — never confirmatory, never in the Bonferroni denominator.
    Deterministic; fail-closed on the same degenerate inputs.
    """
    pre, post = _split_pre_post(series, onset_idx, pre_len, post_len)
    mu_pre, sigma_pre = _baseline_mu_sigma(pre)
    post_z = (post - mu_pre) / sigma_pre
    return float(np.max(post_z))


def area_under_stress_curve(
    series: Sequence[float] | NDArray[np.float64],
    onset_idx: int,
    pre_len: int,
    post_len: int,
) -> float:
    """EXPLORATORY ONLY. Trapezoidal area of the in-crisis z-curve.

    z-standardize the post-window with the pre-window baseline; return
    the trapezoidal integral of ``post_z`` over unit-spaced samples
    (composite trapezoid: sum of interior points + half the endpoints).
    Exploratory cumulative-stress descriptor. Deterministic; fail-closed.
    """
    pre, post = _split_pre_post(series, onset_idx, pre_len, post_len)
    mu_pre, sigma_pre = _baseline_mu_sigma(pre)
    post_z = (post - mu_pre) / sigma_pre
    if post_z.size == 1:
        return 0.0
    # Composite trapezoid rule, unit spacing (explicit; np.trapz is
    # untyped in the pinned numpy stub — equivalent, deterministic).
    return float(np.sum(post_z[:-1] + post_z[1:]) / 2.0)


def recovery_half_life(
    series: Sequence[float] | NDArray[np.float64],
    onset_idx: int,
    pre_len: int,
    post_len: int,
) -> float:
    """EXPLORATORY ONLY. Samples until in-crisis z falls to half its peak.

    z-standardize the post-window with the pre-window baseline; let
    ``zmax`` be the peak; return the count of samples (post-peak) until
    ``post_z`` first drops to <= ``zmax / 2``. Returns ``post_len`` (no
    recovery observed within the window) when the half level is never
    re-crossed — a defined sentinel, not a silent repair. Exploratory
    recovery-speed descriptor. Deterministic; fail-closed on degenerate
    inputs.
    """
    pre, post = _split_pre_post(series, onset_idx, pre_len, post_len)
    mu_pre, sigma_pre = _baseline_mu_sigma(pre)
    post_z = (post - mu_pre) / sigma_pre
    peak_idx = int(np.argmax(post_z))
    half = float(post_z[peak_idx]) / 2.0
    tail = post_z[peak_idx:]
    below = np.nonzero(tail <= half)[0]
    if below.size == 0:
        # bounds: defined no-recovery sentinel == window length (NOT a
        # physical clamp); recovery beyond the locked window is unknown
        # by construction, reported honestly as the censoring value.
        return float(post_len)
    return float(below[0])


def slope_into_crisis(
    series: Sequence[float] | NDArray[np.float64],
    onset_idx: int,
    pre_len: int,
    post_len: int,
) -> float:
    """EXPLORATORY ONLY. OLS slope of the in-crisis z-trajectory.

    z-standardize the post-window with the pre-window baseline; return
    the ordinary-least-squares slope of ``post_z`` against unit-spaced
    sample index. Needs >= 2 post samples (else fail-closed via
    ``_split_pre_post`` + this guard). Exploratory transition-steepness
    descriptor. Deterministic.
    """
    pre, post = _split_pre_post(series, onset_idx, pre_len, post_len)
    mu_pre, sigma_pre = _baseline_mu_sigma(pre)
    post_z = (post - mu_pre) / sigma_pre
    if post_z.size < 2:
        msg = f"slope needs >= 2 post samples, got {post_z.size}"
        raise ValueError(msg)
    x = np.arange(post_z.size, dtype=np.float64)
    slope, _intercept = np.polyfit(x, post_z, 1)
    return float(slope)


def volatility_ratio(
    series: Sequence[float] | NDArray[np.float64],
    onset_idx: int,
    pre_len: int,
    post_len: int,
) -> float:
    """EXPLORATORY ONLY. In-crisis std / pre-window std (variance burst).

    Ratio of the post-window sample std to the pre-window sample std
    (both ddof=1). ``sigma_pre == 0`` is fail-closed via
    ``_baseline_mu_sigma``. Exploratory volatility-burst descriptor.
    Deterministic.
    """
    pre, post = _split_pre_post(series, onset_idx, pre_len, post_len)
    _mu_pre, sigma_pre = _baseline_mu_sigma(pre)
    if post.size < 2:
        msg = f"volatility_ratio needs >= 2 post samples, got {post.size}"
        raise ValueError(msg)
    sigma_post = float(np.std(post, ddof=1))
    return sigma_post / sigma_pre


def persistence_above_threshold(
    series: Sequence[float] | NDArray[np.float64],
    onset_idx: int,
    pre_len: int,
    post_len: int,
    z_threshold: float = 1.0,
) -> float:
    """EXPLORATORY ONLY. Fraction of in-crisis samples with z > threshold.

    z-standardize the post-window with the pre-window baseline; return
    the fraction of ``post_z`` strictly exceeding ``z_threshold`` (a
    fixed descriptive z-level, NOT the deferred decision threshold).
    Exploratory stress-persistence descriptor. Deterministic; fail-
    closed on non-finite ``z_threshold``.
    """
    if not np.isfinite(z_threshold):
        msg = f"z_threshold must be finite, got {z_threshold}"
        raise ValueError(msg)
    pre, post = _split_pre_post(series, onset_idx, pre_len, post_len)
    mu_pre, sigma_pre = _baseline_mu_sigma(pre)
    post_z = (post - mu_pre) / sigma_pre
    return float(np.mean(post_z > z_threshold))


# ---------------------------------------------------------------------------
# Crisis-vs-placebo contrast (uses K-P2 matched placebos; NO threshold)
# ---------------------------------------------------------------------------


def crisis_vs_placebo_contrast(
    metric_fn: Callable[..., float],
    crisis_series: Sequence[float] | NDArray[np.float64],
    placebo_series_list: Sequence[Sequence[float] | NDArray[np.float64]],
    onset_idx: int,
    pre_len: int,
    post_len: int,
) -> dict[str, Any]:
    """Compute ``Delta = metric(crisis) - mean(metric over placebos)``.

    The placebo list is the K-P2 matched-placebo set (the predefined,
    anti-cherry-pick contrast baseline). This function returns the raw
    contrast quantities ONLY — it makes **no threshold decision** and
    emits **no pass/fail**. The numeric decision cut is deferred to the
    D-002K power gate (a later P-power phase), not set here.

    Deterministic: each metric call is deterministic; the aggregate is
    pure arithmetic. Fail-closed: empty placebo list raises.

    Returns:
        ``{crisis_value, placebo_mean, placebo_std, delta, n_placebos}``
        — quantities only, never a verdict.
    """
    if len(placebo_series_list) == 0:
        msg = "placebo_series_list must be non-empty (K-P2 matched placebos)"
        raise ValueError(msg)
    crisis_value = float(metric_fn(crisis_series, onset_idx, pre_len, post_len))
    placebo_values = np.asarray(
        [float(metric_fn(p, onset_idx, pre_len, post_len)) for p in placebo_series_list],
        dtype=np.float64,
    )
    placebo_mean = float(np.mean(placebo_values))
    # ddof=0 here is a descriptive spread of the placebo metric values,
    # not an inferential std; honest single-population summary.
    placebo_std = float(np.std(placebo_values, ddof=0))
    return {
        "crisis_value": crisis_value,
        "placebo_mean": placebo_mean,
        "placebo_std": placebo_std,
        "delta": crisis_value - placebo_mean,
        "n_placebos": int(placebo_values.size),
    }


#: Public metric-id -> callable registry (definition layer only).
METRIC_REGISTRY: dict[str, Callable[..., float]] = {
    PRIMARY_METRIC_ID: pre_post_standardized_mean_shift,
    "max_zscore": max_zscore,
    "area_under_stress_curve": area_under_stress_curve,
    "recovery_half_life": recovery_half_life,
    "slope_into_crisis": slope_into_crisis,
    "volatility_ratio": volatility_ratio,
    "persistence_above_threshold": persistence_above_threshold,
}
