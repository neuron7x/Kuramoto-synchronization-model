"""Top-level TradePulse namespace."""

import os

# Provide benign defaults so importing the SDK in development environments
# does not fail when sensitive configuration is absent. Real deployments
# override these via environment variables or configuration files.
os.environ.setdefault("TRADEPULSE_TWO_FACTOR_SECRET", "test-secret")
os.environ.setdefault("ADMIN_API_SETTINGS__two_factor_secret", "test-secret")
os.environ.setdefault("TRADEPULSE_BOOTSTRAP_STRATEGY", "lazy")

from .integration import (
    AgentCoordinatorAdapter,
    IntegrationConfig,
    ServiceRegistryAdapter,
    SystemIntegrator,
    SystemIntegratorBuilder,
)
from .protocol import (
    DivConvSignal,
    DivConvSnapshot,
    aggregate_signals,
    compute_divergence_functional,
    compute_kappa,
    compute_price_gradient,
    compute_theta,
    compute_threshold_tau_c,
    compute_threshold_tau_d,
    compute_time_warp_invariant_metric,
)
from .sdk import (
    AuditEvent,
    ExecutionResult,
    MarketState,
    RiskCheckResult,
    SDKConfig,
    SuggestedOrder,
    TradePulseSDK,
)

__all__ = [
    # Integration
    "AgentCoordinatorAdapter",
    "IntegrationConfig",
    "ServiceRegistryAdapter",
    "SystemIntegrator",
    "SystemIntegratorBuilder",
    # Protocol
    "DivConvSignal",
    "DivConvSnapshot",
    "aggregate_signals",
    "compute_divergence_functional",
    "compute_kappa",
    "compute_price_gradient",
    "compute_theta",
    "compute_threshold_tau_c",
    "compute_threshold_tau_d",
    "compute_time_warp_invariant_metric",
    # SDK
    "TradePulseSDK",
    "SDKConfig",
    "MarketState",
    "SuggestedOrder",
    "RiskCheckResult",
    "ExecutionResult",
    "AuditEvent",
]
