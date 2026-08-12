#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Pure component-test planning primitives.

This module owns deterministic changed-file -> component-test routing.
It intentionally performs no subprocess execution and no CLI I/O.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
from pathlib import Path
from typing import Any, Literal, Mapping, NotRequired, TypedDict, cast

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "data" / "testing" / "component_test_matrix.json"
SCHEMA = "geosync.component_test_matrix.v1"
BLOCKING_STATUSES = {"invalid_matrix", "unmapped_required_surface"}
DEFAULT_PYTHON_ENV = "COMPONENT_ROUTER_PYTHON"

PlanStatus = Literal["invalid_matrix", "unmapped_required_surface", "ready", "empty"]
TransitionEvent = Literal[
    "matrix_validation_failed",
    "matrix_validated",
    "paths_normalized",
    "components_matched",
    "required_surface_checked",
    "plan_blocked",
    "selectors_prioritized",
    "plan_finalized",
]

TRANSITION_EVENTS: tuple[TransitionEvent, ...] = (
    "matrix_validation_failed",
    "matrix_validated",
    "paths_normalized",
    "components_matched",
    "required_surface_checked",
    "plan_blocked",
    "selectors_prioritized",
    "plan_finalized",
)


class Transition(TypedDict, total=False):
    seq: int
    event: TransitionEvent
    status: str
    error_count: int
    input_count: int
    normalized_count: int
    changed_files: list[str]
    component_ids: list[str]
    selector_count: int
    missing_route_count: int
    missing_routes: list[str]
    cause: str
    selectors: list[str]


class MatchedComponent(TypedDict):
    id: str
    matched_paths: list[str]
    selectors: list[str]
    expected_outcome: str
    isolation_level: str
    max_runtime_seconds: int


class RouterPolicy(TypedDict):
    default_max_run_selectors: int
    priority_component_ids: list[str]
    python_executable_env: str


class Plan(TypedDict):
    status: PlanStatus
    changed_files: list[str]
    components: list[MatchedComponent]
    selectors: list[str]
    pytest_command: list[str]
    transitions: list[Transition]
    errors: NotRequired[list[str]]
    unmapped_required: NotRequired[list[str]]


def load_matrix(path: Path = MATRIX) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def selector_path(selector: str) -> str:
    return selector.split("::", 1)[0]


def string_list(value: object, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or not value:
        errors.append(f"{label} must be a non-empty list")
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label} must contain non-empty strings")
            continue
        out.append(item)
    return out


def transition(transitions: list[Transition], event: TransitionEvent, **state: object) -> None:
    entry: dict[str, object] = {"seq": len(transitions) + 1, "event": event}
    entry.update(state)
    transitions.append(cast(Transition, entry))


def validate_router_policy(matrix: dict[str, Any], path: Path, errors: list[str]) -> RouterPolicy:
    policy = matrix.get("router_policy")
    default_policy: RouterPolicy = {
        "default_max_run_selectors": 1,
        "priority_component_ids": [],
        "python_executable_env": DEFAULT_PYTHON_ENV,
    }
    if not isinstance(policy, dict):
        errors.append(f"{path}: router_policy must be an object")
        return default_policy

    max_run = policy.get("default_max_run_selectors")
    if not isinstance(max_run, int) or not (1 <= max_run <= 64):
        errors.append(
            f"{path}: router_policy.default_max_run_selectors must be " "an int in [1, 64]"
        )
    else:
        default_policy["default_max_run_selectors"] = max_run

    priorities = string_list(
        policy.get("priority_component_ids"),
        f"{path}: router_policy.priority_component_ids",
        errors,
    )
    if priorities:
        default_policy["priority_component_ids"] = priorities

    env_name = policy.get("python_executable_env", DEFAULT_PYTHON_ENV)
    if not isinstance(env_name, str) or not env_name.strip():
        errors.append(f"{path}: router_policy.python_executable_env must be " "a non-empty string")
    else:
        default_policy["python_executable_env"] = env_name

    return default_policy


def router_policy(matrix_path: Path = MATRIX) -> RouterPolicy:
    matrix = load_matrix(matrix_path)
    errors: list[str] = []
    return validate_router_policy(matrix, matrix_path, errors)


