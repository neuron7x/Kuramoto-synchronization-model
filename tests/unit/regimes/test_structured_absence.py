"""Tests for ``geosync_hpc.regimes.structured_absence`` (P2).

Contract under test:

  Absence becomes evidence only when coverage is sufficient AND
  selection bias is absent AND the region is actually observed empty.

  "missing data = true absence" is the lie this module blocks.

This file ships the ten tests required by the PR-#454 brief plus a
small group of structural assertions that protect the contract from
drift:

   1.  full coverage + no bias + empty region → TRUE_ABSENCE
   2.  low coverage → INSUFFICIENT_COVERAGE
   3.  active selection bias → SELECTION_BIAS
   4.  zero sample count → INSUFFICIENT_COVERAGE
   5.  non-empty candidate region cannot be TRUE_ABSENCE (UNKNOWN)
   6.  coverage exactly at threshold → TRUE_ABSENCE (>=, not >)
   7.  coverage just below threshold → INSUFFICIENT_COVERAGE
   8.  NaN / inf rejected at construction
   9.  invalid threshold rejected at construction
  10.  no-overclaim: module/docstring contains no
        "law", "prediction", "physical equivalence",
        "market physics fact"
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from geosync_hpc.regimes import structured_absence
from geosync_hpc.regimes.structured_absence import (
    AbsenceInput,
    AbsenceStatus,
    AbsenceWitness,
    assess_absence,
    assess_many,
)

# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def _input(
    *,
    observed_state_space: frozenset[object] = frozenset({"a", "b", "c"}),
    candidate_empty_region: frozenset[object] = frozenset({"x", "y"}),
    coverage_ratio: float = 0.95,
    selection_bias_flags: tuple[str, ...] = (),
    sample_count: int = 100,
    minimum_coverage_threshold: float = 0.80,
) -> AbsenceInput:
    return AbsenceInput(
        observed_state_space=observed_state_space,
        candidate_empty_region=candidate_empty_region,
        coverage_ratio=coverage_ratio,
        selection_bias_flags=selection_bias_flags,
        sample_count=sample_count,
        minimum_coverage_threshold=minimum_coverage_threshold,
    )


# ---------------------------------------------------------------------------
# 1. full coverage + no bias + empty region → TRUE_ABSENCE
# ---------------------------------------------------------------------------


def test_true_absence_when_all_conditions_satisfied() -> None:
    witness = assess_absence(_input(coverage_ratio=1.0))
    assert witness.status is AbsenceStatus.TRUE_ABSENCE
    assert witness.accepted_as_absence is True
    assert witness.reason == "OK_TRUE_ABSENCE"
    assert witness.selection_bias_present is False
    assert witness.coverage_ratio == 1.0


# ---------------------------------------------------------------------------
# 2. low coverage → INSUFFICIENT_COVERAGE
# ---------------------------------------------------------------------------


def test_low_coverage_returns_insufficient_coverage() -> None:
    witness = assess_absence(_input(coverage_ratio=0.40, minimum_coverage_threshold=0.80))
    assert witness.status is AbsenceStatus.INSUFFICIENT_COVERAGE
    assert witness.accepted_as_absence is False
    assert witness.reason == "COVERAGE_BELOW_THRESHOLD"


# ---------------------------------------------------------------------------
# 3. active selection bias → SELECTION_BIAS
# ---------------------------------------------------------------------------


def test_active_selection_bias_returns_selection_bias() -> None:
    witness = assess_absence(_input(selection_bias_flags=("survivorship",)))
    assert witness.status is AbsenceStatus.SELECTION_BIAS
    assert witness.accepted_as_absence is False
    assert witness.reason == "SELECTION_BIAS_ACTIVE"
    assert witness.selection_bias_present is True


def test_selection_bias_takes_precedence_over_low_coverage() -> None:
    """Bias is louder than low coverage in the priority order. Even if
    coverage is bad, the bias signal must surface — otherwise an
    operator might fix coverage and falsely conclude the absence is
    valid while bias still applies."""
    witness = assess_absence(
        _input(
            coverage_ratio=0.10,
            selection_bias_flags=("look-ahead",),
            minimum_coverage_threshold=0.80,
        )
    )
    assert witness.status is AbsenceStatus.SELECTION_BIAS


# ---------------------------------------------------------------------------
# 4. zero sample count → INSUFFICIENT_COVERAGE
# ---------------------------------------------------------------------------


def test_zero_sample_count_returns_insufficient_coverage() -> None:
    witness = assess_absence(_input(sample_count=0))
    assert witness.status is AbsenceStatus.INSUFFICIENT_COVERAGE
    assert witness.reason == "INSUFFICIENT_SAMPLES"
    assert witness.accepted_as_absence is False


def test_zero_sample_count_overrides_other_signals() -> None:
    """No data = no inference, regardless of any other field."""
    witness = assess_absence(
        _input(
            sample_count=0,
            coverage_ratio=1.0,
            selection_bias_flags=("survivorship",),
        )
    )
    assert witness.status is AbsenceStatus.INSUFFICIENT_COVERAGE
    assert witness.reason == "INSUFFICIENT_SAMPLES"


# ---------------------------------------------------------------------------
# 5. non-empty candidate region cannot be TRUE_ABSENCE
# ---------------------------------------------------------------------------


def test_non_empty_region_returns_unknown_not_true_absence() -> None:
    """Observed points within the candidate empty region falsify
    emptiness directly. The witness MUST return UNKNOWN with reason
    REGION_NOT_EMPTY rather than TRUE_ABSENCE."""
    witness = assess_absence(
        _input(
            observed_state_space=frozenset({"a", "b", "x"}),
            candidate_empty_region=frozenset({"x", "y"}),
            coverage_ratio=1.0,
        )
    )
    assert witness.status is AbsenceStatus.UNKNOWN
    assert witness.reason == "REGION_NOT_EMPTY"
    assert witness.accepted_as_absence is False


# ---------------------------------------------------------------------------
# 6. coverage exactly at threshold follows documented contract (>=, passes)
# ---------------------------------------------------------------------------


def test_coverage_at_threshold_passes() -> None:
    witness = assess_absence(_input(coverage_ratio=0.80, minimum_coverage_threshold=0.80))
    assert witness.status is AbsenceStatus.TRUE_ABSENCE


# ---------------------------------------------------------------------------
# 7. coverage just below threshold fails
# ---------------------------------------------------------------------------


def test_coverage_just_below_threshold_fails() -> None:
    witness = assess_absence(
        _input(
            coverage_ratio=0.7999999999,
            minimum_coverage_threshold=0.80,
        )
    )
    assert witness.status is AbsenceStatus.INSUFFICIENT_COVERAGE


# ---------------------------------------------------------------------------
# 8. NaN / inf rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_nan_inf_coverage_rejected(bad_value: float) -> None:
    with pytest.raises(ValueError, match="coverage_ratio must be finite"):
        _input(coverage_ratio=bad_value)


@pytest.mark.parametrize(
    "bad_value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_nan_inf_threshold_rejected(bad_value: float) -> None:
    with pytest.raises(ValueError, match="minimum_coverage_threshold must be finite"):
        _input(minimum_coverage_threshold=bad_value)


def test_negative_sample_count_rejected() -> None:
    with pytest.raises(ValueError, match="sample_count must be >= 0"):
        _input(sample_count=-1)


def test_non_int_sample_count_rejected() -> None:
    with pytest.raises(TypeError, match="sample_count must be"):
        AbsenceInput(
            observed_state_space=frozenset({"a"}),
            candidate_empty_region=frozenset({"x"}),
            coverage_ratio=0.9,
            selection_bias_flags=(),
            sample_count=3.5,  # type: ignore[arg-type]
            minimum_coverage_threshold=0.8,
        )


def test_boolean_sample_count_rejected() -> None:
    """Booleans are subclasses of int in Python; accept-on-purpose
    surfaces a typo-class regression."""
    with pytest.raises(TypeError):
        AbsenceInput(
            observed_state_space=frozenset({"a"}),
            candidate_empty_region=frozenset({"x"}),
            coverage_ratio=0.9,
            selection_bias_flags=(),
            sample_count=True,
            minimum_coverage_threshold=0.8,
        )


# ---------------------------------------------------------------------------
# 9. invalid threshold / coverage range rejected
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [-0.01, -1.0, 1.01, 2.0, 100.0])
def test_invalid_threshold_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="minimum_coverage_threshold must be in"):
        _input(minimum_coverage_threshold=bad)


@pytest.mark.parametrize("bad", [-0.01, -1.0, 1.01, 2.0, 100.0])
def test_invalid_coverage_rejected(bad: float) -> None:
    with pytest.raises(ValueError, match="coverage_ratio must be in"):
        _input(coverage_ratio=bad)


def test_empty_string_bias_flag_rejected() -> None:
    with pytest.raises(ValueError, match="selection_bias_flags entries"):
        _input(selection_bias_flags=("",))


def test_observed_state_space_must_be_frozenset() -> None:
    with pytest.raises(TypeError, match="observed_state_space must be"):
        AbsenceInput(
            observed_state_space=["a", "b"],  # type: ignore[arg-type]
            candidate_empty_region=frozenset({"x"}),
            coverage_ratio=0.9,
            selection_bias_flags=(),
            sample_count=10,
            minimum_coverage_threshold=0.8,
        )


# ---------------------------------------------------------------------------
# 10. no-overclaim: module text contains no forbidden phrasing
# ---------------------------------------------------------------------------


_MODULE_PATH = Path(structured_absence.__file__)

# Brief-required forbidden phrases — exactly four. Substring match,
# case-insensitive. "law" needs word-boundary semantics because innocent
# words (lawful, lawyer) legitimately contain it.
_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "law",
    "prediction",
    "physical equivalence",
    "market physics fact",
)


@pytest.mark.parametrize("phrase", _FORBIDDEN_PHRASES)
def test_module_body_has_no_overclaim_phrasing(phrase: str) -> None:
    """The module's source MUST NOT contain any of the brief's
    forbidden phrasings — neither in code nor in docstring."""
    text = _MODULE_PATH.read_text(encoding="utf-8").lower()
    if phrase == "law":
        import re

        pattern = re.compile(r"\blaw\b")
        assert not pattern.search(text), (
            "module contains forbidden standalone word 'law'; "
            "rephrase or move out of the runtime module."
        )
    else:
        assert phrase not in text, f"module contains forbidden phrasing: {phrase!r}"


# ---------------------------------------------------------------------------
# Auxiliary structural tests
# ---------------------------------------------------------------------------


def test_witness_is_frozen() -> None:
    """A returned witness must be immutable so callers cannot
    retroactively edit a verdict."""
    witness = assess_absence(_input())
    with pytest.raises(Exception):
        witness.status = AbsenceStatus.UNKNOWN  # type: ignore[misc]


def test_pure_function_no_side_effects_across_calls() -> None:
    """Calling assess_absence twice on the same input must produce
    structurally identical witnesses."""
    inp = _input()
    a = assess_absence(inp)
    b = assess_absence(inp)
    # Compare field-by-field; dataclass eq does not work because the
    # MappingProxyType evidence_fields are equal-by-value but pickled
    # differently. We assert explicit field equality below.
    assert a.status == b.status
    assert a.reason == b.reason
    assert a.accepted_as_absence == b.accepted_as_absence
    assert a.coverage_ratio == b.coverage_ratio
    assert a.selection_bias_present == b.selection_bias_present
    assert a.sample_count == b.sample_count
    assert dict(a.evidence_fields) == dict(b.evidence_fields)


def test_assess_many_preserves_order() -> None:
    inputs = [
        _input(coverage_ratio=1.0),
        _input(coverage_ratio=0.1, minimum_coverage_threshold=0.8),
        _input(selection_bias_flags=("look-ahead",)),
    ]
    witnesses = assess_many(inputs)
    assert len(witnesses) == 3
    assert witnesses[0].status is AbsenceStatus.TRUE_ABSENCE
    assert witnesses[1].status is AbsenceStatus.INSUFFICIENT_COVERAGE
    assert witnesses[2].status is AbsenceStatus.SELECTION_BIAS


def test_witness_carries_no_prediction_class_field() -> None:
    """The absence-inference contract: a witness is evidence
    classification, not a prediction. The witness MUST NOT carry any
    field name that would let a downstream consumer mistake absence
    for a trading signal."""
    forbidden_field_names = {
        "prediction",
        "predicted",
        "signal",
        "forecast",
        "score",
        "direction",
        "recommendation",
        "side",
        "trade",
        "trade_signal",
        "buy",
        "sell",
        "alpha",
        "expected_return",
    }
    from dataclasses import fields

    actual = {f.name for f in fields(AbsenceWitness)}
    overlap = actual & forbidden_field_names
    assert not overlap, f"AbsenceWitness leaks prediction-class fields: {overlap}"


def test_evidence_fields_are_immutable() -> None:
    witness = assess_absence(_input())
    with pytest.raises(TypeError):
        witness.evidence_fields["new"] = "x"  # type: ignore[index]


def test_module_does_not_import_market_or_trading_modules() -> None:
    """Defensive: the structured-absence module must not pull in any
    market / trading module at import time. If it does, the engineering
    analog has leaked into business logic — exactly the inflation this
    module is supposed to prevent."""
    text = _MODULE_PATH.read_text(encoding="utf-8")
    forbidden_imports = (
        "from execution",
        "from backtest",
        "from analytics.signals",
        "from core.strategies",
        "import execution",
        "import backtest",
    )
    for stmt in forbidden_imports:
        assert stmt not in text, (
            f"structured_absence.py imports {stmt!r}; the engineering "
            f"analog must stay decoupled from market / trading layers."
        )


def test_zero_observed_state_space_with_full_coverage_passes() -> None:
    """A region cannot contain anything if there are no observations,
    AND coverage is full, AND samples are present. That is the
    canonical TRUE_ABSENCE shape — most extreme case."""
    witness = assess_absence(
        _input(
            observed_state_space=frozenset(),
            candidate_empty_region=frozenset({"x"}),
            coverage_ratio=1.0,
            sample_count=42,
        )
    )
    assert witness.status is AbsenceStatus.TRUE_ABSENCE


def test_falsifier_text_is_present_in_every_witness() -> None:
    for witness in assess_many(
        [
            _input(coverage_ratio=1.0),
            _input(sample_count=0),
            _input(selection_bias_flags=("x",)),
            _input(coverage_ratio=0.1, minimum_coverage_threshold=0.5),
            _input(
                observed_state_space=frozenset({"x"}),
                candidate_empty_region=frozenset({"x"}),
            ),
        ]
    ):
        assert witness.falsifier
        assert "TRUE_ABSENCE" in witness.falsifier


def test_evidence_fields_record_observed_count_in_region() -> None:
    """The witness exposes the actual count of observed points inside
    the candidate region. This is the load-bearing evidence the rule
    'non-empty region cannot be TRUE_ABSENCE' rests on."""
    witness = assess_absence(
        _input(
            observed_state_space=frozenset({"a", "x", "y"}),
            candidate_empty_region=frozenset({"x", "y", "z"}),
            coverage_ratio=1.0,
        )
    )
    assert witness.status is AbsenceStatus.UNKNOWN
    assert witness.evidence_fields["observed_count_in_region"] == 2


def test_finite_threshold_zero_is_admissible() -> None:
    """A threshold of 0.0 means 'any coverage qualifies'. Edge case;
    any non-trivial coverage passes."""
    witness = assess_absence(_input(coverage_ratio=0.0, minimum_coverage_threshold=0.0))
    # coverage 0.0 >= threshold 0.0, no bias, region empty → TRUE_ABSENCE
    assert witness.status is AbsenceStatus.TRUE_ABSENCE


def test_threshold_one_demands_perfect_coverage() -> None:
    """A threshold of 1.0 means 'only perfect coverage counts'."""
    near = assess_absence(_input(coverage_ratio=0.999999, minimum_coverage_threshold=1.0))
    perfect = assess_absence(_input(coverage_ratio=1.0, minimum_coverage_threshold=1.0))
    assert near.status is AbsenceStatus.INSUFFICIENT_COVERAGE
    assert perfect.status is AbsenceStatus.TRUE_ABSENCE


def test_non_finite_value_through_arithmetic_blocked() -> None:
    """Even when coverage_ratio is computed (e.g. division), passing a
    non-finite result must fail at construction. This test plants
    `0.0 / 0.0` which yields nan, and asserts the input rejects it."""
    bad = float("nan")
    assert math.isnan(bad)
    with pytest.raises(ValueError, match="coverage_ratio must be finite"):
        _input(coverage_ratio=bad)
