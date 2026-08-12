# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed regression: a FAILED command must not promote to LOCAL_VERIFIED.

Before the fix, ``_commands_have_recorded_output`` only required the
``exit_code`` key to be present, never that it equalled 0. A command that
FAILED (non-zero exit) but recorded an ``output_ref`` therefore promoted the
claim all the way to LOCAL_VERIFIED. The fix rejects any non-zero exit_code.
"""

from __future__ import annotations

from tools.governance.quantize_claim_state import (
    ClaimState,
    _commands_have_recorded_output,
    quantize_claim_state,
)


def _envelope(exit_code: int) -> dict[str, object]:
    return {
        "claim_id": "CLAIM-EXIT",
        "claim_text": "Local verification with a recorded command.",
        "source_refs": ["tools/governance/quantize_claim_state.py"],
        "test_refs": ["tests/governance/test_quantize_claim_exit_code.py"],
        "commands": [
            {"cmd": "pytest -q", "output_ref": "local.log", "exit_code": exit_code}
        ],
        "artifacts": ["claim_state_report.json"],
        "ci_proof": {
            "sha": "0" * 40,
            "same_sha": False,
            "required_checks_green": False,
        },
        "failure_mode": "Missing links must prevent promotion.",
        "rollback": "Revert this governance contract commit.",
        "claim_boundary": {
            "allowed": ["governance quantization"],
            "blocked": ["domain validation"],
        },
        "negative_evidence": ["No CI proof attached."],
    }


def test_failed_command_is_not_recorded_output() -> None:
    assert _commands_have_recorded_output({"commands": [{"output_ref": "x", "exit_code": 1}]}) is False


def test_passing_command_is_recorded_output() -> None:
    assert _commands_have_recorded_output({"commands": [{"output_ref": "x", "exit_code": 0}]}) is True


def test_failed_command_does_not_promote_to_local_verified() -> None:
    assert quantize_claim_state(_envelope(exit_code=1)) is ClaimState.PARTIAL


def test_passing_command_promotes_to_local_verified() -> None:
    assert quantize_claim_state(_envelope(exit_code=0)) is ClaimState.LOCAL_VERIFIED
