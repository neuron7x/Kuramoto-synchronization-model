# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for geosync_hpc.nulls.dynamic_null_model.

Cycle of falsification (per 7-link doctrine):

  CNS:          intuition that a moving null can absorb a real signal
                if its drift is not bounded.
  Exploration:  4-status decision tree with NULL_DRIFT_EXCEEDED winning
                over OUTSIDE/WITHIN, INSUFFICIENT_HISTORY first, and
                UNKNOWN as the genuine empty-history escape.
  ЦШС artifact: NullInput / NullWitness frozen dataclasses, pure
                deterministic assess_dynamic_null(...).
  Tests:        this file. 9 brief-required scenarios + auxiliary
                structural / determinism / forbidden-phrase tests.
  Falsifier:    inverting the within_bound check (drift > bound) makes
                test_drift_above_bound_returns_null_drift_exceeded fail.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

from geosync_hpc.nulls.dynamic_null_model import (
    NullInput,
    NullStatus,
    NullWitness,
    assess_dynamic_null,
    assess_many,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _input(
    *,
    baseline_series: tuple[float, ...] = (1.0, 1.0, 1.0),
    observed_value: float = 1.0,
    drift_bound: float = 0.0,
    null_tolerance: float = 0.1,
    minimum_history: int = 3,
) -> NullInput:
    return NullInput(
        baseline_series=baseline_series,
        observed_value=observed_value,
        drift_bound=drift_bound,
        null_tolerance=null_tolerance,
        minimum_history=minimum_history,
    )


# ---------------------------------------------------------------------------
# Brief-required scenarios
# ---------------------------------------------------------------------------


def test_static_null_with_zero_drift_bound() -> None:
    """1. drift_bound=0 with constant baseline still classifies signals."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(2.5, 2.5, 2.5),
            observed_value=2.5,
            drift_bound=0.0,
            null_tolerance=0.1,
        )
    )
    assert witness.status is NullStatus.WITHIN_DYNAMIC_NULL
    assert witness.drift_used == 0.0
    assert witness.within_bound is True
    assert witness.null_value == 2.5
    assert witness.observed_value == 2.5


def test_dynamic_matches_static_when_zero_drift() -> None:
    """Static reduction: zero-drift dynamic null matches a static call."""
    series = (3.14, 3.14, 3.14, 3.14)
    dynamic = assess_dynamic_null(
        _input(
            baseline_series=series,
            observed_value=3.20,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=2,
        )
    )
    static = assess_dynamic_null(
        _input(
            baseline_series=series,
            observed_value=3.20,
            drift_bound=0.0,
            null_tolerance=0.1,
            minimum_history=2,
        )
    )
    assert dynamic.status == static.status
    assert dynamic.drift_used == static.drift_used == 0.0


def test_bounded_drift_accepted() -> None:
    """2. drift below bound, signal in band → WITHIN_DYNAMIC_NULL."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 1.05, 1.10),
            observed_value=1.10,
            drift_bound=0.5,
            null_tolerance=0.05,
            minimum_history=3,
        )
    )
    assert witness.status is NullStatus.WITHIN_DYNAMIC_NULL
    assert witness.within_bound is True
    assert math.isclose(witness.drift_used, 0.10)


def test_drift_above_bound_returns_null_drift_exceeded() -> None:
    """3. drift > drift_bound → NULL_DRIFT_EXCEEDED, fail closed."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 1.5, 2.0),
            observed_value=1.95,  # would otherwise be WITHIN
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=3,
        )
    )
    assert witness.status is NullStatus.NULL_DRIFT_EXCEEDED
    assert witness.within_bound is False
    assert witness.drift_used > witness.drift_bound


def test_observed_signal_outside_bounded_null() -> None:
    """4. observed outside null band but drift within bound → OUTSIDE."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 1.05, 1.10),
            observed_value=2.5,
            drift_bound=0.5,
            null_tolerance=0.05,
            minimum_history=3,
        )
    )
    assert witness.status is NullStatus.OUTSIDE_DYNAMIC_NULL
    assert witness.within_bound is True
    assert (
        abs(witness.observed_value - witness.null_value) > witness.evidence_fields["null_tolerance"]
    )


def test_insufficient_history_returns_insufficient_history() -> None:
    """5a. len(history) < minimum_history → INSUFFICIENT_HISTORY."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 1.0),
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=5,
        )
    )
    assert witness.status is NullStatus.INSUFFICIENT_HISTORY


def test_empty_history_with_zero_minimum_returns_unknown() -> None:
    """5b. empty history with minimum_history=0 → UNKNOWN (no null)."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(),
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=0,
        )
    )
    assert witness.status is NullStatus.UNKNOWN


def test_nan_observed_value_rejected() -> None:
    """6a. NaN in observed_value rejected at construction."""
    with pytest.raises(ValueError, match="observed_value must be finite"):
        NullInput(
            baseline_series=(1.0, 1.0),
            observed_value=float("nan"),
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=2,
        )