def validate_matrix(path: Path = MATRIX, repo_root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        matrix = load_matrix(path)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path}: cannot load component test matrix: {exc}"]

    if matrix.get("schema") != SCHEMA:
        errors.append(f"{path}: schema must be {SCHEMA}")
    if matrix.get("status") != "normative":
        errors.append(f"{path}: status must be normative")

    rule = matrix.get("decision_rule")
    if not isinstance(rule, dict):
        errors.append(f"{path}: decision_rule must be an object")
    else:
        if rule.get("controlled_input") != "changed repository path":
            errors.append(f"{path}: decision_rule.controlled_input is invalid")
        if rule.get("expected_output") != "deterministic pytest selector plan":
            errors.append(f"{path}: decision_rule.expected_output is invalid")
        if rule.get("fail_closed_on_invalid_matrix") is not True:
            errors.append(f"{path}: fail_closed_on_invalid_matrix must be true")
        if rule.get("fail_closed_on_unmapped_required_surface") is not True:
            errors.append(f"{path}: fail_closed_on_unmapped_required_surface must be true")

    policy = validate_router_policy(matrix, path, errors)
    required_patterns = string_list(
        matrix.get("required_mapping_patterns"),
        f"{path}: required_mapping_patterns",
        errors,
    )
    for pattern in required_patterns:
        if pattern.startswith("docs/"):
            errors.append(f"{path}: docs/* cannot be a required mapping pattern")

    components = matrix.get("components")
    if not isinstance(components, list) or not components:
        return errors + [f"{path}: components must be a non-empty list"]

    seen_ids: set[str] = set()
    for index, component in enumerate(components, start=1):
        prefix = f"{path}: components[{index}]"
        if not isinstance(component, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        component_id = component.get("id")
        if not isinstance(component_id, str) or not component_id.strip():
            errors.append(f"{prefix}: id must be a non-empty string")
        elif component_id in seen_ids:
            errors.append(f"{prefix}: duplicate id {component_id}")
        else:
            seen_ids.add(component_id)

        selectors = string_list(component.get("selectors"), f"{prefix}: selectors", errors)
        string_list(component.get("patterns"), f"{prefix}: patterns", errors)
        for selector in selectors:
            selector_file = repo_root / selector_path(selector)
            if not selector_file.exists():
                errors.append(f"{prefix}: selector path does not exist: {selector}")
        if component.get("expected_outcome") != "pass":
            errors.append(f"{prefix}: expected_outcome must be pass")
        if component.get("isolation_level") != "component":
            errors.append(f"{prefix}: isolation_level must be component")
        max_runtime = component.get("max_runtime_seconds")
        if not isinstance(max_runtime, int) or not (1 <= max_runtime <= 600):
            errors.append(f"{prefix}: max_runtime_seconds must be an int in [1, 600]")

    missing_priority_ids = [
        component_id
        for component_id in policy["priority_component_ids"]
        if component_id not in seen_ids
    ]
    for component_id in missing_priority_ids:
        errors.append(f"{path}: router_policy priority id has no component: {component_id}")

    return errors


def matches(path: str, pattern: str) -> bool:
    return fnmatch.fnmatchcase(path, pattern)


def path_matches_any(path: str, patterns: list[str]) -> bool:
    return any(matches(path, pattern) for pattern in patterns)


def is_required_mapping(path: str, matrix: dict[str, Any]) -> bool:
    patterns = matrix.get("required_mapping_patterns", [])
    return isinstance(patterns, list) and path_matches_any(path, patterns)


def normalize_path(path: str) -> str:
    normalized = path.strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def execution_python(
    repo_root: Path,
    matrix_path: Path = MATRIX,
    python_executable: str | None = None,
    env: Mapping[str, str] | None = None,
) -> str:
    if python_executable:
        return python_executable
    policy = router_policy(matrix_path)
    environment = os.environ if env is None else env
    from_env = environment.get(policy["python_executable_env"])
    if from_env:
        return from_env
    venv_python = repo_root / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def prioritize_selectors(
    selectors: list[str],
    matched_components: list[MatchedComponent],
    policy: RouterPolicy,
) -> list[str]:
    priority: list[str] = []
    seen: set[str] = set()
    for component_id in policy["priority_component_ids"]:
        for component in matched_components:
            if component["id"] != component_id:
                continue
            for selector in component["selectors"]:
                if selector not in seen:
                    priority.append(selector)
                    seen.add(selector)
    priority.extend(selector for selector in selectors if selector not in seen)
    return priority


def plan_status(plan: Plan) -> PlanStatus:
    return plan["status"]


def plan_selectors(plan: Plan) -> list[str]:
    return plan["selectors"]


def plan_pytest_command(plan: Plan) -> list[str]:
    return plan["pytest_command"]


def invalid_plan(errors: list[str], transitions: list[Transition]) -> Plan:
    transition(
        transitions,
        "matrix_validation_failed",
        status="invalid_matrix",
        error_count=len(errors),
    )
    return {
        "status": "invalid_matrix",
        "changed_files": [],
        "components": [],
        "selectors": [],
        "pytest_command": [],
        "transitions": transitions,
        "errors": errors,
    }


def blocked_plan(
    normalized: list[str],
    matched_components: list[MatchedComponent],
    selectors: list[str],
    missing_routes: list[str],
    transitions: list[Transition],
) -> Plan:
    transition(
        transitions,
        "plan_blocked",
        status="unmapped_required_surface",
        cause="missing required component-test route",
    )
    return {
        "status": "unmapped_required_surface",
        "changed_files": normalized,
        "components": matched_components,
        "selectors": selectors,
        "unmapped_required": missing_routes,
        "errors": [
            "required mapping surface has no component-test route: " + path
            for path in missing_routes
        ],
        "pytest_command": [],
        "transitions": transitions,
    }


def select_plan(
    changed_files: list[str],
    matrix_path: Path = MATRIX,
    repo_root: Path = ROOT,
    python_executable: str | None = None,
    env: Mapping[str, str] | None = None,
) -> Plan:
    transitions: list[Transition] = []
    errors = validate_matrix(matrix_path, repo_root)
    if errors:
        return invalid_plan(errors, transitions)

    transition(transitions, "matrix_validated", status="ok")
    matrix = load_matrix(matrix_path)
    policy = router_policy(matrix_path)
    matched_components: list[MatchedComponent] = []
    selectors: list[str] = []
    seen_selectors: set[str] = set()
    mapped_paths: set[str] = set()

    normalized = [normalize_path(path) for path in changed_files if path.strip()]
    transition(
        transitions,
        "paths_normalized",
        input_count=len(changed_files),
        normalized_count=len(normalized),
        changed_files=normalized,
    )
    for component in matrix["components"]:
        matched_paths = [
            path
            for path in normalized
            if any(matches(path, pattern) for pattern in component["patterns"])
        ]
        if not matched_paths:
            continue
        mapped_paths.update(matched_paths)
        matched_component: MatchedComponent = {
            "id": component["id"],
            "matched_paths": matched_paths,
            "selectors": component["selectors"],
            "expected_outcome": component["expected_outcome"],
            "isolation_level": component["isolation_level"],
            "max_runtime_seconds": component["max_runtime_seconds"],
        }
        matched_components.append(matched_component)
        for selector in matched_component["selectors"]:
            if selector not in seen_selectors:
                seen_selectors.add(selector)
                selectors.append(selector)

    transition(
        transitions,
        "components_matched",
        component_ids=[component["id"] for component in matched_components],
        selector_count=len(selectors),
    )
    missing_routes = [
        path
        for path in normalized
        if path not in mapped_paths and is_required_mapping(path, matrix)
    ]
    transition(
        transitions,
        "required_surface_checked",
        missing_route_count=len(missing_routes),
        missing_routes=missing_routes,
    )
    if missing_routes:
        return blocked_plan(
            normalized,
            matched_components,
            selectors,
            missing_routes,
            transitions,
        )

    selectors = prioritize_selectors(selectors, matched_components, policy)
    status: PlanStatus = "ready" if selectors else "empty"
    transition(
        transitions,
        "selectors_prioritized",
        selector_count=len(selectors),
        selectors=selectors,
    )
    transition(transitions, "plan_finalized", status=status)
    return {
        "status": status,
        "changed_files": normalized,
        "components": matched_components,
        "selectors": selectors,
        "pytest_command": (
            [
                execution_python(repo_root, matrix_path, python_executable, env),
                "-m",
                "pytest",
                *selectors,
            ]
            if selectors
            else []
        ),
        "transitions": transitions,
    }


def max_run_selectors(value: str | None, matrix_path: Path = MATRIX) -> int:
    fallback = router_policy(matrix_path)["default_max_run_selectors"]
    if not value:
        return fallback
    try:
        parsed = int(value)
    except ValueError:
        return fallback
    return parsed if parsed > 0 else fallback
