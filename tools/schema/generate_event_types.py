# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generate strongly-typed models and JSON Schema documents from Avro schemas."""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from core.messaging.schema_registry import EventSchemaRegistry, SchemaFormat


@dataclass
class FieldDefinition:
    name: str
    type_hint: str
    ts_type: str
    optional: bool = False
    default: str | None = None
    default_factory: str | None = None
    doc: str | None = None
    json_schema: Dict[str, Any] | None = None
    default_value: Any | None = None


@dataclass
class RecordDefinition:
    name: str
    namespace: str | None
    doc: str | None
    fields: List[FieldDefinition]


@dataclass
class EnumDefinition:
    name: str
    namespace: str | None
    doc: str | None
    symbols: List[str]


class AvroSchemaCollector:
    def __init__(self) -> None:
        self.records: Dict[str, RecordDefinition] = {}
        self.enums: Dict[str, EnumDefinition] = {}
        self.python_imports: set[str] = set()
        self.requires_field_import = False
        self._record_keys: set[tuple[str | None, str]] = set()

    def collect(self, schema: Dict) -> None:
        namespace = schema.get("namespace")
        self._parse_record(schema, parent_namespace=namespace)

    def _parse_record(self, schema: Dict, parent_namespace: str | None = None) -> str:
        name = schema["name"]
        namespace = schema.get("namespace", parent_namespace)
        key = (namespace, name)
        if key in self._record_keys:
            return name
        fields: List[FieldDefinition] = []
        for field in schema.get("fields", []):
            field_def = self._parse_field(field, namespace)
            fields.append(field_def)
        record = RecordDefinition(
            name=name, namespace=namespace, doc=schema.get("doc"), fields=fields
        )
        self.records[name] = record
        self._record_keys.add(key)
        return name

    def _parse_field(self, field: Dict, namespace: str | None) -> FieldDefinition:
        field_type = field["type"]
        doc = field.get("doc")
        default = field.get("default")
        (
            type_hint,
            ts_type,
            optional,
            default_expr,
            default_factory,
            json_schema,
        ) = self._parse_type(field_type, default, namespace)
        return FieldDefinition(
            name=field["name"],
            type_hint=type_hint,
            ts_type=ts_type,
            optional=optional,
            default=default_expr,
            default_factory=default_factory,
            doc=doc,
            json_schema=json_schema,
            default_value=default,
        )

    def _parse_type(self, avro_type, default, namespace: str | None):
        optional = False
        default_expr = None
        default_factory = None
        json_schema: Dict[str, Any]
        if isinstance(avro_type, list):
            non_null = [t for t in avro_type if not _is_null_type(t)]
            if len(non_null) != 1:
                raise ValueError(f"Unsupported union type: {avro_type}")
            optional = True
            avro_type = non_null[0]
            if default is None:
                default_expr = "None"

        if isinstance(avro_type, str):
            type_hint = _PYTHON_PRIMITIVES[avro_type]
            ts_type = _TS_PRIMITIVES[avro_type]
            json_schema = copy.deepcopy(_JSON_PRIMITIVES[avro_type])
        elif isinstance(avro_type, dict):
            avro_kind = avro_type["type"]
            if avro_kind in _PYTHON_PRIMITIVES:
                type_hint = _PYTHON_PRIMITIVES[avro_kind]
                ts_type = _TS_PRIMITIVES[avro_kind]
                json_schema = copy.deepcopy(_JSON_PRIMITIVES[avro_kind])
                if "logicalType" in avro_type:
                    logical = avro_type["logicalType"]
                    if logical.startswith("timestamp"):
                        json_schema = {"type": "integer", "format": "unix-time"}
            elif avro_kind == "record":
                nested_name = self._parse_record(avro_type, parent_namespace=namespace)
                type_hint = nested_name
                ts_type = nested_name
                json_schema = {"$ref": f"#/$defs/{nested_name}"}
            elif avro_kind == "enum":
                nested_name = avro_type["name"]
                if nested_name not in self.enums:
                    self.enums[nested_name] = EnumDefinition(
                        name=nested_name,
                        namespace=avro_type.get("namespace", namespace),
                        doc=avro_type.get("doc"),
                        symbols=list(avro_type.get("symbols", [])),
                    )
                type_hint = nested_name
                ts_type = nested_name
                json_schema = {"$ref": f"#/$defs/{nested_name}"}
            elif avro_kind == "array":
                item_type, item_ts, _, _, _, item_schema = self._parse_type(
                    avro_type["items"], None, namespace
                )
                self.python_imports.add("List")
                type_hint = f"List[{item_type}]"
                ts_type = f"{item_ts}[]"
                json_schema = {"type": "array", "items": item_schema}
            elif avro_kind == "map":
                value_type, value_ts, _, _, _, value_schema = self._parse_type(
                    avro_type["values"], None, namespace
                )
                self.python_imports.add("Dict")
                type_hint = f"Dict[str, {value_type}]"
                ts_type = f"Record<string, {value_ts}>"
                json_schema = {"type": "object", "additionalProperties": value_schema}
            elif avro_kind == "fixed":
                type_hint = "bytes"
                ts_type = "Uint8Array"
                json_schema = {"type": "string", "contentEncoding": "base64"}
            else:
                raise ValueError(f"Unsupported complex type: {avro_kind}")
        else:
            raise ValueError(f"Unsupported type declaration: {avro_type}")

        if optional:
            self.python_imports.add("Optional")
            type_hint = f"Optional[{type_hint}]"
            ts_type = f"{ts_type} | null"
            json_schema = _make_optional_schema(json_schema)

        if isinstance(default, dict) and default == {}:
            default_factory = "dict"
            self.requires_field_import = True
        elif isinstance(default, list) and default == []:
            default_factory = "list"
            self.requires_field_import = True
        elif default is not None and default_expr is None:
            default_expr = repr(default)

        return type_hint, ts_type, optional, default_expr, default_factory, json_schema

    def render_python(self) -> str:
        header = [
            "# Auto-generated by tools/schema/generate_event_types.py. DO NOT EDIT.",
            "from __future__ import annotations",
            "",
        ]
        imports = ["from pydantic import BaseModel, ConfigDict"]
        if self.requires_field_import:
            imports[0] = "from pydantic import BaseModel, ConfigDict, Field"
        typing_imports: List[str] = []
        for item in sorted(self.python_imports):
            typing_imports.append(item)
        if typing_imports:
            imports.append(f"from typing import {', '.join(typing_imports)}")
        if self.enums:
            imports.append("from enum import Enum")
        body: List[str] = []
        for enum in (self.enums[name] for name in sorted(self.enums)):
            body.append(_render_python_enum(enum))
        for record in (self.records[name] for name in sorted(self.records)):
            body.append(_render_python_record(record))
        return "\n".join(header + imports + ["", "\n".join(body)])

    def render_typescript(self) -> str:
        header = [
            "// Auto-generated by tools/schema/generate_event_types.py. DO NOT EDIT.",
            "/* eslint-disable */",
        ]
        body: List[str] = []
        for enum in (self.enums[name] for name in sorted(self.enums)):
            body.append(_render_ts_enum(enum))
        for record in (self.records[name] for name in sorted(self.records)):
            body.append(_render_ts_interface(record))
        return "\n\n".join(header + body) + "\n"

    def render_json_schema(self, record_name: str) -> str:
        if record_name not in self.records:
            raise KeyError(f"Unknown record '{record_name}'")
        record = self.records[record_name]
        schema: Dict[str, Any] = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": record.name,
            "type": "object",
            "properties": {},
        }
        if record.doc:
            schema["description"] = record.doc
        if record.namespace:
            schema["$id"] = f"{record.namespace}.{record.name}"

        required: List[str] = []
        for field in record.fields:
            fragment = copy.deepcopy(field.json_schema or {})
            if field.doc:
                fragment.setdefault("description", field.doc)
            if field.default_factory == "dict":
                fragment.setdefault("default", {})
            elif field.default_factory == "list":
                fragment.setdefault("default", [])
            elif field.default_value is not None:
                fragment.setdefault("default", field.default_value)
            schema["properties"][field.name] = fragment
            if not field.optional and field.default is None and field.default_factory is None:
                required.append(field.name)

        if required:
            schema["required"] = required

        referenced_defs = _collect_references(schema["properties"].values())
        defs: Dict[str, Any] = {}
        processed: set[str] = set()
        queue: List[str] = list(referenced_defs)
        while queue:
            candidate = queue.pop(0)
            if candidate in processed:
                continue
            processed.add(candidate)
            if candidate in self.enums:
                defs[candidate] = _render_enum_definition(self.enums[candidate])
            elif candidate in self.records:
                definition = _render_record_definition(self.records[candidate])
                defs[candidate] = definition
                nested_refs = _collect_references(definition.get("properties", {}).values())
                queue.extend(nested_refs)
        if defs:
            schema["$defs"] = defs

        return json.dumps(schema, indent=2, sort_keys=False)


