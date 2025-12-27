"""Utilities for assembling and running end-to-end TradePulse pipelines."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterable, Mapping, Sequence

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

if TYPE_CHECKING:
    from core.neuro.fractal_regulator import EEPFractalRegulator, RegulatorMetrics


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
    """High-level façade that wires ingestion, analytics, and execution.

    Supports optional fractal regulator for adaptive crisis handling and
    system health monitoring.
    """

    def __init__(
        self,
        system: TradePulseSystem,
        *,
        services: ServiceRegistry | None = None,
        enable_fractal_regulator: bool = False,
        regulator_config: Mapping[str, float | int] | None = None,
    ) -> None:
        self._system = system
        self._services = services or ServiceRegistry.from_system(system)
        self._services.ensure_started()
        self._market_data = self._services.market_data
        self._backtesting = self._services.backtesting
        self._execution = self._services.execution

        # Initialize optional fractal regulator for crisis handling
        self._fractal_regulator: "EEPFractalRegulator | None"
        if enable_fractal_regulator:
            Regulator = globals().get("EEPFractalRegulator")
            if Regulator is None:
                from core.neuro.fractal_regulator import (
                    EEPFractalRegulator as Regulator,
                )

            config = regulator_config or {}
            self._fractal_regulator = Regulator(
                window_size=config.get("window_size", 100),
                embodied_baseline=config.get("embodied_baseline", 1.0),
                crisis_threshold=config.get("crisis_threshold", 0.3),
                energy_damping=config.get("energy_damping", 0.9),
                seed=config.get("seed"),
            )
        else:
            self._fractal_regulator = None
        self._crisis_callback = None

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

    @property
    def fractal_regulator(self) -> "EEPFractalRegulator | None":
        """Expose the fractal regulator if enabled."""

        return self._fractal_regulator

    def set_crisis_callback(self, callback: Callable[["RegulatorMetrics"], None]) -> None:
        """Set a callback to be invoked when crisis is detected.

        Args:
            callback: Function taking RegulatorMetrics as argument

        Example:
            >>> def on_crisis(metrics):
            ...     print(f"Crisis detected! CSI={metrics.csi}")
            >>> orchestrator.set_crisis_callback(on_crisis)
        """
        self._crisis_callback = callback

    def update_system_health(self, signal: float) -> "RegulatorMetrics | None":
        """Update system health monitor with a signal value.

        Args:
            signal: System health signal (e.g., latency, error rate, composite metric)

        Returns:
            RegulatorMetrics if regulator is enabled, None otherwise

        Raises:
            ValueError: If signal is not finite

        Example:
            >>> metrics = orchestrator.update_system_health(0.5)
            >>> if metrics and metrics.csi < 0.3:
            ...     handle_crisis(metrics)
        """
        if self._fractal_regulator is None:
            return None

        metrics = self._fractal_regulator.update_state(signal)

        # Invoke crisis callback if in crisis
        if self._crisis_callback and self._fractal_regulator.is_in_crisis():
            self._crisis_callback(metrics)

        return metrics

    def is_system_in_crisis(self) -> bool:
        """Check if system is currently in crisis state.

        Returns:
            True if fractal regulator is enabled and detects crisis, False otherwise
        """
        if self._fractal_regulator is None:
            return False
        return self._fractal_regulator.is_in_crisis()

    def get_system_health_metrics(self) -> "RegulatorMetrics | None":
        """Get current system health metrics without updating state.

        Returns:
            Current RegulatorMetrics if regulator is enabled, None otherwise
        """
        if self._fractal_regulator is None:
            return None
        return self._fractal_regulator.get_metrics()


__all__ = [
    "ExecutionRequest",
    "MarketDataSource",
    "EEPFractalRegulator",
    "RegulatorMetrics",
    "StrategyRun",
    "TradePulseOrchestrator",
    "build_tradepulse_system",
]


def __getattr__(name: str):
    if name in {"RegulatorMetrics", "EEPFractalRegulator"}:
        from core.neuro.fractal_regulator import (
            EEPFractalRegulator as _EEPF,
        )
        from core.neuro.fractal_regulator import (
            RegulatorMetrics as _RM,
        )

        globals()["EEPFractalRegulator"] = _EEPF
        globals()["RegulatorMetrics"] = _RM
        return globals()[name]
    raise AttributeError(f"module 'application.system_orchestrator' has no attribute '{name}'")
