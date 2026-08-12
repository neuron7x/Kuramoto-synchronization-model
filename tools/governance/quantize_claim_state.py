# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic claim-state quantizer.

This module turns a raw evidence envelope into exactly one discrete governance
state. It does not validate physics, markets, cognition, or predictive power.
It only prevents claim promotion when required evidence links are missing.
"""

from __future__ import annotations

import argparse
import json
from enum import Enum
from pathlib import Path
from typing import Any


class ClaimState(str, Enum):
    FALSE = "FALSE"
    UNTESTED = "UNTESTED"
    PARTIAL = "PARTIAL"
    LOCAL_VERIFIED = "LOCAL_VERIFIED"
    CI_VERIFIED = "CI_VERIFIED"
    EVIDENCE_BEARING = "EVIDENCE_BEARING"


REQUIRED_KEYS = {
    "claim_id",
    "claim_text",
    "source_refs",
    "test_refs",
    "commands",
    "artifacts",
    "ci_proof",
    "failure_mode",
    "rollback",
    "claim_boundary",
    "negative_evidence",
}

# Prose that is NOT an allowed discrete claim state. Declaring any of these is an
# attempt to promote a claim by wording rather than by proof chain (#1123).
FORBIDDEN_PROSE_STATES = frozenset(
    {
        "almost ready",
        "mostly verified",
        "probably fine",
        "green enough",
        "looks correct",
        "ship it",
        "ready",
    }
)

# Domain-validity assertions that a claim_boundary may NOT place in scope unless a
# full validation artifact (scientific evidence vector) backs them. Falsification
# target #7: a boundary that implies physics/market/predictive/trading validity
# without a validation artifact must not promote.
FORBIDDEN_DOMAIN_VALIDITY_TERMS = (
    "physics-confirmed",
    "physics confirmed",
    "physics validity",
    "market",
    "alpha",
    "predictive",
    "prediction",
    "forecast",
    "trading",
    "tradeable",
    "investment advice",
    "financial advice",
)


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict, set)):
        return bool(value)
    return True


def _same_sha_ci_green(envelope: dict[str, Any]) -> bool:
    ci = envelope.get("ci_proof", {})
    if not isinstance(ci, dict):
        return False
    return ci.get("same_sha") is True and ci.get("required_checks_green") is True


def _scientific_vector_complete(envelope: dict[str, Any]) -> bool:
    scientific = envelope.get("scientific_evidence", {})
    if not isinstance(scientific, dict):
        return False
    return (
        scientific.get("real_data") is True
        and scientific.get("replay") is True
        and scientific.get("baseline") is True
        and scientific.get("falsifier") is True
        and scientific.get("semantic_validation") is True
    )


def _commands_have_recorded_output(envelope: dict[str, Any]) -> bool:
    """LOCAL_VERIFIED requires command OUTPUT, not merely a command string
    (falsification target #2: local verification claimed without command output)."""
    commands = envelope.get("commands")
    if not isinstance(commands, list) or not commands:
        return False
    for command in commands:
        if not isinstance(command, dict):
            return False
        if not _nonempty(command.get("output_ref")):
            return False
        if "exit_code" not in command:
            return False
        if command.get("exit_code") != 0:
            return False
    return True


def boundary_implies_unvalidated_domain_validity(envelope: dict[str, Any]) -> bool:
    """True when the claim_boundary ALLOWS physics/market/predictive/trading
    validity but no validation artifact (complete scientific vector) backs it
    (falsification target #7). The blocked-side of a boundary listing these terms
    to EXCLUDE them is fine — only the allowed-side asserting them is guarded."""
    boundary = envelope.get("claim_boundary")
    if not isinstance(boundary, dict):
        return False
    allowed = boundary.get("allowed", [])
    if not isinstance(allowed, (list, tuple)):
        return False
    allowed_blob = " ".join(str(item) for item in allowed).lower()
    asserts_domain_validity = any(term in allowed_blob for term in FORBIDDEN_DOMAIN_VALIDITY_TERMS)
    if not asserts_domain_validity:
        return False
    return not _scientific_vector_complete(envelope)


def missing_required_links(envelope: dict[str, Any]) -> list[str]:
    """Return missing proof-chain links in stable order."""

    missing: list[str] = []
    for key in sorted(REQUIRED_KEYS):
        if key not in envelope or not _nonempty(envelope[key]):
            missing.append(key)
    return missing


def quantize_claim_state(envelope: dict[str, Any]) -> ClaimState:
    """Map a claim-evidence envelope to one allowed discrete state."""

    if envelope.get("contradicted") is True:
        return ClaimState.FALSE

    missing = missing_required_links(envelope)
    if len(missing) == len(REQUIRED_KEYS):
        return ClaimState.UNTESTED
    if missing:
        return ClaimState.PARTIAL

    # Fail-closed promotion blocks (all required links present, but the proof is
    # not strong enough to leave PARTIAL):
    #  - #7: boundary asserts physics/market/predictive/trading validity with no
    #        validation artifact;
    #  - #2: local verification asserted without recorded command output.
    if boundary_implies_unvalidated_domain_validity(envelope):
        return ClaimState.PARTIAL
    if not _commands_have_recorded_output(envelope):
        return ClaimState.PARTIAL

    same_sha_ci_green = _same_sha_ci_green(envelope)
    scientific_vector_complete = _scientific_vector_complete(envelope)

    if scientific_vector_complete and same_sha_ci_green:
        return ClaimState.EVIDENCE_BEARING

    if same_sha_ci_green:
        return ClaimState.CI_VERIFIED

    return ClaimState.LOCAL_VERIFIED


def validate_declared_state(envelope: dict[str, Any]) -> dict[str, Any]:
    """Return quantization result and reject upward state drift."""

    actual = quantize_claim_state(envelope)
    declared = envelope.get("declared_state")
    allowed_order = list(ClaimState)
    upward_drift = False
    forbidden_prose_state = False
    if declared:
        if isinstance(declared, str) and declared.strip().lower() in FORBIDDEN_PROSE_STATES:
            # Prose promotion (#1: "ready"/"ship it"/"green enough" …) is never a
            # legitimate declared state — fail closed.
            forbidden_prose_state = True
            upward_drift = True
        else:
            try:
                upward_drift = allowed_order.index(ClaimState(declared)) > allowed_order.index(
                    actual
                )
            except ValueError:
                upward_drift = True
    return {
        "claim_id": envelope.get("claim_id", "UNKNOWN"),
        "state": actual.value,
        "declared_state": declared,
        "upward_drift": upward_drift,
        "forbidden_prose_state": forbidden_prose_state,
        "missing_links": missing_required_links(envelope),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Path to claim evidence JSON envelope")
    args = parser.parse_args()
    envelope = json.loads(Path(args.input).read_text(encoding="utf-8"))
    result = validate_declared_state(envelope)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["upward_drift"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
