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
    y_pred = [1, 0, 1, 0]
    groups = ["A", "A", "B", "B"]

    difference = demographic_parity_difference(y_pred, groups)

    assert pytest.approx(difference, abs=1e-9) == 0.0


def test_demographic_parity_detects_bias() -> None:
    y_pred = [1, 1, 0, 0]
    groups = ["A", "A", "B", "B"]

    difference = demographic_parity_difference(y_pred, groups)

    assert difference == pytest.approx(1.0)


def test_equal_opportunity_difference_balanced() -> None:
    y_true = [1, 1, 1, 1]
    y_pred = [1, 0, 1, 0]
    groups = ["A", "A", "B", "B"]

    difference = equal_opportunity_difference(y_true, y_pred, groups)

    assert difference == pytest.approx(0.0)


def test_equal_opportunity_detects_bias() -> None:
    y_true = [1, 1, 1, 1]
    y_pred = [1, 1, 0, 0]
    groups = ["A", "A", "B", "B"]

    difference = equal_opportunity_difference(y_true, y_pred, groups)

    assert difference == pytest.approx(1.0)


def test_evaluate_fairness_thresholds() -> None:
    y_true = [1, 1, 1, 1]
    y_pred = [1, 1, 0, 0]
    groups = ["A", "A", "B", "B"]

    evaluation = evaluate_fairness(
        y_true,
        y_pred,
        groups,
        thresholds={"demographic_parity": 1.1, "equal_opportunity": 1.1},
    )

    evaluation.assert_within_thresholds()


def test_evaluate_fairness_threshold_failure() -> None:
    y_true = [1, 1, 1, 1]
    y_pred = [1, 1, 0, 0]
    groups = ["A", "A", "B", "B"]

    evaluation = evaluate_fairness(y_true, y_pred, groups)

    with pytest.raises(AssertionError):
        evaluation.assert_within_thresholds()


def test_missing_groups_returns_zero() -> None:
    y_pred = [1, 0, 1]
    groups = ["A", "A", "A"]

    assert demographic_parity_difference(y_pred, groups) == pytest.approx(0.0)


def test_invalid_lengths_raise() -> None:
    with pytest.raises(FairnessMetricError):
        equal_opportunity_difference([1, 1], [1, 0, 1], ["A", "B", "B"])


def test_invalid_group_length_raises() -> None:
    with pytest.raises(FairnessMetricError):
        demographic_parity_difference([1, 0, 1], ["A", "B"])


def test_numpy_inputs_supported() -> None:
    y_true = np.array([1, 1, 0, 0])
    y_pred = np.array([1, 0, 1, 0])
    groups = np.array([0, 0, 1, 1])

    evaluation = evaluate_fairness(y_true, y_pred, groups)

    assert isinstance(evaluation.demographic_parity, float)
