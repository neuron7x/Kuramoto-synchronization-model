"""Contract validation helpers between Pydantic models and registered schemas."""

from __future__ import annotations

from collections.abc import Mapping as MappingABC
from collections.abc import Sequence as SequenceABC
from enum import Enum
from types import NoneType, UnionType
from typing import Any, Tuple, Type, Union, get_args, get_origin

from packaging.version import Version
from pydantic import BaseModel

from .schema_registry import EventSchemaRegistry, SchemaFormat


class SchemaContractError(RuntimeError):
    """Raised when a Python data model diverges from the canonical schema."""


class SchemaContractValidator:
    """Validate that producer/consumer models adhere to the registered schemas."""

    def __init__(self, registry: EventSchemaRegistry) -> None:
        self._registry = registry

    def validate_model(
        self,
        event_type: str,
        model: type[BaseModel],
        version: str | Version | None = None,
    ) -> None:
        """Ensure ``model`` matches the Avro declaration for ``event_type``."""

        schema_meta = self._registry.get(event_type, SchemaFormat.AVRO, version)
        schema = schema_meta.load()
        if schema.get("type") != "record":
            raise SchemaContractError(
                f"Schema for '{event_type}' is not an Avro record: {schema.get('type')}"
            )
        _ensure_model_ready(model)
        _validate_record_schema(
            record_schema=schema,
            model=model,
            context=f"{event_type}@{schema_meta.version_str}",
        )


def _ensure_model_ready(model: type[BaseModel]) -> None:
    """Ensure forward references on the model are resolved."""

    if hasattr(model, "model_rebuild"):
        model.model_rebuild()


def _validate_record_schema(
    record_schema: MappingABC[str, Any],
    model: type[BaseModel],
    context: str,
) -> None:
    schema_fields = record_schema.get("fields", [])
    model_fields = model.model_fields
    schema_field_names = {field["name"] for field in schema_fields}
    model_field_names = set(model_fields.keys())

    missing_fields = schema_field_names - model_field_names
    if missing_fields:
        raise SchemaContractError(
            f"Model '{model.__name__}' missing fields {sorted(missing_fields)} for {context}"
        )

    extra_fields = model_field_names - schema_field_names
    if extra_fields:
        raise SchemaContractError(
            f"Model '{model.__name__}' has extra fields {sorted(extra_fields)} for {context}"
        )

    for field_schema in schema_fields:
        name = field_schema["name"]
        field_context = f"{context}.{name}"
        model_field = model_fields[name]
        avro_optional = _is_nullable(field_schema)
        has_default = "default" in field_schema
        model_required = model_field.is_required()
        if avro_optional and model_required:
            raise SchemaContractError(
                f"{field_context}: schema is optional but model requires the field"
            )
        if not avro_optional and not has_default and not model_required:
            raise SchemaContractError(
                f"{field_context}: schema marks the field as required but model treats it as optional"
            )
        avro_type = _strip_null(field_schema["type"], field_context)
        _validate_type_compatibility(avro_type, model_field.annotation, field_context)


def _validate_type_compatibility(avro_type: Any, annotation: Any, context: str) -> None:
    annotation, _ = _unwrap_optional(annotation)

    if isinstance(avro_type, str):
        _ensure_primitive(annotation, avro_type, context)
        return

    if isinstance(avro_type, MappingABC):
        avro_type_name = avro_type.get("type")
        if avro_type_name == "record":
            model_cls = _as_model_class(annotation, context)
            _ensure_model_ready(model_cls)
            _validate_record_schema(avro_type, model_cls, context)
            return
        if avro_type_name == "enum":
            enum_cls = _as_enum_class(annotation, context)
            _validate_enum(avro_type, enum_cls, context)
            return
        if avro_type_name == "array":
            item_type = avro_type.get("items")
            element_annotation = _sequence_element(annotation, context)
            _validate_type_compatibility(item_type, element_annotation, f"{context}[]")
            return
        if avro_type_name == "map":
            value_type = avro_type.get("values")
            key_annotation, value_annotation = _mapping_types(annotation, context)
            if key_annotation not in (str, Any):
                raise SchemaContractError(
                    f"{context}: Avro maps require string keys, model uses {key_annotation}"
                )
            _validate_type_compatibility(
                value_type, value_annotation, f"{context}<'value'>"
            )
            return
        if avro_type_name == "fixed":
            _ensure_primitive(annotation, "bytes", context)
            return
        if isinstance(avro_type_name, str):
            _ensure_primitive(annotation, avro_type_name, context)
            return
        raise SchemaContractError(f"{context}: unsupported Avro type {avro_type!r}")

    if isinstance(avro_type, SequenceABC):
        # After null stripping we do not expect unions. Guard for defensive programming.
        non_null = [member for member in avro_type if not _is_null(member)]
        if len(non_null) != 1:
            raise SchemaContractError(f"{context}: complex unions are not supported")
        _validate_type_compatibility(non_null[0], annotation, context)
        return

    raise SchemaContractError(f"{context}: unsupported Avro declaration {avro_type!r}")


