# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Schema contract for reproducible capsule manifests (TASK 930).

The schema proves *shape*: a capsule manifest cannot be malformed silently.
These tests pin the contract — a valid manifest passes, and each hard invariant
(required fields, fixed evidence class, relative paths, SHA-256 digests, no
unknown top-level fields) fails for the right reason.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "schemas" / "reproducible_capsule.schema.json"
MANIFEST_PATH = (
    ROOT
    / "artifacts"
    / "reproducible_capsules"
    / "mfn_integration_seed7_p256"
    / "manifest.json"
)


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def valid_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_schema_is_itself_valid(schema: dict[str, Any]) -> None:
    jsonschema.Draft202012Validator.check_schema(schema)


def test_committed_manifest_passes(
    schema: dict[str, Any], valid_manifest: dict[str, Any]
) -> None:
    jsonschema.validate(valid_manifest, schema)


def test_fixed_identity_fields(valid_manifest: dict[str, Any]) -> None:
    assert valid_manifest["evidence_class"] == "REPRODUCIBLE_INFRASTRUCTURE_PROOF"
    assert valid_manifest["artifact_role"] == "instrumentation_capsule"
    assert valid_manifest["is_empirical_evidence"] is False


@pytest.mark.parametrize("field", [
    "schema_version",
    "capsule_id",
    "artifact_role",
    "evidence_class",
    "is_empirical_evidence",
    "generator",
    "git_sha",
    "source_date_epoch",
    "created_at_utc",
    "verify_command",
    "artifacts",
    "sha256_manifest",
    "claim_boundary",
])
def test_missing_required_field_fails(
    schema: dict[str, Any], valid_manifest: dict[str, Any], field: str
) -> None:
    bad = copy.deepcopy(valid_manifest)
    del bad[field]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_invalid_evidence_class_fails(
    schema: dict[str, Any], valid_manifest: dict[str, Any]
) -> None:
    bad = copy.deepcopy(valid_manifest)
    bad["evidence_class"] = "EMPIRICAL_EVIDENCE"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_is_empirical_evidence_true_fails(
    schema: dict[str, Any], valid_manifest: dict[str, Any]
) -> None:
    bad = copy.deepcopy(valid_manifest)
    bad["is_empirical_evidence"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_absolute_artifact_path_fails(
    schema: dict[str, Any], valid_manifest: dict[str, Any]
) -> None:
    bad = copy.deepcopy(valid_manifest)
    bad["artifacts"][0]["path"] = "/etc/passwd"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_parent_traversal_artifact_path_fails(
    schema: dict[str, Any], valid_manifest: dict[str, Any]
) -> None:
    bad = copy.deepcopy(valid_manifest)
    bad["artifacts"][0]["path"] = "../../etc/passwd"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_non_sha256_digest_fails(
    schema: dict[str, Any], valid_manifest: dict[str, Any]
) -> None:
    bad = copy.deepcopy(valid_manifest)
    bad["artifacts"][0]["sha256"] = "deadbeef"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_unknown_top_level_field_fails(
    schema: dict[str, Any], valid_manifest: dict[str, Any]
) -> None:
    bad = copy.deepcopy(valid_manifest)
    bad["surprise"] = "not allowed"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_empty_artifacts_fails(
    schema: dict[str, Any], valid_manifest: dict[str, Any]
) -> None:
    bad = copy.deepcopy(valid_manifest)
    bad["artifacts"] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)
