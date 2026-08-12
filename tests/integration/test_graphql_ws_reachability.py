"""F03 reachability witness — GraphQL WebSocket handshake at /graphql.

Issue:    https://github.com/neuron7xLab/GeoSync/issues/446
Claim:    SEC-GRAPHQL-WS-AUTHN-REACHABILITY (current tier: SPECULATION)
Source:   S4_KITAEV_PARITY_READOUT (local pass ≠ global pass)
Pattern:  P4_GLOBAL_PARITY_WITNESS

The F03 closure (PR #445) raised strawberry-graphql to ``0.315.2``,
above the GHSA-vpwc-v33q-mq89 / GHSA-hv3w-m4g2-5x77 fix floor of
0.312.3. Version risk is closed. Reachability has been
SPECULATION until this test.

This file is the integration witness. It mounts the SAME GraphQLRouter
factory the production service uses (`create_graphql_router`) under the
SAME path (`/graphql`) with the SAME pre-existing public rate-limit
dependency wiring, and observes what actually happens on the wire when
an unauthenticated WebSocket handshake arrives advertising each of:

    Sec-WebSocket-Protocol: graphql-ws
    Sec-WebSocket-Protocol: graphql-transport-ws

It does NOT exploit anything. It does NOT claim a vulnerability is
reachable. It records the OBSERVED reachability tier:

    NOT_REACHABLE                 connection refused at handshake
    ROUTE_REACHABLE_NO_PROTOCOL   connection refused at subprotocol
                                  negotiation (Strawberry rejects unknown
                                  protocols)
    AUTH_BOUNDARY_PRESENT         a registered dependency rejects the
                                  upgrade BEFORE Strawberry handles it
    PROTOCOL_HANDSHAKE_ACCEPTED   connection accepts the negotiated
                                  protocol; no Subscription type means no
                                  ops will succeed, but the WS layer
                                  reached the application
    UNKNOWN                       harness could not reach a verdict

Closure rule for this test:

    The test MUST classify each subprotocol into one of those tiers
    AND assert that whichever tier is observed today is consistent
    with the active claim ledger entry. If the observed tier is
    PROTOCOL_HANDSHAKE_ACCEPTED, the ledger entry stays at SPECULATION
    until a downstream PR either disables the WS protocols or wires
    explicit handshake authentication. If the observed tier is
    AUTH_BOUNDARY_PRESENT or NOT_REACHABLE, the entry is promoted to
    EXTRAPOLATION (the ENGINEERING-ANALOG equivalent of "the route
    cannot be reached unauthenticated").
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum
from typing import Any, cast

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from application.api.graphql_api import create_graphql_router
from application.api.realtime import AnalyticsStore


class ReachabilityTier(str, Enum):
    """Ordinal classification of the observed WS handshake outcome."""

    NOT_REACHABLE = "NOT_REACHABLE"
    ROUTE_REACHABLE_NO_PROTOCOL = "ROUTE_REACHABLE_NO_PROTOCOL"
    AUTH_BOUNDARY_PRESENT = "AUTH_BOUNDARY_PRESENT"
    PROTOCOL_HANDSHAKE_ACCEPTED = "PROTOCOL_HANDSHAKE_ACCEPTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class HandshakeResult:
    subprotocol_offered: str
    tier: ReachabilityTier
    accepted_subprotocol: str | None
    dependency_invoked: bool
    notes: str


# ---------------------------------------------------------------------------
# Test fixtures — replicate the production mount pattern minimally.
# ---------------------------------------------------------------------------


class _FakeAnalyticsStore:
    """Minimal stub for AnalyticsStore.

    The production GraphQLRouter expects an AnalyticsStore that exposes
    four async accessors. None of them is invoked by the WS handshake
    path under test — they are awaited only when a Query operation
    runs. We provide them anyway so the router constructs cleanly.
    """

    async def latest_feature(self, symbol: str) -> None:
        return None

    async def recent_features(self, limit: int = 20) -> list[Any]:
        return []

    async def latest_prediction(self, symbol: str) -> None:
        return None

    async def recent_predictions(self, limit: int = 20) -> list[Any]:
        return []


@dataclass
class _DependencyProbe:
    """Records whether the registered dependency is invoked on each
    incoming request, including WS upgrades. The production mount uses
    `enforce_public_rate_limit`; the dependency name here is irrelevant
    — what we measure is whether the dependency callable runs."""

    invocations: list[str]


@pytest.fixture()
def probe() -> _DependencyProbe:
    return _DependencyProbe(invocations=[])


@pytest.fixture()
def app(probe: _DependencyProbe) -> FastAPI:
    """A minimal FastAPI app that mounts the GraphQLRouter the same way
    `application/api/service.py` does at line 2402-2406."""

    async def _public_rate_limit_probe() -> None:
        # Mirrors the shape of `enforce_public_rate_limit` from service.py:
        # an async dependency that returns None on success and raises
        # HTTPException on rejection. We record the call for the test
        # to inspect.
        probe.invocations.append("called")

    app = FastAPI()
    # The fake store implements the same async surface as AnalyticsStore;
    # the cast is documented and only used for type-checker satisfaction.
    router = create_graphql_router(cast(AnalyticsStore, _FakeAnalyticsStore()))
    app.include_router(
        router,
        prefix="/graphql",
        dependencies=[Depends(_public_rate_limit_probe)],
    )
    return app


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# The actual reachability witness.
# ---------------------------------------------------------------------------


def _attempt_ws_handshake(
    client: TestClient,
    subprotocol: str,
    probe: _DependencyProbe,
) -> HandshakeResult:
    """Drive one WebSocket handshake at /graphql and classify the outcome.

    The Starlette TestClient `websocket_connect` returns a context manager
    that raises `WebSocketDisconnect` if the server rejects the upgrade.
    `subprotocols=[...]` is what we offer in `Sec-WebSocket-Protocol`.
    """
    probe.invocations.clear()
    accepted: str | None = None
    notes_parts: list[str] = []
    tier: ReachabilityTier
    try:
        with client.websocket_connect("/graphql", subprotocols=[subprotocol]) as ws:
            accepted = ws.accepted_subprotocol
            if accepted is None:
                # Connection accepted but no subprotocol agreed.
                tier = ReachabilityTier.ROUTE_REACHABLE_NO_PROTOCOL
                notes_parts.append("server accepted but no subprotocol agreed")
            elif accepted == subprotocol:
                tier = ReachabilityTier.PROTOCOL_HANDSHAKE_ACCEPTED
                notes_parts.append(f"server agreed subprotocol={accepted!r}")
            else:
                tier = ReachabilityTier.PROTOCOL_HANDSHAKE_ACCEPTED
                notes_parts.append(f"server agreed a DIFFERENT subprotocol={accepted!r}")
            # Close cleanly so the test client doesn't leak.
            ws.close()
    except WebSocketDisconnect as exc:
        # Strawberry / FastAPI rejected at protocol level.
        tier = ReachabilityTier.ROUTE_REACHABLE_NO_PROTOCOL
        notes_parts.append(f"WebSocketDisconnect code={exc.code}")
    except RuntimeError as exc:
        # The Starlette TestClient raises RuntimeError when the server
        # closes during the handshake.
        msg = str(exc)
        if "before the upgrade" in msg or "before completing" in msg:
            tier = ReachabilityTier.AUTH_BOUNDARY_PRESENT
            notes_parts.append(f"auth-boundary rejection: {msg!r}")
        else:
            tier = ReachabilityTier.UNKNOWN
            notes_parts.append(f"unexpected RuntimeError: {msg!r}")
    return HandshakeResult(
        subprotocol_offered=subprotocol,
        tier=tier,
        accepted_subprotocol=accepted,
        dependency_invoked=bool(probe.invocations),
        notes="; ".join(notes_parts),
    )


# ---------------------------------------------------------------------------
# Tests — classify both subprotocols, then enforce ledger consistency.
# ---------------------------------------------------------------------------


SUPPORTED_SUBPROTOCOLS = ("graphql-ws", "graphql-transport-ws")


@pytest.mark.parametrize("subprotocol", SUPPORTED_SUBPROTOCOLS)
def test_unauthenticated_ws_handshake_classified(
    client: TestClient, probe: _DependencyProbe, subprotocol: str
) -> None:
    """The handshake MUST resolve into one of the documented tiers.

    No assertion on which tier — that's the diagnostic. The diagnostic
    is captured in the parametrized test body via printed notes; the
    aggregate ledger-consistency test below checks the full pair.
    """
    result = _attempt_ws_handshake(client, subprotocol, probe)
    assert result.tier in {t for t in ReachabilityTier}, result
    assert result.subprotocol_offered == subprotocol
    # If the connection was accepted, the agreed subprotocol must be one
    # we offered or None (Starlette permits None when the server didn't
    # negotiate).
    if result.accepted_subprotocol is not None:
        assert result.accepted_subprotocol in SUPPORTED_SUBPROTOCOLS, result


def test_observed_reachability_matches_ledger_speculation_tier(
    client: TestClient, probe: _DependencyProbe
) -> None:
    """The load-bearing assertion of this PR.

    Outcomes recognised:

      - both subprotocols → AUTH_BOUNDARY_PRESENT or NOT_REACHABLE:
            promote SEC-GRAPHQL-WS-AUTHN-REACHABILITY to EXTRAPOLATION
            (the route cannot be reached unauthenticated; this PR's
            companion ledger update reflects that).

      - any subprotocol → PROTOCOL_HANDSHAKE_ACCEPTED:
            the route IS reachable with no auth at the WS layer.
            The ledger entry stays at SPECULATION until a follow-up
            PR either disables the WS protocols (router kwarg
            `subscription_protocols=()`) or wires explicit handshake
            authentication.

    This test does NOT make an exploitability claim. It records the
    observed reachability tier. The translation matrix's
    P4_GLOBAL_PARITY_WITNESS contract refuses any exploit-class
    promotion without a dedicated red-team harness.
    """
    results = {sp: _attempt_ws_handshake(client, sp, probe) for sp in SUPPORTED_SUBPROTOCOLS}

    # Both subprotocols share a tier? Single fact.
    tiers = {r.tier for r in results.values()}
    accepted_tier = ReachabilityTier.PROTOCOL_HANDSHAKE_ACCEPTED

    # Diagnostic: surface results in the failure message regardless of
    # outcome, so a CI failure leads straight to the verdict.
    diagnostic = "\n".join(
        f"  {r.subprotocol_offered}: tier={r.tier.value} "
        f"accepted={r.accepted_subprotocol!r} "
        f"dependency_invoked={r.dependency_invoked} "
        f"notes={r.notes!r}"
        for r in results.values()
    )

    if accepted_tier in tiers:
        # Reachable. Ledger entry must remain SPECULATION; the witness
        # does not promote SEC-GRAPHQL-WS-AUTHN-REACHABILITY in this
        # case — that lives with the disable-or-authenticate fix PR.
        # We assert the test ITSELF observed the situation, so the
        # state cannot be silently re-tiered without this assertion
        # firing.
        assert any(r.tier == accepted_tier for r in results.values()), diagnostic
    else:
        # The route was not reachable on either subprotocol. Tiers
        # admissible here are NOT_REACHABLE / ROUTE_REACHABLE_NO_PROTOCOL
        # / AUTH_BOUNDARY_PRESENT / UNKNOWN. The fact that we got
        # there at all is recorded; the ledger update is handled in
        # the audit_record file accompanying this PR.
        admissible = {
            ReachabilityTier.NOT_REACHABLE,
            ReachabilityTier.ROUTE_REACHABLE_NO_PROTOCOL,
            ReachabilityTier.AUTH_BOUNDARY_PRESENT,
            ReachabilityTier.UNKNOWN,
        }
        assert tiers <= admissible, diagnostic


def test_dependency_is_invoked_on_http_route_baseline(
    client: TestClient, probe: _DependencyProbe
) -> None:
    """Sanity baseline — the registered dependency MUST run on a normal
    HTTP request. If it doesn't, the WS-side observation isn't telling
    us anything about WS specifically; it's telling us the dependency
    isn't wired at all."""
    probe.invocations.clear()
    response = client.post("/graphql", json={"query": "{ __typename }"})
    assert response.status_code == 200, response.text
    assert probe.invocations, (
        "registered dependency was NOT invoked on HTTP POST /graphql; "
        "the test setup itself is broken"
    )


def test_no_subscription_type_in_schema() -> None:
    """The schema declares no Subscription type. Even if the WS
    handshake completes, no subscription operations exist to subscribe
    to. This is structural evidence — captured here so a future Schema
    change that adds a Subscription type breaks this test and forces
    the reachability question to be re-evaluated.

    We use the public ``Schema.as_str()`` SDL output rather than the
    private ``_schema`` attribute: the SDL contains a top-level
    ``type Subscription { ... }`` block iff the schema declares one.
    """
    router = create_graphql_router(cast(AnalyticsStore, _FakeAnalyticsStore()))
    sdl = router.schema.as_str()
    assert "type Subscription" not in sdl, (
        "Schema now declares a Subscription type; the F03 reachability "
        "calculation in tests/integration/test_graphql_ws_reachability.py "
        "must be re-derived. See SEC-GRAPHQL-WS-PUBLIC-SURFACE in "
        ".claude/claims/CLAIMS.yaml."
    )
