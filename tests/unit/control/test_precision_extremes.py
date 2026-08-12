# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Extreme precision probes for the AAR-PRO comparator distance.

These tests pin the unnormalised inverse-variance contract near the numeric
edge: tiny positive variances must amplify micro-drift into rollback-required
witnesses, while zero variance is still rejected at model construction.
"""

from __future__ import annotations

import math

import pytest

from geosync_hpc.control import (
    ActionResultStatus,
    ExpectedResultModel,
    ObservedActionResult,
    accept_action_result,
)


def _expected_with_variance(variance: float) -> ExpectedResultModel:
    return ExpectedResultModel(
        action_id="precision-extreme",
        action_type="trade",
        expected_result=(0.0,),
        expected_result_variance=(variance,),
        context_signature=(1.0,),
        model_created_seq=1,
        action_started_seq=2,
        error_threshold=0.1,
        rollback_threshold=1.0,
    )


@pytest.mark.parametrize("variance", [1e-15, 1e-14, 1e-13, 1e-12])
def test_tiny_variance_micro_drift_triggers_rollback_without_numeric_failure(
    variance: float,
) -> None:
    expected = _expected_with_variance(variance)
    observed = ObservedActionResult(
        action_id="precision-extreme",
        observed_seq=3,
        observed_result=(1e-4,),
    )

    witness = accept_action_result(expected, observed)

    assert witness.status is ActionResultStatus.ROLLBACK_REQUIRED
    assert witness.rollback_required is True
    assert witness.comparator_error is not None
    assert math.isfinite(witness.comparator_error)
    assert witness.comparator_error >= expected.rollback_threshold


def test_zero_variance_is_rejected_before_comparison() -> None:
    with pytest.raises(ValueError, match="expected_result_variance entries must be > 0"):
        _expected_with_variance(0.0)


def test_extreme_but_finite_delta_does_not_overflow() -> None:
    expected = _expected_with_variance(1e-12)
    observed = ObservedActionResult(
        action_id="precision-extreme",
        observed_seq=3,
        observed_result=(1e100,),
    )

    witness = accept_action_result(expected, observed)

    assert witness.status is ActionResultStatus.ROLLBACK_REQUIRED
    assert witness.comparator_error is not None
    assert math.isfinite(witness.comparator_error)
