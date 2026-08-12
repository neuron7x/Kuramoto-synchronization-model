# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end demo of the cognitive bridge.

Runs a deterministic in-memory exchange (no external services). The
LoopbackHttpTransport target — a local OpenClaw gateway listening on
``http://127.0.0.1:18789`` — is documented in the module docstring and
in ``runtime/cognitive_bridge/transport.py``; switching to it is a
one-line change.

Run::

    PYTHONPATH=. python examples/cognitive_bridge_demo.py
"""

from __future__ import annotations

from runtime.cognitive_bridge import (
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryStatus,
    CognitiveSidecar,
    EvidenceTier,
    InMemoryTransport,
    SidecarConfig,
)


def _stub_handler(request: AdvisoryRequest) -> AdvisoryResponse:
    if request.coherence < 0.5:
        recommendation = "narrow_exposure"
        rationale = "coherence below 0.5; recommend reducing position size"
    else:
        recommendation = "hold"
        rationale = "coherence within nominal band"
    return AdvisoryResponse(
        correlation_id=request.correlation_id(),
        status=AdvisoryStatus.OK,
        tier=EvidenceTier.SPECULATIVE,
        recommendation=recommendation,
        rationale=rationale,
    )


def main() -> int:
    sidecar = CognitiveSidecar(
        transport=InMemoryTransport(_stub_handler),
        config=SidecarConfig(timeout_s=2.0),
    )

    nominal = AdvisoryRequest(
        agent_state="REVIEW",
        coherence=0.82,
        kill_switch_active=False,
        stressed_state=False,
        question="Should we hold the EURUSD basket through the next bar?",
    )
    stressed = nominal.model_copy(update={"coherence": 0.31})
    halted = nominal.model_copy(update={"kill_switch_active": True})

    for label, request in (
        ("nominal", nominal),
        ("low-coherence", stressed),
        ("kill-switch", halted),
    ):
        response = sidecar.advise(request)
        print(
            f"[{label:>14}] status={response.status.value:<11} "
            f"tier={response.tier.value:<11} "
            f"rec={response.recommendation!r}"
        )

    print("\naudit log:")
    for entry in sidecar.audit_log():
        invariant = entry.invariant.value if entry.invariant else "-"
        print(
            f"  {entry.ts.isoformat()} "
            f"cid={entry.correlation_id[:12]}... "
            f"status={entry.status.value} inv={invariant}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
