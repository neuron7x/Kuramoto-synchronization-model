# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Public API for the Kuramoto simulation subsystem.

Core engine:
    :class:`KuramotoConfig` — validated inputs
    :class:`KuramotoEngine` — deterministic RK4 integrator
    :class:`KuramotoResult` — typed outputs
    :func:`run_simulation` — one-shot convenience

Extended engines (Google/DeepMind-grade):
    :class:`JaxKuramotoEngine` — XLA-compiled GPU/TPU acceleration (jax.jit + vmap)
    :class:`SparseKuramotoEngine` — O(E) sparse coupling for million-node networks
    :class:`AdaptiveKuramotoEngine` — Dormand-Prince / LSODA adaptive step control
    :class:`DelayedKuramotoEngine` — DDE with time-delayed coupling τ_ij
    :class:`SecondOrderKuramotoEngine` — inertia + damping (swing equation)
    :class:`EarlyStoppingEngine` — convergence-based early termination

Analysis:
    :class:`PhaseTransitionAnalyzer` — automatic K_c bifurcation detection
"""

from __future__ import annotations

from .adaptive import AdaptiveKuramotoEngine
from .causal_validation import (
    CausalValidationConfig,
    CausalValidationReport,
    compare_to_coupling,
    lag_granger_causality,
    pcmci_causality,
)
from .config import KuramotoConfig
from .contracts import (
    CouplingMatrix,
    DelayMatrix,
    EmergentMetrics,
    FrustrationMatrix,
    NetworkState,
    PhaseMatrix,
    SyntheticGroundTruth,
)
from .coupling_estimator import (
    CouplingEstimationConfig,
    CouplingEstimator,
    complementary_pairs_stability,
    estimate_coupling,
    mcp_prox,
    scad_prox,
    soft_threshold,
)
from .coupling_spec import (
    CLAIM_ATTRACTIVE,
    CLAIM_SIGNED,
    CouplingMode,
    CouplingSpec,
)
from .delay_estimator import (
    DelayEstimationConfig,
    DelayEstimator,
    estimate_delays,
)
from .delayed import DelayedKuramotoEngine
from .dynamic_graph import (
    DynamicGraphConfig,
    DynamicGraphEstimator,
    detect_breakpoints,
)
from .early_stopping import EarlyStoppingEngine
from .engine import KuramotoEngine, KuramotoResult, run_simulation
from .falsification import (
    SurrogateResult,
    counterfactual_hub_removal,
    counterfactual_zero_delays,
    counterfactual_zero_inhibition,
    iaaft_surrogate,
    iaaft_surrogate_test,
    time_shuffle_test,
)
from .feature import FeatureConfig, NetworkKuramotoFeature
from .frustration import (
    FrustrationEstimationConfig,
    FrustrationEstimator,
    estimate_frustration,
)
from .metrics import (
    MetricsConfig,
    chimera_index,
    compute_metrics,
    order_parameter,
    permutation_entropy,
    rolling_csd,
    signed_communities,
)
from .natural_frequency import (
    estimate_natural_frequencies,
    estimate_natural_frequencies_from_theta,
)
from .network_engine import (
    NetworkEngineConfig,
    NetworkEngineReport,
    NetworkKuramotoEngine,
)
from .oos_validation import (
    OOSConfig,
    OOSResult,
    diebold_mariano_test,
    evaluate_oos,
    simulate_forward,
    spa_test,
    temporal_split,
    walk_forward_evaluate,
)
from .phase_extractor import (
    OptionalDependencyError,
    PhaseExtractionConfig,
    PhaseExtractor,
    cross_method_agreement,
    extract_phases_hilbert,
)
from .phase_transition import PhaseTransitionAnalyzer, PhaseTransitionReport
from .ricci_flow_engine import KuramotoRicciFlowEngine, KuramotoRicciFlowResult
from .second_order import SecondOrderKuramotoEngine, SecondOrderResult
from .sparse import SparseKuramotoEngine
from .synthetic import (
    AlphaStructure,
    SyntheticConfig,
    generate_sakaguchi_kuramoto,
)

__all__ = [
    # Core
    "KuramotoConfig",
    "KuramotoEngine",
    "KuramotoResult",
    "run_simulation",
    # Extended engines
    "AdaptiveKuramotoEngine",
    "SparseKuramotoEngine",
    "DelayedKuramotoEngine",
    "SecondOrderKuramotoEngine",
    "SecondOrderResult",
    "EarlyStoppingEngine",
    "KuramotoRicciFlowEngine",
    "KuramotoRicciFlowResult",
    # Analysis
    "PhaseTransitionAnalyzer",
    "PhaseTransitionReport",
    # Inverse-problem contracts (M1.1)
    "PhaseMatrix",
    "CouplingMatrix",
    "DelayMatrix",
    "FrustrationMatrix",
    "NetworkState",
    "EmergentMetrics",
    "SyntheticGroundTruth",
    # Phase extraction (M1.2)
    "PhaseExtractor",
    "PhaseExtractionConfig",
    "OptionalDependencyError",
    "extract_phases_hilbert",
    "cross_method_agreement",
    # Coupling estimation (M1.3)
    "CouplingEstimator",
    "CouplingEstimationConfig",
    "estimate_coupling",
    "complementary_pairs_stability",
    "mcp_prox",
    "scad_prox",
    "soft_threshold",
    # Coupling representation contract (Stream 1 — coupling appears once)
    "CouplingSpec",
    "CouplingMode",
    "CLAIM_ATTRACTIVE",
    "CLAIM_SIGNED",
    # M1.4 — Natural frequency
    "estimate_natural_frequencies",
    "estimate_natural_frequencies_from_theta",
    # M2.1 — Delay estimation
    "DelayEstimator",
    "DelayEstimationConfig",
    "estimate_delays",
    # M2.2 — Frustration
    "FrustrationEstimator",
    "FrustrationEstimationConfig",
    "estimate_frustration",
    # M2.3 — Dynamic graph
    "DynamicGraphEstimator",
    "DynamicGraphConfig",
    "detect_breakpoints",
    # M2.4 — Emergent metrics
    "MetricsConfig",
    "compute_metrics",
    "order_parameter",
    "chimera_index",
    "rolling_csd",
    "signed_communities",
    "permutation_entropy",
    # M3.1 — Synthetic ground truth
    "SyntheticConfig",
    "AlphaStructure",
    "generate_sakaguchi_kuramoto",
    # M3.2 — Falsification
    "SurrogateResult",
    "iaaft_surrogate",
    "iaaft_surrogate_test",
    "time_shuffle_test",
    "counterfactual_hub_removal",
    "counterfactual_zero_inhibition",
    "counterfactual_zero_delays",
    # Orchestrator
    "NetworkKuramotoEngine",
    "NetworkEngineConfig",
    "NetworkEngineReport",
    # M3.4 — Trading feature
    "NetworkKuramotoFeature",
    "FeatureConfig",
    # M1.5 — Causal validation
    "CausalValidationReport",
    "CausalValidationConfig",
    "lag_granger_causality",
    "pcmci_causality",
    "compare_to_coupling",
    # M3.3 — OOS validation
    "OOSConfig",
    "OOSResult",
    "temporal_split",
    "simulate_forward",
    "diebold_mariano_test",
    "spa_test",
    "evaluate_oos",
    "walk_forward_evaluate",
]

# JAX engine is optional (requires jax + jaxlib)
try:
    from .jax_engine import JAX_AVAILABLE, JaxKuramotoEngine

    __all__ += ["JaxKuramotoEngine", "JAX_AVAILABLE"]
except ImportError:
    JAX_AVAILABLE = False
