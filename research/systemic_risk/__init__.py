# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Systemic-risk-as-phase-transition research module — v2.

Pre-registered falsification of the hypothesis that interbank
phase-locking precedes banking-crisis events. All claims under
``CLAIMS.md`` are ``HYPOTHESIS`` tier until the v2 battery returns
``HARD_PASS`` on >= 2 independent crises with real interbank
exposure data and a bootstrap-CI lower bound clearing 0.70.

Layer in the maintenance hierarchy: this module is a *Sustainer*
diagnostic — it reports approach to the Kuramoto bifurcation
without taking any execution action.
"""

from __future__ import annotations

from .adversarial_ladder import (
    LADDER_RUNGS,
    LadderConfig,
    LadderReport,
    ParameterFragilityReport,
    ProsecutorOutcome,
    ProsecutorScore,
    parameter_fragility_audit,
    run_adversarial_ladder,
    run_null_audit,
)
from .baselines import (
    edge_density_score,
    rolling_volatility_score,
)
from .bayes_rigorous import (
    ASYMPTOTIC_BIC_PENALTY,
    auc_per_crisis_bf_rigorous,
    auc_to_z_under_null,
    cramer_rao_alpha_lower_bound,
    derive_kill_threshold_log_odds,
    mann_whitney_effective_n,
    mann_whitney_null_variance,
    wagenmakers_bic_bayes_factor,
)
from .canonical_seven import (
    CanonicalSevenInputs,
    CanonicalSevenOutcome,
    run_canonical_seven,
)
from .coupling import (
    coupling_from_exposures,
    omega_from_volatility,
    sakaguchi_alpha_zero,
)
from .critical_slowing_down import (
    CSDConfig,
    CSDIndicators,
    compute_csd_indicators,
)
from .data_firewall import (
    FIREWALL_GATES,
    PROVENANCE_SCHEMA_VERSION,
    DataFirewallReport,
    GateName,
    GateOutcome,
    Provenance,
    gate_diagonal,
    gate_finite,
    gate_monotonic_time,
    gate_provenance,
    gate_schema_type,
    gate_shape,
    gate_sign,
    gate_sparsity,
    run_data_firewall,
)
from .death_conditions import (
    DataFirewallResultLike,
    DeathConditionsRegistry,
    DeathState,
    FragilityResultLike,
    LadderResultLike,
    LeakageResultLike,
    ReplicationResultLike,
    TierAction,
    TierTransition,
    Trigger,
    TriggerOutcome,
    default_registry,
    trigger_baseline_dominance,
    trigger_data_proxy_invalid,
    trigger_leakage_positive,
    trigger_parameter_fragility,
    trigger_replication_mismatch,
)
from .early_warning import (
    EarlyWarningConfig,
    EarlyWarningResult,
    compute_early_warning,
    kuramoto_order_parameter,
)
from .errors import (
    InvalidExposureMatrixError,
    InvalidNodeLabelsError,
    InvalidTemporalPanelError,
    SystemicRiskInputError,
)
from .event_ledger import (
    DEFAULT_LEDGER,
    BankingCrisisEvent,
    BankingCrisisLedger,
)
from .evidence_ledger import (
    DEFAULT_PRIOR_LOG_ODDS,
    DOWNGRADE_TRIGGER_DELTA,
    KILL_TRIGGER_LOG_ODDS,
    Evidence,
    EvidenceLedger,
    EvidenceType,
    LedgerEntry,
    auc_per_crisis_bayes_factor,
    baseline_dominance_bayes_factor,
    external_review_bayes_factor,
    replication_match_bayes_factor,
)
from .falsification import (
    CrisisOutcome,
    FalsificationConfig,
    FalsificationReport,
    auc_bootstrap_ci,
    auc_mann_whitney,
    bonferroni_correction,
    run_end_to_end_falsification,
    run_falsification,
    run_score_level_falsification,
)
from .governance import (
    FORBIDDEN_OVERCLAIM_TERMS,
    PremergeGateReport,
    ValidationReadinessReport,
    assert_claim_tier,
    build_validation_readiness_report,
    run_premerge_science_gate,
)
from .governance_fsm import (
    INITIAL_STATE,
    PROMOTABLE_LADDER,
    TERMINAL_STATES,
    GovernanceFSM,
    GovernanceState,
    GovernanceTransitionRecord,
    InvalidTransitionError,
)
from .kuramoto_extensions import (
    ExplosiveSyncReport,
    HigherOrderConfig,
    explosive_sync_sweep,
    sakaguchi_kuramoto_step,
    triadic_kuramoto_step,
)
from .leakage_sentinel import (
    LeakageOutcome,
    LeakageReport,
    LeakageType,
    OpRecord,
    check_centered_windows,
    check_crisis_date_tuning,
    check_full_sample_normalisation,
    check_future_data_via_mutation,
    check_label_leakage,
    check_post_event_contamination,
    run_leakage_audit,
)
from .metrics import (
    ClassificationMetrics,
    LeadTimeConfig,
    LeadTimeMetrics,
    compute_classification_metrics,
    compute_lead_time_metrics,
)
from .minimal import (
    Claim as MinimalClaim,
)
from .minimal import (
    TierAction as MinimalTierAction,
)
from .minimal import (
    evaluate as minimal_evaluate,
)
from .minimal import (
    initial_claim as minimal_initial_claim,
)
from .network_fitting import (
    MIN_RELATIVE_SE_VALIDATION,
    MIN_TAIL_SIZE_VALIDATION,
    ExponentialFit,
    ModelComparison,
    PowerLawFit,
    compare_power_law_vs_exponential,
    fit_barabasi_albert,
    fit_barabasi_albert_from_topology,
    fit_barabasi_albert_validation_from_topology,
    fit_exponential,
    fit_power_law,
    fit_power_law_validation,
)
from .null_models import (
    NullSurrogate,
    degree_preserving_randomization,
    linear_correlation_surrogate,
    permuted_crisis_dates,
    random_exposure_weights,
    shuffled_time_labels,
    static_topology_baseline,
)
from .occam_penalty import (
    aic_penalized_log_likelihood,
    bic_penalized_log_likelihood,
    mdl_penalized_log_likelihood,
    occam_winner,
)
from .phase_extraction import (
    INTERBANK_DEFAULT_BAND,
    interbank_phase_extract,
)
from .quick_round import quick_round
from .real_data_contract import (
    DataContractReport,
    validate_real_data_contract,
)
from .replication import (
    RunManifest,
    build_run_manifest,
)
from .replication_capsule import (
    DEFAULT_BIT_IDENTICAL_TOLERANCE,
    DEFAULT_DETERMINISTIC_TOLERANCE,
    MismatchReason,
    ReplicationOutcome,
    ReplicationToleranceClass,
    compare_run_outputs,
    manifest_replication_sha,
)
from .synthetic import SyntheticPanelConfig, generate_panel
from .temporal_panel import (
    validate_temporal_exposure_panel,
)
from .topology import (
    InterbankTopology,
    barabasi_albert_null,
    from_exposure_matrix,
)
from .verdict_lattice import (
    TierLattice,
    aggregate_actions,
)

__all__ = [
    "ASYMPTOTIC_BIC_PENALTY",
    "BankingCrisisEvent",
    "BankingCrisisLedger",
    "CSDConfig",
    "CSDIndicators",
    "CanonicalSevenInputs",
    "CanonicalSevenOutcome",
    "ClassificationMetrics",
    "CrisisOutcome",
    "DEFAULT_BIT_IDENTICAL_TOLERANCE",
    "DEFAULT_DETERMINISTIC_TOLERANCE",
    "DEFAULT_LEDGER",
    "DEFAULT_PRIOR_LOG_ODDS",
    "DataContractReport",
    "DOWNGRADE_TRIGGER_DELTA",
    "DataFirewallReport",
    "DataFirewallResultLike",
    "DeathConditionsRegistry",
    "DeathState",
    "EarlyWarningConfig",
    "EarlyWarningResult",
    "Evidence",
    "EvidenceLedger",
    "EvidenceType",
    "ExplosiveSyncReport",
    "ExponentialFit",
    "FIREWALL_GATES",
    "FORBIDDEN_OVERCLAIM_TERMS",
    "FalsificationConfig",
    "FalsificationReport",
    "FragilityResultLike",
    "GateName",
    "HigherOrderConfig",
    "GateOutcome",
    "GovernanceFSM",
    "GovernanceState",
    "GovernanceTransitionRecord",
    "INITIAL_STATE",
    "INTERBANK_DEFAULT_BAND",
    "InvalidTransitionError",
    "InterbankTopology",
    "InvalidExposureMatrixError",
    "InvalidNodeLabelsError",
    "InvalidTemporalPanelError",
    "KILL_TRIGGER_LOG_ODDS",
    "LADDER_RUNGS",
    "LadderConfig",
    "LadderReport",
    "LadderResultLike",
    "LeadTimeConfig",
    "LeadTimeMetrics",
    "LeakageOutcome",
    "LeakageReport",
    "LeakageResultLike",
    "LeakageType",
    "LedgerEntry",
    "MIN_RELATIVE_SE_VALIDATION",
    "MIN_TAIL_SIZE_VALIDATION",
    "MismatchReason",
    "MinimalClaim",
    "MinimalTierAction",
    "ModelComparison",
    "NullSurrogate",
    "OpRecord",
    "PROMOTABLE_LADDER",
    "PROVENANCE_SCHEMA_VERSION",
    "ParameterFragilityReport",
    "PowerLawFit",
    "PremergeGateReport",
    "ProsecutorOutcome",
    "ProsecutorScore",
    "Provenance",
    "ReplicationOutcome",
    "ReplicationResultLike",
    "ReplicationToleranceClass",
    "RunManifest",
    "SyntheticPanelConfig",
    "SystemicRiskInputError",
    "TERMINAL_STATES",
    "TierAction",
    "TierLattice",
    "TierTransition",
    "Trigger",
    "TriggerOutcome",
    "ValidationReadinessReport",
    "aggregate_actions",
    "aic_penalized_log_likelihood",
    "assert_claim_tier",
    "auc_bootstrap_ci",
    "auc_mann_whitney",
    "auc_per_crisis_bayes_factor",
    "auc_per_crisis_bf_rigorous",
    "auc_to_z_under_null",
    "barabasi_albert_null",
    "baseline_dominance_bayes_factor",
    "bic_penalized_log_likelihood",
    "bonferroni_correction",
    "build_run_manifest",
    "build_validation_readiness_report",
    "check_centered_windows",
    "check_crisis_date_tuning",
    "check_full_sample_normalisation",
    "check_future_data_via_mutation",
    "check_label_leakage",
    "check_post_event_contamination",
    "compare_power_law_vs_exponential",
    "compare_run_outputs",
    "compute_classification_metrics",
    "compute_csd_indicators",
    "compute_early_warning",
    "compute_lead_time_metrics",
    "coupling_from_exposures",
    "cramer_rao_alpha_lower_bound",
    "default_registry",
    "degree_preserving_randomization",
    "derive_kill_threshold_log_odds",
    "edge_density_score",
    "explosive_sync_sweep",
    "external_review_bayes_factor",
    "fit_barabasi_albert",
    "fit_barabasi_albert_from_topology",
    "fit_barabasi_albert_validation_from_topology",
    "fit_exponential",
    "fit_power_law",
    "fit_power_law_validation",
    "from_exposure_matrix",
    "generate_panel",
    "gate_diagonal",
    "gate_finite",
    "gate_monotonic_time",
    "gate_provenance",
    "gate_schema_type",
    "gate_shape",
    "gate_sign",
    "gate_sparsity",
    "interbank_phase_extract",
    "kuramoto_order_parameter",
    "linear_correlation_surrogate",
    "manifest_replication_sha",
    "mann_whitney_effective_n",
    "mann_whitney_null_variance",
    "mdl_penalized_log_likelihood",
    "minimal_evaluate",
    "minimal_initial_claim",
    "occam_winner",
    "omega_from_volatility",
    "parameter_fragility_audit",
    "permuted_crisis_dates",
    "quick_round",
    "random_exposure_weights",
    "replication_match_bayes_factor",
    "rolling_volatility_score",
    "run_adversarial_ladder",
    "run_canonical_seven",
    "run_data_firewall",
    "run_end_to_end_falsification",
    "run_falsification",
    "run_leakage_audit",
    "run_null_audit",
    "run_premerge_science_gate",
    "run_score_level_falsification",
    "sakaguchi_alpha_zero",
    "sakaguchi_kuramoto_step",
    "shuffled_time_labels",
    "static_topology_baseline",
    "triadic_kuramoto_step",
    "trigger_baseline_dominance",
    "trigger_data_proxy_invalid",
    "trigger_leakage_positive",
    "trigger_parameter_fragility",
    "trigger_replication_mismatch",
    "validate_real_data_contract",
    "validate_temporal_exposure_panel",
    "wagenmakers_bic_bayes_factor",
]
