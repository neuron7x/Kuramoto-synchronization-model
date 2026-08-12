# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic threshold-calibration contract.

This module selects a single scalar decision threshold from an explicit
candidate grid under a declared, leakage-free objective, with a separated
calibration / validation split and a recorded sensitivity sweep. It is
controlled parameter governance, not curve fitting and not forecasting.

Objective
---------
Given calibration observations and a declared ``target_upper_share`` in
``[0, 1]``, the selected threshold is the candidate whose *upper share*
on the calibration sample — the fraction of finite observations strictly
above the threshold — is closest to the target. The upper share is a
purely structural property of where a sample sits relative to a cut point;
it references no outcome, return, or future value, so the calibrated
threshold carries no predictive or financial meaning.

Leakage discipline
------------------
The validation split is scored for every candidate and recorded in the
sweep, but it is **never** consulted to choose the selected threshold.
Selection depends only on the calibration sample. A fixed candidate grid
fits nothing on unseen data, so an early observation's state cannot depend
on later observations.

Failure behaviour
-----------------
Fails closed (``ValueError``) on a malformed protocol: empty candidate
grid, non-finite or non-distinct candidates, ``target_upper_share`` outside
``[0, 1]``, or an empty calibration sample after invalid observations are
removed. Non-finite observations are counted, not silently dropped.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

__all__ = [
    "ThresholdCalibrationResult",
    "calibrate_threshold",
    "TIE_POLICY",
    "FAILURE_POLICY",
]

# Among candidates equally close to the target on the calibration sample,
# the smallest threshold is selected. Deterministic and independent of the
# order in which candidates are supplied.
TIE_POLICY = "nearest-to-target; ties broken by smallest candidate threshold"

FAILURE_POLICY = (
    "fail-closed (ValueError) on empty/non-finite/non-distinct candidates, "
    "target_upper_share outside [0, 1], or empty calibration sample"
)


