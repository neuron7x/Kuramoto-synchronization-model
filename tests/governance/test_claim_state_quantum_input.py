# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for deterministic claim-state quantization."""

from __future__ import annotations

import json
from pathlib import Path

from tools.governance.quantize_claim_state import (
    ClaimState,
    boundary_implies_unvalidated_domain_validity,
    quantize_claim_state,
    validate_declared_state,
)


SCHEMA_PATH = Path("schemas/governance/claim_state_quantum_input.schema.json")


def _envelope() -> dict[str, object]:
    return {
        "claim_id": "CLAIM-001",
        "claim_text": "The checked governance claim is locally verifiable.",
        "source_refs": ["tools/governance/quantize_claim_state.py"],
        "test_refs": ["tests/governance/test_claim_state_quantum_input.py"],
        "commands": [
            {
                "cmd": "pytest -q tests/governance/test_claim_state_quantum_input.py",
                "output_ref": "local",
                "exit_code": 0,
            }
        ],
        "artifacts": ["claim_state_report.json"],
        "ci_proof": {
            "sha": "0000000000000000000000000000000000000000",
            "same_sha": False,
            "required_checks_green": False,
        },
        "failure_mode": "Missing links must prevent promotion.",
        "rollback": "Revert this governance contract commit.",
        "claim_boundary": {"allowed": ["governance quantization"], "blocked": ["domain validation"]},
        "negative_evidence": ["No CI proof is attached in this fixture."],
    }


def test_empty_envelope_is_untested() -> None:
    assert quantize_claim_state({}) is ClaimState.UNTESTED


def test_contradicted_envelope_is_false() -> None:
    envelope = _envelope()
    envelope["contradicted"] = True
    assert quantize_claim_state(envelope) is ClaimState.FALSE


def test_missing_links_are_partial() -> None:
    envelope = _envelope()
    envelope.pop("rollback")
    assert quantize_claim_state(envelope) is ClaimState.PARTIAL


def test_complete_without_ci_is_local_verified() -> None:
    assert quantize_claim_state(_envelope()) is ClaimState.LOCAL_VERIFIED


def test_same_sha_green_ci_is_ci_verified() -> None:
    envelope = _envelope()
    envelope["ci_proof"] = {
        "sha": "0000000000000000000000000000000000000000",
        "same_sha": True,
        "required_checks_green": True,
    }
    assert quantize_claim_state(envelope) is ClaimState.CI_VERIFIED


def test_scientific_vector_without_same_sha_ci_is_not_evidence_bearing() -> None:
    envelope = _envelope()
    envelope["scientific_evidence"] = {
        "real_data": True,
        "replay": True,
        "baseline": True,
        "falsifier": True,
        "semantic_validation": True,
    }
    assert quantize_claim_state(envelope) is ClaimState.LOCAL_VERIFIED


def test_real_data_replay_baseline_falsifier_semantic_validation_is_evidence_bearing() -> None:
    envelope = _envelope()
    envelope["ci_proof"] = {
        "sha": "0000000000000000000000000000000000000000",
        "same_sha": True,
        "required_checks_green": True,
    }
    envelope["scientific_evidence"] = {
        "real_data": True,
        "replay": True,
        "baseline": True,
        "falsifier": True,
        "semantic_validation": True,
    }
    assert quantize_claim_state(envelope) is ClaimState.EVIDENCE_BEARING


def test_declared_state_cannot_round_up() -> None:
    envelope = _envelope()
    envelope["declared_state"] = "CI_VERIFIED"
    result = validate_declared_state(envelope)
    assert result["state"] == "LOCAL_VERIFIED"
    assert result["upward_drift"] is True


def _full_scientific_envelope() -> dict[str, object]:
    envelope = _envelope()
    envelope["ci_proof"] = {
        "sha": "0000000000000000000000000000000000000000",
        "same_sha": True,
        "required_checks_green": True,
    }
    envelope["scientific_evidence"] = {
        "real_data": True,
        "replay": True,
        "baseline": True,
        "falsifier": True,
        "semantic_validation": True,
    }
    return envelope


def test_local_verified_requires_recorded_command_output() -> None:
    # Falsification target #2: commands present but no recorded output ⇒ blocked.
    envelope = _envelope()
    envelope["commands"] = [{"cmd": "pytest -q", "output_ref": "", "exit_code": 0}]
    assert quantize_claim_state(envelope) is ClaimState.PARTIAL


def test_commands_without_exit_code_cannot_reach_local_verified() -> None:
    envelope = _envelope()
    envelope["commands"] = [{"cmd": "pytest -q", "output_ref": "local"}]
    assert quantize_claim_state(envelope) is ClaimState.PARTIAL


def test_boundary_claiming_predictive_validity_without_artifact_is_blocked() -> None:
    # Falsification target #7: boundary asserts predictive/market validity, no
    # validation artifact ⇒ cannot leave PARTIAL.
    envelope = _envelope()
    envelope["claim_boundary"] = {"allowed": ["predictive market validity"], "blocked": []}
    assert boundary_implies_unvalidated_domain_validity(envelope) is True
    assert quantize_claim_state(envelope) is ClaimState.PARTIAL


def test_boundary_claiming_domain_validity_allowed_when_validation_artifact_present() -> None:
    # Same overclaiming boundary IS allowed once the full scientific vector backs it.
    envelope = _full_scientific_envelope()
    envelope["claim_boundary"] = {"allowed": ["physics validity"], "blocked": []}
    assert boundary_implies_unvalidated_domain_validity(envelope) is False
    assert quantize_claim_state(envelope) is ClaimState.EVIDENCE_BEARING


def test_boundary_blocking_domain_terms_is_not_an_overclaim() -> None:
    # Listing physics/market/predictive on the BLOCKED side is the honest boundary.
    envelope = _envelope()
    envelope["claim_boundary"] = {
        "allowed": ["governance quantization"],
        "blocked": ["physics validity", "market", "predictive"],
    }
    assert boundary_implies_unvalidated_domain_validity(envelope) is False
    assert quantize_claim_state(envelope) is ClaimState.LOCAL_VERIFIED


def test_forbidden_prose_declared_state_is_rejected() -> None:
    # Falsification target #1: prose promotion ("ready"/"ship it"/…) fails closed.
    for prose in ("ready", "ship it", "green enough", "almost ready"):
        envelope = _envelope()
        envelope["declared_state"] = prose
        result = validate_declared_state(envelope)
        assert result["forbidden_prose_state"] is True, prose
        assert result["upward_drift"] is True, prose
        assert result["state"] == "LOCAL_VERIFIED"


def test_schema_is_fail_closed_for_claim_envelope_shape() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["additionalProperties"] is False
    assert schema["properties"]["commands"]["minItems"] == 1
    assert schema["properties"]["ci_proof"]["additionalProperties"] is False
    assert schema["properties"]["scientific_evidence"]["additionalProperties"] is False
    assert schema["properties"]["claim_boundary"]["additionalProperties"] is False
