# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Schema and determinism tests for the cognitive bridge protocol."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from runtime.cognitive_bridge.protocol import (
    PROTOCOL_VERSION,
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryStatus,
    EvidenceTier,
)


def _request(
    *,
    agent_state: str = "REVIEW",
    coherence: float = 0.5,
    kill_switch_active: bool = False,
    stressed_state: bool = False,
    question: str = "is the gradient bounded?",
) -> AdvisoryRequest:
    return AdvisoryRequest(
        agent_state=agent_state,
        coherence=coherence,
        kill_switch_active=kill_switch_active,
        stressed_state=stressed_state,
        question=question,
    )


def test_request_correlation_id_is_deterministic() -> None:
    issued = datetime(2026, 1, 1, tzinfo=timezone.utc)
    a = AdvisoryRequest(
        agent_state="REVIEW",
        coherence=0.5,
        kill_switch_active=False,
        stressed_state=False,
        question="q",
        issued_at=issued,
    )
    b = AdvisoryRequest(
        agent_state="REVIEW",
        coherence=0.5,
        kill_switch_active=False,
        stressed_state=False,
        question="q",
        issued_at=issued,
    )
    assert a.correlation_id() == b.correlation_id()
    assert len(a.correlation_id()) == 64


def test_request_correlation_id_changes_with_payload() -> None:
    a = _request()
    b = _request(question="different")
    assert a.correlation_id() != b.correlation_id()


def test_request_rejects_out_of_range_coherence() -> None:
    with pytest.raises(ValidationError):
        _request(coherence=1.2)


def test_request_rejects_unknown_protocol_version() -> None:
    with pytest.raises(ValidationError):
        AdvisoryRequest(
            protocol_version="cb-99.0.0",
            agent_state="REVIEW",
            coherence=0.5,
            kill_switch_active=False,
            stressed_state=False,
            question="q",
        )


def test_request_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        AdvisoryRequest(
            agent_state="REVIEW",
            coherence=0.5,
            kill_switch_active=False,
            stressed_state=False,
            question="q",
            extra_field="boom",  # type: ignore[call-arg]
        )


def test_response_unavailable_constructor_keeps_protocol_version() -> None:
    cid = "0" * 64
    resp = AdvisoryResponse.unavailable(correlation_id=cid, reason="timeout")
    assert resp.status is AdvisoryStatus.UNAVAILABLE
    assert resp.tier is EvidenceTier.UNKNOWN
    assert resp.protocol_version == PROTOCOL_VERSION


def test_response_rejects_non_hex_correlation_id() -> None:
    with pytest.raises(ValidationError):
        AdvisoryResponse(
            correlation_id="z" * 64,
            status=AdvisoryStatus.OK,
        )


def test_response_roundtrip_json() -> None:
    cid = "a" * 64
    resp = AdvisoryResponse(
        correlation_id=cid,
        status=AdvisoryStatus.OK,
        tier=EvidenceTier.SPECULATIVE,
        recommendation="hold",
        rationale="echo",
    )
    raw = json.dumps(resp.model_dump(mode="json"), sort_keys=True)
    rebuilt = AdvisoryResponse.model_validate_json(raw)
    assert rebuilt.correlation_id == cid
    assert rebuilt.status is AdvisoryStatus.OK