_PYTHON_PRIMITIVES = {
    "string": "str",
    "int": "int",
    "long": "int",
    "double": "float",
    "float": "float",
    "boolean": "bool",
    "bytes": "bytes",
}

_TS_PRIMITIVES = {
    "string": "string",
    "int": "number",
    "long": "number",
    "double": "number",
    "float": "number",
    "boolean": "boolean",
    "bytes": "Uint8Array",
}

_JSON_PRIMITIVES = {
    "string": {"type": "string"},
    "int": {"type": "integer"},
    "long": {"type": "integer"},
    "double": {"type": "number"},
    "float": {"type": "number"},
    "boolean": {"type": "boolean"},
    "bytes": {"type": "string", "contentEncoding": "base64"},
}


def _render_python_enum(enum: EnumDefinition) -> str:
    lines = ["", f"class {enum.name}(Enum):"]
    if enum.doc:
        lines.append(f'    """{enum.doc}"""')
    for symbol in enum.symbols:
        lines.append(f'    {symbol} = "{symbol}"')
    lines.append("")
    return "\n".join(lines)


def _render_python_record(record: RecordDefinition) -> str:
    lines = [""]
    lines.append(f"class {record.name}(BaseModel):")
    if record.doc:
        lines.append(f'    """{record.doc}"""')
    lines.append('    model_config = ConfigDict(extra="forbid")')
    if not record.fields:
        lines.append("    pass")
    for field in record.fields:
        annotation = field.type_hint
        default = ""
        if field.default_factory:
            default = f" = Field(default_factory={field.default_factory})"
        elif field.default is not None:
            default = f" = {field.default}"
        elif field.optional:
            default = " = None"
        lines.append(f"    {field.name}: {annotation}{default}")
    lines.append("")
    return "\n".join(lines)


