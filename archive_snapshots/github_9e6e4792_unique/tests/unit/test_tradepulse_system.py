from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import yaml

from application.system import (
    ExchangeAdapterConfig,
    LiveLoopSettings,
    TradePulseSystem,
    TradePulseSystemConfig,
)
from core.data.models import InstrumentType, PriceTick
from domain import Order, OrderSide, OrderStatus, OrderType, Signal, SignalAction
from execution.connectors import BinanceConnector
from src.security import AccessController, AccessDeniedError, AccessPolicy


def _build_controller(tmp_path: Path, payload: dict[str, object]) -> AccessController:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    policy = AccessPolicy.load(policy_path)
    return AccessController(policy)


class FakeAsyncIngestor:
    """Minimal async ingestor double used for isolating system tests."""

    def __init__(
        self,
        *,
        stream_ticks: Sequence[PriceTick] | None = None,
        snapshot_ticks: Sequence[PriceTick] | None = None,
    ) -> None:
        self._stream_ticks = list(stream_ticks or [])
        self._snapshot_ticks = list(snapshot_ticks or [])
        self.last_stream_call: dict[str, Any] | None = None
        self.last_snapshot_call: dict[str, Any] | None = None

    async def stream_ticks(
        self,
        source: str,
        symbol: str,
        *,
        instrument_type: InstrumentType,
        interval_ms: int,
        max_ticks: int | None,
    ) -> AsyncIterator[PriceTick]:
        self.last_stream_call = {
            "source": source,
            "symbol": symbol,
            "instrument_type": instrument_type,
            "interval_ms": interval_ms,
            "max_ticks": max_ticks,
        }

        ticks_to_emit = self._stream_ticks
        if max_ticks is not None:
            ticks_to_emit = ticks_to_emit[:max_ticks]

        for tick in ticks_to_emit:
            yield tick

    async def fetch_market_snapshot(
        self,
        source: str,
        *,
        symbol: str,
        instrument_type: InstrumentType,
        **kwargs: Any,
    ) -> list[PriceTick]:
        self.last_snapshot_call = {
            "source": source,
            "symbol": symbol,
            "instrument_type": instrument_type,
            "kwargs": dict(kwargs),
        }
        return list(self._snapshot_ticks)


class FakeLiveLoop:
    def __init__(self) -> None:
        self.last_venue: str | None = None
        self.last_order: Order | None = None
        self.last_correlation_id: str | None = None

    def submit_order(self, venue: str, order: Order, *, correlation_id: str) -> Order:
        self.last_venue = venue
        self.last_order = order
        self.last_correlation_id = correlation_id
        return order


def _build_system(tmp_path: Path) -> TradePulseSystem:
    venue = ExchangeAdapterConfig(name="binance", connector=BinanceConnector())
    settings = LiveLoopSettings(state_dir=tmp_path / "state")
    config = TradePulseSystemConfig(venues=[venue], live_settings=settings)
    return TradePulseSystem(config)


def _data_path() -> Path:
    return Path(__file__).resolve().parents[2] / "data" / "sample.csv"


def test_tradepulse_system_generates_features_and_orders(tmp_path: Path) -> None:
    system = _build_system(tmp_path)

    market = system.ingest_csv(_data_path(), symbol="BTCUSDT", venue="BINANCE")
    assert not market.empty
    assert market.index.tz is not None
    assert system.last_ingestion_completed_at is not None
    assert system.last_ingestion_duration_seconds is not None
    assert system.last_ingestion_error is None
    assert system.last_ingestion_symbol == "BTCUSDT"

    features = system.build_feature_frame(market)
    assert "rsi" in features.columns

    def strategy(prices: np.ndarray) -> np.ndarray:
        threshold = float(prices.mean())
        return np.where(prices > threshold, 1.0, -1.0)

    signals = system.generate_signals(features, strategy=strategy)
    assert signals
    assert all(signal.symbol == "BTCUSDT" for signal in signals)
    assert system.last_signal_generated_at is not None
    assert system.last_signal_latency_seconds is not None
    assert system.last_signal_error is None

    payloads = system.signals_to_dtos(signals)
    assert payloads[-1]["symbol"] == "BTCUSDT"

    loop = system.ensure_live_loop()
    assert loop is system.ensure_live_loop()  # idempotent

    terminal_signal = signals[-1]
    order = system.submit_signal(
        terminal_signal,
        venue="binance",
        quantity=0.25,
        price=float(features[system.feature_pipeline.config.price_col].iloc[-1]),
    )

    assert order.symbol == "BTCUSDT"
    assert order.status == OrderStatus.PENDING
    assert order.side.value in {"buy", "sell"}
    assert system.last_execution_submission_at is not None
    assert system.last_execution_error is None


def test_tradepulse_system_rejects_hold_signal(tmp_path: Path) -> None:
    system = _build_system(tmp_path)
    signal = Signal(symbol="BTCUSDT", action=SignalAction.HOLD, confidence=0.2)

    with pytest.raises(ValueError):
        system.submit_signal(signal, venue="binance", quantity=1.0)


def test_generate_signals_filters_invalid_scores(tmp_path: Path) -> None:
    system = _build_system(tmp_path)

    index = pd.date_range("2024-01-01", periods=4, freq="min", tz="UTC")
    feature_frame = pd.DataFrame(
        {
            "close": [100.0, 100.5, 101.0, 101.5],
            "feature": [0.1, 0.2, 0.3, 0.4],
        },
        index=index,
    )

    def strategy(_prices: np.ndarray) -> np.ndarray:
        return np.array([0.5, np.nan, np.inf, -0.75])

    signals = system.generate_signals(
        feature_frame, strategy=strategy, symbol="BTCUSDT"
    )

    assert len(signals) == 2
    assert {signal.action for signal in signals} == {
        SignalAction.BUY,
        SignalAction.SELL,
    }
    assert all(np.isfinite(signal.metadata["score"]) for signal in signals)


