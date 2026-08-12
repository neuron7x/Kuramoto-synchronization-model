# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Schemathesis contract gate for the GeoSync HTTP API.

IERD-PAI-FPS-UX-001 §5 (Phase-3 entry gate) — every public operation declared
in the OpenAPI 3.1 specification is exercised against a property-based suite
that enforces:

    * response status code is one of the declared codes for the operation;
    * response body matches the declared schema for that status code;
    * response Content-Type is consistent with the declared media types.

The test runs Schemathesis against the in-process ASGI application produced
by `application.api.service.create_app()`, so it is hermetic — no live
server, no transient ports. It is bounded by an explicit hypothesis budget
to keep CI wall-clock predictable.

Failure of this test is a contract violation between the runtime app and
the persisted `schemas/openapi/geosync-online-inference-v1.json` spec. The
remediation is always one of: (a) fix the implementation, (b) update the
spec snapshot, (c) declare the missing response code in the spec.

Tracks claim `api-contract-openapi-coverage` in `docs/CLAIMS.yaml`.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from schemathesis import Case

# Auth / settings env are required by `create_app()`; mirror the values used by
# `tests/api/test_openapi_contract.py` so the two contract tests stay aligned.
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "schemathesis-contract-secret")
os.environ.setdefault("GEOSYNC_OAUTH2_ISSUER", "https://schemathesis.test")
os.environ.setdefault("GEOSYNC_OAUTH2_AUDIENCE", "geosync-api")
os.environ.setdefault("GEOSYNC_OAUTH2_JWKS_URI", "https://schemathesis.test/jwks")
os.environ.setdefault("GEOSYNC_RBAC_AUDIT_SECRET", "schemathesis-rbac-secret")

schemathesis = pytest.importorskip(
    "schemathesis",
    reason="Schemathesis is an optional contract-test dep; install with `pip install schemathesis>=4`.",
)

from hypothesis import HealthCheck, settings  # noqa: E402

from application.api.service import create_app  # noqa: E402

# Load OpenAPI-specific checks into the registry; otherwise only
# `not_a_server_error` is available for filtering.
schemathesis.checks.load_all_checks()
_CHECK_REGISTRY = schemathesis.checks.CHECKS

# Phase-3 entry gate (this PR): contract-level conformance only.
# Exercises every (path, method) pair against the declared schema and asserts:
#   * no 5xx;
#   * status code is declared;
#   * response body matches declared content-type schema;
#   * declared headers are present;
#   * negative (schema-violating) inputs are rejected.
# Out of scope until Phase-3 exit: `positive_data_acceptance` (deeper auth /
# rate-limit / business-rule hardening) and stateful link traversal.
_ACTIVE_CHECK_NAMES = (
    "not_a_server_error",
    "status_code_conformance",
    "content_type_conformance",
    "response_headers_conformance",
    "response_schema_conformance",
    "negative_data_rejection",
)
_ACTIVE_CHECKS = tuple(_CHECK_REGISTRY.get_by_names(list(_ACTIVE_CHECK_NAMES)))

# Hypothesis budget — bounded so CI wall-clock is predictable while still
# covering each operation with multiple generated cases.
HYPOTHESIS_MAX_EXAMPLES = int(os.environ.get("GEOSYNC_SCHEMATHESIS_EXAMPLES", "8"))
HYPOTHESIS_DEADLINE_MS = int(os.environ.get("GEOSYNC_SCHEMATHESIS_DEADLINE_MS", "5000"))

_app = create_app()

# Detach lifespan handlers so each generated case runs in its own asyncio
# loop without the metrics sampler tripping a "bound to a different event
# loop" RuntimeError on shutdown. The contract test exercises HTTP surface
# only — background telemetry tasks are out of scope.
_app.router.on_startup.clear()
_app.router.on_shutdown.clear()

_schema = schemathesis.openapi.from_asgi("/openapi.json", app=_app).exclude(
    # GraphQL has its own typed schema (Strawberry); the FastAPI OpenAPI
    # rendering of `/graphql` only declares the JSON transport, but the
    # GraphiQL IDE on GET serves text/html and validation failures emit
    # 400 responses outside the OpenAPI catalogue. GraphQL schema
    # conformance belongs in a dedicated GraphQL contract suite, not in
    # the OpenAPI Phase-3 EXIT gate.
    path_regex=r"^/graphql",
)


@_schema.parametrize()  # type: ignore[misc]
@settings(
    max_examples=HYPOTHESIS_MAX_EXAMPLES,
    deadline=HYPOTHESIS_DEADLINE_MS,
    derandomize=True,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
        HealthCheck.filter_too_much,
    ],
)
def test_api_operation_conforms_to_schema(case: Case) -> None:
    """Every (path, method) declared in OpenAPI satisfies the response contract.

    `call_and_validate` runs the generated request against the in-process app
    and asserts that the response status, body, and headers conform to the
    declared schema for that operation. Status codes 401/403/429 produced by
    auth/rate-limit middleware are declared in the spec, so they pass.
    """
    case.call_and_validate(checks=list(_ACTIVE_CHECKS))
