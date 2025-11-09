# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""JSON Schema generation for TradePulse data structures."""
from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Type, get_args, get_origin, get_type_hints

try:  # pragma: no cover - optional dependency shim
    from pydantic import BaseModel
except ModuleNotFoundError:  # pragma: no cover - exercised when dependency missing
    BaseModel = None  # type: ignore[assignment]


def dataclass_to_json_schema(
    cls: Type[Any], title: str | None = None
) -> Dict[str, Any]:
    """Convert a dataclass to JSON Schema.

    Args:
        cls: Dataclass type to convert
        title: Optional schema title (defaults to class name)

    Returns:
        JSON Schema dictionary

    Example:
        >>> from core.indicators.base import FeatureResult
        >>> schema = dataclass_to_json_schema(FeatureResult)
        >>> print(json.dumps(schema, indent=2))
    """
    if not is_dataclass(cls):
        raise TypeError(f"{cls} is not a dataclass")

    schema: Dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "title": title or cls.__name__,
        "description": cls.__doc__ or f"Schema for {cls.__name__}",
        "properties": {},
        "required": [],
    }

    # Get type hints for the class
    hints = get_type_hints(cls)

    for field in fields(cls):
        field_name = field.name
        field_type = hints.get(field_name, field.type)

        # Build property schema
        prop_schema = _type_to_schema(field_type)

        # Add field metadata if available
        if field.metadata:
            prop_schema.update(field.metadata)

        schema["properties"][field_name] = prop_schema

        # Check if required (no default value)
        from dataclasses import MISSING

        if field.default is MISSING and field.default_factory is MISSING:
            schema["required"].append(field_name)

    # Clean up if no required fields
    if not schema["required"]:
        del schema["required"]

    return schema


def _type_to_schema(typ: Any) -> Dict[str, Any]:
    """Convert a Python type to JSON Schema type."""

    origin = get_origin(typ)
    args = get_args(typ)

    # Handle None/Optional
    if typ is type(None):
        return {"type": "null"}

    # Handle Annotated types (PEP 593)
    from typing import (
        Annotated,
        Union,
    )  # Local import to avoid circular deps at module import

    if origin is Annotated:
        return _type_to_schema(args[0])

    # Handle Union types (including Optional)
    if origin is Union:
        allow_null = False
        schemas = []
        for arg in args:
            if arg is type(None):
                allow_null = True
                continue
            schemas.append(_type_to_schema(arg))

        if not schemas and allow_null:
            return {"type": "null"}

        if allow_null:
            schemas.append({"type": "null"})

        if len(schemas) == 1:
            return schemas[0]

        return {"anyOf": schemas}

    # Handle typing.Any explicitly
    if typ is Any:
        return {}

    # Handle basic types
    type_mapping = {
        int: {"type": "integer"},
        float: {"type": "number"},
        str: {"type": "string"},
        bool: {"type": "boolean"},
        dict: {"type": "object"},
        list: {"type": "array"},
        Decimal: {"type": "number"},
        datetime: {"type": "string", "format": "date-time"},
        date: {"type": "string", "format": "date"},
        time: {"type": "string", "format": "time"},
    }

    if typ in type_mapping:
        return type_mapping[typ]

    # Handle Enum types
    if isinstance(typ, type) and issubclass(typ, Enum):
        return {"type": "string", "enum": [member.value for member in typ]}

    # Handle dataclass types
    if isinstance(typ, type) and is_dataclass(typ):
        return dataclass_to_json_schema(typ)

    # Handle Pydantic models
    if BaseModel is not None and isinstance(typ, type) and issubclass(typ, BaseModel):
        schema = typ.model_json_schema()
        schema.setdefault("title", typ.__name__)
        if typ.__doc__:
            schema.setdefault("description", typ.__doc__.strip())
        return schema

    # Handle Dict types
    if origin is dict or typ is dict:
        result_schema: Dict[str, Any] = {"type": "object"}
        if args and len(args) == 2:
            value_schema = _type_to_schema(args[1])
            result_schema["additionalProperties"] = value_schema
        return result_schema

    # Handle Mapping types
    from collections.abc import Mapping

    if origin and issubclass(origin, Mapping):
        mapping_schema: Dict[str, Any] = {"type": "object"}
        if args and len(args) == 2:
            mapping_schema["additionalProperties"] = _type_to_schema(args[1])
        return mapping_schema

    # Handle List/Sequence/Set types
    if origin in {list, tuple, set, frozenset} or typ in {list, tuple, set, frozenset}:
        list_schema: Dict[str, Any] = {"type": "array"}
        if args:
            list_schema["items"] = _type_to_schema(args[0])
        if origin in {set, frozenset} or typ in {set, frozenset}:
            list_schema["uniqueItems"] = True
        return list_schema

    # Handle generic Iterable[...] as arrays
    from collections.abc import Iterable as ABCIterable

    if origin and issubclass(origin, ABCIterable):
        list_schema = {"type": "array"}
        if args:
            list_schema["items"] = _type_to_schema(args[0])
        return list_schema

    # Default to Any
    return {}


