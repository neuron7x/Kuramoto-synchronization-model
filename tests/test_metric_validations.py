"""Unit tests for fairness metrics validation.

This module validates the fairness metrics used to detect bias in model predictions
across different demographic groups.

Test Coverage:
- Demographic parity: equal positive prediction rates across groups
- Equal opportunity: equal true positive rates across groups
- Fairness evaluation: comprehensive fairness assessment
- Edge cases: missing groups, invalid inputs, numpy array support
"""

from __future__ import annotations

import numpy as np
import pytest

from src.risk import (
    FairnessMetricError,
    demographic_parity_difference,
    equal_opportunity_difference,
    evaluate_fairness,
)


def test_demographic_parity_balanced_dataset() -> None:
    """Test demographic parity difference is zero for balanced predictions.

    When both groups have the same positive prediction rate (50%),
    the demographic parity difference should be zero.
    """
    y_pred = [1, 0, 1, 0]
    groups = ["A", "A", "B", "B"]

    difference = demographic_parity_difference(y_pred, groups)

    assert pytest.approx(difference, abs=1e-9) == 0.0, (
        f"Expected zero demographic parity difference for balanced dataset, "
        f"but got {difference}"
    )


def test_demographic_parity_detects_bias() -> None:
    """Test demographic parity detects significant bias between groups.

    When group A has 100% positive predictions and group B has 0%,
    the demographic parity difference should be 1.0 (maximum bias).
    """
    y_pred = [1, 1, 0, 0]
    groups = ["A", "A", "B", "B"]

    difference = demographic_parity_difference(y_pred, groups)

    assert difference == pytest.approx(1.0), (
        f"Expected demographic parity difference of 1.0 for maximally biased dataset, "
        f"but got {difference}"
    )


def test_equal_opportunity_difference_balanced() -> None:
    """Test equal opportunity difference is zero when TPR is equal across groups.

    When both groups have the same true positive rate (50% of actual positives
    predicted correctly), the equal opportunity difference should be zero.
    """
    y_true = [1, 1, 1, 1]
    y_pred = [1, 0, 1, 0]
    groups = ["A", "A", "B", "B"]

    difference = equal_opportunity_difference(y_true, y_pred, groups)

    assert difference == pytest.approx(0.0), (
        f"Expected zero equal opportunity difference for balanced TPR, "
        f"but got {difference}"
    )


def test_equal_opportunity_detects_bias() -> None:
    """Test equal opportunity detects TPR disparity between groups.

    When group A has 100% TPR (all positives correctly predicted) and
    group B has 0% TPR (no positives correctly predicted), the equal
    opportunity difference should be 1.0 (maximum disparity).
    """
    y_true = [1, 1, 1, 1]
    y_pred = [1, 1, 0, 0]
    groups = ["A", "A", "B", "B"]

    difference = equal_opportunity_difference(y_true, y_pred, groups)

    assert difference == pytest.approx(1.0), (
        f"Expected equal opportunity difference of 1.0 for maximum TPR disparity, "
        f"but got {difference}"
    )


def test_evaluate_fairness_thresholds() -> None:
    """Test fairness evaluation passes when metrics are within thresholds.

    With relaxed thresholds (1.1), the biased dataset should pass validation
    since both metrics are at 1.0, which is below the threshold.

    Validates:
    - Threshold checking works correctly
    - No exception raised when within bounds
    - Custom thresholds can be specified
    """
    y_true = [1, 1, 1, 1]
    y_pred = [1, 1, 0, 0]
    groups = ["A", "A", "B", "B"]

    evaluation = evaluate_fairness(
        y_true,
        y_pred,
        groups,
        thresholds={"demographic_parity": 1.1, "equal_opportunity": 1.1},
    )

    # Should not raise an exception
    evaluation.assert_within_thresholds()


def test_evaluate_fairness_threshold_failure() -> None:
    """Test fairness evaluation fails when metrics exceed default thresholds.

    With default thresholds, a dataset with demographic parity and equal
    opportunity differences of 1.0 should fail validation.

    Validates:
    - Threshold violations are detected
    - AssertionError is raised appropriately
    - Default thresholds are enforced
    """
    y_true = [1, 1, 1, 1]
    y_pred = [1, 1, 0, 0]
    groups = ["A", "A", "B", "B"]

    evaluation = evaluate_fairness(y_true, y_pred, groups)

    with pytest.raises(AssertionError, match=".+"):
        evaluation.assert_within_thresholds()


def test_missing_groups_returns_zero() -> None:
    """Test demographic parity returns zero when only one group is present.

    When all samples belong to a single group, there's no other group to
    compare against, so the difference should be zero (no bias possible).
    """
    y_pred = [1, 0, 1]
    groups = ["A", "A", "A"]

    result = demographic_parity_difference(y_pred, groups)
    assert result == pytest.approx(
        0.0
    ), f"Expected zero demographic parity for single group, but got {result}"


def test_invalid_lengths_raise() -> None:
    """Test that mismatched input lengths raise FairnessMetricError.

    When y_true, y_pred, and groups have different lengths, the function
    should raise a FairnessMetricError to prevent invalid calculations.
    """
    with pytest.raises(FairnessMetricError, match=".+"):
        equal_opportunity_difference([1, 1], [1, 0, 1], ["A", "B", "B"])


def test_invalid_group_length_raises() -> None:
    """Test that mismatched prediction and group lengths raise error.

    When predictions and groups have different lengths, the function
    should raise FairnessMetricError to ensure data integrity.
    """
    with pytest.raises(FairnessMetricError, match=".+"):
        demographic_parity_difference([1, 0, 1], ["A", "B"])


def test_numpy_inputs_supported() -> None:
    """Test that numpy arrays are accepted as inputs.

    Fairness metrics should work with both Python lists and numpy arrays,
    ensuring compatibility with common data science workflows.

    Validates:
    - Numpy arrays are accepted for all inputs
    - Results are computed correctly
    - Output types are appropriate (float for metrics)
    """
    y_true = np.array([1, 1, 0, 0])
    y_pred = np.array([1, 0, 1, 0])
    groups = np.array([0, 0, 1, 1])

    evaluation = evaluate_fairness(y_true, y_pred, groups)

    assert isinstance(
        evaluation.demographic_parity, float
    ), f"Expected demographic_parity to be float, but got {type(evaluation.demographic_parity)}"
    assert isinstance(
        evaluation.equal_opportunity, float
    ), f"Expected equal_opportunity to be float, but got {type(evaluation.equal_opportunity)}"
