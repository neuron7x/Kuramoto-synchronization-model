# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Per-invariant fail-closed tests (CB-INV-1..7)."""

from __future__ import annotations

from typing import Callable

import pytest

from runtime.cognitive_bridge.errors import (
    BridgeInvariantError,
    BridgeTimeoutError,
    BridgeTransportError,
)
from runtime.cognitive_bridge.invariants import CB_INVARIANTS, InvariantId
from runtime.cognitive_bridge.protocol import (
    PROTOCOL_VERSION,
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryStatus,
)
from runtime.cognitive_bridge.sidecar import CognitiveSidecar, SidecarConfig
from runtime.cognitive_bridge.transport import InMemoryTransport


def _stress_request(
    *,
    agent_state: str = "REVIEW",
    coherence: float = 0.5,
    kill_switch_active: bool = False,
    stressed_state: bool = False,
    question: str = "q",
) -> AdvisoryRequest:
    return AdvisoryRequest(
        agent_state=agent_state,
        coherence=coherence,
        kill_switch_active=kill_switch_active,
        stressed_state=stressed_state,
        question=question,
    )


def _make(handler: Callable[[AdvisoryRequest], AdvisoryResponse]) -> CognitiveSidecar:
    return CognitiveSidecar(
        transport=InMemoryTransport(handler),
        config=SidecarConfig(timeout_s=1.0),
    )


def test_invariant_registry_is_complete_and_unique() -> None:
    keys = list(CB_INVARIANTS.keys())
    assert set(keys) == set(InvariantId)
    assert len(keys) == 7


def test_cb_inv_1_schema_violation_collapses_to_unavailable() -> None:
    def bad_handler(_: AdvisoryRequest) -> AdvisoryResponse:
        # Returning a malformed shape would be caught upstream in transport;
        # here we simulate the LoopbackHttpTransport's ValidationError path
        # by raising it directly.
        from pydantic import ValidationError

        try:
            AdvisoryResponse(correlation_id="not-hex", status=AdvisoryStatus.OK)
        except ValidationError as exc:
            raise exc
        raise AssertionError("expected ValidationError")

    sidecar = _make(bad_handler)
    response = sidecar.advise(_stress_request())
    assert response.status is AdvisoryStatus.UNAVAILABLE
    audit = sidecar.audit_log()
    assert audit[-1].invariant is InvariantId.CB_INV_1_SCHEMA


def test_cb_inv_2_timeout_collapses_to_unavailable() -> None:
    def slow_handler(_: AdvisoryRequest) -> AdvisoryResponse:
        raise BridgeTimeoutError("over budget")

    sidecar = _make(slow_handler)
    response = sidecar.advise(_stress_request())
    assert response.status is AdvisoryStatus.UNAVAILABLE
    audit = sidecar.audit_log()
    assert audit[-1].invariant is InvariantId.CB_INV_2_TIMEOUT


def test_cb_inv_3_advisory_only_default_tier_is_speculative() -> None:
    # Branch (c) of the falsification contract: tier MUST default to
    # SPECULATIVE on a free-form reply. If a future change defaults it
    # to ANCHORED the host could mistake LLM output for ground truth.
    def ok_handler(req: AdvisoryRequest) -> AdvisoryResponse:
        return AdvisoryResponse(
            correlation_id=req.correlation_id(),
            status=AdvisoryStatus.OK,
            recommendation="hold",
        )

    sidecar = _make(ok_handler)
    response = sidecar.advise(_stress_request())
    assert response.status is AdvisoryStatus.OK
    assert response.tier.value == "speculative"


def test_cb_inv_3_advisory_response_is_frozen() -> None:
    # Branch (a) of the falsification contract: AdvisoryResponse MUST
    # be immutable, otherwise a host could mutate the reply mid-flight
    # and re-publish it as authoritative state.
    response = AdvisoryResponse(
        correlation_id="a" * 64,
        status=AdvisoryStatus.OK,
        recommendation="hold",
    )
    with pytest.raises(Exception):
        response.status = AdvisoryStatus.UNAVAILABLE  # type: ignore[misc]
    with pytest.raises(Exception):
        response.recommendation = "MARKET ORDER NOW"  # type: ignore[misc]


