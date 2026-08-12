from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schemas/json_artifact_contract.schema.json").read_text(encoding="utf-8"))
CANDIDATE = json.loads((ROOT / "examples/json_artifact_contract.candidate.json").read_text(encoding="utf-8"))
BLOCKED = json.loads((ROOT / "examples/json_artifact_contract.blocked.json").read_text(encoding="utf-8"))


def _errors(payload: dict[str, object]) -> list[jsonschema.ValidationError]:
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return sorted(validator.iter_errors(payload), key=lambda exc: list(exc.path))


def test_candidate_fixture_matches_json_schema() -> None:
    assert _errors(CANDIDATE) == []


def test_blocked_fixture_matches_json_schema() -> None:
    assert _errors(BLOCKED) == []


def test_candidate_without_runner_evidence_cannot_promote_status() -> None:
    payload = deepcopy(CANDIDATE)
    payload["evidence_status"]["status"] = "CI_VERIFIED"  # type: ignore[index]
    payload["final_verdict"]["status"] = "CI_VERIFIED"  # type: ignore[index]

    assert _errors(payload)


def test_blocked_contract_requires_missing_input() -> None:
    payload = deepcopy(BLOCKED)
    payload["inputs"]["missing"] = []  # type: ignore[index]

    assert _errors(payload)


def test_schema_rejects_unknown_top_level_property() -> None:
    payload = deepcopy(CANDIDATE)
    payload["extra"] = "not allowed"

    assert _errors(payload)


def test_schema_rejects_non_string_list_items() -> None:
    payload = deepcopy(CANDIDATE)
    payload["objective"]["optimization"]["minimize"] = [123]  # type: ignore[index]

    assert _errors(payload)
