from __future__ import annotations

from typing import Any

from cognitive_mirror_methods.system.orchestration.registry import module_exists

STATUS_BLOCKED = "BLOCKED"
STATUS_PASS = "PASS"


def _response(
    request: dict[str, Any],
    status: str,
    output: dict[str, Any],
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "request_id": str(request.get("request_id", "")),
        "module": str(request.get("module", "")),
        "status": status,
        "output": output,
        "artifacts": [],
        "errors": errors or [],
        "warnings": [],
        "validation": {
            "schema_valid": bool(request.get("request_id") and request.get("module")),
            "contract_valid": status == STATUS_PASS,
            "tests_passed": [],
        },
        "next_action": "inspect output" if status == STATUS_PASS else "repair request",
    }


def blocked_response(request: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """Canonical BLOCKED response — fail closed, never raise, never leak shape."""
    return _response(request, STATUS_BLOCKED, {}, errors)


def route_request(request: dict[str, Any]) -> dict[str, Any]:
    module_id = str(request.get("module", ""))
    if not module_exists(module_id):
        return blocked_response(request, ["unknown module"])
    # Fail closed on malformed input: a non-object `input` (string/list/null) or a
    # non-string `input.text` becomes a canonical BLOCKED, never a runtime exception.
    raw_input = request.get("input", {})
    if not isinstance(raw_input, dict):
        return blocked_response(request, ["invalid input: expected object"])
    text = raw_input.get("text", "")
    if not isinstance(text, str):
        return blocked_response(request, ["invalid input.text: expected string"])
    return _response(
        request,
        STATUS_PASS,
        {"text": " ".join(text.split()), "module": module_id},
    )
