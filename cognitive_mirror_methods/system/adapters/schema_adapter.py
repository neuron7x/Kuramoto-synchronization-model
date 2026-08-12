from __future__ import annotations

from typing import Any

REQUEST_KEYS = {
    "request_id",
    "module",
    "operation",
    "input",
    "context",
    "constraints",
    "output_format",
    "language",
}
RESPONSE_KEYS = {
    "request_id",
    "module",
    "status",
    "output",
    "artifacts",
    "errors",
    "warnings",
    "validation",
    "next_action",
}


def validate_request_shape(request: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = sorted(REQUEST_KEYS - set(request))
    unknown = sorted(set(request) - REQUEST_KEYS - {"safety_mode"})
    errors = [f"missing:{key}" for key in missing] + [f"unknown:{key}" for key in unknown]
    return not errors, errors


def validate_response_shape(response: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = sorted(RESPONSE_KEYS - set(response))
    unknown = sorted(set(response) - RESPONSE_KEYS)
    errors = [f"missing:{key}" for key in missing] + [f"unknown:{key}" for key in unknown]
    return not errors, errors
