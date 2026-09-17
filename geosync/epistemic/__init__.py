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

__all__ = [
    "AdmissionController", "AdmissionDecision", "PromotionContract", "default_contracts",
    "IndependenceReport", "evaluate_oracle_independence", "Claim", "ClaimState",
    "Evidence", "EvidenceKind", "ExperimentCandidate", "NegativeEvidence",
    "NegativeEvidenceKind", "Oracle", "OracleAxis", "OracleIndependence",
    "PromotionCertificate", "rank_experiments", "HashChainLedger", "LedgerEvent", "EpistemicRuntime", "DependencyEdge", "DependencyGraph", "DependencyKind", "ClaimContractSpec", "compile_structured_claim",
]
