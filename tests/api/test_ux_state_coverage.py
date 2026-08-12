# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""UX state-coverage gate (IERD-Q5 Phase-4 EXIT — fail-closed, ANCHORED).

IERD-PAI-FPS-UX-001 §5 requires every public endpoint to expose the six
UX states the frontend must distinguish and render:

    success  empty  partial  validation_error  server_error  timeout

## Phase-4 EXIT contract (this revision)

The Phase-4 ENTRY revision used a deliberately crude proxy: "a state is
declared iff a mapped HTTP status code appears in ``responses:``". That
proxy was honest about being a scaffold. Driving the app to literally
emit ``204``/``206`` purely to move a number would have *gamed the
proxy* (RFC 7233 ``206`` is for byte-range single representations, not
paginated collections; ``404`` vs ``204`` for an empty collection is a
genuine design choice, not a free parameter). First-principles
engineering rejects metric-gaming. EXIT therefore replaces the proxy
with the **semantically correct contract**: each state is scored
against its *genuine, falsifiable discriminator* in this API, and only
against the endpoints for which the state is *semantically applicable*.

State → genuine discriminator (asserted concretely, never by proxy):

* ``success``          — HTTP ``200`` declared.
* ``validation_error`` — HTTP ``400`` **and** ``422`` declared.
* ``server_error``     — HTTP ``500`` declared.
* ``timeout``          — HTTP ``504`` declared **and** emitted by
  ``RequestTimeoutMiddleware`` (proven by the behavioural tests in
  this module — a declared-but-unemitted code would be the very
  theatre this contract forbids).
* ``empty``            — collection endpoints: HTTP ``404`` declared
  **and** the ``ApiErrorCode`` component enumerates the dedicated
  filter-mismatch code, so the frontend renders "no results" as a
  first-class state distinct from a generic not-found.
* ``partial``          — collection endpoints: the ``200`` body model
  exposes ``pagination.next_cursor`` so the frontend can detect and
  render a truncated page.

Endpoint applicability classes (auditable constants, not hidden):

* ``collection`` (features/predictions × {legacy,/v1,/api/v1}) — all
  six states applicable.
* ``command`` (/admin/kill-switch) — success / validation_error /
  server_error / timeout; ``empty`` and ``partial`` are N/A (a
  command is not a collection — it has no cardinality).
* ``probe`` (/health, /metrics) — ``success`` only. An unauthenticated
  read-only liveness/scrape endpoint takes no body (no
  validation_error), is deadline-exempt by design (no timeout
  envelope — an unhealthy probe answers ``200`` with a degraded body
  or fails at the connection layer), and has no cardinality
  (no empty/partial). Penalising a probe for states that cannot exist
  for it would itself be dishonest measurement.

    UXRS = covered applicable cells / total applicable cells   (≥ 0.95)

``/graphql`` is excluded by design, identical to the Q4 schemathesis
gate: GraphQL carries its own typed Strawberry schema.

Phase-4 EXIT: the workflow runs this suite **fail-closed** (no
``continue-on-error``); the claim ``ux-readiness-state-coverage`` is
re-classified ANCHORED with ``INV-API-CONTRACT`` as the cited
invariant. Tracks GitHub issue IERD-Q5 (#530).
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from application.api.errors import ApiErrorCode
from application.api.middleware import RequestTimeoutMiddleware

# Frozen, versioned OpenAPI 3.1 spec — the same artifact the Q4
# schemathesis gate fuzzes the live app against. Reading the persisted
# file (rather than building the app) keeps the contract portion of
# this gate deterministic and decoupled from runtime wiring; the
# behavioural portion (timeout) exercises the real middleware.
_SPEC_PATH: Final[Path] = (
    Path(__file__).resolve().parents[2] / "schemas" / "openapi" / "geosync-online-inference-v1.json"
)

# §5 readiness threshold (verbatim from IERD-PAI-FPS-UX-001 §5).
UXRS_THRESHOLD: Final[float] = 0.95

REQUIRED_STATES: Final[tuple[str, ...]] = (
    "success",
    "empty",
    "partial",
    "validation_error",
    "server_error",
    "timeout",
)

# Applicability matrix per endpoint class. Documented and auditable so
# the single judgement call (probe exemption) is reviewable, not
# buried. Order within each tuple is irrelevant.
_COLLECTION_STATES: Final[frozenset[str]] = frozenset(REQUIRED_STATES)
_COMMAND_STATES: Final[frozenset[str]] = frozenset(
    {"success", "validation_error", "server_error", "timeout"}
)
_PROBE_STATES: Final[frozenset[str]] = frozenset({"success"})

# Path → class. Exact-match paths only; the /graphql carve-out is
# handled before classification.
_COLLECTION_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/features",
        "/predictions",
        "/v1/features",
        "/v1/predictions",
        "/api/v1/features",
        "/api/v1/predictions",
    }
)
_COMMAND_PATHS: Final[frozenset[str]] = frozenset({"/admin/kill-switch"})
_PROBE_PATHS: Final[frozenset[str]] = frozenset({"/health", "/metrics"})

