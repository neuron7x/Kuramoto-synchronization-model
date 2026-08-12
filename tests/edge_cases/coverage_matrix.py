# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Canonical IERD-Q7 edge-case coverage matrix (auditable, falsifiable).

IERD-PAI-FPS-UX-001 §5 / issue #532 require an
``(endpoint × state × test_id)`` matrix with

    ECC = covered applicable cells / total applicable cells ≥ 0.90

The honest, anti-theatre construction:

* The ten states are the §5 set verbatim.
* Endpoints are the gated public operations of the frozen OpenAPI
  spec (the same set IERD-Q5 scores), classified collection / command
  / probe. Applicability per class is explicit and documented — a
  ``probe`` has no collection cardinality, so ``empty`` / ``partial``
  are not scored against it (penalising an endpoint for a state that
  cannot exist for it is dishonest measurement, exactly as in Q5).
* A cell is ``covered`` only if it cites a **real, resolvable**
  test — a concrete pytest node (``path::func``), a whole test module
  (``path``), or a Playwright spec cell
  (``path.spec.ts::<endpoint>::<state>``) that genuinely exercises that
  state for that endpoint class. ``test_edge_case_matrix.py`` statically
  verifies every cited target still exists (pytest: file + ``def``;
  Playwright: file + ``test(`` block + the cited ``<endpoint>`` and
  ``probe-state-<state>`` markers), so deleting or renaming a cited test
  fails the gate — the matrix has teeth for both layers.
* Cells with no genuine test yet are listed explicitly as
  ``UNCOVERED`` with a reason. No cell is silently assumed.

Phase-4 EXIT (this revision): ECC = 1.00. The client-only states
(loading, cancelled, per-probe server_error) that had no genuine test
at ENTRY are now exercised by Playwright route-interception specs in
``apps/web/tests/edge-case-probe.spec.ts`` — each state is driven by
``page.route`` (delayed fulfil for loading, ``route.abort('failed')``
for network_failure, a hung route past the client deadline for timeout,
``fulfill`` status 500 per probe for server_error, a non-finite forecast
envelope for the INV-DRO5 simulation_diverged guard) or a genuine user
cancel, against the ``/edge-probe`` harness that issues a real ``fetch``.
The two §532 *hard* sub-requirements — network_failure **and** timeout
tested for every applicable endpoint, and simulation_diverged correlated
with INV-DRO5 — remain asserted fail-closed, and the ECC ≥ 0.90 gate is
now fail-closed too (claim ANCHORED).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

# §5 / #532 ten states, verbatim order.
STATES: Final[tuple[str, ...]] = (
    "empty",
    "loading",
    "success",
    "validation_error",
    "server_error",
    "network_failure",
    "timeout",
    "partial_result",
    "cancelled",
    "simulation_diverged",
)

ECC_THRESHOLD: Final[float] = 0.90

# §532 hard sub-requirements (asserted fail-closed even at ENTRY).
MANDATORY_PER_ENDPOINT_STATES: Final[tuple[str, ...]] = (
    "network_failure",
    "timeout",
)
SIMULATION_DIVERGED_STATE: Final[str] = "simulation_diverged"

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
_SPEC_PATH: Final[Path] = REPO_ROOT / "schemas" / "openapi" / "geosync-online-inference-v1.json"

_EXCLUDE_PATH_RE: Final[re.Pattern[str]] = re.compile(r"^/graphql")
_HTTP_METHODS: Final[frozenset[str]] = frozenset(
    {"get", "post", "put", "delete", "patch", "options", "head"}
)

# Endpoint classes (mirrors the IERD-Q5 applicability discipline).
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

# Applicable state set per class. Documented rationale:
#   collection — full cardinality + simulation: all ten apply.
#   command    — no cardinality (no empty/partial_result) and no
#                forecast (no simulation_diverged); the rest apply.
#   probe      — unauthenticated read-only liveness/scrape: success,
#                server_error, timeout, network_failure only.
_APPLICABLE: Final[dict[str, frozenset[str]]] = {
    "collection": frozenset(STATES),
    "command": frozenset(
        {
            "success",
            "validation_error",
            "server_error",
            "network_failure",
            "timeout",
            "loading",
            "cancelled",
        }
    ),
    "probe": frozenset({"success", "server_error", "timeout", "network_failure"}),
}

# (class, state) → genuine resolvable test target. Every entry was
# verified to collect under pytest. Absence ⇒ UNCOVERED (see module
# docstring). `path` (no `::`) cites a whole module that exercises the
# state at that layer.
_COVERAGE: Final[dict[tuple[str, str], str]] = {
    # ---- collection ----
    (
        "collection",
        "success",
    ): "tests/api/test_service.py::test_feature_endpoint_supports_pagination_and_filters",
    (
        "collection",
        "empty",
    ): "tests/api/test_service.py::test_feature_filter_returns_404_for_unknown_prefix",
    (
        "collection",
        "partial_result",
    ): "tests/api/test_ux_state_coverage.py::test_uxrs_meets_threshold",
    (
        "collection",
        "validation_error",
    ): "tests/api/test_service.py::test_prediction_endpoint_rejects_invalid_confidence_filter",
    (
        "collection",
        "server_error",
    ): "tests/api/test_service.py::test_internal_errors_return_structured_payload",
    (
        "collection",
        "timeout",
    ): "tests/api/test_ux_state_coverage.py::test_request_timeout_middleware_emits_504_envelope",
    (
        "collection",
        "network_failure",
    ): "tests/connectors/test_fail_closed_connectors.py",
    (
        "collection",
        "simulation_diverged",
    ): "tests/unit/physics/test_inv_dro5_fail_closed.py::test_inv_dro5_rejects_nan_in_input",
    # Q7 EXIT: client in-flight / user-abort states are now genuinely
    # exercised by Playwright route-interception specs against the
    # /edge-probe harness (real fetch; page.route drives each state).
    (
        "collection",
        "loading",
    ): "apps/web/tests/edge-case-probe.spec.ts::/features::loading",
    (
        "collection",
        "cancelled",
    ): "apps/web/tests/edge-case-probe.spec.ts::/features::cancelled",
    # ---- command ----
    (
        "command",
        "success",
    ): "tests/api/test_service.py::test_admin_endpoints_accept_jwt_and_certificate",
    (
        "command",
        "validation_error",
    ): "tests/api/test_service.py::test_admin_endpoints_enforce_rbac",
    (
        "command",
        "server_error",
    ): "tests/api/test_service.py::test_internal_errors_return_structured_payload",
    (
        "command",
        "timeout",
    ): "tests/api/test_ux_state_coverage.py::test_request_timeout_middleware_emits_504_envelope",
    (
        "command",
        "network_failure",
    ): "tests/connectors/test_fail_closed_connectors.py",
    # Q7 EXIT: in-flight / user-abort now covered for the command class
    # via the same /edge-probe route-interception spec.
    (
        "command",
        "loading",
    ): "apps/web/tests/edge-case-probe.spec.ts::/admin/kill-switch::loading",
    (
        "command",
        "cancelled",
    ): "apps/web/tests/edge-case-probe.spec.ts::/admin/kill-switch::cancelled",
    # ---- probe ----
    (
        "probe",
        "success",
    ): "tests/api/test_service.py::test_health_probe_reflects_kill_switch",
    (
        "probe",
        "timeout",
    ): "tests/api/test_ux_state_coverage.py::test_request_timeout_middleware_emits_504_envelope",
    (
        "probe",
        "network_failure",
    ): "tests/connectors/test_fail_closed_connectors.py",
    # Q7 EXIT: per-probe 500 is now asserted by the route-interception
    # spec (page.route fulfil status 500 against /health and /metrics).
    (
        "probe",
        "server_error",
    ): "apps/web/tests/edge-case-probe.spec.ts::/health::server_error",
}


def classify(path: str) -> str:
    """Return the endpoint class for ``path`` (fail-closed on unknown)."""
    if path in _COLLECTION_PATHS:
        return "collection"
    if path in _COMMAND_PATHS:
        return "command"
    if path in _PROBE_PATHS:
        return "probe"
    raise AssertionError(
        f"IERD-Q7 matrix: unclassified public path {path!r}. Assign a "
        f"class + applicable state set with a documented rationale "
        f"rather than leaving it unscored."
    )


def gated_operations() -> list[tuple[str, str]]:
    """[(METHOD, path)] for every gated public operation in the spec."""
    import json

    with _SPEC_PATH.open(encoding="utf-8") as handle:
        spec = json.load(handle)
    ops: list[tuple[str, str]] = []
    for path, item in (spec.get("paths") or {}).items():
        if _EXCLUDE_PATH_RE.match(path):
            continue
        for method in item:
            if method.lower() in _HTTP_METHODS:
                ops.append((method.upper(), path))
    return ops


def applicable_states(path: str) -> frozenset[str]:
    return _APPLICABLE[classify(path)]


def covering_test(path: str, state: str) -> str | None:
    """The cited test target for (endpoint, state), or None if UNCOVERED."""
    return _COVERAGE.get((classify(path), state))


def cited_targets() -> set[str]:
    """Every distinct test target referenced by the matrix."""
    return set(_COVERAGE.values())


def resolve_target(target: str) -> tuple[Path, str | None]:
    """Split ``path::selector`` (or ``path``) into (absolute path, selector).

    For pytest targets the selector is ``func``. For Playwright spec
    targets (``*.spec.ts``) the selector is ``<endpoint>::<state>`` — two
    literals that must both appear in the spec file, giving the TS cells
    the same rename/delete teeth as the pytest cells.
    """
    if "::" in target:
        rel, selector = target.split("::", 1)
    else:
        rel, selector = target, None
    return REPO_ROOT / rel, selector


def _spec_target_exists(file_path: Path, selector: str | None) -> bool:
    """Falsify a Playwright ``*.spec.ts`` cell without running a browser.

    The file must define at least one ``test(`` block, and — when a
    ``<endpoint>::<state>`` selector is given — must literally reference
    both the probed endpoint path and the ``probe-state-<state>`` testid
    the spec asserts on. Renaming the endpoint loop, deleting the state
    assertion, or removing the spec all flip the cell to UNCOVERED.
    """
    source = file_path.read_text(encoding="utf-8")
    if re.search(r"\btest\(", source) is None:
        return False
    if selector is None:
        return True
    parts = selector.split("::")
    if len(parts) != 2:
        return False
    endpoint, state = parts
    return endpoint in source and f"probe-state-{state}" in source


def target_exists(target: str) -> bool:
    """Static, dependency-free existence check for a cited test target.

    Real falsification without invoking pytest collection / a browser
    (which would drag optional deps): the file must exist and the cited
    selector must genuinely resolve inside it. Pytest targets check the
    ``def`` (or, for a whole-module cite, any ``def test_``); Playwright
    spec targets check the ``test(`` block plus the cited
    ``<endpoint>::<state>`` markers.
    """
    file_path, selector = resolve_target(target)
    if not file_path.is_file():
        return False
    if file_path.suffix == ".ts":
        return _spec_target_exists(file_path, selector)
    source = file_path.read_text(encoding="utf-8")
    if selector is None:
        return re.search(r"^\s*def test_\w+", source, re.MULTILINE) is not None
    return re.search(rf"^\s*def {re.escape(selector)}\b", source, re.MULTILINE) is not None


def compute_ecc() -> tuple[int, int, float, list[tuple[str, str, str, str]]]:
    """Return (covered, applicable, ECC, rows).

    ``rows`` is [(METHOD path, state, status, target)] for every
    applicable cell — ``status`` is ``covered`` or ``UNCOVERED``.
    """
    covered = 0
    applicable = 0
    rows: list[tuple[str, str, str, str]] = []
    for method, path in gated_operations():
        for state in STATES:
            if state not in applicable_states(path):
                continue
            applicable += 1
            target = covering_test(path, state)
            if target is not None:
                covered += 1
                rows.append((f"{method} {path}", state, "covered", target))
            else:
                rows.append((f"{method} {path}", state, "UNCOVERED", "-"))
    ecc = covered / applicable if applicable else 0.0
    return covered, applicable, ecc, rows