def test_cb_inv_3_advisory_response_rejects_extra_fields() -> None:
    # Branch (b) of the falsification contract: extra='forbid' MUST
    # block any new field that could carry a callable, code blob, or
    # other executable side-effect into the host process.
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AdvisoryResponse(
            correlation_id="a" * 64,
            status=AdvisoryStatus.OK,
            execute_now=True,  # type: ignore[call-arg]
        )


def test_cb_inv_3_advisory_response_exposes_no_callable_fields() -> None:
    # Structural sweep: nothing in the public schema should be a
    # callable type — the response is descriptive text + enum + hash.
    schema = AdvisoryResponse.model_json_schema()
    for name, field in schema.get("properties", {}).items():
        field_type = field.get("type")
        assert field_type in {
            "string",
            "boolean",
            "integer",
            "number",
            None,
        }, f"AdvisoryResponse.{name} has non-descriptive type {field_type!r}"


def test_cb_inv_4_correlation_mismatch_raises() -> None:
    def wrong_cid(_: AdvisoryRequest) -> AdvisoryResponse:
        return AdvisoryResponse(
            correlation_id="0" * 64,
            status=AdvisoryStatus.OK,
        )

    sidecar = _make(wrong_cid)
    with pytest.raises(BridgeInvariantError) as excinfo:
        sidecar.advise(_stress_request())
    assert excinfo.value.invariant_id == InvariantId.CB_INV_4_CORRELATION.value


def test_cb_inv_5_kill_switch_short_circuits_to_disabled() -> None:
    sidecar = _make(_should_not_be_called)
    response = sidecar.advise(_stress_request(kill_switch_active=True))
    assert response.status is AdvisoryStatus.DISABLED
    audit = sidecar.audit_log()
    assert audit[-1].invariant is InvariantId.CB_INV_5_KILL_SWITCH


def test_cb_inv_6_stressed_state_short_circuits_to_disabled() -> None:
    sidecar = _make(_should_not_be_called)
    response = sidecar.advise(_stress_request(stressed_state=True))
    assert response.status is AdvisoryStatus.DISABLED
    audit = sidecar.audit_log()
    assert audit[-1].invariant is InvariantId.CB_INV_6_STRESSED


def test_cb_inv_7_protocol_version_mismatch_raises() -> None:
    # Build a response whose protocol_version was tampered with at the wire
    # boundary. We bypass the validator by building, then mutating via copy.
    def bad_version(req: AdvisoryRequest) -> AdvisoryResponse:
        ok = AdvisoryResponse(
            correlation_id=req.correlation_id(),
            status=AdvisoryStatus.OK,
        )
        return ok.model_copy(update={"protocol_version": "cb-9.9.9"})

    sidecar = _make(bad_version)
    with pytest.raises(BridgeInvariantError) as excinfo:
        sidecar.advise(_stress_request())
    assert excinfo.value.invariant_id == InvariantId.CB_INV_7_VERSION.value


def test_transport_error_collapses_to_unavailable() -> None:
    def explode(_: AdvisoryRequest) -> AdvisoryResponse:
        raise BridgeTransportError("boom")

    sidecar = _make(explode)
    response = sidecar.advise(_stress_request())
    assert response.status is AdvisoryStatus.UNAVAILABLE


def _should_not_be_called(_: AdvisoryRequest) -> AdvisoryResponse:
    raise AssertionError("transport must not be invoked when bridge is disabled")


def test_protocol_version_constant_is_the_one_in_invariant_7() -> None:
    # Sanity: the wire constant doesn't drift away from the registry text.
    assert PROTOCOL_VERSION.startswith("cb-")
    assert "PROTOCOL_VERSION" in CB_INVARIANTS[InvariantId.CB_INV_7_VERSION].description