def test_inf_observed_value_rejected() -> None:
    """6b. +inf in observed_value rejected."""
    with pytest.raises(ValueError, match="observed_value must be finite"):
        NullInput(
            baseline_series=(1.0,),
            observed_value=float("inf"),
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=1,
        )


def test_nan_in_baseline_rejected() -> None:
    """6c. NaN in baseline_series rejected."""
    with pytest.raises(ValueError, match=r"baseline_series\[1\] must be finite"):
        NullInput(
            baseline_series=(1.0, float("nan"), 1.0),
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=3,
        )


def test_nan_drift_bound_rejected() -> None:
    """6d. NaN in drift_bound rejected."""
    with pytest.raises(ValueError, match="drift_bound must be finite"):
        NullInput(
            baseline_series=(1.0,),
            observed_value=1.0,
            drift_bound=float("nan"),
            null_tolerance=0.1,
            minimum_history=1,
        )


def test_nan_null_tolerance_rejected() -> None:
    """6e. NaN in null_tolerance rejected."""
    with pytest.raises(ValueError, match="null_tolerance must be finite"):
        NullInput(
            baseline_series=(1.0,),
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=float("nan"),
            minimum_history=1,
        )


def test_negative_drift_bound_rejected() -> None:
    """7. negative drift_bound rejected at construction."""
    with pytest.raises(ValueError, match="drift_bound must be >= 0"):
        NullInput(
            baseline_series=(1.0,),
            observed_value=1.0,
            drift_bound=-0.01,
            null_tolerance=0.1,
            minimum_history=1,
        )


def test_negative_null_tolerance_rejected() -> None:
    """Auxiliary: negative null_tolerance rejected."""
    with pytest.raises(ValueError, match="null_tolerance must be >= 0"):
        NullInput(
            baseline_series=(1.0,),
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=-0.01,
            minimum_history=1,
        )


def test_negative_minimum_history_rejected() -> None:
    """Auxiliary: negative minimum_history rejected."""
    with pytest.raises(ValueError, match="minimum_history must be >= 0"):
        NullInput(
            baseline_series=(1.0,),
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=-1,
        )


def test_baseline_series_must_be_tuple() -> None:
    """Auxiliary: list passed as baseline rejected."""
    with pytest.raises(TypeError, match="baseline_series must be a tuple"):
        NullInput(
            baseline_series=[1.0, 1.0],  # type: ignore[arg-type]
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=2,
        )


def test_bool_observed_value_rejected() -> None:
    """Auxiliary: bool is not int for our purposes."""
    with pytest.raises(TypeError, match="observed_value must be a finite float"):
        NullInput(
            baseline_series=(1.0,),
            observed_value=True,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=1,
        )


def test_bool_minimum_history_rejected() -> None:
    """Auxiliary: bool not accepted as int for minimum_history."""
    with pytest.raises(TypeError, match="minimum_history must be a non-negative int"):
        NullInput(
            baseline_series=(1.0,),
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=True,
        )


def test_deterministic_output() -> None:
    """8. assess_dynamic_null is byte-deterministic for identical inputs."""
    args = dict(
        baseline_series=(1.0, 1.05, 1.10, 1.20),
        observed_value=1.18,
        drift_bound=0.5,
        null_tolerance=0.05,
        minimum_history=3,
    )
    a = assess_dynamic_null(NullInput(**args))  # type: ignore[arg-type]
    b = assess_dynamic_null(NullInput(**args))  # type: ignore[arg-type]
    assert a == b
    assert a.status is b.status
    assert a.reason == b.reason
    assert a.drift_used == b.drift_used
    assert a.null_value == b.null_value
    assert a.evidence_fields == b.evidence_fields


# ---------------------------------------------------------------------------
# Priority interactions
# ---------------------------------------------------------------------------


def test_drift_exceeded_takes_precedence_over_outside_signal() -> None:
    """An out-of-band signal with a blown null still classifies as drift."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 5.0),
            observed_value=99.0,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=2,
        )
    )
    assert witness.status is NullStatus.NULL_DRIFT_EXCEEDED


def test_insufficient_history_takes_precedence_over_drift() -> None:
    """A short history with apparent drift still classifies as insufficient."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 5.0),
            observed_value=1.0,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=10,
        )
    )
    assert witness.status is NullStatus.INSUFFICIENT_HISTORY


def test_within_band_at_exact_tolerance() -> None:
    """Equality at the tolerance edge passes (within band).

    Uses an exactly-representable binary fraction to avoid the float
    drift that makes 1.1 - 1.0 land at 0.10000000000000009.
    """
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 1.0, 1.0),
            observed_value=1.0625,
            drift_bound=0.0,
            null_tolerance=0.0625,
            minimum_history=3,
        )
    )
    assert witness.status is NullStatus.WITHIN_DYNAMIC_NULL


