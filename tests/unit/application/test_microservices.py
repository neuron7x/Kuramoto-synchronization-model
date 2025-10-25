from __future__ import annotations

from pathlib import Path

import numpy as np

from application import (
    ExecutionRequest,
    LiveLoopSettings,
    MarketDataSource,
    ServiceRegistry,
    TradePulseOrchestrator,
    build_tradepulse_system,
)


def _sample_csv() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "sample.csv"


def _build_system(tmp_path: Path):
    return build_tradepulse_system(
        allowed_data_roots=[_sample_csv().parent],
        live_settings=LiveLoopSettings(state_dir=tmp_path / "state"),
    )


def test_service_registry_provides_isolated_services(tmp_path):
    system = _build_system(tmp_path)
    registry = ServiceRegistry.from_system(system)

    source = MarketDataSource(path=_sample_csv(), symbol="BTCUSDT", venue="BINANCE")

    def strategy(prices: np.ndarray) -> np.ndarray:
        baseline = float(prices.mean())
        return np.where(prices >= baseline, 1.0, -1.0)

    market_frame = registry.market_data.ingest(source)
    feature_frame = registry.market_data.build_features(market_frame)
    assert not market_frame.empty
    assert not feature_frame.empty

    run = registry.backtesting.run_backtest(source, strategy=strategy)
    assert run.signals
    registry.execution.ensure_live_loop()

    price = float(feature_frame.iloc[-1][system.feature_pipeline.config.price_col])
    order = registry.execution.submit(
        ExecutionRequest(
            signal=run.signals[-1],
            venue="binance",
            quantity=0.1,
            price=price,
        )
    )

    assert order.symbol == "BTCUSDT"
    assert registry.market_data.health().healthy
    assert registry.execution.health().metadata["last_quantity"] == 0.1


def test_orchestrator_reuses_microservices(tmp_path):
    system = _build_system(tmp_path)
    registry = ServiceRegistry.from_system(system)
    orchestrator = TradePulseOrchestrator(system, services=registry)

    source = MarketDataSource(path=_sample_csv(), symbol="BTCUSDT", venue="BINANCE")

    def strategy(prices: np.ndarray) -> np.ndarray:
        return np.ones_like(prices)

    run = orchestrator.run_strategy(source, strategy=strategy)
    assert run.payloads
    assert orchestrator.market_data_service is registry.market_data
    orchestrator.ensure_live_loop()

    price = float(run.feature_frame.iloc[-1][system.feature_pipeline.config.price_col])
    order = orchestrator.submit_signal(
        ExecutionRequest(
            signal=run.signals[-1],
            venue="binance",
            quantity=0.2,
            price=price,
        )
    )

    assert order.quantity == 0.2
