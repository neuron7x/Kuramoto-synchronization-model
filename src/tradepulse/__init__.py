"""Top-level TradePulse namespace with lazy exports to avoid heavy dependencies."""

from __future__ import annotations

from importlib import import_module
from typing import Any

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


_INTEGRATION_EXPORTS = {
    "AgentCoordinatorAdapter",
    "IntegrationConfig",
    "ServiceRegistryAdapter",
    "SystemIntegrator",
    "SystemIntegratorBuilder",
}
_PROTOCOL_EXPORTS = {
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
}
_SDK_EXPORTS = {
    "TradePulseSDK",
    "SDKConfig",
    "MarketState",
    "SuggestedOrder",
    "RiskCheckResult",
    "ExecutionResult",
    "AuditEvent",
}


def __getattr__(name: str) -> Any:
    if name in _INTEGRATION_EXPORTS:
        module = import_module("tradepulse.integration")
        return getattr(module, name)
    if name in _PROTOCOL_EXPORTS:
        module = import_module("tradepulse.protocol")
        return getattr(module, name)
    if name in _SDK_EXPORTS:
        module = import_module("tradepulse.sdk")
        return getattr(module, name)
    raise AttributeError(name)