def generate_all_schemas() -> Dict[str, Dict[str, Any]]:
    """Generate schemas for all key TradePulse data structures.

    Returns:
        Dictionary mapping class names to schemas
    """
    from backtest.engine import Result
    from core.data.models import Ticker
    from core.indicators.base import FeatureResult

    schemas = {}

    # Core schemas
    schemas["FeatureResult"] = dataclass_to_json_schema(
        FeatureResult, title="FeatureResult"
    )
    schemas["FeatureResult"]["description"] = (
        "Result from a feature/indicator transformation. Contains the computed "
        "value, metadata, and feature name."
    )

    schemas["BacktestResult"] = dataclass_to_json_schema(Result, title="BacktestResult")
    schemas["BacktestResult"]["description"] = (
        "Result from a backtest run. Contains profit/loss, maximum drawdown, "
        "and number of trades."
    )

    schemas["Ticker"] = model_to_json_schema(Ticker, title="Ticker")
    schemas["Ticker"][
        "description"
    ] = "Market data tick with instrument metadata, price and volume information."

    return schemas


def save_schemas(output_dir: str = "docs/schemas") -> None:
    """Generate and save all schemas to JSON files.

    Args:
        output_dir: Directory to save schema files
    """
    import os

    os.makedirs(output_dir, exist_ok=True)

    schemas = generate_all_schemas()

    for name, schema in schemas.items():
        filename = os.path.join(output_dir, f"{name}.json")
        with open(filename, "w") as f:
            json.dump(schema, f, indent=2)

    # Generate index file
    index = {
        "schemas": list(schemas.keys()),
        "version": "1.0.0",
        "base_url": "/schemas/",
    }

    with open(os.path.join(output_dir, "index.json"), "w") as f:
        json.dump(index, f, indent=2)


def validate_against_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """Validate data against a JSON schema (basic validation).

    Args:
        data: Data dictionary to validate
        schema: JSON Schema to validate against

    Returns:
        True if valid

    Raises:
        ValueError: If validation fails
    """
    # Check required fields
    if "required" in schema:
        for field in schema["required"]:
            if field not in data:
                raise ValueError(f"Missing required field: {field}")

    # Check property types
    if "properties" in schema:
        for key, value in data.items():
            if key not in schema["properties"]:
                continue

            prop_schema = schema["properties"][key]
            expected_types = _extract_expected_types(prop_schema)

            if not expected_types:
                continue

            if not any(_value_matches_type(value, expected_type) for expected_type in expected_types):
                expected_description = _format_expected_types(expected_types)
                raise ValueError(
                    f"Field {key} should be {expected_description}, got {type(value)}"
                )

    return True


def _extract_expected_types(prop_schema: Dict[str, Any]) -> set[str]:
    """Return the set of JSON schema type names expected for a property."""

    types: set[str] = set()

    raw_type = prop_schema.get("type")
    if isinstance(raw_type, str):
        types.add(raw_type)
    elif isinstance(raw_type, list):
        for type_name in raw_type:
            if isinstance(type_name, str):
                types.add(type_name)

    for keyword in ("anyOf", "oneOf"):
        for option in prop_schema.get(keyword, []):
            if isinstance(option, dict):
                types.update(_extract_expected_types(option))

    return types


def _value_matches_type(value: Any, schema_type: str) -> bool:
    """Return whether a value conforms to the provided schema type."""

    if schema_type == "null":
        return value is None
    if schema_type == "integer":
        return isinstance(value, int)
    if schema_type == "number":
        return isinstance(value, (int, float))
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "object":
        return isinstance(value, dict)

    # Unknown type specifiers fall back to permissive validation
    return True


def _format_expected_types(expected_types: set[str]) -> str:
    """Return a human-readable description of the expected types."""

    types = sorted(expected_types)

    if not types:
        return "valid type"
    if len(types) == 1:
        return types[0]

    return ", ".join(types[:-1]) + f" or {types[-1]}"


def model_to_json_schema(cls: Type[Any], title: str | None = None) -> Dict[str, Any]:
    """Return a JSON schema for either a dataclass or a Pydantic model."""

    if BaseModel is not None and isinstance(cls, type) and issubclass(cls, BaseModel):
        schema = cls.model_json_schema()
        if title:
            schema["title"] = title
        if cls.__doc__:
            schema.setdefault("description", cls.__doc__.strip())
        return schema

    if is_dataclass(cls):
        return dataclass_to_json_schema(cls, title=title)

    raise TypeError(f"{cls} is neither a dataclass nor a Pydantic BaseModel")


__all__ = [
    "dataclass_to_json_schema",
    "generate_all_schemas",
    "model_to_json_schema",
    "save_schemas",
    "validate_against_schema",
]
