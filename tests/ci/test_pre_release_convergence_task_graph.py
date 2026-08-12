# SPDX-License-Identifier: MIT
"""Forward-contract tests for the pre-release convergence task-graph schema.

The schema constrains a candidate-only convergence task graph. No instance
is committed (run dumps are transient), so these tests prove the schema is a
valid metaschema and structurally fails closed: a conforming instance can
never change the claim tier, self-score, or report anything but a blocked,
candidate-not-validated state.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = ROOT / "schemas" / "pre_release_convergence_task_graph.schema.json"


def _schema() -> dict[str, object]:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def test_pre_release_convergence_schema_is_a_valid_metaschema() -> None:
    Draft202012Validator.check_schema(_schema())


def test_pre_release_convergence_schema_fails_closed() -> None:
    schema = _schema()
    lock = schema["properties"]["definition_lock"]["properties"]
    evidence = schema["properties"]["evidence_status"]["properties"]
    final_gate = schema["properties"]["final_gate"]["properties"]

    assert lock["status"]["const"] == "CANDIDATE_NOT_VALIDATED"
    assert lock["claim_tier_change"]["const"] == "none"
    assert evidence["status"]["const"] == "CANDIDATE_NOT_VALIDATED"
    assert evidence["score"] == {"type": "null"}
    assert evidence["confidence"]["maximum"] <= 0.65
    assert final_gate["status"]["const"] == "BLOCKED_BY_EVIDENCE"


def test_pre_release_convergence_schema_rejects_promotion() -> None:
    validator = Draft202012Validator(_schema())
    # A definition_lock that promotes the claim tier must be rejected.
    promoted_lock = {
        "status": "CANDIDATE_NOT_VALIDATED",
        "claim_tier_change": "promoted",  # forbidden: only "none" admissible
        "forbidden_promotion": ["production ready"],
        "invariants": ["x"],
    }
    assert not validator.is_valid({"definition_lock": promoted_lock})
