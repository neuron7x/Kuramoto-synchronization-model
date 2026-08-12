# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Shared fixtures for cognitive bridge tests."""

from __future__ import annotations

from typing import Callable

import pytest

from runtime.cognitive_bridge.protocol import (
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryStatus,
    EvidenceTier,
)
from runtime.cognitive_bridge.sidecar import CognitiveSidecar, SidecarConfig
from runtime.cognitive_bridge.transport import InMemoryTransport


@pytest.fixture
def healthy_request() -> AdvisoryRequest:
    return AdvisoryRequest(
        agent_state="REVIEW",
        coherence=0.82,
        kill_switch_active=False,
        stressed_state=False,
        question="Is the ECS field within the Lyapunov bound?",
        context={"regime": "normal"},
    )


@pytest.fixture
def echo_handler() -> Callable[[AdvisoryRequest], AdvisoryResponse]:
    def _handler(request: AdvisoryRequest) -> AdvisoryResponse:
        return AdvisoryResponse(
            correlation_id=request.correlation_id(),
            status=AdvisoryStatus.OK,
            tier=EvidenceTier.SPECULATIVE,
            recommendation="hold",
            rationale="echo",
        )

    return _handler


@pytest.fixture
def sidecar(
    echo_handler: Callable[[AdvisoryRequest], AdvisoryResponse],
) -> CognitiveSidecar:
    return CognitiveSidecar(
        transport=InMemoryTransport(echo_handler),
        config=SidecarConfig(timeout_s=1.0),
    )
