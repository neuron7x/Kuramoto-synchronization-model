"""Utilities for assembling and running end-to-end TradePulse pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from analytics.signals.pipeline import FeaturePipelineConfig
from application.microservices.backtesting import BacktestingService
from application.microservices.contracts import (
    ExecutionRequest,
    MarketDataSource,
    StrategyCallable,
    StrategyRun,
)
from application.microservices.execution import ExecutionService
from application.microservices.market_data import MarketDataService
from application.microservices.registry import ServiceRegistry
from application.system import (
    ExchangeAdapterConfig,
    LiveLoopSettings,
    TradePulseSystem,
    TradePulseSystemConfig,
)
from domain import Order
from execution.connectors import BinanceConnector, CoinbaseConnector
from execution.risk import RiskLimits

def build_tradepulse_system(
    venues: Sequence[ExchangeAdapterConfig] | None = None,
    *,
    feature_pipeline: FeaturePipelineConfig | None = None,
    risk_limits: RiskLimits | None = None,
    live_settings: LiveLoopSettings | None = None,
    allowed_data_roots: Iterable[str | Path] | None = None,
    max_csv_bytes: int | None = None,
) -> TradePulseSystem:
    """Return a ready-to-use :class:`TradePulseSystem` instance.

    The helper provides sensible defaults so tests and prototypes can stand up a
    full pipeline with a couple of lines of code while still allowing callers to
    supply bespoke connectors, feature pipelines, or risk limits when required.
    """

    if venues is None:
        venues = (
            ExchangeAdapterConfig(name="binance", connector=BinanceConnector()),
            ExchangeAdapterConfig(name="coinbase", connector=CoinbaseConnector()),
        )

    pipeline_config = feature_pipeline or FeaturePipelineConfig()
    risk = risk_limits or RiskLimits()
    live = live_settings or LiveLoopSettings()

    config = TradePulseSystemConfig(
        venues=tuple(venues),
        feature_pipeline=pipeline_config,
        risk_limits=risk,
        live_settings=live,
        allowed_data_roots=allowed_data_roots,
        max_csv_bytes=max_csv_bytes,
    )
    return TradePulseSystem(config)


class TradePulseOrchestrator:
    """High-level façade that wires ingestion, analytics, and execution."""

    def __init__(
        self,
        system: TradePulseSystem,
        *,
        services: ServiceRegistry | None = None,
    ) -> None:
        self._system = system
        self._services = services or ServiceRegistry.from_system(system)
        self._services.ensure_started()
        self._market_data = self._services.market_data
        self._backtesting = self._services.backtesting
        self._execution = self._services.execution

    @property
    def system(self) -> TradePulseSystem:
        """Expose the underlying :class:`TradePulseSystem`."""

        return self._system

    @property
    def services(self) -> ServiceRegistry:
        """Return the service registry coordinating the microservices."""

        return self._services

    @property
    def market_data_service(self) -> MarketDataService:
        """Expose the market data microservice."""

        return self._market_data

    @property
    def backtesting_service(self) -> BacktestingService:
        """Expose the backtesting microservice."""

        return self._backtesting

    @property
    def execution_service(self) -> ExecutionService:
        """Expose the execution microservice."""

        return self._execution

    def ingest_market_data(self, source: MarketDataSource) -> pd.DataFrame:
        """Load a CSV data source into a normalised OHLCV frame."""

        return self._market_data.ingest(source)

    def build_features(self, market_frame: pd.DataFrame) -> pd.DataFrame:
        """Return a feature-enriched frame derived from *market_frame*."""

        return self._market_data.build_features(market_frame)

    def run_strategy(
        self,
        source: MarketDataSource,
        strategy: StrategyCallable,
    ) -> StrategyRun:
        """Execute the canonical ingestion → features → strategy pipeline."""

        return self._backtesting.run_backtest(source, strategy=strategy)

    def submit_signal(self, request: ExecutionRequest) -> Order:
        """Forward a signal to execution and return the resulting order."""

        return self._execution.submit(request)

    def ensure_live_loop(self) -> None:
        """Ensure the live loop has been instantiated."""

        self._execution.ensure_live_loop()


__all__ = [
    "ExecutionRequest",
    "MarketDataSource",
    "StrategyRun",
    "TradePulseOrchestrator",
    "build_tradepulse_system",
]
