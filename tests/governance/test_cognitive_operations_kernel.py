# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Contract tests for the Cognitive Operations Kernel governance data.

This kernel is a governance control surface only: it maps input to an
evidence-bound verdict. It is not a cognitive model of the brain, not
scientific validation, and not a runtime correctness proof. These tests
assert that the machine-readable contract schema-validates, that the final
verdict enum is exactly ``{PASS, FAIL, PARTIAL, UNKNOWN}``, that all 18
kernel functions are present, and — critically — that a contract carrying a
forbidden verdict token is REJECTED by the strict schema. The last test is
the falsifier that proves the governance gate has teeth rather than being
decorative.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

DATA_PATH = Path("data/governance/cognitive_operations_kernel_v1_0.json")
SCHEMA_PATH = Path("schemas/governance/cognitive_operations_kernel.schema.json")
DOC_PATH = Path("docs/prompts/cognitive_operations_kernel_v1_0.md")

VERDICT_ENUM = {"PASS", "FAIL", "PARTIAL", "UNKNOWN"}

EXPECTED_FUNCTION_IDS = {
    "FUNCTION_01_INTENT_COLLAPSE",
    "FUNCTION_02_ATOMIC_DECOMPOSITION",
    "FUNCTION_03_SIGNAL_NOISE_FILTER",
    "FUNCTION_04_EVIDENCE_BINDING",
    "FUNCTION_05_CAUSAL_CHAINING",
    "FUNCTION_06_CONSTRAINT_EXTRACTION",
    "FUNCTION_07_GATE_SYNTHESIS",
    "FUNCTION_08_FAILURE_LOCALIZATION",
    "FUNCTION_09_COUNTERFACTUAL_TEST",
    "FUNCTION_10_DECISION_COMPRESSION",
    "FUNCTION_11_ACTION_SYNTHESIS",
    "FUNCTION_12_VERIFICATION_COMMAND",
    "FUNCTION_13_SELF_AUDIT_LOOP",
    "FUNCTION_14_CONFIDENCE_CALIBRATION",
    "FUNCTION_15_QUALITY_SCORING",
    "FUNCTION_16_STATE_TRANSITION",
    "FUNCTION_17_ACCEPTANCE_GATE",
    "FUNCTION_18_FINAL_VERDICT",
}

# Verbatim claim boundary copied from Issue #1136.
BLOCKED_CLAIMS_VERBATIM = [
    "This kernel is not a cognitive model of the brain.",
    "This kernel is not scientific validation.",
    "This kernel is not runtime correctness proof.",
    "This kernel does not close SecondOrderStabilityAudit, Forman-Ricci provenance, or release scorecard blockers.",
]


def _data() -> dict[str, object]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validator() -> Draft202012Validator:
    return Draft202012Validator(_schema())


def test_kernel_artifacts_exist_and_parse() -> None:
    assert DOC_PATH.is_file()
    assert DATA_PATH.is_file()
    assert SCHEMA_PATH.is_file()
    assert _data()["artifact_id"] == "cognitive-operations-kernel-v1.0"


def test_contract_validates_against_strict_schema() -> None:
    """The shipped contract must satisfy the strict schema with no errors."""
    errors = sorted(_validator().iter_errors(_data()), key=str)
    assert errors == [], [error.message for error in errors]


def test_final_verdict_enum_is_exactly_the_closed_set() -> None:
    output_contract = _data()["output_contract"]
    assert isinstance(output_contract, dict)
    assert set(output_contract["final_verdict"]) == VERDICT_ENUM


def test_kernel_has_all_eighteen_functions() -> None:
    data = _data()
    functions = data["functions"]
    assert isinstance(functions, list)
    assert len(functions) == 18
    ids = {item["id"] for item in functions if isinstance(item, dict)}
    assert ids == EXPECTED_FUNCTION_IDS


def test_output_contract_contains_required_cognitive_fields() -> None:
    output_contract = _data()["output_contract"]
    assert isinstance(output_contract, dict)
    required_fields = set(output_contract["required_fields"])
    assert {
        "intent_vector",
        "verified_atoms",
        "unsupported_atoms",
        "causal_graph",
        "validation_gates",
        "failed_gates",
        "action_steps",
        "verification_steps",
        "confidence_score",
        "quality_score",
        "final_verdict",
    } <= required_fields


def test_final_gate_blocks_pass_without_required_evidence() -> None:
    final_gate = _data()["final_gate"]
    assert isinstance(final_gate, dict)
    pass_requires = set(final_gate["pass_requires"])
    assert {
        "intent evidence",
        "atom evidence",
        "gate evidence",
        "counterfactual evidence",
        "action evidence",
        "verification evidence",
        "self-audit evidence",
    } <= pass_requires
    assert "PARTIAL" in final_gate["weakest_link_rule"]


def test_claim_boundary_is_verbatim_from_issue_1136() -> None:
    scope = _data()["scope"]
    assert isinstance(scope, dict)
    blocked_claims = scope["blocked_claims"]
    assert blocked_claims == BLOCKED_CLAIMS_VERBATIM


def test_schema_required_keys_match_data_keys() -> None:
    data = _data()
    schema = _schema()
    required = schema["required"]
    assert isinstance(required, list)
    for key in required:
        assert key in data


# ---------------------------------------------------------------------------
# Falsifier: the strict schema must REJECT a forbidden verdict token.
# A governance gate that accepts "ship it" or "green enough" is decorative.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("forbidden_token", ["ship it", "green enough", "LGTM", "approved"])
def test_forbidden_verdict_token_is_rejected(forbidden_token: str) -> None:
    """Feeding a verdict outside the closed enum must fail validation.

    This proves the schema is the authority: any token other than
    {PASS, FAIL, PARTIAL, UNKNOWN} is rejected, so a fluent-but-empty
    "ship it" cannot masquerade as a passing governance verdict.
    """
    tampered = copy.deepcopy(_data())
    output_contract = tampered["output_contract"]
    assert isinstance(output_contract, dict)
    output_contract["final_verdict"] = ["PASS", "FAIL", "PARTIAL", forbidden_token]

    validator = _validator()
    assert not validator.is_valid(tampered)
    errors = list(validator.iter_errors(tampered))
    assert errors, "strict schema must reject a forbidden verdict token"
    assert any("enum" in error.validator for error in errors)
