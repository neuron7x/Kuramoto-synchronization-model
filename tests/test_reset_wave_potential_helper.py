"""Public-helper guards on `phase_alignment_potential` (cycle #5).

Cross-stress probe surfaced two silent contract issues in the public
helper used by callers outside the engine pipeline:

  1. NaN/Inf in either vector returned NaN silently (defence-in-depth gap)
  2. Empty vectors raised ZeroDivisionError instead of a typed ValueError

Both now fail-closed with a typed ValueError and an explicit message.
"""

from __future__ import annotations

import math

import pytest

from geosync.neuroeconomics.reset_wave_engine import phase_alignment_potential


def test_potential_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        phase_alignment_potential([], [])


def test_potential_rejects_mismatched_length() -> None:
    with pytest.raises(ValueError, match="equal length"):
        phase_alignment_potential([0.1, 0.2], [0.0])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_potential_rejects_non_finite_node(bad: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        phase_alignment_potential([0.1, bad], [0.0, 0.0])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_potential_rejects_non_finite_baseline(bad: float) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        phase_alignment_potential([0.1, 0.2], [0.0, bad])


def test_potential_returns_in_canonical_range() -> None:
    """1 - cos δ ∈ [0, 2] always for finite inputs."""
    val = phase_alignment_potential([0.1, -0.2, math.pi - 0.01], [0.0, 0.0, 0.0])
    assert 0.0 <= val <= 2.0
    assert math.isfinite(val)


def test_potential_zero_at_perfect_alignment() -> None:
    val = phase_alignment_potential([0.7, -0.3], [0.7, -0.3])
    assert math.isclose(val, 0.0, abs_tol=1e-12)
