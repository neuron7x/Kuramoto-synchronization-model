from __future__ import annotations

from pathlib import Path

import numpy as np

from application.system import LiveLoopSettings
from application.system_orchestrator import (
    ExecutionRequest,
    MarketDataSource,
    TradePulseOrchestrator,
    build_tradepulse_system,
)


def _sample_csv() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "sample.csv"


def test_tradepulse_orchestrator_end_to_end(tmp_path):
    system = build_tradepulse_system(
        allowed_data_roots=[_sample_csv().parent],
        live_settings=LiveLoopSettings(state_dir=tmp_path / "state"),
    )
    orchestrator = TradePulseOrchestrator(system)

    source = MarketDataSource(path=_sample_csv(), symbol="BTCUSDT", venue="BINANCE")

    def strategy(prices: np.ndarray) -> np.ndarray:
        mean = float(prices.mean())
        return np.where(prices >= mean, 1.0, -1.0)

    run = orchestrator.run_strategy(source, strategy=strategy)

    assert not run.market_frame.empty
    assert not run.feature_frame.empty
    assert run.signals
    assert run.payloads[-1]["symbol"] == "BTCUSDT"

    orchestrator.ensure_live_loop()
    terminal_signal = run.signals[-1]
    price = float(run.feature_frame[system.feature_pipeline.config.price_col].iloc[-1])
    order = orchestrator.submit_signal(
        ExecutionRequest(
            signal=terminal_signal,
            venue="binance",
            quantity=0.2,
            price=price,
        )
    )

    assert order.symbol == "BTCUSDT"
    assert order.quantity == 0.2
