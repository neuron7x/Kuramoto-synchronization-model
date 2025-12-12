"""Top-level TradePulse namespace with lazy attribute loading."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_ATTR_TO_MODULE = {
    # Integration
    "AgentCoordinatorAdapter": "tradepulse.integration",
    "IntegrationConfig": "tradepulse.integration",
    "ServiceRegistryAdapter": "tradepulse.integration",
    "SystemIntegrator": "tradepulse.integration",
    "SystemIntegratorBuilder": "tradepulse.integration",
    # Protocol
    "DivConvSignal": "tradepulse.protocol",
    "DivConvSnapshot": "tradepulse.protocol",
    "aggregate_signals": "tradepulse.protocol",
    "compute_divergence_functional": "tradepulse.protocol",
    "compute_kappa": "tradepulse.protocol",
    "compute_price_gradient": "tradepulse.protocol",
    "compute_theta": "tradepulse.protocol",
    "compute_threshold_tau_c": "tradepulse.protocol",
    "compute_threshold_tau_d": "tradepulse.protocol",
    "compute_time_warp_invariant_metric": "tradepulse.protocol",
    # SDK
    "TradePulseSDK": "tradepulse.sdk",
    "SDKConfig": "tradepulse.sdk",
    "MarketState": "tradepulse.sdk",
    "SuggestedOrder": "tradepulse.sdk",
    "RiskCheckResult": "tradepulse.sdk",
    "ExecutionResult": "tradepulse.sdk",
    "AuditEvent": "tradepulse.sdk",
}

__all__ = list(_ATTR_TO_MODULE)


def __getattr__(name: str) -> Any:
    module_path = _ATTR_TO_MODULE.get(name)
    if module_path is None:
        raise AttributeError(name)
    module = import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value