def _ensure_primitive(annotation: Any, avro_primitive: str, context: str) -> None:
    expected = _PRIMITIVE_TYPE_MAP.get(avro_primitive)
    if expected is None:
        raise SchemaContractError(
            f"{context}: unsupported Avro primitive '{avro_primitive}'"
        )
    if annotation is Any:
        return
    if annotation is None:
        raise SchemaContractError(f"{context}: annotation missing for primitive type")
    origin = get_origin(annotation)
    if origin is not None:
        raise SchemaContractError(
            f"{context}: expected scalar compatible with {avro_primitive}, got {annotation!r}"
        )
    if not isinstance(annotation, type):
        raise SchemaContractError(
            f"{context}: expected concrete type for primitive, got {annotation!r}"
        )
    if not any(_issubclass_safe(annotation, candidate) for candidate in expected):
        expected_names = ", ".join(t.__name__ for t in expected)
        raise SchemaContractError(
            f"{context}: expected type compatible with {expected_names}, got {annotation.__name__}"
        )


def _validate_enum(
    avro_enum: MappingABC[str, Any], enum_cls: Type[Enum], context: str
) -> None:
    symbols = set(avro_enum.get("symbols", []))
    enum_values = {member.value for member in enum_cls}
    if symbols != enum_values:
        raise SchemaContractError(
            f"{context}: enum values mismatch, schema has {sorted(symbols)}, model has {sorted(enum_values)}"
        )


def _sequence_element(annotation: Any, context: str) -> Any:
    origin = get_origin(annotation)
    if origin in {list, tuple} or _is_sequence_origin(origin):
        args = get_args(annotation)
        if not args:
            raise SchemaContractError(
                f"{context}: sequence annotation missing type arguments"
            )
        return args[0]
    if isinstance(annotation, type) and issubclass(annotation, SequenceABC):
        raise SchemaContractError(
            f"{context}: sequence annotations must include item type information"
        )
    raise SchemaContractError(
        f"{context}: schema defines an array but model annotation is {annotation!r}"
    )


def _mapping_types(annotation: Any, context: str) -> Tuple[Any, Any]:
    origin = get_origin(annotation)
    if origin in {dict} or _is_mapping_origin(origin):
        args = get_args(annotation)
        if len(args) != 2:
            raise SchemaContractError(
                f"{context}: mapping annotation must declare key/value types"
            )
        return args[0], args[1]
    if isinstance(annotation, type) and issubclass(annotation, MappingABC):
        raise SchemaContractError(
            f"{context}: mapping annotations must include key/value type hints"
        )
    raise SchemaContractError(
        f"{context}: schema defines a map but model annotation is {annotation!r}"
    )


def _as_model_class(annotation: Any, context: str) -> type[BaseModel]:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    raise SchemaContractError(
        f"{context}: expected Pydantic BaseModel for record field, got {annotation!r}"
    )


def _as_enum_class(annotation: Any, context: str) -> type[Enum]:
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation
    raise SchemaContractError(
        f"{context}: expected Enum for enum field, got {annotation!r}"
    )


def _unwrap_optional(annotation: Any) -> Tuple[Any, bool]:
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        args = get_args(annotation)
        non_null = [arg for arg in args if arg is not NoneType]
        if len(non_null) == 1 and len(non_null) != len(args):
            return non_null[0], True
    return annotation, False


def _strip_null(avro_type: Any, context: str) -> Any:
    if isinstance(avro_type, list):
        non_null = [member for member in avro_type if not _is_null(member)]
        if len(non_null) != 1:
            raise SchemaContractError(
                f"{context}: union types must only contain optional null members"
            )
        return non_null[0]
    return avro_type


def _is_null(member: Any) -> bool:
    return member == "null" or (
        isinstance(member, MappingABC) and member.get("type") == "null"
    )


def _is_nullable(field_schema: MappingABC[str, Any]) -> bool:
    return isinstance(field_schema.get("type"), list) and any(
        _is_null(member) for member in field_schema["type"]
    )


def _issubclass_safe(candidate: type, expected: type) -> bool:
    try:
        return issubclass(candidate, expected)
    except TypeError:  # pragma: no cover - defensive for non-class annotations
        return False


def _is_sequence_origin(origin: Any) -> bool:
    try:
        return issubclass(origin, SequenceABC)
    except TypeError:
        return False


def _is_mapping_origin(origin: Any) -> bool:
    try:
        return issubclass(origin, MappingABC)
    except TypeError:
        return False


_PRIMITIVE_TYPE_MAP: dict[str, Tuple[type, ...]] = {
    "string": (str,),
    "bytes": (bytes, bytearray, memoryview),
    "boolean": (bool,),
    "double": (float,),
    "float": (float,),
    "long": (int,),
    "int": (int,),
}
