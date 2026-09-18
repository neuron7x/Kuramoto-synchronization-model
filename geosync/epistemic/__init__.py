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

from .evaluator_control import (
    EvaluatorObservation, LineageQuorumPolicy, QuorumAction, QuorumDecision,
    synthesize_quorum_oracle,
)

from .dependence_bounds import (
    EvaluatorMarginal, QuorumRiskBounds, RobustQuorumCertificate,
    RiskCertifiedLineageQuorumPolicy, certify_quorum, quorum_risk_bounds,
    search_triplet_quorums,
)
from .soundness_stress import (
    JudgeProfile, SoundnessCase, StressMetrics, default_profiles, evaluate_profile,
    load_soundness_slice, run_stress_suite,
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
    "EvaluatorObservation", "LineageQuorumPolicy", "QuorumAction", "QuorumDecision",
    "synthesize_quorum_oracle", "JudgeProfile", "SoundnessCase", "StressMetrics",
    "default_profiles", "evaluate_profile", "load_soundness_slice", "run_stress_suite",
    "EvaluatorMarginal", "QuorumRiskBounds", "RobustQuorumCertificate",
    "RiskCertifiedLineageQuorumPolicy", "certify_quorum", "quorum_risk_bounds",
    "search_triplet_quorums",
]

from .rational_certificates import (
    RationalQuorumCertificate, CertificateVerification,
    event_indicator, verify_rational_certificate, iteration_006_certificates,
)
__all__ += [
    "RationalQuorumCertificate", "CertificateVerification", "event_indicator",
    "verify_rational_certificate", "iteration_006_certificates",
]

from .quorum_viability import (
    ExactEvaluatorMarginal, ExactQuorumInterval, ViabilityStatus, ViabilityVerdict,
    classify_viability, exact_kof3_event_bounds, exact_quorum_interval,
    load_exact_marginals, scan_distinct_model_triplets,
)

__all__ += [
    "ExactEvaluatorMarginal", "ExactQuorumInterval", "ViabilityStatus", "ViabilityVerdict",
    "classify_viability", "exact_kof3_event_bounds", "exact_quorum_interval",
    "load_exact_marginals", "scan_distinct_model_triplets",
]
