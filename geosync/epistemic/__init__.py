"""ECP-AS: domain-independent epistemic control plane for autonomous research."""

from .admission import AdmissionController, AdmissionDecision
from .contracts import PromotionContract, default_contracts
from .lineage import IndependenceReport, evaluate_oracle_independence
from .models import (
    Claim, ClaimState, Evidence, EvidenceKind, ExperimentCandidate, NegativeEvidence,
    NegativeEvidenceKind, Oracle, OracleAxis, OracleIndependence, PromotionCertificate,
)
from .scheduler import rank_experiments
from .ledger import HashChainLedger, LedgerEvent
from .runtime import EpistemicRuntime
from .dependencies import DependencyEdge, DependencyGraph, DependencyKind
from .compiler import ClaimContractSpec, compile_structured_claim

from .adjudication import (
    AdjudicationAction, AdjudicationDecision, AdjudicationKind, AuthorityClass,
    DefectClass, ExternalAdjudicationEvent, ExternalAdjudicationPolicy, IndependenceLevel,
)
from .historical_replay import (
    AllEditorialActionsDegradeBaseline, ECPASHistoricalPolicy, HistoricalCase,
    HistoricalDecision, HistoricalMetrics, RetractionEqualsFalsificationBaseline,
    default_historical_policies, load_historical_cases, run_historical_policy,
)

from .benchmark import (
    ArtifactChainBaseline, ECPASNoLineageAblation, ECPASNoNegativeAblation,
    ECPASPolicy, MultiAgentVoteBaseline, PolicyDecision, PolicyMetrics,
    PromotionScenario, RequiredEvidenceBaseline, SelfReviewBaseline,
    build_core_scenarios, build_repository_negative_probes, default_policies,
    run_benchmark, run_policy,
)

__all__ = [
    "AdmissionController", "AdmissionDecision", "PromotionContract", "default_contracts",
    "IndependenceReport", "evaluate_oracle_independence", "Claim", "ClaimState",
    "Evidence", "EvidenceKind", "ExperimentCandidate", "NegativeEvidence",
    "NegativeEvidenceKind", "Oracle", "OracleAxis", "OracleIndependence",
    "PromotionCertificate", "rank_experiments", "PromotionScenario", "PolicyDecision", "PolicyMetrics",
    "RequiredEvidenceBaseline", "SelfReviewBaseline", "MultiAgentVoteBaseline", "ArtifactChainBaseline",
    "ECPASNoNegativeAblation", "ECPASNoLineageAblation", "ECPASPolicy",
    "build_core_scenarios", "build_repository_negative_probes", "default_policies", "run_benchmark", "run_policy", "HashChainLedger", "LedgerEvent", "EpistemicRuntime", "DependencyEdge", "DependencyGraph", "DependencyKind", "ClaimContractSpec", "compile_structured_claim",
    "AdjudicationAction", "AdjudicationDecision", "AdjudicationKind", "AuthorityClass", "DefectClass", "ExternalAdjudicationEvent", "ExternalAdjudicationPolicy", "IndependenceLevel",
    "HistoricalCase", "HistoricalDecision", "HistoricalMetrics", "RetractionEqualsFalsificationBaseline", "AllEditorialActionsDegradeBaseline", "ECPASHistoricalPolicy", "default_historical_policies", "load_historical_cases", "run_historical_policy",
]
