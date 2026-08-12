# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Microservice coordinating backtesting workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from application.microservices.base import Microservice, ServiceState
from application.microservices.contracts import (
    IntegrationContractRegistry,
    MarketDataSource,
    StrategyCallable,
    StrategyRun,
    default_contract_registry,
)
from application.system import GeoSyncSystem
from application.trading import signal_to_dto
from domain import Signal

if TYPE_CHECKING:
    from application.microservices.market_data import MarketDataService


@dataclass(slots=True)
class BacktestResult:
    """Captures the inputs and outputs of the most recent backtest."""

    source: MarketDataSource
    strategy_name: str
    run: StrategyRun


class BacktestingService(Microservice):
    """Provide an isolated boundary for executing strategy backtests."""

    def __init__(
        self,
        system: GeoSyncSystem,
        *,
        market_data_service: "MarketDataService | None" = None,
        contracts: IntegrationContractRegistry | None = None,
    ) -> None:
        super().__init__(name="backtesting")
        self._system = system
        self._market_data_service = market_data_service
        self._last_result: BacktestResult | None = None
        self._contracts = contracts or default_contract_registry()
        try:
            self._operation_contracts["run_backtest"] = self._contracts.get_service(
                "geosync.service.backtesting.run"
            )
        except KeyError:  # pragma: no cover - defensive
            pass

    @property
    def market_data_service(self) -> "MarketDataService":
        from application.microservices.market_data import MarketDataService

        if self._market_data_service is None:
            self._market_data_service = MarketDataService(self._system, contracts=self._contracts)
            if self.state is not ServiceState.STOPPED:
                self._market_data_service.start()
        return self._market_data_service

    def start(self) -> None:
        if (
            self._market_data_service is not None
            and self._market_data_service.state is ServiceState.STOPPED
        ):
            self._market_data_service.start()
        super().start()

    def run_backtest(
        self,
        source: MarketDataSource,
        strategy: StrategyCallable,
    ) -> StrategyRun:
        """Execute the ingestion → feature → signal pipeline for *strategy*."""

        self._ensure_active()
        strategy_name = getattr(strategy, "__name__", strategy.__class__.__name__)
        market_frame = self.market_data_service.ingest(source)
        feature_frame = self.market_data_service.build_features(market_frame)

        contract = self._operation_contract("run_backtest")
        attributes = {"strategy": strategy_name, "symbol": source.symbol}
        if contract and contract.observability:
            attributes = contract.observability.attributes(attributes)
        with self._operation_context("run_backtest", attributes=attributes):
            try:
                signals = self._execute_with_retries(
                    lambda: self._system.generate_signals(
                        feature_frame,
                        strategy=strategy,
                        symbol=source.symbol,
                    ),
                    contract.retry_policy if contract else None,
                )
            except Exception as exc:
                self._mark_error(exc)
                raise

        payloads = self._serialise_signals(signals)
        run = StrategyRun(
            market_frame=market_frame,
            feature_frame=feature_frame,
            signals=signals,
            payloads=payloads,
        )
        self._last_result = BacktestResult(source=source, strategy_name=strategy_name, run=run)
        self._mark_healthy()
        return run

    def _serialise_signals(self, signals: list[Signal]) -> list[dict[str, object]]:
        return [signal_to_dto(signal) for signal in signals]

    def _health_metadata(self) -> dict[str, object] | None:
        if self.state is ServiceState.STOPPED:
            return None
        metadata: dict[str, object] = {}
        if self._last_result is not None:
            metadata["strategy"] = self._last_result.strategy_name
            metadata["signals"] = len(self._last_result.run.signals)
            metadata["symbol"] = self._last_result.source.symbol
        if self.last_error is not None:
            metadata["last_error"] = self.last_error
        return metadata or None


__all__ = ["BacktestingService", "BacktestResult"]
