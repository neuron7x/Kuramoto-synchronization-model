from __future__ import annotations

from typing import Any

from cognitive_mirror_methods.system.adapters.schema_adapter import validate_response_shape
from cognitive_mirror_methods.system.orchestration.registry import ordered_modules
from cognitive_mirror_methods.system.orchestration.router import route_request

HALT_STATES = {"BLOCKED", "FAILED"}


def _pipeline_response(
    request: dict[str, Any],
    status: str,
    results: list[dict[str, Any]],
    errors: list[str],
    validation: dict[str, Any],
    next_action: str,
) -> dict[str, Any]:
    return {
        "request_id": str(request.get("request_id", "")),
        "module": "pipeline",
        "status": status,
        "output": {"results": results},
        "artifacts": [],
        "errors": errors,
        "warnings": [],
        "validation": validation,
        "next_action": next_action,
    }


def _initial_text(request: dict[str, Any]) -> str:
    raw_input = request.get("input", {})
    if not isinstance(raw_input, dict):
        return ""
    text = raw_input.get("text", "")
    return text if isinstance(text, str) else ""


def run_pipeline(request: dict[str, Any]) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    text = _initial_text(request)
    for module_id in ordered_modules():
        step_request = dict(request)
        step_request["module"] = module_id
        step_request["input"] = {"text": text}
        result = route_request(step_request)
        # Fail closed on a malformed module response: validate the shape BEFORE
        # reading any key, so a future non-canonical module returns a structured
        # BLOCKED instead of leaking a KeyError up the pipeline.
        shape_ok, shape_errors = validate_response_shape(result)
        if not shape_ok:
            return _pipeline_response(
                request,
                "BLOCKED",
                results,
                [f"malformed module response from {module_id}", *shape_errors],
                {"schema_valid": False, "contract_valid": False, "tests_passed": []},
                "repair module response",
            )
        results.append(result)
        if result.get("status") in HALT_STATES:
            return _pipeline_response(
                request,
                str(result.get("status")),
                results,
                list(result.get("errors", [])),
                dict(result.get("validation", {})),
                "repair pipeline input",
            )
        output = result.get("output", {})
        if isinstance(output, dict) and isinstance(output.get("text"), str):
            text = output["text"]
    return _pipeline_response(
        request,
        "PASS",
        results,
        [],
        {"schema_valid": True, "contract_valid": True, "tests_passed": []},
        "create artifact",
    )
