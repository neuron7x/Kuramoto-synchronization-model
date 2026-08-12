# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end tests for the CognitiveSidecar orchestrator."""

from __future__ import annotations

from typing import Callable

import pytest

from runtime.cognitive_bridge.protocol import (
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryStatus,
)
from runtime.cognitive_bridge.sidecar import CognitiveSidecar, SidecarConfig
from runtime.cognitive_bridge.transport import InMemoryTransport


def test_happy_path_returns_ok_and_appends_audit(
    sidecar: CognitiveSidecar,
    healthy_request: AdvisoryRequest,
) -> None:
    response = sidecar.advise(healthy_request)
    assert response.status is AdvisoryStatus.OK
    log = sidecar.audit_log()
    assert log[-1].correlation_id == healthy_request.correlation_id()
    assert log[-1].status is AdvisoryStatus.OK


def test_disabled_config_short_circuits_without_calling_transport(
    healthy_request: AdvisoryRequest,
) -> None:
    def must_not_call(_: AdvisoryRequest) -> AdvisoryResponse:
        raise AssertionError("transport must not run when sidecar is disabled")

    sidecar = CognitiveSidecar(
        transport=InMemoryTransport(must_not_call),
        config=SidecarConfig(enabled=False),
    )
    response = sidecar.advise(healthy_request)
    assert response.status is AdvisoryStatus.DISABLED


def test_audit_log_is_bounded_to_config(
    echo_handler: Callable[[AdvisoryRequest], AdvisoryResponse],
    healthy_request: AdvisoryRequest,
) -> None:
    sidecar = CognitiveSidecar(
        transport=InMemoryTransport(echo_handler),
        config=SidecarConfig(audit_log_size=4),
    )
    for i in range(10):
        sidecar.advise(healthy_request.model_copy(update={"question": f"q-{i}"}))
    log = sidecar.audit_log()
    assert len(log) == 4


def test_invalid_config_rejected() -> None:
    with pytest.raises(ValueError):
        SidecarConfig(timeout_s=0.0)
    with pytest.raises(ValueError):
        SidecarConfig(audit_log_size=0)


def test_config_property_exposes_immutable_view(
    sidecar: CognitiveSidecar,
) -> None:
    cfg = sidecar.config
    with pytest.raises(Exception):
        cfg.timeout_s = 99.0  # type: ignore[misc]


def test_audit_correlation_id_matches_request(
    sidecar: CognitiveSidecar,
    healthy_request: AdvisoryRequest,
) -> None:
    sidecar.advise(healthy_request)
    log = sidecar.audit_log()
    assert log[-1].correlation_id == healthy_request.correlation_id()
