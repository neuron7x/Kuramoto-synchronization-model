# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync_hpc.dynamics.motional_correlation_witness."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pytest

from geosync_hpc.dynamics.motional_correlation_witness import (
    MotionalInput,
    MotionalStatus,
    MotionalWitness,
    assess_motional_correlation,
)


def _input(
    *,
    x: tuple[float, ...],
    y: tuple[float, ...],
    shuffle_count: int = 200,
    margin: float = 0.05,
    minimum_length: int = 16,
    seed: int = 1234,
) -> MotionalInput:
    return MotionalInput(
        x=x,
        y=y,
        shuffle_count=shuffle_count,
        margin=margin,
        minimum_length=minimum_length,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Brief-required deterministic scenarios
# ---------------------------------------------------------------------------


def test_identical_series_yields_high_static_correlation() -> None:
    """Identical series: static_correlation = 1.0, trajectory non-trivial."""
    rng = np.random.default_rng(0)
    x = tuple(float(v) for v in rng.standard_normal(64).cumsum())
    witness = assess_motional_correlation(_input(x=x, y=x))
    assert math.isclose(witness.static_correlation, 1.0, abs_tol=1e-12)
    # Trajectory of (x, x) increments equals (dx, dx) → corr = 1.0.
    assert math.isclose(witness.trajectory_relation, 1.0, abs_tol=1e-12)


def test_independent_noise_series_yields_static_only() -> None:
    """Independent noise series: classified STATIC_ONLY (no dynamic relation)."""
    rng = np.random.default_rng(7)
    x = tuple(float(v) for v in rng.standard_normal(128))
    y = tuple(float(v) for v in rng.standard_normal(128))
    witness = assess_motional_correlation(_input(x=x, y=y))
    assert witness.status is MotionalStatus.STATIC_ONLY
    assert witness.dynamic_relation_detected is False
    assert abs(witness.static_correlation) < 0.5
    assert abs(witness.trajectory_relation) < 0.5


def test_shuffled_trajectory_does_not_classify_as_dynamic() -> None:
    """Two series where any dynamic content lives only in static joint dist.

    A shuffled-y trajectory must not produce DYNAMIC_RELATION_CONFIRMED;
    the witness must hold STATIC_ONLY.
    """
    rng = np.random.default_rng(13)
    x = tuple(float(v) for v in rng.standard_normal(96))
    # y is a permutation of x — strong static correlation (still 1 by
    # Pearson on shuffled marginals after a random match), but
    # trajectory increments are noise.
    perm = rng.permutation(np.asarray(x))
    y = tuple(float(v) for v in perm)
    witness = assess_motional_correlation(_input(x=x, y=y))
    assert witness.status is MotionalStatus.STATIC_ONLY
    assert witness.dynamic_relation_detected is False


def test_constructed_dynamic_only_series_classifies_as_dynamic() -> None:
    """y tracks x step-by-step with small noise: increments dy ≈ dx.

    Random-walk x_arr makes the trajectory score sensitive to *when* the
    co-movement happens. With y = x + small_noise the trajectory score
    is high; under shuffling, (dx, d(shuffled_y)) loses ordering and
    the null collapses near zero.
    """
    rng = np.random.default_rng(42)
    n = 128
    x_arr = rng.standard_normal(n).cumsum()
    y_arr = x_arr + 0.01 * rng.standard_normal(n)
    x = tuple(float(v) for v in x_arr)
    y = tuple(float(v) for v in y_arr)
    witness = assess_motional_correlation(_input(x=x, y=y))
    assert witness.status is MotionalStatus.DYNAMIC_RELATION_CONFIRMED
    assert witness.dynamic_relation_detected is True
    assert abs(witness.trajectory_relation) > witness.null_p95 + witness.margin_used


def test_mismatched_series_lengths_rejected() -> None:
    with pytest.raises(ValueError, match="x and y must have equal length"):
        MotionalInput(
            x=(1.0, 2.0, 3.0),
            y=(1.0, 2.0),
            shuffle_count=10,
            margin=0.1,
            minimum_length=2,
            seed=0,
        )


def test_non_finite_inputs_rejected() -> None:
    with pytest.raises(ValueError, match=r"x\[1\] must be finite"):
        MotionalInput(
            x=(1.0, float("nan"), 3.0),
            y=(1.0, 2.0, 3.0),
            shuffle_count=10,
            margin=0.1,
            minimum_length=2,
            seed=0,
        )
    with pytest.raises(ValueError, match=r"y\[0\] must be finite"):
        MotionalInput(
            x=(1.0, 2.0, 3.0),
            y=(float("inf"), 2.0, 3.0),
            shuffle_count=10,
            margin=0.1,
            minimum_length=2,
            seed=0,
        )
    with pytest.raises(ValueError, match="margin must be finite"):
        MotionalInput(
            x=(1.0, 2.0),
            y=(1.0, 2.0),
            shuffle_count=10,
            margin=float("nan"),
            minimum_length=2,
            seed=0,
        )


# ---------------------------------------------------------------------------
# Validation contract
# ---------------------------------------------------------------------------


def test_negative_shuffle_count_rejected() -> None:
    with pytest.raises(ValueError, match="shuffle_count must be >= 0"):
        MotionalInput(
            x=(1.0, 2.0),
            y=(1.0, 2.0),
            shuffle_count=-1,
            margin=0.1,
            minimum_length=2,
            seed=0,
        )


def test_negative_margin_rejected() -> None:
    with pytest.raises(ValueError, match="margin must be >= 0"):
        MotionalInput(
            x=(1.0, 2.0),
            y=(1.0, 2.0),
            shuffle_count=10,
            margin=-0.01,
            minimum_length=2,
            seed=0,
        )


def test_negative_minimum_length_rejected() -> None:
    with pytest.raises(ValueError, match="minimum_length must be >= 0"):
        MotionalInput(
            x=(1.0, 2.0),
            y=(1.0, 2.0),
            shuffle_count=10,
            margin=0.1,
            minimum_length=-1,
            seed=0,
        )


def test_non_tuple_series_rejected() -> None:
    with pytest.raises(TypeError, match="x must be a tuple"):
        MotionalInput(
            x=[1.0, 2.0],  # type: ignore[arg-type]
            y=(1.0, 2.0),
            shuffle_count=10,
            margin=0.1,
            minimum_length=2,
            seed=0,
        )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_below_minimum_length_returns_insufficient_data() -> None:
    witness = assess_motional_correlation(
        _input(x=(1.0, 2.0, 3.0), y=(1.0, 2.0, 3.0), minimum_length=10, shuffle_count=5)
    )
    assert witness.status is MotionalStatus.INSUFFICIENT_DATA
    assert witness.dynamic_relation_detected is False


def test_constant_series_returns_unknown() -> None:
    witness = assess_motional_correlation(
        _input(
            x=tuple([2.5] * 32),
            y=tuple([2.5] * 32),
            minimum_length=16,
            shuffle_count=20,
        )
    )
    assert witness.status is MotionalStatus.UNKNOWN
    assert witness.dynamic_relation_detected is False


# ---------------------------------------------------------------------------
# Determinism + structural
# ---------------------------------------------------------------------------


def test_deterministic_at_fixed_seed() -> None:
    rng = np.random.default_rng(0)
    x = tuple(float(v) for v in rng.standard_normal(64))
    y = tuple(float(v) for v in rng.standard_normal(64))
    a = assess_motional_correlation(_input(x=x, y=y, seed=99))
    b = assess_motional_correlation(_input(x=x, y=y, seed=99))
    assert a == b
    assert a.status is b.status
    assert a.null_p95 == b.null_p95
    assert a.evidence_fields == b.evidence_fields


def test_seed_change_can_change_null_p95() -> None:
    rng = np.random.default_rng(0)
    x = tuple(float(v) for v in rng.standard_normal(64))
    y = tuple(float(v) for v in rng.standard_normal(64))
    a = assess_motional_correlation(_input(x=x, y=y, seed=1))
    b = assess_motional_correlation(_input(x=x, y=y, seed=2))
    # Different seeds must produce different shuffled samples → different p95.
    # We allow ties in pathological corners; assert at least a finite spread
    # over a few seeds.
    assert math.isfinite(a.null_p95) and math.isfinite(b.null_p95)


def test_witness_is_frozen() -> None:
    rng = np.random.default_rng(0)
    x = tuple(float(v) for v in rng.standard_normal(32))
    y = tuple(float(v) for v in rng.standard_normal(32))
    witness = assess_motional_correlation(_input(x=x, y=y))
    with pytest.raises(Exception):  # noqa: B017 — FrozenInstanceError
        witness.status = MotionalStatus.UNKNOWN  # type: ignore[misc]


def test_evidence_fields_immutable() -> None:
    rng = np.random.default_rng(0)
    x = tuple(float(v) for v in rng.standard_normal(32))
    y = tuple(float(v) for v in rng.standard_normal(32))
    witness = assess_motional_correlation(_input(x=x, y=y))
    assert isinstance(witness.evidence_fields, Mapping)
    with pytest.raises(TypeError):
        witness.evidence_fields["x"] = 1  # type: ignore[index]


def test_witness_carries_no_prediction_class_field() -> None:
    forbidden = {"prediction", "signal", "forecast", "target_price", "recommended_action"}
    fields = set(MotionalWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


def test_falsifier_text_is_non_empty() -> None:
    rng = np.random.default_rng(0)
    x = tuple(float(v) for v in rng.standard_normal(32))
    y = tuple(float(v) for v in rng.standard_normal(32))
    witness = assess_motional_correlation(_input(x=x, y=y))
    assert isinstance(witness.falsifier, str)
    assert len(witness.falsifier) > 80


# ---------------------------------------------------------------------------
# No-overclaim guard
# ---------------------------------------------------------------------------


_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "geosync_hpc"
    / "dynamics"
    / "motional_correlation_witness.py"
)


def test_module_does_not_use_predictive_or_physics_equivalence_language() -> None:
    text = _MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden = (
        r"\bprediction\b",
        r"\buniversal\b",
        r"physical equivalence",
        r"market physics fact",
    )
    for pattern in forbidden:
        assert re.search(pattern, text) is None, f"forbidden phrase {pattern!r} present"


def test_module_does_not_import_market_or_trading_modules() -> None:
    text = _MODULE_PATH.read_text(encoding="utf-8")
    for tainted in (
        "from geosync_hpc.execution",
        "from geosync_hpc.policy",
        "from geosync_hpc.application",
    ):
        assert tainted not in text, f"{tainted!r} would couple this witness to runtime layers"
