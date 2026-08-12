# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for the fail-closed temporal-leakage guards in ``core.data.leakage``.

Sixteen cases: a clean split and strictly-after labels PASS; overlap, adjacency,
insufficient embargo, ``label == decision``, ``label < decision``, shape
mismatch, and every malformed-input family (empty, non-1-D, non-finite, negative
embargo) all FAIL-CLOSED with :class:`LeakageError`.
"""

from __future__ import annotations

import numpy as np
import pytest

from core.data.leakage import (
    LeakageError,
    assert_no_future_label_leakage,
    assert_no_train_test_leakage,
)

# ───────────────────────── train/test guard — passing ─────────────────────────


def test_clean_split_passes() -> None:
    """A split whose training max sits strictly before the test min is clean."""
    assert_no_train_test_leakage([0, 1, 2, 3], [4, 5, 6]) is None


def test_sufficient_embargo_passes() -> None:
    """A gap that exceeds the embargo is leakage-free."""
    # max(train)=3, min(test)=10, boundary=10-5=5; 3 < 5 → clean.
    assert_no_train_test_leakage([0, 1, 3], [10, 11], embargo=5.0) is None


def test_unordered_inputs_use_extremes() -> None:
    """Order is irrelevant — only max(train) vs min(test) matters."""
    assert_no_train_test_leakage([3, 0, 2, 1], [6, 4, 5]) is None


# ───────────────────────── train/test guard — failing ─────────────────────────


def test_overlap_fails() -> None:
    """max(train) strictly greater than min(test) is a hard leak."""
    with pytest.raises(LeakageError, match="train/test leakage"):
        assert_no_train_test_leakage([0, 1, 5], [3, 4])


def test_adjacency_fails_at_zero_embargo() -> None:
    """max(train) == min(test) leaks: the boundary bar is shared."""
    with pytest.raises(LeakageError, match="train/test leakage"):
        assert_no_train_test_leakage([0, 1, 5], [5, 6])


def test_insufficient_embargo_fails() -> None:
    """A gap smaller than the embargo leaves the dead zone violated."""
    # max(train)=4, min(test)=6, boundary=6-3=3; 4 >= 3 → leak.
    with pytest.raises(LeakageError, match="train/test leakage"):
        assert_no_train_test_leakage([0, 4], [6, 7], embargo=3.0)


def test_negative_embargo_fails() -> None:
    """A negative embargo would license overlap — rejected up front."""
    with pytest.raises(LeakageError, match="embargo must be >= 0"):
        assert_no_train_test_leakage([0, 1], [2, 3], embargo=-1.0)


def test_non_finite_embargo_fails() -> None:
    """A non-finite embargo is an undefined dead zone — rejected."""
    with pytest.raises(LeakageError, match="embargo must be finite"):
        assert_no_train_test_leakage([0, 1], [2, 3], embargo=float("inf"))


def test_empty_train_fails() -> None:
    """An empty training coordinate cannot be proven leakage-free."""
    with pytest.raises(LeakageError, match="train_times is empty"):
        assert_no_train_test_leakage([], [1, 2])


def test_empty_test_fails() -> None:
    """An empty test coordinate cannot be proven leakage-free."""
    with pytest.raises(LeakageError, match="test_times is empty"):
        assert_no_train_test_leakage([0, 1], [])


def test_non_1d_train_fails() -> None:
    """A 2-D training coordinate is a contract violation, not reshaped."""
    with pytest.raises(LeakageError, match="train_times must be 1-D"):
        assert_no_train_test_leakage([[0, 1], [2, 3]], [4, 5])


def test_non_finite_test_fails() -> None:
    """A NaN in the test coordinate is undefined order — rejected."""
    with pytest.raises(LeakageError, match="test_times has 1 non-finite"):
        assert_no_train_test_leakage([0, 1], [2, float("nan")])


# ───────────────────────── future-label guard — passing ─────────────────────────


def test_strictly_after_labels_pass() -> None:
    """Every label strictly post-dating its decision is clean."""
    assert_no_future_label_leakage([0, 1, 2], [1, 2, 3]) is None


# ───────────────────────── future-label guard — failing ─────────────────────────


def test_label_equal_decision_fails() -> None:
    """A label observed at the decision instant leaks future information."""
    with pytest.raises(LeakageError, match="future-label leakage"):
        assert_no_future_label_leakage([0, 1, 2], [1, 2, 2])


def test_label_before_decision_fails() -> None:
    """A label predating its decision is impossible without leakage."""
    with pytest.raises(LeakageError, match="future-label leakage"):
        assert_no_future_label_leakage([0, 5, 2], [1, 4, 3])


def test_label_decision_shape_mismatch_fails() -> None:
    """Decisions and labels are paired positionally and must align."""
    with pytest.raises(LeakageError, match="shape mismatch"):
        assert_no_future_label_leakage([0, 1, 2], [1, 2])


def test_non_finite_label_fails() -> None:
    """A NaN label has no observation time — rejected before comparison."""
    with pytest.raises(LeakageError, match="label_times has 1 non-finite"):
        assert_no_future_label_leakage([0, 1], [1, float("nan")])


def test_empty_decision_fails() -> None:
    """An empty decision coordinate cannot be proven leakage-free."""
    with pytest.raises(LeakageError, match="decision_times is empty"):
        assert_no_future_label_leakage([], [])
