# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core.messaging.schema_registry import (
    EventSchemaRegistry,
    SchemaCompatibilityError,
    SchemaFormat,
    SchemaFormatCoverageError,
    SchemaLintError,
    _field_name_index,
    _is_nullable,
    _normalise_avro_type,
)


def test_registry_loads_known_events() -> None:
    registry = EventSchemaRegistry.from_directory("schemas/events")
    assert "ticks" in set(registry.available_events())
    latest = registry.latest("ticks", SchemaFormat.AVRO)
    schema = latest.load()
    assert schema["name"] == "TickEvent"


def test_registry_exposes_subject_and_namespace() -> None:
    registry = EventSchemaRegistry.from_directory("schemas/events")
    assert registry.subject("ticks") == "geosync.market.ticks.v1_0_0"
    assert registry.namespace("ticks") == "geosync.events.marketdata.v1_0_0"


def test_format_coverage_requires_declared_formats(tmp_path: Path) -> None:
    source_dir = Path("schemas/events")
    target = tmp_path / "events"
    shutil.copytree(source_dir, target)

    registry_path = target / "registry.json"
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    payload["events"]["ticks"]["versions"][0].pop("json_schema", None)
    registry_path.write_text(json.dumps(payload), encoding="utf-8")

    registry = EventSchemaRegistry.from_directory(target)
    with pytest.raises(SchemaFormatCoverageError):
        registry.validate_format_coverage("ticks")
    with pytest.raises(SchemaFormatCoverageError):
        registry.validate_all()


def test_backward_compatibility_violation_detected(tmp_path: Path) -> None:
    source_dir = Path("schemas/events")
    target = tmp_path / "events"
    shutil.copytree(source_dir, target)

    tick_v1_path = target / "avro" / "v1.0.0" / "tick.avsc"
    tick_v2_path = target / "avro" / "v2.0.0" / "tick.avsc"
    tick_v2_path.parent.mkdir(parents=True, exist_ok=True)
    with tick_v1_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    schema["fields"] = [field for field in schema["fields"] if field["name"] != "symbol"]
    with tick_v2_path.open("w", encoding="utf-8") as handle:
        json.dump(schema, handle)

    registry_path = target / "registry.json"
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_payload["events"]["ticks"]["versions"].append(
        {
            "version": "2.0.0",
            "avro": "avro/v2.0.0/tick.avsc",
            "protobuf": "../../libs/proto/events.proto",
        }
    )
    registry_path.write_text(json.dumps(registry_payload), encoding="utf-8")

    registry = EventSchemaRegistry.from_directory(target)
    with pytest.raises(SchemaCompatibilityError):
        registry.validate_backward_and_forward("ticks")


def test_forward_compatibility_allows_nullable_fields(tmp_path: Path) -> None:
    source_dir = Path("schemas/events")
    target = tmp_path / "events"
    shutil.copytree(source_dir, target)

    tick_v1_path = target / "avro" / "v1.0.0" / "tick.avsc"
    tick_v2_path = target / "avro" / "v2.0.0" / "tick.avsc"
    tick_v2_path.parent.mkdir(parents=True, exist_ok=True)

    with tick_v1_path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    schema["fields"].append({"name": "new_nullable", "type": ["null", "string"], "default": None})
    with tick_v2_path.open("w", encoding="utf-8") as handle:
        json.dump(schema, handle)

    registry_path = target / "registry.json"
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    registry_payload["events"]["ticks"]["versions"].append(
        {
            "version": "2.0.0",
            "avro": "avro/v2.0.0/tick.avsc",
            "protobuf": "../../libs/proto/events.proto",
        }
    )
    registry_path.write_text(json.dumps(registry_payload), encoding="utf-8")

    registry = EventSchemaRegistry.from_directory(target)
    registry.validate_backward_and_forward("ticks")


def test_helper_normalises_complex_types() -> None:
    record_type = {
        "type": "record",
        "name": "Parent",
        "fields": [
            {
                "name": "child",
                "type": {"type": "record", "name": "Nested", "fields": []},
            },
        ],
    }
    enum_type = {"type": "enum", "name": "Direction", "symbols": ["BUY", "SELL"]}
    array_type = {"type": "array", "items": "string"}
    map_type = {"type": "map", "values": "int"}
    fixed_type = {"type": "fixed", "name": "Hash", "size": 32}

    assert _normalise_avro_type(record_type)[0] == "record"
    assert _normalise_avro_type(enum_type) == ("enum", "Direction", ("BUY", "SELL"))
    assert _normalise_avro_type(array_type) == ("array", ("string",))
    assert _normalise_avro_type(map_type) == ("map", ("int",))
    assert _normalise_avro_type(fixed_type) == ("fixed", "Hash", 32)

    schema = {
        "fields": [
            {"name": "optional", "type": ["null", "string"]},
            {"name": "required", "type": "double"},
        ]
    }
    index = _field_name_index(schema)
    assert set(index.keys()) == {"optional", "required"}
    assert _is_nullable(index["optional"]) is True
    assert _is_nullable(index["required"]) is False


def test_lint_detects_missing_avro_doc(tmp_path: Path) -> None:
    source_dir = Path("schemas/events")
    target = tmp_path / "events"
    shutil.copytree(source_dir, target)

    tick_path = target / "avro" / "v1.0.0" / "tick.avsc"
    payload = json.loads(tick_path.read_text(encoding="utf-8"))
    payload["fields"][0].pop("doc")
    tick_path.write_text(json.dumps(payload), encoding="utf-8")

    registry = EventSchemaRegistry.from_directory(target)
    with pytest.raises(SchemaLintError):
        registry.lint_event("ticks")


def test_lint_detects_json_schema_mismatch(tmp_path: Path) -> None:
    source_dir = Path("schemas/events")
    target = tmp_path / "events"
    shutil.copytree(source_dir, target)

    json_path = target / "json" / "1.0.0" / "ticks.schema.json"
    json_payload = json.loads(json_path.read_text(encoding="utf-8"))
    json_payload["properties"].pop("bid_price")
    json_path.write_text(json.dumps(json_payload), encoding="utf-8")

    registry = EventSchemaRegistry.from_directory(target)
    with pytest.raises(SchemaLintError):
        registry.lint_event("ticks")


def test_catalogue_exposes_event_versions() -> None:
    registry = EventSchemaRegistry.from_directory("schemas/events")
    catalogue = registry.catalogue()
    assert "ticks" in catalogue
    tick_entry = catalogue["ticks"]
    assert tick_entry["latest"] == "1.0.0"
    assert tick_entry["versions"][0]["formats"] == [
        "avro",
        "json_schema",
        "protobuf",
    ]
