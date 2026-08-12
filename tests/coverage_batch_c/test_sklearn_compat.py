# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Behavioral coverage for analytics.regime.src.core._sklearn_compat."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pytest

from analytics.regime.src.core._sklearn_compat import (
    IsotonicRegression,
    LogisticRegression,
    TimeSeriesSplit,
    average_precision_score,
    check_random_state,
    roc_auc_score,
    _pava,
)


# --------------------------------------------------------------------------
# LogisticRegression
# --------------------------------------------------------------------------
def test_logistic_regression_separable_fit() -> None:
    rng = np.random.RandomState(0)
    x_pos = rng.normal(loc=3.0, size=(40, 2))
    x_neg = rng.normal(loc=-3.0, size=(40, 2))
    x = np.vstack([x_pos, x_neg])
    y = np.concatenate([np.ones(40), np.zeros(40)])

    model = LogisticRegression(C=1.0, random_state=0).fit(x, y)
    assert model.coef_ is not None
    assert model.intercept_ is not None

    scores = model.decision_function(x)
    preds = (scores > 0).astype(int)
    accuracy = np.mean(preds == y)
    assert accuracy > 0.9


def test_logistic_regression_balanced_class_weight() -> None:
    rng = np.random.RandomState(1)
    x = np.vstack([rng.normal(loc=2.0, size=(50, 2)), rng.normal(loc=-2.0, size=(10, 2))])
    y = np.concatenate([np.ones(50), np.zeros(10)])
    model = LogisticRegression(class_weight="balanced", random_state=1).fit(x, y)
    assert model.coef_ is not None
    scores = model.decision_function(x)
    assert scores.shape == (60,)


def test_logistic_regression_balanced_degenerate_single_class() -> None:
    # All positives -> degenerate balanced weighting falls back to uniform.
    x = np.random.RandomState(2).normal(size=(10, 2))
    y = np.ones(10)
    model = LogisticRegression(class_weight="balanced", random_state=2).fit(x, y)
    assert model.coef_ is not None


def test_logistic_regression_requires_2d_features() -> None:
    model = LogisticRegression()
    with pytest.raises(ValueError, match="2D array"):
        model.fit(np.array([1.0, 2.0, 3.0]), np.array([0, 1, 0]))


def test_logistic_regression_label_alignment() -> None:
    model = LogisticRegression()
    with pytest.raises(ValueError, match="align"):
        model.fit(np.zeros((3, 2)), np.array([0, 1]))


def test_logistic_regression_decision_function_before_fit() -> None:
    model = LogisticRegression()
    with pytest.raises(RuntimeError, match="fitted"):
        model.decision_function(np.zeros((2, 2)))


# --------------------------------------------------------------------------
# IsotonicRegression
# --------------------------------------------------------------------------
def test_isotonic_monotone_fit_predict_nan_bounds() -> None:
    x = np.array([1.0, 2.0, 3.0, 4.0])
    y = np.array([1.0, 3.0, 2.0, 4.0])  # violation at 3rd point
    iso = IsotonicRegression().fit(x, y)
    fitted = iso.predict(x)
    assert np.all(np.diff(fitted) >= -1e-9)  # monotone non-decreasing
    # out-of-bounds default nan
    out = iso.predict(np.array([0.0, 5.0]))
    assert np.all(np.isnan(out))


def test_isotonic_clip_bounds() -> None:
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([0.0, 0.5, 1.0])
    iso = IsotonicRegression(out_of_bounds="clip").fit(x, y)
    out = iso.predict(np.array([-5.0, 10.0]))
    assert out[0] == pytest.approx(0.0)
    assert out[1] == pytest.approx(1.0)


def test_isotonic_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="first dimension"):
        IsotonicRegression().fit(np.array([1.0, 2.0]), np.array([1.0]))


def test_isotonic_predict_before_fit() -> None:
    with pytest.raises(RuntimeError, match="fitted"):
        IsotonicRegression().predict(np.array([1.0]))


# --------------------------------------------------------------------------
# TimeSeriesSplit
# --------------------------------------------------------------------------
def test_time_series_split_numpy_default() -> None:
    tss = TimeSeriesSplit(n_splits=3)
    splits = list(tss.split(np.arange(20)))
    assert len(splits) == 3
    for train, test in splits:
        assert train[-1] < test[0]  # strictly expanding, no leakage
        assert len(test) > 0


