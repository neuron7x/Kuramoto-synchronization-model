# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Application layer bridging domain entities to upper layers."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = [
    "BacktestingService",
    "ExecutionRequest",
    "ExecutionService",
    "ExchangeAdapterConfig",
    "LiveLoopSettings",
    "MarketDataSource",
    "MarketDataService",
    "ServiceHealth",
    "ServiceRegistry",
    "ServiceState",
    "StrategyRun",
    "GeoSyncOrchestrator",
    "GeoSyncSystem",
    "GeoSyncSystemConfig",
    "build_geosync_system",
    "order_to_dto",
    "position_to_dto",
    "signal_to_dto",
]

# Delay importing heavyweight modules (e.g., neuro adapters, torch) until the
# corresponding symbols are actually accessed. This keeps lightweight helpers
# like `application.api.service` usable in environments where optional
# dependencies are not installed (e.g., unit tests that only exercise DTO
# models).
_IMPORT_MAP: dict[str, tuple[str, str]] = {
    "BacktestingService": ("application.microservices", "BacktestingService"),
    "ExecutionRequest": ("application.microservices", "ExecutionRequest"),
    "ExecutionService": ("application.microservices", "ExecutionService"),
    "MarketDataService": ("application.microservices", "MarketDataService"),
    "MarketDataSource": ("application.microservices", "MarketDataSource"),
    "ServiceHealth": ("application.microservices", "ServiceHealth"),
    "ServiceRegistry": ("application.microservices", "ServiceRegistry"),
    "ServiceState": ("application.microservices", "ServiceState"),
    "StrategyRun": ("application.microservices", "StrategyRun"),
    "ExchangeAdapterConfig": ("application.system", "ExchangeAdapterConfig"),
    "LiveLoopSettings": ("application.system", "LiveLoopSettings"),
    "GeoSyncSystem": ("application.system", "GeoSyncSystem"),
    "GeoSyncSystemConfig": ("application.system", "GeoSyncSystemConfig"),
    "GeoSyncOrchestrator": (
        "application.system_orchestrator",
        "GeoSyncOrchestrator",
    ),
    "build_geosync_system": (
        "application.system_orchestrator",
        "build_geosync_system",
    ),
    "order_to_dto": ("application.trading", "order_to_dto"),
    "position_to_dto": ("application.trading", "position_to_dto"),
    "signal_to_dto": ("application.trading", "signal_to_dto"),
}


def __getattr__(name: str) -> Any:
    """Lazily import application symbols to avoid hard dependencies at import time."""

    module_attr = _IMPORT_MAP.get(name)
    if module_attr:
        module_name, attr_name = module_attr
        module = importlib.import_module(module_name)
        attr = getattr(module, attr_name)
        globals()[name] = attr
        return attr
    raise AttributeError(f"module 'application' has no attribute '{name}'")
