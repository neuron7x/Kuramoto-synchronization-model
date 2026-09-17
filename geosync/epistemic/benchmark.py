"""Controlled adversarial benchmark for ECP-AS claim-promotion policies.

This module measures policy behavior under declared cases. It does not establish
external scientific truth or natural-workload generalization.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from .admission import AdmissionController
from .contracts import PromotionContract, default_contracts
from .models import (
    Claim,
    ClaimState,
    Evidence,
    EvidenceKind,
    NegativeEvidence,
    NegativeEvidenceKind,
    Oracle,
    OracleIndependence,
)


@dataclass(frozen=True, slots=True)
class PromotionScenario:
    scenario_id: str
    claim: Claim
    target: ClaimState
    evidence: tuple[Evidence, ...]
    negative_evidence: tuple[NegativeEvidence, ...]
    oracles: tuple[Oracle, ...]
    falsifier_executed: bool
    safe_to_promote: bool
    failure_class: str
    rationale: str
    source_ref: str = "synthetic:ecp-as-iteration-002"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True, slots=True)
class PolicyMetrics:
    policy: str
    total: int
    safe_cases: int
    unsafe_cases: int
    unsafe_promotions: int
    false_blocks: int
    correct: int

    @property
    def unsafe_promotion_rate(self) -> float:
        return self.unsafe_promotions / self.unsafe_cases if self.unsafe_cases else 0.0

    @property
    def false_block_rate(self) -> float:
        return self.false_blocks / self.safe_cases if self.safe_cases else 0.0

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "policy": self.policy,
            "total": self.total,
            "safe_cases": self.safe_cases,
            "unsafe_cases": self.unsafe_cases,
            "unsafe_promotions": self.unsafe_promotions,
            "unsafe_promotion_rate": self.unsafe_promotion_rate,
            "false_blocks": self.false_blocks,
            "false_block_rate": self.false_block_rate,
            "correct": self.correct,
            "accuracy": self.accuracy,
        }


class PromotionPolicy(Protocol):
    name: str

    def decide(self, scenario: PromotionScenario) -> PolicyDecision: ...


def _contract(s: PromotionScenario) -> PromotionContract:
    return default_contracts()[s.target]


def _required_evidence_present(s: PromotionScenario) -> tuple[bool, str]:
    contract = default_contracts().get(s.target)
    if contract is None:
        return False, "no contract"
    if any(e.claim_id != s.claim.claim_id for e in s.evidence):
        return False, "cross-claim evidence"
    present = {e.kind for e in s.evidence if e.valid}
    missing = contract.required_evidence - present
    if missing:
        return False, "missing evidence: " + ",".join(sorted(k.value for k in missing))
    return True, "required evidence present"


def _active_blocking_negative(s: PromotionScenario) -> bool:
    return any(
        n.claim_id == s.claim.claim_id and n.blocking and not n.resolved
        for n in s.negative_evidence
    )


class RequiredEvidenceBaseline:
    name = "required_evidence_only"

    def decide(self, s: PromotionScenario) -> PolicyDecision:
        ok, reason = _required_evidence_present(s)
        return PolicyDecision(ok, reason)


class SelfReviewBaseline:
    name = "self_review"

    def decide(self, s: PromotionScenario) -> PolicyDecision:
        ok, reason = _required_evidence_present(s)
        if not ok:
            return PolicyDecision(False, reason)
        if _contract(s).requires_falsifier_execution and not s.falsifier_executed:
            return PolicyDecision(False, "falsifier missing")
        return PolicyDecision(True, "self-review accepted")


class MultiAgentVoteBaseline:
    name = "multi_agent_vote"

    def decide(self, s: PromotionScenario) -> PolicyDecision:
        decision = SelfReviewBaseline().decide(s)
        if not decision.allowed:
            return decision
        if _contract(s).requires_independent_oracle and len(s.oracles) < 2:
            return PolicyDecision(False, "fewer than two verifier reports")
        return PolicyDecision(True, "verifier vote threshold met")


class ArtifactChainBaseline:
    name = "artifact_chain_no_lineage"

    def decide(self, s: PromotionScenario) -> PolicyDecision:
        decision = SelfReviewBaseline().decide(s)
        if not decision.allowed:
            return decision
        contract = _contract(s)
        if contract.requires_clean_negative_evidence and _active_blocking_negative(s):
            return PolicyDecision(False, "blocking negative evidence")
        if contract.requires_independent_oracle and not s.oracles:
            return PolicyDecision(False, "no oracle")
        return PolicyDecision(True, "artifact chain accepted without lineage analysis")


class ECPASPolicy:
    name = "ecp_as"

    def __init__(self, controller: AdmissionController | None = None) -> None:
        self.controller = controller or AdmissionController()

    def decide(self, s: PromotionScenario) -> PolicyDecision:
        try:
            decision = self.controller.evaluate(
                s.claim,
                s.target,
                s.evidence,
                s.negative_evidence,
                s.oracles,
                falsifier_executed=s.falsifier_executed,
            )
        except ValueError as exc:
            return PolicyDecision(False, str(exc))
        return PolicyDecision(decision.allowed, "; ".join(decision.blockers) or "admitted")


class ECPASNoNegativeAblation(ECPASPolicy):
    name = "ecp_as_no_negative_gate"

    def __init__(self) -> None:
        contracts: Mapping[ClaimState, PromotionContract] = {
            state: replace(contract, requires_clean_negative_evidence=False)
            for state, contract in default_contracts().items()
        }
        super().__init__(
            AdmissionController(contracts=contracts, policy_version="ECP-AS/0.2-ablation-neg")
        )


class ECPASNoLineageAblation(ArtifactChainBaseline):
    name = "ecp_as_no_lineage_gate"


def _claim(claim_id: str, state: ClaimState) -> Claim:
    return Claim(
        claim_id,
        f"Proposition {claim_id}",
        "benchmark",
        "iteration-002",
        state,
        generator_ancestors=frozenset({"model:generator"}),
    )


def _evidence(claim_id: str, target: ClaimState) -> tuple[Evidence, ...]:
    kinds = sorted(default_contracts()[target].required_evidence, key=lambda item: item.value)
    return tuple(
        Evidence(
            f"{claim_id}:{kind.value.lower()}",
            kind,
            f"digest:{claim_id}:{kind.value.lower()}",
            "benchmark",
            "1",
            claim_id,
        )
        for kind in kinds
    )


def _oracle(
    claim_id: str,
    suffix: str,
    *,
    ancestor: str = "model:external",
    axes: tuple[bool, bool, bool, bool] = (True, True, True, True),
    admissible: bool = True,
    bound_claim_id: str | None = None,
) -> Oracle:
    return Oracle(
        f"oracle:{suffix}",
        bound_claim_id or claim_id,
        f"oracle-digest:{suffix}",
        OracleIndependence(*axes),
        frozenset({ancestor}),
        admissible=admissible,
    )


def _default_oracles(claim_id: str, target: ClaimState) -> tuple[Oracle, ...]:
    if not default_contracts()[target].requires_independent_oracle:
        return ()
    return (
        _oracle(claim_id, "external-a"),
        _oracle(claim_id, "external-b", ancestor="model:external-b"),
    )


def _scenario(
    scenario_id: str,
    current: ClaimState,
    target: ClaimState,
    *,
    safe: bool,
    failure_class: str,
    rationale: str,
    evidence: tuple[Evidence, ...] | None = None,
    negative: tuple[NegativeEvidence, ...] = (),
    oracles: tuple[Oracle, ...] | None = None,
    falsifier: bool = True,
    source_ref: str = "synthetic:ecp-as-iteration-002",
) -> PromotionScenario:
    return PromotionScenario(
        scenario_id,
        _claim(scenario_id, current),
        target,
        _evidence(scenario_id, target) if evidence is None else evidence,
        negative,
        _default_oracles(scenario_id, target) if oracles is None else oracles,
        falsifier,
        safe,
        failure_class,
        rationale,
        source_ref,
    )


def _negative(
    claim_id: str,
    kind: NegativeEvidenceKind,
    *,
    blocking: bool = True,
    resolved: bool = False,
) -> NegativeEvidence:
    return NegativeEvidence(
        f"neg:{claim_id}:{kind.value}",
        kind,
        f"neg-digest:{claim_id}:{kind.value}",
        claim_id,
        blocking=blocking,
        resolved=resolved,
    )


def build_core_scenarios() -> tuple[PromotionScenario, ...]:
    rows: list[PromotionScenario] = []

    safe_specs = (
        ("safe-replicated-a", ClaimState.OBSERVED, ClaimState.REPLICATED),
        ("safe-replicated-b", ClaimState.OBSERVED, ClaimState.REPLICATED),
        ("safe-bounded", ClaimState.REPLICATED, ClaimState.BOUNDED),
        ("safe-transfer", ClaimState.BOUNDED, ClaimState.TRANSFER_TESTED),
    )
    for sid, current, target in safe_specs:
        rows.append(_scenario(sid, current, target, safe=True, failure_class="clean", rationale="Clean promotion control."))

    sid = "safe-bounded-resolved-negative"
    rows.append(_scenario(sid, ClaimState.REPLICATED, ClaimState.BOUNDED, safe=True, failure_class="resolved_negative", rationale="Resolved negative must not create a permanent dead state.", negative=(_negative(sid, NegativeEvidenceKind.REPLAY_MISMATCH, resolved=True),)))

    for sid, current, target in (
        ("safe-replicated-single-independent", ClaimState.OBSERVED, ClaimState.REPLICATED),
        ("safe-bounded-single-independent", ClaimState.REPLICATED, ClaimState.BOUNDED),
        ("safe-transfer-single-independent", ClaimState.BOUNDED, ClaimState.TRANSFER_TESTED),
    ):
        rows.append(_scenario(sid, current, target, safe=True, failure_class="single_independent_oracle", rationale="One genuinely independent oracle is sufficient for the ECP contract.", oracles=(_oracle(sid, "single"),)))

    sid = "safe-replicated-mixed-oracles"
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=True, failure_class="mixed_oracles", rationale="At least one admissible independent oracle exists.", oracles=(_oracle(sid, "shared", ancestor="model:generator"), _oracle(sid, "independent", ancestor="model:external-b"))))

    sid = "safe-replicated-one-bad-one-good"
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=True, failure_class="mixed_independence_quality", rationale="A weak oracle does not invalidate a separate admissible independent oracle.", oracles=(_oracle(sid, "bad", axes=(True, True, True, False)), _oracle(sid, "good", ancestor="model:external-b"))))

    sid = "safe-replicated-nonblocking-negative"
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=True, failure_class="nonblocking_negative", rationale="Non-blocking negative context remains visible without prohibiting promotion.", negative=(_negative(sid, NegativeEvidenceKind.CALIBRATION_MISS, blocking=False),)))

    sid = "safe-replicated-resolved-negative"
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=True, failure_class="resolved_negative", rationale="Resolved blocking evidence remains recorded but no longer blocks.", negative=(_negative(sid, NegativeEvidenceKind.REPLAY_MISMATCH, resolved=True),)))

    sid = "unsafe-shared-lineage-single"
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="hidden_lineage", rationale="Verifier shares the generator model ancestor.", oracles=(_oracle(sid, "shared-a", ancestor="model:generator"),)))

    sid = "unsafe-two-correlated-verifiers"
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="correlated_verifiers", rationale="Two verifier votes share the generator ancestor.", oracles=(_oracle(sid, "vote-1", ancestor="model:generator"), _oracle(sid, "vote-2", ancestor="model:generator"))))

    for index, name in enumerate(("provenance", "control", "acquisition", "interpretation")):
        axes = [True, True, True, True]
        axes[index] = False
        sid = f"unsafe-axis-{name}"
        rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class=f"independence_{name}", rationale=f"Oracle fails {name} independence.", oracles=(_oracle(sid, "axis-a", axes=tuple(axes)), _oracle(sid, "axis-b", ancestor="model:external-b", axes=tuple(axes)))))

    rows.append(_scenario("unsafe-no-oracle", ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="missing_oracle", rationale="Replication is not independently adjudicated.", oracles=()))

    sid = "unsafe-inadmissible-oracle"
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="oracle_admissibility", rationale="Oracles are explicitly inadmissible.", oracles=(_oracle(sid, "bad-a", admissible=False), _oracle(sid, "bad-b", ancestor="model:external-b", admissible=False))))

    sid = "unsafe-wrong-claim-oracle"
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="oracle_binding", rationale="Verifier evidence is bound to another claim.", oracles=(_oracle(sid, "wrong-a", bound_claim_id="other-claim"), _oracle(sid, "wrong-b", ancestor="model:external-b", bound_claim_id="other-claim"))))

    for kind in (EvidenceKind.REPLICATION, EvidenceKind.REPLAY, EvidenceKind.PROVENANCE):
        sid = f"unsafe-missing-{kind.value.lower()}"
        evidence = tuple(e for e in _evidence(sid, ClaimState.REPLICATED) if e.kind is not kind)
        rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="missing_evidence", rationale=f"Required {kind.value} artifact is missing.", evidence=evidence))

    rows.append(_scenario("unsafe-falsifier-not-executed", ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="falsifier_not_executed", rationale="A falsifier was defined but never executed.", falsifier=False))

    for index, kind in enumerate((NegativeEvidenceKind.REPLAY_MISMATCH, NegativeEvidenceKind.EXTERNAL_ORACLE_DISAGREEMENT)):
        sid = f"unsafe-active-negative-{index}"
        rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="active_negative_evidence", rationale=f"Unresolved blocking negative evidence exists: {kind.value}.", negative=(_negative(sid, kind),)))

    for target, missing in (
        (ClaimState.BOUNDED, EvidenceKind.NULL_COMPARISON),
        (ClaimState.BOUNDED, EvidenceKind.BOUNDARY),
        (ClaimState.TRANSFER_TESTED, EvidenceKind.TRANSFER_TEST),
    ):
        sid = f"unsafe-{target.value.lower()}-missing-{missing.value.lower()}"
        current = ClaimState.REPLICATED if target is ClaimState.BOUNDED else ClaimState.BOUNDED
        evidence = tuple(e for e in _evidence(sid, target) if e.kind is not missing)
        rows.append(_scenario(sid, current, target, safe=False, failure_class="missing_evidence", rationale=f"{target.value} attempted without {missing.value}.", evidence=evidence))

    sid = "unsafe-cross-claim-evidence"
    evidence = list(_evidence(sid, ClaimState.REPLICATED))
    evidence[0] = replace(evidence[0], claim_id="other-claim")
    rows.append(_scenario(sid, ClaimState.OBSERVED, ClaimState.REPLICATED, safe=False, failure_class="cross_claim_evidence", rationale="One required artifact belongs to another claim.", evidence=tuple(evidence)))

    ids = [row.scenario_id for row in rows]
    if len(rows) != 31 or len(ids) != len(set(ids)):
        raise AssertionError("canonical core benchmark must contain 31 unique scenarios")
    return tuple(rows)


def build_repository_negative_probes(repo_root: str | Path) -> tuple[PromotionScenario, ...]:
    """Project preserved GeoSync negatives into bounded-promotion blocking probes."""
    import yaml

    root = Path(repo_root)
    raw = yaml.safe_load((root / "governance" / "NEGATIVE_EVIDENCE.yaml").read_text(encoding="utf-8"))
    kind_map = {
        "failed_null_comparison": NegativeEvidenceKind.FAILED_NULL_COMPARISON,
        "invalid_input": NegativeEvidenceKind.INVALID_INPUT,
        "calibration_miss": NegativeEvidenceKind.CALIBRATION_MISS,
        "replay_mismatch": NegativeEvidenceKind.REPLAY_MISMATCH,
    }
    rows: list[PromotionScenario] = []
    for entry in raw.get("entries", []):
        category = str(entry["category"])
        if category not in kind_map:
            continue
        sid = f"repo-negative:{entry['id']}"
        neg = NegativeEvidence(
            f"neg:{entry['id']}",
            kind_map[category],
            f"sha:{entry['sha']}",
            sid,
            blocking=True,
            resolved=False,
            note=str(entry.get("description", "")),
        )
        rows.append(_scenario(sid, ClaimState.REPLICATED, ClaimState.BOUNDED, safe=False, failure_class=f"repository_negative:{category}", rationale="A preserved repository negative blocks stronger bounded promotion until resolved.", negative=(neg,), source_ref=str(entry["artifact"])))
    return tuple(rows)


def run_policy(policy: PromotionPolicy, scenarios: Sequence[PromotionScenario]) -> PolicyMetrics:
    safe_cases = sum(s.safe_to_promote for s in scenarios)
    unsafe_cases = len(scenarios) - safe_cases
    unsafe_promotions = false_blocks = correct = 0
    for scenario in scenarios:
        allowed = policy.decide(scenario).allowed
        unsafe_promotions += int(allowed and not scenario.safe_to_promote)
        false_blocks += int(not allowed and scenario.safe_to_promote)
        correct += int(allowed == scenario.safe_to_promote)
    return PolicyMetrics(policy.name, len(scenarios), safe_cases, unsafe_cases, unsafe_promotions, false_blocks, correct)


def default_policies() -> tuple[PromotionPolicy, ...]:
    return (
        RequiredEvidenceBaseline(),
        SelfReviewBaseline(),
        MultiAgentVoteBaseline(),
        ArtifactChainBaseline(),
        ECPASNoNegativeAblation(),
        ECPASNoLineageAblation(),
        ECPASPolicy(),
    )


def run_benchmark(
    scenarios: Sequence[PromotionScenario],
    policies: Iterable[PromotionPolicy] | None = None,
) -> tuple[PolicyMetrics, ...]:
    return tuple(run_policy(policy, scenarios) for policy in tuple(policies or default_policies()))
