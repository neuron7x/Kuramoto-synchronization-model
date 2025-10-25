"""Service registry bundling the individual TradePulse microservices."""

from __future__ import annotations

from dataclasses import dataclass

from application.microservices.base import Microservice, ServiceState
from application.microservices.backtesting import BacktestingService
from application.microservices.execution import ExecutionService
from application.microservices.market_data import MarketDataService
from application.system import TradePulseSystem


@dataclass(slots=True)
class ServiceRegistry:
    """Aggregate the platform's microservices for easier dependency management."""

    market_data: MarketDataService
    backtesting: BacktestingService
    execution: ExecutionService

    def services(self) -> tuple[Microservice, ...]:
        return self.market_data, self.backtesting, self.execution

    def start_all(self) -> None:
        for service in self.services():
            if service.state is ServiceState.STOPPED:
                service.start()

    def stop_all(self) -> None:
        for service in self.services():
            if service.state is not ServiceState.STOPPED:
                service.stop()

    def ensure_started(self) -> None:
        for service in self.services():
            if service.state is ServiceState.STOPPED:
                service.start()

    @classmethod
    def from_system(cls, system: TradePulseSystem) -> "ServiceRegistry":
        market_data = MarketDataService(system)
        backtesting = BacktestingService(system, market_data_service=market_data)
        execution = ExecutionService(system)
        registry = cls(
            market_data=market_data,
            backtesting=backtesting,
            execution=execution,
        )
        registry.start_all()
        return registry


__all__ = ["ServiceRegistry"]