def test_time_series_split_iterable_and_explicit_test_size() -> None:
    tss = TimeSeriesSplit(n_splits=2, test_size=3)
    splits = list(tss.split(iter(range(12))))
    assert len(splits) == 2
    for _train, test in splits:
        assert len(test) <= 3


def test_time_series_split_clamps_final_window() -> None:
    # test_end may overshoot n_samples and must clamp.
    tss = TimeSeriesSplit(n_splits=2, test_size=4)
    splits = list(tss.split(np.arange(11)))
    last_test = splits[-1][1]
    assert last_test[-1] == 10  # clamped to last index


def test_time_series_split_breaks_when_start_exceeds() -> None:
    tss = TimeSeriesSplit(n_splits=5, test_size=3)
    splits = list(tss.split(np.arange(8)))
    # test_start grows 3,6,9(>=8 -> break) so only 2 usable splits.
    assert len(splits) == 2


def test_time_series_split_invalid_n_splits() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        TimeSeriesSplit(n_splits=0)


def test_time_series_split_too_many_splits() -> None:
    tss = TimeSeriesSplit(n_splits=10)
    with pytest.raises(ValueError, match="Not enough samples"):
        list(tss.split(np.arange(5)))


# --------------------------------------------------------------------------
# check_random_state
# --------------------------------------------------------------------------
def test_check_random_state_variants() -> None:
    assert check_random_state(None) is np.random.mtrand._rand
    # the numpy module itself is accepted as a sentinel for the global RNG
    assert check_random_state(cast(Any, np.random)) is np.random.mtrand._rand
    assert isinstance(check_random_state(5), np.random.RandomState)
    # np.integer is normalised via the isinstance(seed, np.integer) branch
    assert isinstance(check_random_state(cast(Any, np.int64(5))), np.random.RandomState)
    existing = np.random.RandomState(1)
    assert check_random_state(existing) is existing


def test_check_random_state_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid random_state"):
        check_random_state(cast(Any, "bad"))


# --------------------------------------------------------------------------
# roc_auc_score
# --------------------------------------------------------------------------
def test_roc_auc_perfect_and_partial() -> None:
    labels = np.array([0, 0, 1, 1])
    perfect = roc_auc_score(labels, np.array([0.1, 0.2, 0.8, 0.9]))
    assert perfect == pytest.approx(1.0)
    partial = roc_auc_score(labels, np.array([0.1, 0.6, 0.4, 0.9]))
    assert 0.0 < partial < 1.0


def test_roc_auc_single_class_is_nan() -> None:
    assert np.isnan(roc_auc_score(np.array([1, 1, 1]), np.array([0.1, 0.2, 0.3])))
    assert np.isnan(roc_auc_score(np.array([0, 0, 0]), np.array([0.1, 0.2, 0.3])))


def test_roc_auc_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="first dimension"):
        roc_auc_score(np.array([0, 1]), np.array([0.1]))


# --------------------------------------------------------------------------
# average_precision_score
# --------------------------------------------------------------------------
def test_average_precision_ordering() -> None:
    labels = np.array([0, 0, 1, 1])
    perfect = average_precision_score(labels, np.array([0.1, 0.2, 0.8, 0.9]))
    assert perfect == pytest.approx(1.0)
    worse = average_precision_score(labels, np.array([0.9, 0.8, 0.2, 0.1]))
    assert worse < perfect


def test_average_precision_no_positives() -> None:
    assert average_precision_score(np.array([0, 0, 0]), np.array([0.1, 0.2, 0.3])) == 0.0


# --------------------------------------------------------------------------
# _pava (direct edge cases)
# --------------------------------------------------------------------------
def test_pava_cascading_pool_backwards() -> None:
    # forces a backward merge (idx>0 decrement path)
    y = np.array([1.0, 4.0, 2.0])
    out = _pava(y, np.ones(3))
    assert np.all(np.diff(out) >= -1e-9)
    # 4 and 2 pool to 3.0
    assert out[1] == pytest.approx(3.0)
    assert out[2] == pytest.approx(3.0)


def test_pava_requires_1d() -> None:
    with pytest.raises(ValueError, match="one-dimensional"):
        _pava(np.zeros((2, 2)), np.ones(4))


def test_pava_weight_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="weights must match"):
        _pava(np.array([1.0, 2.0, 3.0]), np.ones(2))
