# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pytest

from core.utils import schemas


@dataclass
class SampleSchema:
    identifier: int
    name: str
    weight: float
    tags: list[str]
    metadata: dict[str, int] = field(default_factory=dict)
    active: bool = True
    description: Optional[str] = None


def test_dataclass_to_json_schema_generates_expected_properties() -> None:
    schema = schemas.dataclass_to_json_schema(SampleSchema, title="Sample")
    assert schema["title"] == "Sample"
    assert set(schema["properties"].keys()) == {
        "identifier",
        "name",
        "weight",
        "tags",
        "metadata",
        "active",
        "description",
    }
    assert set(schema["required"]) == {"identifier", "name", "weight", "tags"}
    assert schema["properties"]["identifier"]["type"] == "integer"
    assert schema["properties"]["tags"]["type"] == "array"
    assert schema["properties"]["metadata"]["type"] == "object"


def test_dataclass_to_json_schema_requires_dataclass_type() -> None:
    with pytest.raises(TypeError):
        schemas.dataclass_to_json_schema(int)  # type: ignore[arg-type]


def test_validate_against_schema_accepts_valid_payload() -> None:
    schema = schemas.dataclass_to_json_schema(SampleSchema)
    payload = {
        "identifier": 1,
        "name": "alpha",
        "weight": 10.5,
        "tags": ["core"],
        "metadata": {"count": 2},
        "active": False,
    }
    assert schemas.validate_against_schema(payload, schema)


def test_validate_against_schema_detects_missing_required_field() -> None:
    schema = schemas.dataclass_to_json_schema(SampleSchema)
    payload = {
        "identifier": 1,
        "weight": 10.5,
        "tags": [],
    }
    with pytest.raises(ValueError, match="Missing required field: name"):
        schemas.validate_against_schema(payload, schema)


def test_validate_against_schema_detects_type_mismatch() -> None:
    schema = schemas.dataclass_to_json_schema(SampleSchema)
    payload = {
        "identifier": 1,
        "name": "alpha",
        "weight": "heavy",
        "tags": [],
    }
    with pytest.raises(ValueError, match="should be number"):
        schemas.validate_against_schema(payload, schema)


def test_generate_all_schemas_includes_expected_keys() -> None:
    generated = schemas.generate_all_schemas()
    assert {"FeatureResult", "BacktestResult", "Ticker"} <= set(generated.keys())


def test_save_schemas_writes_json_files(tmp_path: Path) -> None:
    schemas.save_schemas(str(tmp_path))
    saved_files = {p.name for p in tmp_path.glob("*.json")}
    assert {"FeatureResult.json", "BacktestResult.json", "Ticker.json"} <= saved_files
    index_path = tmp_path / "index.json"
    index_data = json.loads(index_path.read_text())
    assert "schemas" in index_data and "version" in index_data
