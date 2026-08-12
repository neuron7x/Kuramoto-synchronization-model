# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Self-contained CNS ontology guard (witness-first control contract)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ALLOWED_AXES = {"Intent", "Time", "Energy", "Error", "Control"}
ALLOWED_ROLES = {"witness_state", "actor_state", "coherence_state", "risk_state"}
FLOW_MODES = {"stream"}
OWNER_MODULE_PATTERN = re.compile(r"^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)*$")
CONTRADICTION_EVENT_PATTERN = re.compile(r"^HiddenContradiction\.[A-Za-z][A-Za-z0-9]*$")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA_PATH = REPO_ROOT / "schemas" / "cns" / "control_ontology.schema.json"
DEFAULT_ONTOLOGY_PATH = REPO_ROOT / "configs" / "cns" / "control_ontology.v1.json"
DEFAULT_STREAM_REGISTRY_PATH = REPO_ROOT / "configs" / "cns" / "stream_registry.v1.json"


def _load_json(path: Path, label: str) -> tuple[Any | None, list[str]]:
    if not path.exists():
        return None, [f"{label} missing: {path}"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return None, [f"{label} JSON decode error: {exc}"]


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_flow(idx: int, flow: Any, registry_streams: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(flow, dict):
        return [f"variables[{idx}].flow must be an object"]

    required = {"mode", "source_stream", "cadence_ms", "max_staleness_ms", "lag_tolerance_ms"}
    missing = sorted(required.difference(flow))
    if missing:
        errors.append(f"variables[{idx}].flow missing required keys: {missing}")

    mode = flow.get("mode")
    if mode not in FLOW_MODES:
        errors.append(
            f"variables[{idx}].flow.mode must be one of {tuple(FLOW_MODES)}; got {mode!r}"
        )

    source_stream = flow.get("source_stream")
    if not _is_non_empty_string(source_stream):
        errors.append(f"variables[{idx}].flow.source_stream must be a non-empty string")
    elif registry_streams and source_stream not in registry_streams:
        errors.append(f"variables[{idx}].flow.source_stream is not registered: {source_stream!r}")

    cadence_ms = flow.get("cadence_ms")
    max_staleness_ms = flow.get("max_staleness_ms")
    lag_tolerance_ms = flow.get("lag_tolerance_ms")

    if not isinstance(cadence_ms, int) or cadence_ms < 1:
        errors.append(f"variables[{idx}].flow.cadence_ms must be an integer >= 1")
    if not isinstance(max_staleness_ms, int) or max_staleness_ms < 1:
        errors.append(f"variables[{idx}].flow.max_staleness_ms must be an integer >= 1")
    if not isinstance(lag_tolerance_ms, int) or lag_tolerance_ms < 0:
        errors.append(f"variables[{idx}].flow.lag_tolerance_ms must be an integer >= 0")

    if (
        isinstance(cadence_ms, int)
        and isinstance(max_staleness_ms, int)
        and max_staleness_ms < cadence_ms
    ):
        errors.append(f"variables[{idx}].flow.max_staleness_ms must be >= cadence_ms")

    if _is_non_empty_string(source_stream) and source_stream in registry_streams:
        meta = registry_streams[source_stream]
        if not isinstance(meta, dict):
            errors.append(f"Stream registry entry must be an object: {source_stream!r}")
        else:
            reg_cadence = meta.get("cadence_ms")
            reg_staleness = meta.get("max_staleness_ms")
            if (
                isinstance(cadence_ms, int)
                and isinstance(reg_cadence, int)
                and cadence_ms < reg_cadence
            ):
                errors.append(
                    f"variables[{idx}].flow.cadence_ms ({cadence_ms}) cannot be faster than "
                    f"registry cadence ({reg_cadence}) for {source_stream!r}"
                )
            if (
                isinstance(max_staleness_ms, int)
                and isinstance(reg_staleness, int)
                and max_staleness_ms > reg_staleness
            ):
                errors.append(
                    f"variables[{idx}].flow.max_staleness_ms ({max_staleness_ms}) cannot exceed "
                    f"registry staleness ({reg_staleness}) for {source_stream!r}"
                )

    return errors


def validate_cns_ontology(
    schema_path: Path,
    ontology_path: Path,
    stream_registry_path: Path | None = DEFAULT_STREAM_REGISTRY_PATH,
) -> list[str]:
    schema, schema_errors = _load_json(schema_path, "Schema")
    ontology, ontology_errors = _load_json(ontology_path, "Ontology")
    errors = [*schema_errors, *ontology_errors]
    if schema is None or ontology is None:
        return errors

    registry: dict[str, Any] = {}
    if stream_registry_path is not None:
        loaded, registry_errors = _load_json(stream_registry_path, "Stream registry")
        errors.extend(registry_errors)
        if loaded is not None and isinstance(loaded, dict):
            registry = loaded

    registry_streams = registry.get("streams", {}) if isinstance(registry, dict) else {}
    if registry and not isinstance(registry_streams, dict):
        errors.append("Stream registry field 'streams' must be an object")
        registry_streams = {}

    for key in schema.get("required", []):
        if key not in ontology:
            errors.append(f"Missing required top-level field: {key}")

    axes = ontology.get("axes")
    if not isinstance(axes, list):
        errors.append("'axes' must be a list")
    elif set(axes) != ALLOWED_AXES:
        errors.append("'axes' must contain exactly {Intent, Time, Energy, Error, Control}")

    variables = ontology.get("variables")
    if not isinstance(variables, list) or not variables:
        errors.append("'variables' must be a non-empty list")
        return errors

    required_variable_keys = {
        "name",
        "role",
        "axis",
        "source",
        "units",
        "owner_module",
        "contradiction_event",
        "flow",
    }

    seen_names: set[str] = set()
    covered_axes: set[str] = set()
    covered_roles: set[str] = set()

    for idx, var in enumerate(variables):
        if not isinstance(var, dict):
            errors.append(f"variables[{idx}] must be an object")
            continue

        missing = sorted(required_variable_keys.difference(var))
        if missing:
            errors.append(f"variables[{idx}] missing required keys: {missing}")

        name = var.get("name")
        if not _is_non_empty_string(name):
            errors.append(f"variables[{idx}].name must be a non-empty string")
        elif name in seen_names:
            errors.append(f"Duplicate variable name: {name}")
        else:
            seen_names.add(name)

        role = var.get("role")
        if role not in ALLOWED_ROLES:
            errors.append(
                f"variables[{idx}].role must be one of {tuple(ALLOWED_ROLES)}; got {role!r}"
            )
        else:
            covered_roles.add(role)

        axis = var.get("axis")
        if axis not in ALLOWED_AXES:
            errors.append(
                f"variables[{idx}].axis must be one of {tuple(ALLOWED_AXES)}; got {axis!r}"
            )
        else:
            covered_axes.add(axis)

        for field in ("source", "units", "owner_module", "contradiction_event"):
            if not _is_non_empty_string(var.get(field)):
                errors.append(f"variables[{idx}].{field} must be a non-empty string")

        owner_module = var.get("owner_module")
        if _is_non_empty_string(owner_module):
            if OWNER_MODULE_PATTERN.fullmatch(owner_module) is None:
                errors.append(f"variables[{idx}].owner_module has invalid format: {owner_module!r}")
            top_level_module = owner_module.split(".", maxsplit=1)[0]
            if not (REPO_ROOT / top_level_module).exists():
                errors.append(
                    f"variables[{idx}].owner_module references missing module path: {owner_module!r}"
                )

        contradiction_event = var.get("contradiction_event")
        if (
            _is_non_empty_string(contradiction_event)
            and CONTRADICTION_EVENT_PATTERN.fullmatch(contradiction_event) is None
        ):
            errors.append(
                f"variables[{idx}].contradiction_event has invalid format: {contradiction_event!r}"
            )

        errors.extend(_validate_flow(idx, var.get("flow"), registry_streams))

    missing_axes = sorted(ALLOWED_AXES.difference(covered_axes))
    if missing_axes:
        errors.append(f"Ontology variables must cover all coherence axes; missing: {missing_axes}")

    missing_roles = sorted(ALLOWED_ROLES.difference(covered_roles))
    if missing_roles:
        errors.append(f"Ontology variables must cover all control roles; missing: {missing_roles}")

    return errors


def main() -> int:
    errors = validate_cns_ontology(
        DEFAULT_SCHEMA_PATH,
        DEFAULT_ONTOLOGY_PATH,
        DEFAULT_STREAM_REGISTRY_PATH,
    )
    if errors:
        print("CNS ontology guard failed:")
        for err in errors:
            print(f" - {err}")
        return 1

    print("CNS ontology guard passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
