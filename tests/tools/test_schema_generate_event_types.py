# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import json

from tools.schema.generate_event_types import AvroSchemaCollector


def build_schema():
    return {
        "type": "record",
        "name": "TradeEvent",
        "namespace": "trade.pulse",
        "fields": [
            {"name": "id", "type": "string"},
            {
                "name": "metadata",
                "type": [
                    "null",
                    {
                        "type": "record",
                        "name": "Metadata",
                        "fields": [
                            {
                                "name": "tags",
                                "type": {"type": "array", "items": "string"},
                                "default": [],
                            },
                            {
                                "name": "dimensions",
                                "type": {"type": "map", "values": "double"},
                                "default": {},
                            },
                        ],
                    },
                ],
                "default": None,
            },
            {
                "name": "event_type",
                "type": {
                    "type": "enum",
                    "name": "EventKind",
                    "symbols": ["BUY", "SELL"],
                    "doc": "Kind of event",
                },
            },
            {
                "name": "payload",
                "type": ["null", "bytes"],
                "default": None,
            },
            {
                "name": "count",
                "type": "int",
                "default": 0,
            },
        ],
    }


def test_collector_marks_optional_and_defaults():
    collector = AvroSchemaCollector()
    collector.collect(build_schema())

    trade_event = collector.records["TradeEvent"]
    metadata_field = next(field for field in trade_event.fields if field.name == "metadata")
    payload_field = next(field for field in trade_event.fields if field.name == "payload")
    count_field = next(field for field in trade_event.fields if field.name == "count")

    assert metadata_field.optional is True
    assert metadata_field.default == "None"
    assert metadata_field.type_hint == "Optional[Metadata]"

    metadata_record = collector.records["Metadata"]
    tags_field = next(field for field in metadata_record.fields if field.name == "tags")
    dims_field = next(field for field in metadata_record.fields if field.name == "dimensions")

    assert tags_field.default_factory == "list"
    assert dims_field.default_factory == "dict"
    assert collector.requires_field_import is True
    assert "List" in collector.python_imports
    assert "Dict" in collector.python_imports
    assert "Optional" in collector.python_imports

    assert payload_field.optional is True
    assert payload_field.type_hint == "Optional[bytes]"
    assert count_field.default == "0"


def test_render_python_types_and_defaults():
    collector = AvroSchemaCollector()
    collector.collect(build_schema())

    output = collector.render_python()
    assert "class EventKind(Enum):" in output
    assert "class TradeEvent(BaseModel):" in output
    assert "tags: List[str] = Field(default_factory=list)" in output
    assert "dimensions: Dict[str, float] = Field(default_factory=dict)" in output
    assert "metadata: Optional[Metadata] = None" in output
    assert "payload: Optional[bytes] = None" in output


def test_render_typescript_and_json_schema():
    collector = AvroSchemaCollector()
    collector.collect(build_schema())

    ts_output = collector.render_typescript()
    assert "export enum EventKind" in ts_output
    assert "metadata?: Metadata | null;" in ts_output
    assert "payload?: Uint8Array | null;" in ts_output

    schema_json = json.loads(collector.render_json_schema("TradeEvent"))
    assert set(schema_json["required"]) == {"id", "event_type"}
    metadata_schema = schema_json["properties"]["metadata"]
    assert metadata_schema["anyOf"][0]["$ref"] == "#/$defs/Metadata"
    defs = schema_json["$defs"]
    metadata_def = defs["Metadata"]
    assert metadata_def["properties"]["tags"]["default"] == []
    assert metadata_def["properties"]["dimensions"]["default"] == {}
    enum_def = defs["EventKind"]
    assert enum_def["enum"] == ["BUY", "SELL"]
