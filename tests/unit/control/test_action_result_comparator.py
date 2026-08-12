# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Typed invariant tests for the comparator surface."""

from __future__ import annotations

import dataclasses
import math
from typing import Any

import pytest

from geosync_hpc import control as control_pkg
from geosync_hpc.control import (
    ActionResultComparator,
    ActionResultEvidence,
    ActionResultStatus,
    ActionResultWitness,
    ExpectedResultModel,
    ObservedActionResult,
    accept_action_result,
    compare_action_result,
    seal_action_result_evidence,
)


def _field_names(model: Any) -> set[str]:
    return {field.name for field in dataclasses.fields(model)}


def _make_expected(
    *,
    action_id: str = "act-1",
    expected_result: tuple[float, ...] = (1.0, 0.0, -1.0),
    expected_result_variance: tuple[float, ...] | None = None,
    error_threshold: float = 0.5,
    rollback_threshold: float = 1.0,
    model_created_seq: int = 1,
    action_started_seq: int = 2,
) -> ExpectedResultModel:
    return ExpectedResultModel(
        action_id=action_id,
        action_type="trade",
        expected_result=expected_result,
        expected_result_variance=expected_result_variance,
        context_signature=(0.1, 0.2, 0.3),
        model_created_seq=model_created_seq,
        action_started_seq=action_started_seq,
        error_threshold=error_threshold,
        rollback_threshold=rollback_threshold,
    )


def _make_observed(
    *,
    action_id: str = "act-1",
    observed_result: tuple[float, ...] | None = (1.0, 0.0, -1.0),
    reverse_afferentation_present: bool = True,
    observed_seq: int = 3,
) -> ObservedActionResult:
    return ObservedActionResult(
        action_id=action_id,
        observed_seq=observed_seq,
        observed_result=observed_result,
        reverse_afferentation_present=reverse_afferentation_present,
    )


def test_01_missing_expected_returns_invalid_input() -> None:
    witness = accept_action_result(None, _make_observed())

    assert witness.status is ActionResultStatus.INVALID_INPUT
    assert witness.accepted is False
    assert witness.rollback_required is True
    assert witness.reason.startswith("INVALID_EXPECTED_MODEL")


def test_01c_comparator_facade_and_alias_match_function() -> None:
    expected = _make_expected()
    observed = _make_observed()
    direct = accept_action_result(expected, observed)
    comparator = ActionResultComparator()

    assert comparator.compare(expected, observed) == direct
    assert compare_action_result(expected, observed) == direct
    assert comparator.seal_evidence(expected, observed).status is direct.status


def test_01d_action_result_evidence_is_deterministic_and_tamper_evident() -> None:
    expected = _make_expected(expected_result_variance=(1.0, 4.0, 9.0))
    observed = _make_observed(observed_result=(1.1, 0.2, -1.3))
    witness = accept_action_result(expected, observed)

    sealed = seal_action_result_evidence(expected, observed, witness)
    replayed = seal_action_result_evidence(expected, observed)
    changed = seal_action_result_evidence(
        expected,
        _make_observed(observed_result=(1.2, 0.2, -1.3)),
    )

    assert isinstance(sealed, ActionResultEvidence)
    assert sealed == replayed
    assert sealed.schema_version == "AAR-PRO-V1-EVIDENCE"
    assert sealed.expected_action_id == expected.action_id
    assert sealed.observed_action_id == observed.action_id
    assert sealed.status is witness.status
    assert len(sealed.expected_digest) == 64
    assert len(sealed.observed_digest) == 64
    assert len(sealed.witness_digest) == 64
    assert len(sealed.evidence_digest) == 64
    assert changed.observed_digest != sealed.observed_digest
    assert changed.evidence_digest != sealed.evidence_digest


@pytest.mark.parametrize(
    ("created_seq", "started_seq"),
    [(2, 2), (3, 2)],
)
def test_02_model_seq_must_be_strictly_less_than_action_seq(
    created_seq: int,
    started_seq: int,
) -> None:
    with pytest.raises(ValueError, match="SEQUENCE_ORDER_INVALID"):
        _make_expected(model_created_seq=created_seq, action_started_seq=started_seq)