def _render_ts_enum(enum: EnumDefinition) -> str:
    lines = [f"export enum {enum.name} {{"]
    for symbol in enum.symbols:
        lines.append(f'  {symbol} = "{symbol}",')
    lines.append("}")
    return "\n".join(lines)


def _render_ts_interface(record: RecordDefinition) -> str:
    lines = [f"export interface {record.name} {{"]
    for field in record.fields:
        ts_type = field.ts_type
        optional_flag = "?" if field.optional else ""
        lines.append(f"  {field.name}{optional_flag}: {ts_type};")
    lines.append("}")
    return "\n".join(lines)


def _render_enum_definition(enum: EnumDefinition) -> Dict[str, Any]:
    schema: Dict[str, Any] = {"type": "string", "enum": enum.symbols}
    if enum.doc:
        schema["description"] = enum.doc
    if enum.namespace:
        schema["title"] = enum.name
    return schema


def _render_record_definition(record: RecordDefinition) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for field in record.fields:
        fragment = copy.deepcopy(field.json_schema or {})
        if field.doc:
            fragment.setdefault("description", field.doc)
        if field.default_factory == "dict":
            fragment.setdefault("default", {})
        elif field.default_factory == "list":
            fragment.setdefault("default", [])
        elif field.default_value is not None:
            fragment.setdefault("default", field.default_value)
        properties[field.name] = fragment
        if not field.optional and field.default is None and field.default_factory is None:
            required.append(field.name)
    schema: Dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    if record.doc:
        schema["description"] = record.doc
    if record.namespace:
        schema["title"] = record.name
    return schema


def _collect_references(nodes) -> List[str]:
    refs: set[str] = set()
    stack = list(nodes)
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/$defs/"):
                refs.add(ref.split("/")[-1])
            for value in node.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return list(refs)


def _make_optional_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    schema_copy = copy.deepcopy(schema)
    schema_type = schema_copy.get("type")
    if isinstance(schema_type, list):
        if "null" not in schema_type:
            schema_copy["type"] = schema_type + ["null"]
    elif isinstance(schema_type, str):
        schema_copy["type"] = [schema_type, "null"]
    else:
        schema_copy = {"anyOf": [schema_copy, {"type": "null"}]}
    return schema_copy


def _is_null_type(value) -> bool:
    return value == "null" or (isinstance(value, dict) and value.get("type") == "null")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate event types from Avro schemas")
    parser.add_argument(
        "--registry", default="schemas/events", help="Path to schema registry directory"
    )
    parser.add_argument("--python-output", default="core/events/models.py")
    parser.add_argument("--ts-output", default="ui/dashboard/src/types/events.ts")
    args = parser.parse_args()

    registry = EventSchemaRegistry.from_directory(args.registry)
    collector = AvroSchemaCollector()
    for event in sorted(registry.available_events()):
        schema_info = registry.latest(event, SchemaFormat.AVRO)
        schema_doc = schema_info.load()
        collector.collect(schema_doc)
        json_output_dir = Path(args.registry) / "json" / schema_info.version_str
        json_output_dir.mkdir(parents=True, exist_ok=True)
        json_path = json_output_dir / f"{event}.schema.json"
        json_schema = collector.render_json_schema(schema_doc["name"])
        json_path.write_text(json_schema + "\n", encoding="utf-8")
    python_code = collector.render_python()
    Path(args.python_output).write_text(python_code + "\n", encoding="utf-8")
    ts_code = collector.render_typescript()
    Path(args.ts_output).write_text(ts_code, encoding="utf-8")


if __name__ == "__main__":
    main()