@dataclass(frozen=True, slots=True)
class ThresholdCalibrationResult:
    """Outcome of one deterministic calibration run.

    Attributes
    ----------
    selected_value:
        The calibrated threshold (a member of ``candidates``).
    sensitivity_sweep:
        One record per candidate: its calibration metric, validation
        metric, whether it falls inside the sensitivity band, and a
        failure reason when it does not.
    metadata:
        Complete, replayable calibration-contract record.
    """

    selected_value: float
    sensitivity_sweep: tuple[Mapping[str, Any], ...]
    metadata: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Serialise the calibration outcome for logging / replay."""
        return {
            "selected_value": self.selected_value,
            "sensitivity_sweep": [dict(row) for row in self.sensitivity_sweep],
            "metadata": dict(self.metadata),
        }


def _finite(values: Sequence[float]) -> tuple[list[float], int]:
    """Split observations into finite values and a count of invalid ones."""
    finite: list[float] = []
    invalid = 0
    for raw in values:
        x = float(raw)
        if math.isfinite(x):
            finite.append(x)
        else:
            invalid += 1
    return finite, invalid


def _upper_share(sample: Sequence[float], threshold: float) -> float:
    """Fraction of the finite sample strictly above ``threshold``."""
    if not sample:
        return float("nan")
    arr = np.asarray(sample, dtype=float)
    return float(np.count_nonzero(arr > threshold) / arr.size)


def _validate_candidates(candidates: Sequence[float]) -> list[float]:
    values = [float(c) for c in candidates]
    if not values:
        raise ValueError("calibrate_threshold: candidates must be non-empty (fail-closed).")
    if any(not math.isfinite(c) for c in values):
        raise ValueError(f"calibrate_threshold: candidates must all be finite; got {values!r}.")
    if len(set(values)) != len(values):
        raise ValueError(f"calibrate_threshold: candidates must be distinct; got {values!r}.")
    return values


def calibrate_threshold(
    calibration_values: Sequence[float],
    validation_values: Sequence[float],
    *,
    candidates: Sequence[float],
    target_upper_share: float,
    sensitivity_band: float = 0.1,
    seed: int = 0,
) -> ThresholdCalibrationResult:
    """Select a scalar threshold from ``candidates`` by a declared objective.

    Parameters
    ----------
    calibration_values:
        Observations used to *select* the threshold.
    validation_values:
        Held-out observations used only to *report* the validation metric;
        never used to choose the selected threshold (leakage discipline).
    candidates:
        Explicit, distinct, finite candidate thresholds (the allowed range).
    target_upper_share:
        Declared objective in ``[0, 1]``: the desired fraction of finite
        calibration observations strictly above the threshold.
    sensitivity_band:
        A candidate "passes" when its calibration upper share is within
        this absolute distance of the target. Recorded per candidate.
    seed:
        Recorded for provenance. Selection is deterministic regardless.

    Returns
    -------
    ThresholdCalibrationResult
        ``selected_value``, the per-candidate ``sensitivity_sweep``, and a
        complete ``metadata`` record.

    Raises
    ------
    ValueError
        On a malformed protocol (see module ``FAILURE_POLICY``).
    """
    candidate_list = _validate_candidates(candidates)
    if not (0.0 <= float(target_upper_share) <= 1.0):
        raise ValueError(
            "calibrate_threshold: target_upper_share must be in [0, 1]; "
            f"got {target_upper_share!r}."
        )
    if not math.isfinite(float(sensitivity_band)) or float(sensitivity_band) < 0.0:
        raise ValueError(
            "calibrate_threshold: sensitivity_band must be finite and non-negative; "
            f"got {sensitivity_band!r}."
        )

    calib_finite, calib_invalid = _finite(calibration_values)
    valid_finite, valid_invalid = _finite(validation_values)
    if not calib_finite:
        raise ValueError(
            "calibrate_threshold: calibration sample is empty after removing "
            "non-finite observations (fail-closed)."
        )

    target = float(target_upper_share)
    band = float(sensitivity_band)

    sweep: list[dict[str, Any]] = []
    metric_values: dict[float, float] = {}
    for candidate in candidate_list:
        calib_metric = _upper_share(calib_finite, candidate)
        val_metric = _upper_share(valid_finite, candidate)
        distance = abs(calib_metric - target)
        passes = distance <= band
        metric_values[candidate] = calib_metric
        sweep.append(
            {
                "candidate": candidate,
                "calibration_metric": calib_metric,
                "validation_metric": val_metric,
                "passes": passes,
                "failure_reason": (
                    "" if passes else f"|upper_share-target|={distance:.4f} > band={band:.4f}"
                ),
            }
        )

    # Selection rule: nearest calibration upper share to target; ties → smallest
    # candidate. Uses ONLY the calibration metric (no validation leakage).
    selected_value = min(
        candidate_list,
        key=lambda c: (abs(metric_values[c] - target), c),
    )

    band_counts: Counter[bool] = Counter(row["passes"] for row in sweep)
    metadata: dict[str, Any] = {
        "method": "grid_nearest_upper_share",
        "parameter_name": "decision_threshold",
        "candidate_values": list(candidate_list),
        "selected_value": selected_value,
        "metric_name": "upper_share",
        "metric_values": {c: metric_values[c] for c in candidate_list},
        "target_upper_share": target,
        "calibration_count": len(calib_finite),
        "validation_count": len(valid_finite),
        "invalid_count": calib_invalid + valid_invalid,
        "seed": int(seed),
        "tie_policy": TIE_POLICY,
        "sensitivity_band": band,
        "sensitivity_pass_count": band_counts.get(True, 0),
        "failure_policy": FAILURE_POLICY,
        "claim_boundary": "descriptor_only_not_predictor",
        "not_financial_advice": True,
        "not_predictive_claim": True,
    }
    return ThresholdCalibrationResult(
        selected_value=selected_value,
        sensitivity_sweep=tuple(sweep),
        metadata=metadata,
    )
