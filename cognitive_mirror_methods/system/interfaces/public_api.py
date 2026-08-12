from __future__ import annotations

from typing import Any

from cognitive_mirror_methods.system.adapters.schema_adapter import validate_request_shape
from cognitive_mirror_methods.system.orchestration.router import blocked_response, route_request


def execute(request: dict[str, Any]) -> dict[str, Any]:
    """Run one module through the public system boundary.

    The declared request contract is ENFORCED here, not merely documented: a
    non-object request or one that fails the schema shape returns a canonical
    BLOCKED response instead of leaking an exception downstream. The validator
    sits on the hot path, not in a neighbouring room.
    """
    if not isinstance(request, dict):
        return blocked_response({}, ["invalid request: expected object"])
    ok, errors = validate_request_shape(request)
    if not ok:
        return blocked_response(request, errors)
    return route_request(request)
