"""Local schema registry with compatibility validation for TradePulse events."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Tuple

from packaging.version import Version


class SchemaFormat(str, Enum):
    """Supported serialization formats."""

    AVRO = "avro"
    PROTOBUF = "protobuf"
    JSON = "json_schema"


class SchemaCompatibilityError(RuntimeError):
    """Raised when schema compatibility validation fails."""


class SchemaFormatCoverageError(RuntimeError):
    """Raised when required schema formats are missing for a version."""


class SchemaLintError(RuntimeError):
    """Raised when schema linting detects documentation or contract issues."""


@dataclass(frozen=True)
class SchemaVersionInfo:
    """Metadata describing a concrete schema version."""

    version: Version
    version_str: str
    path: Path
    format: SchemaFormat
    subject: str | None = None
    namespace: str | None = None

    def load(self) -> Mapping[str, Any]:
        """Return the parsed schema document."""

        if self.format in (SchemaFormat.AVRO, SchemaFormat.JSON):
            with self.path.open("r", encoding="utf-8") as handle:
                result: Mapping[str, Any] = json.load(handle)
                return result
        raise ValueError(f"Unsupported load operation for {self.format}")


class EventSchemaRegistry:
    """Local schema registry backed by JSON metadata files."""

    def __init__(
        self,
        base_path: Path,
        registry: Dict[str, List[SchemaVersionInfo]],
        subjects: Dict[str, Dict[Version, str]],
        namespaces: Dict[str, Dict[Version, str]],
        versions: Dict[str, Dict[Version, Dict[SchemaFormat, SchemaVersionInfo]]],
    ):
        self._base_path = base_path
        self._registry = registry
        self._subjects = subjects
        self._namespaces = namespaces
        self._versions = versions

    @classmethod
    def from_directory(cls, base_path: str | Path) -> "EventSchemaRegistry":
        """Build a registry instance from the canonical registry.json file."""

        root = Path(base_path)
        registry_path = root / "registry.json"
        if not registry_path.exists():
            raise FileNotFoundError(
                f"Schema registry descriptor not found: {registry_path}"
            )
        with registry_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        events: Dict[str, List[SchemaVersionInfo]] = {}
        subjects: Dict[str, Dict[Version, str]] = {}
        namespaces: Dict[str, Dict[Version, str]] = {}
        versions_index: Dict[
            str, Dict[Version, Dict[SchemaFormat, SchemaVersionInfo]]
        ] = {}
        for event_type, event_data in payload.get("events", {}).items():
            versions: List[SchemaVersionInfo] = []
            subject_map: Dict[Version, str] = {}
            namespace_map: Dict[Version, str] = {}
            format_map: Dict[Version, Dict[SchemaFormat, SchemaVersionInfo]] = {}
            for version_info in event_data.get("versions", []):
                raw_version = version_info["version"]
                parsed_version = Version(raw_version)
                subject = version_info.get("subject") or event_data.get("subject")
                namespace = version_info.get("namespace") or event_data.get("namespace")
                if subject:
                    subject_map[parsed_version] = subject
                if namespace:
                    namespace_map[parsed_version] = namespace
                avro_path = root / version_info[SchemaFormat.AVRO.value]
                version_bucket = format_map.setdefault(parsed_version, {})
                if SchemaFormat.AVRO in version_bucket:
                    raise ValueError(
                        f"Duplicate Avro schema declaration for {event_type} {raw_version}"
                    )
                avro_info = SchemaVersionInfo(
                    version=parsed_version,
                    version_str=raw_version,
                    path=avro_path,
                    format=SchemaFormat.AVRO,
                    subject=subject,
                    namespace=namespace,
                )
                versions.append(avro_info)
                version_bucket[SchemaFormat.AVRO] = avro_info
                if SchemaFormat.JSON.value in version_info:
                    json_path = root / version_info[SchemaFormat.JSON.value]
                    if SchemaFormat.JSON in version_bucket:
                        raise ValueError(
                            f"Duplicate JSON schema declaration for {event_type} {raw_version}"
                        )
                    json_info = SchemaVersionInfo(
                        version=parsed_version,
                        version_str=raw_version,
                        path=json_path,
                        format=SchemaFormat.JSON,
                        subject=subject,
                        namespace=namespace,
                    )
                    versions.append(json_info)
                    version_bucket[SchemaFormat.JSON] = json_info
                if SchemaFormat.PROTOBUF.value in version_info:
                    if SchemaFormat.PROTOBUF in version_bucket:
                        raise ValueError(
                            f"Duplicate protobuf schema declaration for {event_type} {raw_version}"
                        )
                    proto_info = SchemaVersionInfo(
                        version=parsed_version,
                        version_str=raw_version,
                        path=(
                            root / version_info[SchemaFormat.PROTOBUF.value]
                        ).resolve(),
                        format=SchemaFormat.PROTOBUF,
                        subject=subject,
                        namespace=namespace,
                    )
                    versions.append(proto_info)
                    version_bucket[SchemaFormat.PROTOBUF] = proto_info
            events[event_type] = versions
            subjects[event_type] = subject_map
            namespaces[event_type] = namespace_map
            versions_index[event_type] = format_map
        return cls(root, events, subjects, namespaces, versions_index)

    def available_events(self) -> Iterable[str]:
        return self._registry.keys()

    @property
    def base_path(self) -> Path:
        """Return the root directory containing schema definitions."""

        return self._base_path

    def versions(self, event_type: str) -> List[Version]:
        """Return all known versions for the requested event type."""

        if event_type not in self._versions:
            raise KeyError(f"Unknown event type '{event_type}'")
        return sorted(self._versions[event_type].keys())

    def get_versions(
        self, event_type: str, fmt: SchemaFormat
    ) -> List[SchemaVersionInfo]:
        if event_type not in self._registry:
            raise KeyError(f"Unknown event type '{event_type}'")
        return [info for info in self._registry[event_type] if info.format is fmt]

    def get(
        self,
        event_type: str,
        fmt: SchemaFormat,
        version: str | Version | None = None,
    ) -> SchemaVersionInfo:
        """Return the schema metadata for the requested version and format."""

        if version is None:
            return self.latest(event_type, fmt)
        if isinstance(version, str):
            version = Version(version)
        if event_type not in self._versions:
            raise KeyError(f"Unknown event type '{event_type}'")
        event_versions = self._versions[event_type]
        if version not in event_versions:
            raise KeyError(
                f"Version '{version}' not registered for event '{event_type}'"
            )
        format_map = event_versions[version]
        if fmt not in format_map:
            raise KeyError(
                f"No {fmt.value} schema registered for version '{version}' of '{event_type}'"
            )
        return format_map[fmt]

    def latest(self, event_type: str, fmt: SchemaFormat) -> SchemaVersionInfo:
        versions = self.get_versions(event_type, fmt)
        if not versions:
            raise KeyError(f"No {fmt.value} schema registered for '{event_type}'")
        return max(versions, key=lambda info: info.version)

    def subject(self, event_type: str, version: str | Version | None = None) -> str:
        """Return the canonical subject for the requested event version."""

        if event_type not in self._subjects:
            raise KeyError(f"Unknown event type '{event_type}'")
        if version is None:
            version = self.latest(event_type, SchemaFormat.AVRO).version
        elif isinstance(version, str):
            version = Version(version)
        subject_map = self._subjects[event_type]
        if version not in subject_map:
            raise KeyError(
                f"No subject registered for version '{version}' of '{event_type}'"
            )
        return subject_map[version]

    def namespace(self, event_type: str, version: str | Version | None = None) -> str:
        """Return the canonical Avro namespace for the requested event version."""

        if event_type not in self._namespaces:
            raise KeyError(f"Unknown event type '{event_type}'")
        if version is None:
            version = self.latest(event_type, SchemaFormat.AVRO).version
        elif isinstance(version, str):
            version = Version(version)
        namespace_map = self._namespaces[event_type]
        if version not in namespace_map:
            raise KeyError(
                f"No namespace registered for version '{version}' of '{event_type}'"
            )
        return namespace_map[version]

    def validate_format_coverage(
        self,
        event_type: str,
        required_formats: Iterable[SchemaFormat] | None = (
            SchemaFormat.AVRO,
            SchemaFormat.JSON,
        ),
    ) -> None:
        """Ensure every version for an event exposes the expected serialization formats."""

        if event_type not in self._versions:
            raise KeyError(f"Unknown event type '{event_type}'")
        event_versions = self._versions[event_type]
        if not event_versions:
            return
        expected_formats: set[SchemaFormat] | None = None
        required_set = set(required_formats or [])
        for version, format_map in sorted(event_versions.items()):
            formats = set(format_map.keys())
            if expected_formats is None:
                expected_formats = formats
            elif formats != expected_formats:
                missing = expected_formats - formats
                extra = formats - expected_formats
                raise SchemaFormatCoverageError(
                    "Format coverage mismatch for "
                    f"'{event_type}' version '{version}': missing {sorted(m.value for m in missing)}; "
                    f"unexpected {sorted(fmt.value for fmt in extra)}"
                )
            missing_required = required_set - formats
            if missing_required:
                raise SchemaFormatCoverageError(
                    "Required formats missing for "
                    f"'{event_type}' version '{version}': {sorted(fmt.value for fmt in missing_required)}"
                )

    def validate_backward_and_forward(self, event_type: str) -> None:
        """Ensure all registered versions are backward and forward compatible."""

        avro_versions = sorted(
            self.get_versions(event_type, SchemaFormat.AVRO),
            key=lambda info: info.version,
        )
        if not avro_versions:
            return
        schemas = [version.load() for version in avro_versions]
        self._validate_sequential_backward(schemas)
        self._validate_sequential_forward(schemas)

    def validate_all(self) -> None:
        for event in self.available_events():
            self.validate_format_coverage(event)
            self.validate_backward_and_forward(event)
            self.lint_event(event)

    def lint_all(self) -> None:
        """Run linting for all registered events."""

        for event in self.available_events():
            self.lint_event(event)

    def lint_event(self, event_type: str) -> None:
        """Run schema linting checks for a specific event type."""

        avro_versions = self.get_versions(event_type, SchemaFormat.AVRO)
        if not avro_versions:
            raise SchemaLintError(f"No Avro schema registered for '{event_type}'")
        for avro_info in avro_versions:
            schema = avro_info.load()
            _lint_avro_schema(schema, event_type, avro_info.version_str)
            json_info = self._versions[event_type][avro_info.version].get(
                SchemaFormat.JSON
            )
            if json_info:
                json_schema = json_info.load()
                _lint_json_schema_alignment(
                    schema,
                    json_schema,
                    event_type,
                    avro_info.version_str,
                )
            proto_info = self._versions[event_type][avro_info.version].get(
                SchemaFormat.PROTOBUF
            )
            if proto_info:
                _lint_protobuf_alignment(
                    schema,
                    proto_info.path,
                    event_type,
                    avro_info.version_str,
                )

    def catalogue(self) -> Dict[str, Dict[str, Any]]:
        """Return a serialisable catalogue of events and versions."""

        summary: Dict[str, Dict[str, Any]] = {}
        for event in sorted(self.available_events()):
            versions = []
            for version in sorted(
                self._versions[event].items(), key=lambda item: item[0]
            ):
                version_id, formats = version
                entry = {
                    "version": str(version_id),
                    "formats": sorted(fmt.value for fmt in formats.keys()),
                }
                if version_id in self._subjects[event]:
                    entry["subject"] = self._subjects[event][version_id]
                if version_id in self._namespaces[event]:
                    entry["namespace"] = self._namespaces[event][version_id]
                versions.append(entry)
            summary[event] = {
                "versions": versions,
                "latest": str(self.latest(event, SchemaFormat.AVRO).version),
            }
            if self._subjects[event]:
                summary[event]["subjects"] = {
                    str(version): subject
                    for version, subject in sorted(
                        self._subjects[event].items(), key=lambda item: item[0]
                    )
                }
            if self._namespaces[event]:
                summary[event]["namespaces"] = {
                    str(version): namespace
                    for version, namespace in sorted(
                        self._namespaces[event].items(), key=lambda item: item[0]
                    )
                }
        return summary

    def _validate_sequential_backward(self, schemas: List[Mapping[str, Any]]) -> None:
        for previous, current in zip(schemas, schemas[1:]):
            missing = [
                field["name"]
                for field in previous.get("fields", [])
                if field["name"] not in _field_name_index(current)
            ]
            if missing:
                raise SchemaCompatibilityError(
                    f"Backward compatibility broken: fields {missing} removed or renamed"
                )
            for field in previous.get("fields", []):
                name = field["name"]
                prev_type = _normalise_avro_type(field["type"])
                curr_field = _field_name_index(current)[name]
                curr_type = _normalise_avro_type(curr_field["type"])
                if prev_type != curr_type:
                    raise SchemaCompatibilityError(
                        f"Backward compatibility broken for field '{name}': {prev_type} != {curr_type}"
                    )

    def _validate_sequential_forward(self, schemas: List[Mapping[str, Any]]) -> None:
        for previous, current in zip(schemas, schemas[1:]):
            for field in current.get("fields", []):
                name = field["name"]
                if name not in _field_name_index(previous):
                    if not _is_nullable(field) and "default" not in field:
                        raise SchemaCompatibilityError(
                            f"Forward compatibility broken: new field '{name}' missing default or nullable"
                        )


def _field_name_index(schema: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {field["name"]: field for field in schema.get("fields", [])}


def _normalise_avro_type(avro_type: Any) -> Tuple:
    """Normalise Avro type declarations to tuples for comparison."""

    if isinstance(avro_type, str):
        return (avro_type,)
    if isinstance(avro_type, list):
        return tuple(sorted(_normalise_union_member(member) for member in avro_type))
    if isinstance(avro_type, Mapping):
        type_name = avro_type.get("type")
        if type_name == "record":
            return (
                "record",
                avro_type.get("name"),
                tuple(
                    (field["name"], _normalise_avro_type(field["type"]))
                    for field in avro_type.get("fields", [])
                ),
            )
        if type_name == "enum":
            return ("enum", avro_type.get("name"), tuple(avro_type.get("symbols", [])))
        if type_name == "array":
            return ("array", _normalise_avro_type(avro_type.get("items")))
        if type_name == "map":
            return ("map", _normalise_avro_type(avro_type.get("values")))
        if type_name == "fixed":
            return ("fixed", avro_type.get("name"), avro_type.get("size"))
        return (type_name,)
    raise TypeError(f"Unsupported Avro type declaration: {avro_type!r}")


def _normalise_union_member(member: Any) -> Tuple:
    if isinstance(member, str):
        return (member,)
    return _normalise_avro_type(member)


def _is_nullable(field: Mapping[str, Any]) -> bool:
    avro_type = field["type"]
    if isinstance(avro_type, list):
        return any(
            member == "null"
            or (isinstance(member, Mapping) and member.get("type") == "null")
            for member in avro_type
        )
    return False


def _lint_avro_schema(schema: Mapping[str, Any], event_type: str, version: str) -> None:
    if schema.get("type") != "record":
        raise SchemaLintError(
            f"{event_type}@{version}: root schema must be an Avro record"
        )
    record_name = schema.get("name", "<unknown>")
    if not schema.get("doc"):
        raise SchemaLintError(
            f"{event_type}@{version}: record '{record_name}' missing documentation"
        )

    fields = schema.get("fields", [])
    if not isinstance(fields, list) or not fields:
        raise SchemaLintError(
            f"{event_type}@{version}: record '{record_name}' defines no fields"
        )

    schema_field_names = {field.get("name") for field in fields}
    if "schema_version" not in schema_field_names:
        raise SchemaLintError(
            f"{event_type}@{version}: record '{record_name}' missing 'schema_version' field"
        )
    schema_version_field = next(
        field for field in fields if field.get("name") == "schema_version"
    )
    if _normalise_avro_type(schema_version_field.get("type")) != ("string",):
        raise SchemaLintError(
            f"{event_type}@{version}: 'schema_version' must be a string"
        )

    for record in _iter_avro_records(schema):
        record_doc = record.get("doc")
        record_name = record.get("name", "<anonymous>")
        if not record_doc:
            raise SchemaLintError(
                f"{event_type}@{version}: record '{record_name}' missing documentation"
            )
        for field in record.get("fields", []):
            field_name = field.get("name")
            if not field_name:
                raise SchemaLintError(
                    f"{event_type}@{version}: unnamed field in record '{record_name}'"
                )
            field_doc = field.get("doc")
            if not field_doc:
                raise SchemaLintError(
                    f"{event_type}@{version}: field '{record_name}.{field_name}' missing documentation"
                )
            if _is_nullable(field) and "default" not in field:
                raise SchemaLintError(
                    f"{event_type}@{version}: field '{record_name}.{field_name}' is nullable but lacks a default"
                )


def _lint_json_schema_alignment(
    avro_schema: Mapping[str, Any],
    json_schema: Mapping[str, Any],
    event_type: str,
    version: str,
) -> None:
    properties = json_schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise SchemaLintError(
            f"{event_type}@{version}: JSON schema missing object properties"
        )

    avro_fields = avro_schema.get("fields", [])
    avro_field_names = [field["name"] for field in avro_fields]
    json_field_names = set(properties.keys())
    missing = set(avro_field_names) - json_field_names
    extra = json_field_names - set(avro_field_names)
    if missing or extra:
        raise SchemaLintError(
            f"{event_type}@{version}: JSON schema mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )

    json_required = set(json_schema.get("required", []))
    for field in avro_fields:
        name = field["name"]
        optional = _is_nullable(field) or "default" in field
        if optional and name in json_required:
            raise SchemaLintError(
                f"{event_type}@{version}: JSON schema marks optional field '{name}' as required"
            )
        if not optional and name not in json_required:
            raise SchemaLintError(
                f"{event_type}@{version}: JSON schema missing required field '{name}'"
            )
        fragment = properties[name]
        if not isinstance(fragment, Mapping):
            raise SchemaLintError(
                f"{event_type}@{version}: JSON property '{name}' must be an object"
            )
        if "description" not in fragment:
            raise SchemaLintError(
                f"{event_type}@{version}: JSON property '{name}' missing description"
            )

    for def_name, definition in json_schema.get("$defs", {}).items():
        if not isinstance(definition, Mapping):
            raise SchemaLintError(
                f"{event_type}@{version}: JSON definition '{def_name}' must be an object"
            )
        if definition.get("type") == "object":
            if "description" not in definition:
                raise SchemaLintError(
                    f"{event_type}@{version}: JSON definition '{def_name}' missing description"
                )
            nested_props = definition.get("properties", {})
            if isinstance(nested_props, Mapping):
                for nested_name, nested_fragment in nested_props.items():
                    if (
                        isinstance(nested_fragment, Mapping)
                        and "description" not in nested_fragment
                    ):
                        raise SchemaLintError(
                            f"{event_type}@{version}: JSON definition '{def_name}.{nested_name}' missing description"
                        )


def _lint_protobuf_alignment(
    avro_schema: Mapping[str, Any],
    proto_path: Path,
    event_type: str,
    version: str,
) -> None:
    record_name = avro_schema.get("name")
    if not record_name:
        raise SchemaLintError(
            f"{event_type}@{version}: unable to infer record name for protobuf validation"
        )
    major_version = Version(version).major
    expected_message = f"message {record_name}V{major_version}"
    try:
        contents = proto_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:  # pragma: no cover - surfaced in linting
        raise SchemaLintError(
            f"{event_type}@{version}: protobuf file missing at {proto_path}"
        ) from exc
    if expected_message not in contents:
        raise SchemaLintError(
            f"{event_type}@{version}: protobuf definition missing '{expected_message}'"
        )


def _iter_avro_records(schema: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    queue: List[Mapping[str, Any]] = []
    if schema.get("type") == "record":
        queue.append(schema)
    seen: set[Tuple[str | None, str | None]] = set()
    while queue:
        record = queue.pop(0)
        key = (record.get("namespace"), record.get("name"))
        if key in seen:
            continue
        seen.add(key)
        yield record
        for field in record.get("fields", []):
            queue.extend(_extract_record_types(field.get("type")))


def _extract_record_types(avro_type: Any) -> List[Mapping[str, Any]]:
    records: List[Mapping[str, Any]] = []
    if isinstance(avro_type, Mapping):
        avro_kind = avro_type.get("type")
        if avro_kind == "record":
            records.append(avro_type)
            for field in avro_type.get("fields", []):
                records.extend(_extract_record_types(field.get("type")))
        elif avro_kind == "array":
            records.extend(_extract_record_types(avro_type.get("items")))
        elif avro_kind == "map":
            records.extend(_extract_record_types(avro_type.get("values")))
    elif isinstance(avro_type, list):
        for member in avro_type:
            records.extend(_extract_record_types(member))
    return records