def test_drift_at_exact_bound_within() -> None:
    """Equality at the drift bound counts as within bound."""
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 1.5),
            observed_value=1.5,
            drift_bound=0.5,
            null_tolerance=0.1,
            minimum_history=2,
        )
    )
    assert witness.status is NullStatus.WITHIN_DYNAMIC_NULL
    assert witness.within_bound is True
    assert math.isclose(witness.drift_used, 0.5)


# ---------------------------------------------------------------------------
# Witness structural tests
# ---------------------------------------------------------------------------


def test_witness_is_frozen_dataclass() -> None:
    """The witness is immutable; assignment raises."""
    witness = assess_dynamic_null(_input())
    with pytest.raises(Exception):  # noqa: B017 — dataclasses raise FrozenInstanceError
        witness.status = NullStatus.UNKNOWN  # type: ignore[misc]


def test_witness_has_required_fields() -> None:
    """Brief-required witness fields are all present."""
    witness = assess_dynamic_null(_input())
    required = {
        "status",
        "null_value",
        "observed_value",
        "drift_used",
        "drift_bound",
        "within_bound",
        "reason",
        "falsifier",
    }
    assert required.issubset(set(NullWitness.__dataclass_fields__.keys()))
    for field_name in required:
        assert hasattr(witness, field_name)


def test_falsifier_text_is_non_empty() -> None:
    witness = assess_dynamic_null(_input())
    assert isinstance(witness.falsifier, str)
    assert len(witness.falsifier) > 80


def test_evidence_fields_are_immutable_mapping() -> None:
    witness = assess_dynamic_null(_input())
    assert isinstance(witness.evidence_fields, Mapping)
    with pytest.raises(TypeError):
        witness.evidence_fields["x"] = 1  # type: ignore[index]


def test_evidence_carries_decision_inputs() -> None:
    witness = assess_dynamic_null(
        _input(
            baseline_series=(1.0, 1.05, 1.10),
            observed_value=1.10,
            drift_bound=0.5,
            null_tolerance=0.05,
            minimum_history=3,
        )
    )
    ev = witness.evidence_fields
    assert ev["history_len"] == 3
    assert ev["minimum_history"] == 3
    assert math.isclose(ev["drift_used"], 0.10)
    assert ev["drift_bound"] == 0.5
    assert ev["null_tolerance"] == 0.05
    assert math.isclose(ev["null_value"], 1.10)
    assert math.isclose(ev["observed_value"], 1.10)


def test_witness_carries_no_prediction_class_field() -> None:
    """Witness must not carry a forecast-shaped field."""
    forbidden = {
        "prediction",
        "signal",
        "forecast",
        "target_price",
        "recommended_action",
    }
    fields = set(NullWitness.__dataclass_fields__.keys())
    assert fields.isdisjoint(forbidden)


# ---------------------------------------------------------------------------
# No-overclaim guard
# ---------------------------------------------------------------------------


_MODULE_PATH = (
    Path(__file__).resolve().parents[3] / "geosync_hpc" / "nulls" / "dynamic_null_model.py"
)


def test_module_does_not_use_predictive_or_physics_equivalence_language() -> None:
    """9. No predictive / universal / physical-equivalence language allowed."""
    text = _MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden_phrases: tuple[str, ...] = (
        r"\bprediction\b",
        r"\buniversal\b",
        r"physical equivalence",
        r"market physics fact",
    )
    for pattern in forbidden_phrases:
        assert (
            re.search(pattern, text) is None
        ), f"forbidden phrase {pattern!r} found in module text"


def test_module_does_not_import_market_or_trading_modules() -> None:
    """Structural decoupling: no leakage from this null model into market code."""
    text = _MODULE_PATH.read_text(encoding="utf-8")
    for tainted in ("from geosync_hpc.execution", "from geosync_hpc.policy"):
        assert (
            tainted not in text
        ), f"{tainted!r} import would couple this null model to trading code"


# ---------------------------------------------------------------------------
# Batch helper
# ---------------------------------------------------------------------------


def test_assess_many_preserves_order_and_results() -> None:
    inputs = (
        _input(),
        _input(observed_value=99.0, drift_bound=0.5, null_tolerance=0.05),
        _input(baseline_series=(1.0, 5.0), drift_bound=0.5, minimum_history=2),
    )
    out = assess_many(inputs)
    assert len(out) == 3
    assert out[0].status is NullStatus.WITHIN_DYNAMIC_NULL
    # second has out-of-band signal but zero drift bound + non-constant series? — still
    # constant (1,1,1), so the comparison kicks in:
    assert out[1].status is NullStatus.OUTSIDE_DYNAMIC_NULL
    assert out[2].status is NullStatus.NULL_DRIFT_EXCEEDED
