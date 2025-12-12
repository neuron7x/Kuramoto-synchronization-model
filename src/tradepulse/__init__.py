"""Top-level TradePulse namespace."""

from __future__ import annotations

import importlib
from typing import Dict, Tuple

_EXPORTS: Dict[str, Tuple[str, str]] = {
    # Integration
    "AgentCoordinatorAdapter": (".integration", "AgentCoordinatorAdapter"),
    "IntegrationConfig": (".integration", "IntegrationConfig"),
    "ServiceRegistryAdapter": (".integration", "ServiceRegistryAdapter"),
    "SystemIntegrator": (".integration", "SystemIntegrator"),
    "SystemIntegratorBuilder": (".integration", "SystemIntegratorBuilder"),
    # Protocol
    "DivConvSignal": (".protocol", "DivConvSignal"),
    "DivConvSnapshot": (".protocol", "DivConvSnapshot"),
    "aggregate_signals": (".protocol", "aggregate_signals"),
    "compute_divergence_functional": (".protocol", "compute_divergence_functional"),
    "compute_kappa": (".protocol", "compute_kappa"),
    "compute_price_gradient": (".protocol", "compute_price_gradient"),
    "compute_theta": (".protocol", "compute_theta"),
    "compute_threshold_tau_c": (".protocol", "compute_threshold_tau_c"),
    "compute_threshold_tau_d": (".protocol", "compute_threshold_tau_d"),
    "compute_time_warp_invariant_metric": (
        ".protocol",
        "compute_time_warp_invariant_metric",
    ),
    # SDK
    "TradePulseSDK": (".sdk", "TradePulseSDK"),
    "SDKConfig": (".sdk", "SDKConfig"),
    "MarketState": (".sdk", "MarketState"),
    "SuggestedOrder": (".sdk", "SuggestedOrder"),
    "RiskCheckResult": (".sdk", "RiskCheckResult"),
    "ExecutionResult": (".sdk", "ExecutionResult"),
    "AuditEvent": (".sdk", "AuditEvent"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module = importlib.import_module(target[0], __name__)
    value = getattr(module, target[1])
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(__all__))
