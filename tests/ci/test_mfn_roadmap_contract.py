# SPDX-License-Identifier: MIT
"""Schema tests for the MFN roadmap repair contract."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
ROADMAP = ROOT / "docs" / "MFN_VERIFICATION_ROADMAP.json"
SCHEMA = ROOT / "schemas" / "mfn_verification_roadmap.schema.json"


def test_mfn_roadmap_contract_validates_against_schema() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    payload = json.loads(ROADMAP.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_mfn_roadmap_remains_candidate_until_external_evidence_exists() -> None:
    payload = json.loads(ROADMAP.read_text(encoding="utf-8"))

    assert payload["evidence_status"]["external_evidence_available"] is False
    assert payload["evidence_status"]["score"] is None
    assert payload["evidence_status"]["confidence"] <= 0.65
    assert payload["final_verdict"]["status"] == "CANDIDATE_NOT_VALIDATED"
