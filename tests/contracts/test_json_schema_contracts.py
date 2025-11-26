from __future__ import annotations

import json
import os
from copy import deepcopy
from itertools import pairwise
from pathlib import Path
from typing import Any, Iterable

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError

os.environ.setdefault("TRADEPULSE_ADMIN_TOKEN", "import-admin-token")
os.environ.setdefault("TRADEPULSE_AUDIT_SECRET", "import-audit-secret")

from application.api.service import (  # noqa: E402  - environment variables must be set before import
    FeatureRequest,
    FeatureResponse,
    PredictionRequest,
    PredictionResponse,
)
from src.data.versioning import SemanticVersion

BASELINE_DIR = Path("schemas/http/json/1.0.0")
SCHEMA_ROOT = Path("schemas/http/json")


def _load_schema(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_schema_versions() -> list[tuple[SemanticVersion, Path]]:
    discovered: list[tuple[SemanticVersion, Path]] = []
    for entry in SCHEMA_ROOT.iterdir():
        if entry.is_dir():
            discovered.append((SemanticVersion.parse(entry.name), entry))
    discovered.sort(key=lambda item: item[0])
    return discovered


@pytest.mark.parametrize(
    ("model", "filename"),
    [
        (FeatureRequest, "feature_request.schema.json"),
        (FeatureResponse, "feature_response.schema.json"),
        (PredictionRequest, "prediction_request.schema.json"),
        (PredictionResponse, "prediction_response.schema.json"),
    ],
)
def test_dto_json_schema_matches_baseline(model: type, filename: str) -> None:
    baseline = _load_schema(BASELINE_DIR / filename)
    current = model.model_json_schema()
    assert current == baseline


@pytest.mark.parametrize(
    ("model", "filename"),
    [
        (FeatureRequest, "feature_request.schema.json"),
        (PredictionRequest, "prediction_request.schema.json"),
    ],
)
def test_dto_required_fields_are_stable(model: type, filename: str) -> None:
    baseline = _load_schema(BASELINE_DIR / filename)
    current = model.model_json_schema()
    assert set(baseline.get("required", ())) <= set(current.get("required", ()))


@pytest.mark.parametrize(
    ("model", "filename"),
    [
        (FeatureRequest, "feature_request.schema.json"),
        (FeatureResponse, "feature_response.schema.json"),
        (PredictionRequest, "prediction_request.schema.json"),
        (PredictionResponse, "prediction_response.schema.json"),
    ],
)
def test_dto_json_schema_examples_roundtrip(model: type, filename: str) -> None:
    schema = _load_schema(BASELINE_DIR / filename)
    validator = Draft202012Validator(schema)
    examples: Iterable[dict[str, Any]] = schema.get("examples", ())
    assert list(examples), f"{filename} must define at least one example payload"
    for example in examples:
        validator.validate(example)
        model.model_validate(example)


@pytest.mark.parametrize(
    ("model", "filename"),
    [
        (FeatureRequest, "feature_request.schema.json"),
        (FeatureResponse, "feature_response.schema.json"),
        (PredictionRequest, "prediction_request.schema.json"),
        (PredictionResponse, "prediction_response.schema.json"),
    ],
)
def test_dto_json_schema_rejects_missing_required(model: type, filename: str) -> None:
    schema = _load_schema(BASELINE_DIR / filename)
    required = list(schema.get("required", ()))
    if not required:
        pytest.skip("schema does not declare required fields")
    examples: Iterable[dict[str, Any]] = schema.get("examples", ())
    if not examples:
        pytest.skip("schema does not declare examples")
    candidate = deepcopy(list(examples)[0])
    candidate.pop(required[0], None)
    validator = Draft202012Validator(schema)
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(candidate)
    with pytest.raises(PydanticValidationError):
        model.model_validate(candidate)


def test_json_schema_contract_versions_are_semantic() -> None:
    versions = _iter_schema_versions()
    assert versions, "No JSON schema contract versions discovered"
    parsed_versions = [version for version, _ in versions]
    assert len(parsed_versions) == len(
        set(parsed_versions)
    ), "Duplicate schema versions found"
    assert parsed_versions == sorted(
        parsed_versions
    ), "Schema versions must increase monotonically"


def test_json_schema_backward_and_forward_compatibility() -> None:
    versions = _iter_schema_versions()
    if len(versions) < 2:
        pytest.skip("Single schema version present; nothing to compare")

    version_schemas: list[tuple[SemanticVersion, dict[str, dict[str, Any]]]] = []
    for version, path in versions:
        files = {
            file.name: _load_schema(file)
            for file in path.glob("*.schema.json")
            if file.is_file()
        }
        version_schemas.append((version, files))

    for (previous_version, previous_files), (
        current_version,
        current_files,
    ) in pairwise(version_schemas):
        for name, previous_schema in previous_files.items():
            current_schema = current_files.get(name)
            if current_schema is None:
                assert current_version.major > previous_version.major, (
                    f"Schema {name} removed without major version bump: "
                    f"{previous_version} -> {current_version}"
                )
                continue

            if current_version.major == previous_version.major:
                previous_required = set(previous_schema.get("required", ()))
                current_required = set(current_schema.get("required", ()))
                assert previous_required <= current_required, (
                    f"Required fields were removed from {name}: "
                    f"{sorted(previous_required - current_required)}"
                )
                assert current_required <= previous_required, (
                    f"Required fields were added to {name} without major bump: "
                    f"{sorted(current_required - previous_required)}"
                )

                previous_properties = set(previous_schema.get("properties", {}).keys())
                current_properties = set(current_schema.get("properties", {}).keys())
                assert previous_properties <= current_properties, (
                    f"Properties removed from {name} without major bump: "
                    f"{sorted(previous_properties - current_properties)}"
                )

                previous_validator = Draft202012Validator(previous_schema)
                current_validator = Draft202012Validator(current_schema)
                for example in previous_schema.get("examples", ()):
                    current_validator.validate(example)
                for example in current_schema.get("examples", ()):
                    previous_validator.validate(example)