@pytest.mark.parametrize(
    ("started_seq", "observed_seq"),
    [(5, 5), (5, 4)],
)
def test_03_observed_seq_must_be_strictly_greater_than_action_seq(
    started_seq: int,
    observed_seq: int,
) -> None:
    expected = _make_expected(model_created_seq=1, action_started_seq=started_seq)
    observed = _make_observed(observed_seq=observed_seq)
    witness = accept_action_result(expected, observed)

    assert witness.status is ActionResultStatus.INVALID_INPUT
    assert witness.rollback_required is True
    assert witness.reason.startswith("SEQUENCE_ORDER_INVALID")


def test_04_exact_match_returns_sanctioned_and_dissolved() -> None:
    witness = accept_action_result(_make_expected(), _make_observed())

    assert witness.status is ActionResultStatus.SANCTIONED_MATCH
    assert witness.accepted is True
    assert witness.dissolved is True
    assert witness.update_required is False
    assert witness.rollback_required is False
    assert witness.outcome_prediction_error == 0.0
    assert witness.comparator_error == 0.0


def test_05_medium_error_returns_update_required() -> None:
    expected = _make_expected(error_threshold=0.5, rollback_threshold=2.0)
    observed = _make_observed(observed_result=(1.7, 0.0, -1.0))
    witness = accept_action_result(expected, observed)

    assert witness.status is ActionResultStatus.UPDATE_REQUIRED
    assert witness.accepted is True
    assert witness.dissolved is False
    assert witness.update_required is True
    assert witness.rollback_required is False
    assert witness.next_context_expansion_required is True


def test_06_large_error_returns_rollback_required() -> None:
    expected = _make_expected(error_threshold=0.5, rollback_threshold=1.0)
    observed = _make_observed(observed_result=(3.5, 0.0, -1.0))
    witness = accept_action_result(expected, observed)

    assert witness.status is ActionResultStatus.ROLLBACK_REQUIRED
    assert witness.rollback_required is True
    assert witness.update_required is False
    assert witness.inhibit_repetition is True


def test_07_missing_reverse_afferentation() -> None:
    expected = _make_expected()
    observed = _make_observed(reverse_afferentation_present=False)
    witness = accept_action_result(expected, observed)

    assert witness.status is ActionResultStatus.INSUFFICIENT_REVERSE_AFFERENTATION
    assert witness.accepted is False
    assert witness.reason.startswith("MISSING_REVERSE_AFFERENTATION")


def test_08_missing_observed_result() -> None:
    expected = _make_expected()
    observed = _make_observed(observed_result=None)
    witness = accept_action_result(expected, observed)

    assert witness.status is ActionResultStatus.INSUFFICIENT_OBSERVATION
    assert witness.accepted is False
    assert witness.reason.startswith("MISSING_OBSERVATION")


def test_09_action_id_mismatch_returns_action_mismatch() -> None:
    expected = _make_expected(action_id="alpha")
    observed = _make_observed(action_id="beta")
    witness = accept_action_result(expected, observed)

    assert witness.status is ActionResultStatus.ACTION_MISMATCH
    assert witness.rollback_required is True
    assert witness.update_required is False
    assert witness.reason.startswith("ACTION_ID_MISMATCH")


def test_13_raw_ope_is_euclidean_norm() -> None:
    expected = _make_expected(
        expected_result=(0.0, 0.0, 0.0),
        error_threshold=10.0,
        rollback_threshold=10.0,
    )
    observed = _make_observed(observed_result=(3.0, 4.0, 0.0))
    witness = accept_action_result(expected, observed)

    assert witness.outcome_prediction_error is not None
    assert math.isclose(witness.outcome_prediction_error, 5.0, abs_tol=1e-12)


def test_14b_precision_inversion_is_falsifiable() -> None:
    variance = (1.0, 4.0)
    observed = (1.0, 4.0)
    expected_pwope = math.sqrt(5.0)
    inverted_pwope = math.sqrt(65.0)
    expected = _make_expected(
        expected_result=(0.0, 0.0),
        expected_result_variance=variance,
        error_threshold=100.0,
        rollback_threshold=100.0,
    )
    witness = accept_action_result(expected, _make_observed(observed_result=observed))

    assert witness.precision_weighted_outcome_error is not None
    assert math.isclose(
        witness.precision_weighted_outcome_error,
        expected_pwope,
        abs_tol=1e-9,
    )
    assert not math.isclose(
        witness.precision_weighted_outcome_error,
        inverted_pwope,
        abs_tol=1e-9,
    )


