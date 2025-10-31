"""Top-level TradePulse namespace."""

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
    "TradePulseSDK",
    "SDKConfig",
    "MarketState",
    "SuggestedOrder",
    "RiskCheckResult",
    "ExecutionResult",
    "AuditEvent",
]
