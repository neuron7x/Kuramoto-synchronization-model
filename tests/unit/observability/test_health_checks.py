# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import numpy as np

from application.system import (
    ExchangeAdapterConfig,
    GeoSyncSystem,
    GeoSyncSystemConfig,
    LiveLoopSettings,
)
from execution.connectors import BinanceConnector
from observability.health_checks import (
    build_default_health_checks,
    evaluate_data_pipeline_health,
    evaluate_execution_health,
    evaluate_signal_pipeline_health,
)


def _build_system(tmp_path: Path) -> GeoSyncSystem:
    venue = ExchangeAdapterConfig(name="binance", connector=BinanceConnector())
    settings = LiveLoopSettings(state_dir=tmp_path / "state")
    config = GeoSyncSystemConfig(venues=[venue], live_settings=settings)
    return GeoSyncSystem(config)


def _data_path() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "sample.csv"


def test_data_pipeline_health_reflects_status(tmp_path: Path) -> None:
    system = _build_system(tmp_path)

    result = evaluate_data_pipeline_health(system)
    assert not result.healthy

    market = system.ingest_csv(_data_path(), symbol="BTCUSDT", venue="BINANCE")
    assert not market.empty

    result = evaluate_data_pipeline_health(system)
    assert result.healthy

    system._last_ingestion_completed_at = system.last_ingestion_completed_at - timedelta(
        seconds=400
    )  # type: ignore[assignment]
    result = evaluate_data_pipeline_health(system, stale_after_seconds=300.0)
    assert not result.healthy

    system._last_ingestion_error = "boom"  # type: ignore[assignment]
    result = evaluate_data_pipeline_health(system)
    assert not result.healthy


def test_signal_pipeline_health_detects_staleness(tmp_path: Path) -> None:
    system = _build_system(tmp_path)
    market = system.ingest_csv(_data_path(), symbol="BTCUSDT", venue="BINANCE")
    features = system.build_feature_frame(market)

    def strategy(prices: np.ndarray) -> np.ndarray:
        return np.ones_like(prices)

    system.generate_signals(features, strategy=strategy)
    result = evaluate_signal_pipeline_health(system)
    assert result.healthy

    system._last_signal_generated_at = system.last_signal_generated_at - timedelta(seconds=500)  # type: ignore[assignment]
    result = evaluate_signal_pipeline_health(system, stale_after_seconds=120.0)
    assert not result.healthy

    system._last_signal_error = "bad"  # type: ignore[assignment]
    result = evaluate_signal_pipeline_health(system)
    assert not result.healthy


def test_execution_health_validates_loop_state(tmp_path: Path) -> None:
    system = _build_system(tmp_path)

    result = evaluate_execution_health(system)
    assert not result.healthy

    loop = system.ensure_live_loop()
    result = evaluate_execution_health(system)
    assert not result.healthy  # loop not started yet

    loop._started = True  # type: ignore[attr-defined]
    system._last_execution_submission_at = system._clock()  # type: ignore[attr-defined]
    result = evaluate_execution_health(system)
    assert result.healthy

    system._last_execution_submission_at = system._clock() - timedelta(seconds=200)  # type: ignore[attr-defined]
    result = evaluate_execution_health(system, stale_after_seconds=60.0)
    assert not result.healthy

    system._last_execution_error = "disconnect"  # type: ignore[attr-defined]
    result = evaluate_execution_health(system)
    assert not result.healthy

    checks = build_default_health_checks(system)
    assert {check.name for check in checks} == {
        "data_pipeline",
        "signal_pipeline",
        "execution",
    }
