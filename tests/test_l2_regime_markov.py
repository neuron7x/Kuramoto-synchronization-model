"""Tests for regime_markov module."""

from __future__ import annotations

import numpy as np
import pytest

from research.microstructure.regime_markov import (
    STATE_LABELS,
    RegimeMarkovReport,
    classify_states,
    regime_markov_report,
    transition_matrix,
)


def test_classify_states_basic_encoding() -> None:
    """Direct truth table for the 6-state encoding."""
    high = np.array([False, False, False, True, True, True], dtype=bool)
    direction = np.array([-1, 0, 1, -1, 0, 1], dtype=np.int64)
    states = classify_states(high, direction)
    assert list(states) == [0, 1, 2, 3, 4, 5]
    assert STATE_LABELS[0] == "low_vol_neg"
    assert STATE_LABELS[5] == "high_vol_pos"


def test_classify_states_shape_mismatch_raises() -> None:
    high = np.array([True, False], dtype=bool)
    direction = np.array([0], dtype=np.int64)
    with pytest.raises(ValueError):
        classify_states(high, direction)


def test_classify_states_clips_direction_outside_range() -> None:
    """Out-of-range direction values should clip to ±1 (safe behavior)."""
    high = np.array([False, False, True], dtype=bool)
    direction = np.array([5, -9, 3], dtype=np.int64)
    states = classify_states(high, direction)
    # 5 → +1 → state 2 (low_vol_pos); -9 → -1 → state 0; 3 → +1 → state 5
    assert list(states) == [2, 0, 5]


def test_transition_matrix_rows_sum_to_one_or_zero() -> None:
    rng = np.random.default_rng(42)
    states = rng.integers(0, 6, size=1000, dtype=np.int64)
    p = transition_matrix(states)
    assert p.shape == (6, 6)
    for row in p:
        s = float(row.sum())
        assert abs(s - 1.0) < 1e-9 or s == 0.0


def test_transition_matrix_perfectly_persistent_state_diag_one() -> None:
    """A state that always transitions to itself has diag=1."""
    states = np.zeros(100, dtype=np.int64)
    states[:] = 3
    p = transition_matrix(states)
    assert p[3, 3] == pytest.approx(1.0)


def test_transition_matrix_alternating_states_zero_diag() -> None:
    states = np.tile([0, 1], 50).astype(np.int64)
    p = transition_matrix(states)
    assert p[0, 0] == 0.0
    assert p[1, 1] == 0.0
    assert p[0, 1] == pytest.approx(1.0)
    assert p[1, 0] == pytest.approx(1.0)


def test_transition_matrix_rejects_multi_dim() -> None:
    with pytest.raises(ValueError):
        transition_matrix(np.zeros((5, 5), dtype=np.int64))


def test_regime_markov_report_persistent_diagonal_yields_long_dwell() -> None:
    """95 % self-transition → expected dwell ~ 20 seconds."""
    rng = np.random.default_rng(42)
    n = 10_000
    # Synthesize a state trajectory with known persistence.
    states = np.zeros(n, dtype=np.int64)
    current = 0
    for t in range(n):
        if rng.random() < 0.05:
            current = int(rng.integers(0, 6))
        states[t] = current

    # Map synthetic states → inputs the report expects
    high = np.isin(states, [3, 4, 5])
    direction = np.where(
        np.isin(states, [0, 3]), -1, np.where(np.isin(states, [1, 4]), 0, 1)
    ).astype(np.int64)

    report = regime_markov_report(high, direction)
    assert isinstance(report, RegimeMarkovReport)
    assert report.n_transitions == n - 1
    assert 0.85 < report.mean_diagonal < 1.0
    # At least one state has dwell > 10 s
    assert max(report.expected_dwell_sec) > 10.0


def test_regime_markov_report_stationary_distribution_sums_to_one() -> None:
    rng = np.random.default_rng(42)
    n = 5000
    high = rng.random(n) > 0.25
    direction = rng.integers(-1, 2, size=n, dtype=np.int64)
    report = regime_markov_report(high, direction)
    total = sum(report.stationary_distribution)
    assert abs(total - 1.0) < 1e-9
    for p in report.stationary_distribution:
        assert p >= 0.0


def test_regime_markov_report_schema_complete() -> None:
    n = 200
    high = np.zeros(n, dtype=bool)
    direction = np.zeros(n, dtype=np.int64)
    report = regime_markov_report(high, direction)
    assert len(report.states) == 6
    assert len(report.transition_matrix) == 6
    assert len(report.diagonal_persistence) == 6
    assert len(report.expected_dwell_sec) == 6
    assert len(report.stationary_distribution) == 6
    assert len(report.state_counts) == 6
    # With all (False, 0) → all rows in state 1 (low_vol_flat)
    assert report.state_counts[1] == n