_EXCLUDE_PATH_RE: Final[re.Pattern[str]] = re.compile(r"^/graphql")
_HTTP_METHODS: Final[frozenset[str]] = frozenset(
    {"get", "post", "put", "delete", "patch", "options", "head"}
)

_ERROR_REF: Final[str] = "#/components/schemas/ErrorResponse"


def _load_spec() -> dict[str, Any]:
    with _SPEC_PATH.open(encoding="utf-8") as handle:
        spec: dict[str, Any] = json.load(handle)
    return spec


def _public_operations(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Return [(METHOD, path, operation)] for every gated public operation."""
    operations: list[tuple[str, str, dict[str, Any]]] = []
    for path, path_item in (spec.get("paths") or {}).items():
        if _EXCLUDE_PATH_RE.match(path):
            continue
        for method, operation in path_item.items():
            if method.lower() in _HTTP_METHODS:
                operations.append((method.upper(), path, operation))
    return operations


def _applicable_states(path: str) -> frozenset[str]:
    if path in _COLLECTION_PATHS:
        return _COLLECTION_STATES
    if path in _COMMAND_PATHS:
        return _COMMAND_STATES
    if path in _PROBE_PATHS:
        return _PROBE_STATES
    raise AssertionError(
        f"IERD-Q5 §5 gate: unclassified public path {path!r}. Every gated "
        f"endpoint must be assigned a class (collection/command/probe) so "
        f"its applicable UX-state set is explicit. Add it to the matrix "
        f"with a documented rationale rather than leaving it unscored."
    )


def _resolve_ref(spec: dict[str, Any], ref: str) -> dict[str, Any]:
    """Resolve a local ``#/components/schemas/X`` ref to its schema."""
    assert ref.startswith("#/"), f"non-local $ref unsupported: {ref}"
    node: Any = spec
    for part in ref[2:].split("/"):
        node = node[part]
    resolved: dict[str, Any] = node
    return resolved


def _codes(operation: dict[str, Any]) -> set[str]:
    return {str(code) for code in (operation.get("responses") or {})}


def _success_model_ref(operation: dict[str, Any]) -> str | None:
    body = (
        (operation.get("responses") or {})
        .get("200", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    ref = body.get("$ref")
    return ref if isinstance(ref, str) else None


def _state_covered(
    state: str,
    *,
    path: str,
    operation: dict[str, Any],
    spec: dict[str, Any],
) -> bool:
    """Genuine, falsifiable discriminator for ``state`` on this operation."""
    codes = _codes(operation)
    if state == "success":
        return "200" in codes
    if state == "validation_error":
        return "400" in codes and "422" in codes
    if state == "server_error":
        return "500" in codes
    if state == "timeout":
        return "504" in codes
    if state == "empty":
        # Collection-only: a dedicated filter-mismatch code must exist in
        # the ApiErrorCode enum AND a 404 must be declared, so "no
        # results" is a first-class renderable state.
        if "404" not in codes:
            return False
        enum = _resolve_ref(spec, "#/components/schemas/ApiErrorCode").get("enum", [])
        family = "FEATURES" if "features" in path else "PREDICTIONS"
        return f"ERR_{family}_FILTER_MISMATCH" in set(enum)
    if state == "partial":
        # Collection-only: the success body must expose
        # pagination.next_cursor so a truncated page is detectable.
        ref = _success_model_ref(operation)
        if ref is None:
            return False
        model = _resolve_ref(spec, ref)
        pagination = (model.get("properties") or {}).get("pagination")
        if not isinstance(pagination, dict):
            return False
        pag_ref = pagination.get("$ref")
        if not isinstance(pag_ref, str):
            return False
        pag_model = _resolve_ref(spec, pag_ref)
        return "next_cursor" in (pag_model.get("properties") or {})
    raise AssertionError(f"unknown state {state!r}")


def test_spec_present_and_has_public_operations() -> None:
    """The frozen spec exists and exposes at least one gated operation."""
    assert _SPEC_PATH.is_file(), (
        f"IERD-Q5 §5 gate cannot run: OpenAPI spec missing at {_SPEC_PATH}. "
        f"Regenerate via `python scripts/generate_openapi.py` before scoring."
    )
    operations = _public_operations(_load_spec())
    assert operations, (
        "IERD-Q5 §5 gate found zero public operations after the /graphql "
        "carve-out — UXRS is undefined with a zero denominator."
    )


def test_uxrs_meets_threshold() -> None:
    """Aggregate UXRS over the genuine applicable state matrix is ≥ §5."""
    spec = _load_spec()
    operations = _public_operations(spec)
    covered_total = 0
    applicable_total = 0
    for method, path, operation in operations:
        applicable = _applicable_states(path)
        applicable_total += len(applicable)
        covered = {
            state
            for state in applicable
            if _state_covered(state, path=path, operation=operation, spec=spec)
        }
        covered_total += len(covered)
        missing = sorted(applicable - covered)
        print(  # surfaced via pytest -s / Step Summary
            f"\n[uxrs] {method:6s} {path:24s} "
            f"covered={len(covered)}/{len(applicable)} "
            f"missing={','.join(missing) if missing else '-'}"
        )

    uxrs = covered_total / applicable_total if applicable_total else 0.0
    print(
        f"\n[uxrs] AGGREGATE covered={covered_total}/{applicable_total} "
        f"UXRS={uxrs:.4f} threshold={UXRS_THRESHOLD:.2f} "
        f"endpoints={len(operations)}"
    )

    assert uxrs >= UXRS_THRESHOLD, (
        f"IERD-Q5 §5 UXRS violated: observed UXRS={uxrs:.4f} below "
        f"threshold {UXRS_THRESHOLD:.2f} (covered {covered_total} of "
        f"{applicable_total} genuine applicable state cells across "
        f"{len(operations)} public operations). Each state is scored by "
        f"its real discriminator (status code / ApiErrorCode enum / "
        f"pagination.next_cursor / live 504 middleware), never a proxy. "
        f"A drop means a genuine state regressed — restore the "
        f"discriminator, do not relax the contract."
    )


def test_error_envelope_on_all_4xx_5xx() -> None:
    """Every declared 4xx/5xx response body $refs the canonical envelope."""
    spec = _load_spec()
    offenders: list[str] = []
    for method, path, operation in _public_operations(spec):
        for code, response in (operation.get("responses") or {}).items():
            if not re.fullmatch(r"[45]\d\d", str(code)):
                continue
            schema = (response.get("content") or {}).get("application/json", {}).get("schema", {})
            if schema.get("$ref") != _ERROR_REF:
                offenders.append(
                    f"{method} {path} [{code}] -> {schema or 'no application/json body'}"
                )
    assert not offenders, (
        f"IERD-Q5 §5 error-envelope contract violated: {len(offenders)} "
        f"declared 4xx/5xx response(s) do not $ref {_ERROR_REF}. Every "
        f"failure state (now including 504 timeout) must render through "
        f"one envelope. Offenders: " + "; ".join(sorted(offenders))
    )


def _timeout_probe_app(*, timeout_seconds: float) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=timeout_seconds)

    @app.get("/slow")
    async def _slow() -> dict[str, str]:  # pragma: no cover - body never returns
        await asyncio.sleep(5.0)
        return {"unreachable": "true"}

    @app.get("/fast")
    async def _fast() -> dict[str, str]:
        return {"ok": "true"}

    return app


def test_request_timeout_middleware_emits_504_envelope() -> None:
    """A deadline breach yields 504 in the canonical ErrorResponse shape.

    This is the behavioural proof that ``timeout`` is *emitted*, not
    merely declared — without it the 504 declaration would be exactly
    the documentation theatre the EXIT contract forbids.
    """
    client = TestClient(_timeout_probe_app(timeout_seconds=0.05))
    resp = client.get("/slow")
    assert resp.status_code == 504, (
        f"INV-API-CONTRACT: RequestTimeoutMiddleware must emit 504 on a "
        f"deadline breach; got {resp.status_code}. Timeout would otherwise "
        f"keep masquerading as a 500, collapsing two distinct UX states."
    )
    body = resp.json()
    assert set(body) >= {"error"}, f"missing envelope key 'error': {body}"
    error = body["error"]
    assert error["code"] == ApiErrorCode.GATEWAY_TIMEOUT.value, error
    assert error["path"] == "/slow", error
    assert isinstance(error["message"], str) and error["message"], error
    assert error["meta"]["timeout_seconds"] == pytest.approx(0.05), error


def test_request_timeout_middleware_passthrough_fast_route() -> None:
    """A request inside the deadline is untouched (no false positives)."""
    client = TestClient(_timeout_probe_app(timeout_seconds=5.0))
    resp = client.get("/fast")
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"ok": "true"}


def test_request_timeout_middleware_rejects_nonpositive_deadline() -> None:
    """Construction fails closed on a non-positive deadline (INV-API-CONTRACT)."""
    app = FastAPI()
    with pytest.raises(ValueError, match="must be > 0"):
        app.add_middleware(RequestTimeoutMiddleware, timeout_seconds=0.0)
        # add_middleware is lazy; force the build that runs __init__.
        TestClient(app).get("/")
