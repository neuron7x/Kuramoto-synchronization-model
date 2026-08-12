# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""End-to-end semantic-sieve cycle on a GeoSync hypothesis.

Demonstrates the full 15-stage flow:

    RAW_SIGNAL → CLAIM → CLEAN_CLAIM → INVARIANT → EROSION
        → FALSIFICATION_CONTRACT → STABILITY → CROSS_DOMAIN
        → MEANING_FACT → CRYSTALLIZED_FORM → EXECUTABLE_PROTOCOL
        → RESULT_ARTIFACT → VERIFICATION → AUDIT → KNOWLEDGE_NODE

The orchestrator consults the cognitive sidecar at the adversarial
stages (EROSION, CROSS_DOMAIN). All sidecar output is SPECULATIVE-tier
per Inference Discipline §7; the deterministic state machine + V(O)
remain authoritative.

Run::

    PYTHONPATH=. python examples/semantic_sieve_demo.py
"""

from __future__ import annotations

from runtime.cognitive_bridge import (
    AdvisoryRequest,
    AdvisoryResponse,
    AdvisoryStatus,
    CognitiveSidecar,
    Cycle,
    EvidenceTier,
    InMemoryTransport,
    SidecarConfig,
    Stage,
    ValueComponents,
)

SEED = (
    "OFI imbalance on EURUSD bid/ask exceeds 3σ exactly when Ricci on "
    "spread enters the negative-curvature regime."
)


def _components(*, signal: float, noise: float) -> ValueComponents:
    return ValueComponents(
        invariance=signal,
        falsifiability=signal,
        stability=signal,
        cross_domain=signal,
        actionability=signal,
        reproducibility=signal,
        productivity=signal,
        noise=noise,
        hallucination=noise,
        cognitive_cost=noise,
    )


def _stub_advisor(request: AdvisoryRequest) -> AdvisoryResponse:
    if "erode" in request.question.lower():
        rationale = (
            "Counter-examples: liquidity holidays show OFI > 3σ without "
            "Ricci collapse; consider regime conditioning before promoting."
        )
    else:
        rationale = (
            "Cross-domain anchor: same imbalance/curvature pattern observed "
            "in neural network spike trains (Watanabe 2018); plausible "
            "fractal repeat."
        )
    return AdvisoryResponse(
        correlation_id=request.correlation_id(),
        status=AdvisoryStatus.OK,
        tier=EvidenceTier.SPECULATIVE,
        recommendation="continue",
        rationale=rationale,
    )


def _ask(sidecar: CognitiveSidecar, *, question: str) -> str:
    request = AdvisoryRequest(
        agent_state="REVIEW",
        coherence=0.78,
        kill_switch_active=False,
        stressed_state=False,
        question=question,
    )
    response = sidecar.advise(request)
    return response.rationale or response.status.value


def main() -> int:
    sidecar = CognitiveSidecar(
        transport=InMemoryTransport(_stub_advisor),
        config=SidecarConfig(timeout_s=2.0),
    )
    cycle = Cycle(seed_summary=SEED)

    print(f"[seed]   cycle_id={cycle.cycle_id[:12]}...")
    print(f"[seed]   {SEED}\n")

    cycle.advance(
        Stage.CLAIM,
        summary="OFI > 3σ ⇔ negative Ricci on spread",
        components=_components(signal=0.85, noise=0.10),
    )
    cycle.advance(
        Stage.CLEAN_CLAIM,
        summary="strip emotion/metaphor; keep measurable variables only",
        components=_components(signal=0.90, noise=0.05),
    )
    cycle.advance(
        Stage.INVARIANT,
        summary="invariant kernel: imbalance/curvature alignment under regime change",
        components=_components(signal=0.92, noise=0.05),
    )

    erosion_note = _ask(sidecar, question="erode the OFI/Ricci alignment claim — what breaks it?")
    print(f"[erosion advisory] {erosion_note}\n")
    cycle.advance(
        Stage.EROSION,
        summary=f"adversarial review survived; advisory: {erosion_note[:80]}",
        components=_components(signal=0.80, noise=0.15),
    )

    cycle.set_falsification_contract(
        "if OFI/Ricci alignment IC OOS < 0.05 over 12 walk-forward windows, the invariant is broken"
    )
    cycle.advance(
        Stage.FALSIFICATION_CONTRACT,
        summary="explicit kill-condition attached",
        components=_components(signal=0.95, noise=0.02),
    )
    cycle.advance(
        Stage.STABILITY,
        summary="invariant survives parameter sweep; γ-validation passes",
        components=_components(signal=0.88, noise=0.08),
    )

    cross_note = _ask(sidecar, question="cross-domain analog of OFI/Ricci alignment?")
    print(f"[cross-domain advisory] {cross_note}\n")
    cycle.advance(
        Stage.CROSS_DOMAIN,
        summary=f"analog found: {cross_note[:80]}",
        components=_components(signal=0.85, noise=0.10),
        cross_domain_hits=("neuroscience", "spike-train statistics"),
    )

    cycle.advance(
        Stage.MEANING_FACT,
        summary="apply: regime gate for cross_asset_kuramoto entry signal",
        components=_components(signal=0.90, noise=0.05),
    )
    cycle.advance(
        Stage.CRYSTALLIZED_FORM,
        summary="rule: OFI > 3σ AND Ricci < 0 → emit ENTRY signal",
        components=_components(signal=0.92, noise=0.04),
    )
    cycle.advance(
        Stage.EXECUTABLE_PROTOCOL,
        summary="implementation: research/kernels/ofi_unity_live.py + ricci_on_spread.py",
        components=_components(signal=0.90, noise=0.05),
    )
    cycle.advance(
        Stage.RESULT_ARTIFACT,
        summary="produced kernel + walk-forward report (RUN_MANIFEST.json)",
        components=_components(signal=0.88, noise=0.06),
    )
    cycle.advance(
        Stage.VERIFICATION,
        summary="OOS IC=0.11 over 12 windows; SIGNAL_READY threshold met",
        components=_components(signal=0.91, noise=0.05),
    )

    cycle.set_verification_evidence(
        "research/askar/closing_report.py FINAL_REPORT.json: IC=0.11, "
        "12 OOS windows, deterministic seed=42"
    )
    cycle.advance(
        Stage.AUDIT,
        summary="recursive audit: regime conditioning still required; no single-source dependence",
        components=_components(signal=0.87, noise=0.08),
    )

    node = cycle.commit_to_memory(
        summary=(
            "OFI > 3σ ∧ Ricci < 0 emits ENTRY signal in CRITICAL/TRANSITION "
            "regimes; falsified if OOS IC < 0.05 over 12 walk-forward windows."
        )
    )

    print("[knowledge node]")
    print(f"  cycle_id    : {node.cycle_id[:12]}...")
    print(f"  status      : {node.status.value}")
    print(f"  V(O)        : {node.value_score:.4f}")
    print(f"  cross-domain: {', '.join(node.cross_domain_hits)}")
    print(f"  contract    : {node.falsification_contract[:80]}...")
    print(f"  evidence    : {node.verification_evidence[:80]}...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
