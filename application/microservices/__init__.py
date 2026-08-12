# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microservice-oriented façade for GeoSync subsystems."""

from .backtesting import BacktestingService
from .base import Microservice, ServiceHealth, ServiceState
from .contracts import (
    ExecutionRequest,
    IntegrationContractRegistry,
    MarketDataSource,
    StrategyRun,
    default_contract_registry,
)
from .execution import ExecutionService
from .market_data import MarketDataService
from .registry import ServiceRegistry

__all__ = [
    "BacktestingService",
    "ExecutionRequest",
    "ExecutionService",
    "MarketDataService",
    "MarketDataSource",
    "Microservice",
    "IntegrationContractRegistry",
    "ServiceHealth",
    "ServiceRegistry",
    "ServiceState",
    "StrategyRun",
    "default_contract_registry",
]