def test_submit_signal_exit_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    system = _build_system(tmp_path)
    fake_loop = FakeLiveLoop()
    monkeypatch.setattr(system, "ensure_live_loop", lambda: fake_loop)

    timestamp = datetime.fromtimestamp(1_700_000_000, tz=timezone.utc)
    signal = Signal(
        symbol="BTCUSDT",
        action=SignalAction.EXIT,
        confidence=1.0,
        timestamp=timestamp,
    )

    order = system.submit_signal(signal, venue="binance", quantity=0.5)

    assert order.side is OrderSide.SELL
    assert order.order_type is OrderType.MARKET
    expected_correlation = f"{signal.symbol}-{int(signal.timestamp.timestamp() * 1e9)}"
    assert fake_loop.last_correlation_id == expected_correlation

    limit_order = system.submit_signal(
        signal,
        venue="binance",
        quantity=0.75,
        price=42_000.0,
    )
    assert limit_order.order_type is OrderType.LIMIT

    stop_order = system.submit_signal(
        signal,
        venue="binance",
        quantity=0.75,
        price=42_500.0,
        order_type="stop",
    )
    assert stop_order.order_type is OrderType.STOP

    stop_limit_order = system.submit_signal(
        signal,
        venue="binance",
        quantity=0.75,
        price=43_000.0,
        order_type=OrderType.STOP_LIMIT,
    )
    assert stop_limit_order.order_type is OrderType.STOP_LIMIT


@pytest.mark.asyncio
async def test_stream_market_data_uses_fake_async_ingestor(tmp_path: Path) -> None:
    ticks = [
        PriceTick.create(
            symbol="BTCUSDT",
            venue="BINANCE",
            price="27000.10",
            timestamp=1_700_000_000,
        ),
        PriceTick.create(
            symbol="BTCUSDT",
            venue="BINANCE",
            price="27000.25",
            timestamp=1_700_000_001,
        ),
    ]
    fake_ingestor = FakeAsyncIngestor(stream_ticks=ticks)
    config = TradePulseSystemConfig(
        venues=[ExchangeAdapterConfig(name="binance", connector=BinanceConnector())],
        live_settings=LiveLoopSettings(state_dir=tmp_path / "state"),
    )
    system = TradePulseSystem(config, async_data_ingestor=fake_ingestor)

    results: list[PriceTick] = []
    async for tick in system.stream_market_data(
        "binance_ws",
        "BTCUSDT",
        instrument_type=InstrumentType.SPOT,
        interval_ms=250,
        max_ticks=len(ticks),
    ):
        results.append(tick)

    assert results == ticks
    assert fake_ingestor.last_stream_call == {
        "source": "binance_ws",
        "symbol": "BTCUSDT",
        "instrument_type": InstrumentType.SPOT,
        "interval_ms": 250,
        "max_ticks": len(ticks),
    }


@pytest.mark.asyncio
async def test_fetch_market_snapshot_records_kwargs(tmp_path: Path) -> None:
    snapshot = [
        PriceTick.create(
            symbol="ETHUSDT",
            venue="BINANCE",
            price="1800.5",
            timestamp=1_700_000_100,
            instrument_type=InstrumentType.FUTURES,
        )
    ]
    fake_ingestor = FakeAsyncIngestor(snapshot_ticks=snapshot)
    config = TradePulseSystemConfig(
        venues=[ExchangeAdapterConfig(name="binance", connector=BinanceConnector())],
        live_settings=LiveLoopSettings(state_dir=tmp_path / "state"),
    )
    system = TradePulseSystem(config, async_data_ingestor=fake_ingestor)

    depth = 5
    snapshot_result = await system.fetch_market_snapshot(
        "binance_ws",
        symbol="ETHUSDT",
        instrument_type=InstrumentType.FUTURES,
        depth=depth,
    )

    assert snapshot_result == snapshot
    assert fake_ingestor.last_snapshot_call == {
        "source": "binance_ws",
        "symbol": "ETHUSDT",
        "instrument_type": InstrumentType.FUTURES,
        "kwargs": {"depth": depth},
    }


def test_connector_credentials_enforces_access_control(tmp_path: Path) -> None:
    controller = _build_controller(
        tmp_path,
        {
            "subjects": {"system": {"permissions": ["read_exchange_keys"]}},
            "roles": {
                "risk": {"permissions": ["read_exchange_keys"]},
                "ops": {"permissions": ["reset_kill_switch"]},
            },
        },
    )

    venue = ExchangeAdapterConfig(
        name="binance",
        connector=BinanceConnector(),
        credentials={"API_KEY": "key", "API_SECRET": "secret"},
    )
    config = TradePulseSystemConfig(venues=[venue], live_settings=LiveLoopSettings())
    system = TradePulseSystem(config, access_controller=controller)

    credentials = system.connector_credentials(
        "binance", actor="alice", roles=("risk",)
    )
    assert credentials == {"API_KEY": "key", "API_SECRET": "secret"}

    with pytest.raises(AccessDeniedError):
        system.connector_credentials("binance", actor="bob", roles=("ops",))
