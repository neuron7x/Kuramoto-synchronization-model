"""Microservice-oriented façade for TradePulse subsystems."""

from .base import Microservice, ServiceHealth, ServiceState
from .contracts import ExecutionRequest, MarketDataSource, StrategyRun
from .market_data import MarketDataService
from .backtesting import BacktestingService
from .execution import ExecutionService
from .registry import ServiceRegistry

__all__ = [
    "BacktestingService",
    "ExecutionRequest",
    "ExecutionService",
    "MarketDataService",
    "MarketDataSource",
    "Microservice",
    "ServiceHealth",
    "ServiceRegistry",
    "ServiceState",
    "StrategyRun",
]