def test_15_comparator_error_uses_pwope_when_variance_present() -> None:
    expected = _make_expected(
        expected_result=(0.0, 0.0),
        expected_result_variance=(1.0, 4.0),
        error_threshold=10.0,
        rollback_threshold=10.0,
    )
    observed = _make_observed(observed_result=(2.0, 2.0))
    witness = accept_action_result(expected, observed)

    assert witness.precision_weighted_outcome_error is not None
    assert witness.comparator_error is not None
    assert math.isclose(
        witness.comparator_error,
        witness.precision_weighted_outcome_error,
        abs_tol=1e-12,
    )


def test_16_comparator_error_uses_raw_ope_when_variance_none() -> None:
    expected = _make_expected(
        expected_result=(0.0, 0.0),
        expected_result_variance=None,
        error_threshold=10.0,
        rollback_threshold=10.0,
    )
    observed = _make_observed(observed_result=(3.0, 4.0))
    witness = accept_action_result(expected, observed)

    assert witness.precision_weighted_outcome_error is None
    assert witness.outcome_prediction_error is not None
    assert witness.comparator_error is not None
    assert math.isclose(
        witness.comparator_error,
        witness.outcome_prediction_error,
        abs_tol=1e-12,
    )


def test_19_zero_variance_rejected() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        _make_expected(
            expected_result=(0.0, 0.0),
            expected_result_variance=(1.0, 0.0),
        )


def test_20_negative_variance_rejected() -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        _make_expected(
            expected_result=(0.0, 0.0),
            expected_result_variance=(1.0, -0.5),
        )


def test_24_witness_is_frozen() -> None:
    witness = accept_action_result(_make_expected(), _make_observed())

    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(witness, "status", ActionResultStatus.UPDATE_REQUIRED)


def test_26_no_created_before_action_field() -> None:
    assert "created_before_action" not in _field_names(ExpectedResultModel)


def test_27_no_prior_confidence_field() -> None:
    assert "prior_confidence" not in _field_names(ExpectedResultModel)
    assert "prior_confidence" not in _field_names(ActionResultWitness)


def test_30_no_forecast_or_trading_fields() -> None:
    forbidden = {"forecast", "trading_signal", "biological_equivalence"}

    for cls in (ExpectedResultModel, ObservedActionResult, ActionResultWitness):
        names = _field_names(cls)
        assert names.isdisjoint(forbidden), f"{cls.__name__} has forbidden field"


def test_33_comparator_error_at_rollback_threshold_is_rollback() -> None:
    expected = _make_expected(error_threshold=0.5, rollback_threshold=1.0)
    observed = _make_observed(observed_result=(2.0, 0.0, -1.0))
    witness = accept_action_result(expected, observed)

    assert witness.comparator_error is not None
    assert math.isclose(witness.comparator_error, 1.0, abs_tol=1e-12)
    assert witness.status is ActionResultStatus.ROLLBACK_REQUIRED


def test_34_comparator_error_at_error_threshold_is_sanctioned() -> None:
    expected = _make_expected(error_threshold=0.5, rollback_threshold=2.0)
    observed = _make_observed(observed_result=(1.5, 0.0, -1.0))
    witness = accept_action_result(expected, observed)

    assert witness.comparator_error is not None
    assert math.isclose(witness.comparator_error, 0.5, abs_tol=1e-12)
    assert witness.status is ActionResultStatus.SANCTIONED_MATCH


def test_public_surface_unchanged() -> None:
    comparator_surface = {
        "ActionResultComparator",
        "ActionResultEvidence",
        "ActionResultStatus",
        "ActionResultWitness",
        "ExpectedResultModel",
        "ObservedActionResult",
        "accept_action_result",
        "compare_action_result",
        "seal_action_result_evidence",
    }

    assert comparator_surface.issubset(set(control_pkg.__all__))
