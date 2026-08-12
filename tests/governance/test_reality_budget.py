# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for tools/governance/reality_budget.py."""

from __future__ import annotations

import pytest

from tools.governance.reality_budget import (
    BudgetInput,
    BudgetVerdict,
    evaluate,
)


def _input(**overrides: object) -> BudgetInput:
    base: dict[str, object] = {
        "files_changed": 2,
        "new_loc": 100,
        "new_tests": 50,
        "new_validators": 0,
        "new_docs": 0,
        "new_claims": 0,
        "falsifiers_added": 1,
        "known_lies_blocked": ("test lie",),
        "acceptable_exception_reason": "",
    }
    base.update(overrides)
    return BudgetInput(**base)  # type: ignore[arg-type]


def test_small_pr_with_lie_and_falsifier_within_budget() -> None:
    witness = evaluate(_input())
    assert witness.verdict is BudgetVerdict.WITHIN_BUDGET


def test_large_pr_without_lie_needs_split() -> None:
    """Falsifier surface from brief: large PR with no named lie → NEEDS_SPLIT."""
    witness = evaluate(_input(new_loc=1500, files_changed=20, known_lies_blocked=()))
    assert witness.verdict is BudgetVerdict.NEEDS_SPLIT
    assert any("no named lie" in r for r in witness.reasons)


def test_large_pr_with_thin_tests_needs_split() -> None:
    witness = evaluate(_input(new_loc=2000, new_tests=100, files_changed=15))
    assert witness.verdict is BudgetVerdict.NEEDS_SPLIT
    assert any("tests/loc" in r for r in witness.reasons)


def test_large_pr_without_falsifier_needs_split() -> None:
    witness = evaluate(_input(new_loc=1000, new_tests=500, files_changed=15, falsifiers_added=0))
    assert witness.verdict is BudgetVerdict.NEEDS_SPLIT
    assert any("no falsifiers_added" in r for r in witness.reasons)


def test_doc_heavy_pr_with_no_falsifier_is_ceremony_risk() -> None:
    witness = evaluate(
        _input(
            new_loc=200,
            new_tests=100,
            new_docs=500,
            falsifiers_added=0,
            known_lies_blocked=("documented lie",),
        )
    )
    assert witness.verdict is BudgetVerdict.CEREMONY_RISK


def test_too_many_validators_for_few_claims_is_ceremony_risk() -> None:
    witness = evaluate(
        _input(
            new_loc=100,
            new_tests=50,
            new_validators=10,
            new_claims=2,
            falsifiers_added=2,
        )
    )
    assert witness.verdict is BudgetVerdict.CEREMONY_RISK


def test_acceptable_exception_overrides_size() -> None:
    witness = evaluate(
        _input(
            new_loc=10000,
            files_changed=200,
            known_lies_blocked=(),
            acceptable_exception_reason="mass dependabot bump",
        )
    )
    assert witness.verdict is BudgetVerdict.ACCEPTABLE_EXCEPTION


def test_negative_metrics_rejected() -> None:
    with pytest.raises(ValueError, match=">= 0"):
        BudgetInput(
            files_changed=-1,
            new_loc=0,
            new_tests=0,
            new_validators=0,
            new_docs=0,
            new_claims=0,
            falsifiers_added=0,
            known_lies_blocked=(),
        )


def test_empty_lie_string_rejected() -> None:
    with pytest.raises(ValueError, match="non-empty string"):
        BudgetInput(
            files_changed=1,
            new_loc=10,
            new_tests=10,
            new_validators=0,
            new_docs=0,
            new_claims=0,
            falsifiers_added=0,
            known_lies_blocked=("",),
        )


def test_non_tuple_lies_rejected() -> None:
    with pytest.raises(TypeError, match="known_lies_blocked"):
        BudgetInput(
            files_changed=1,
            new_loc=10,
            new_tests=10,
            new_validators=0,
            new_docs=0,
            new_claims=0,
            falsifiers_added=0,
            known_lies_blocked=["x"],  # type: ignore[arg-type]
        )


def test_deterministic_at_same_input() -> None:
    a = evaluate(_input())
    b = evaluate(_input())
    assert a == b


def test_witness_is_frozen() -> None:
    witness = evaluate(_input())
    with pytest.raises(Exception):  # noqa: B017
        witness.verdict = BudgetVerdict.NEEDS_SPLIT  # type: ignore[misc]
