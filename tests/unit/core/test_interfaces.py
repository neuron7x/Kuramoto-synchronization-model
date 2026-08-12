# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.interfaces module - core protocols and contracts."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping

import pytest

from core.interfaces import (
    DataRecord,
    DataSource,
    EngineClock,
    Event,
    EventBus,
    EventHandler,
    Feature,
    FeatureStore,
    Indicator,
    IndicatorResult,
    LifecycleComponent,
    RiskAssessment,
    RiskSignal,
    SimulatedClock,
    WallClock,
)


class TestDataRecord:
    """Tests for DataRecord dataclass."""

    def test_creation(self) -> None:
        """DataRecord should accept all required fields."""
        now = datetime.now(timezone.utc)
        record = DataRecord(
            source="binance",
            symbol="BTC/USD",
            timestamp=now,
            payload={"open": 50000, "close": 51000},
        )
        assert record.source == "binance"
        assert record.symbol == "BTC/USD"
        assert record.timestamp == now
        assert record.payload["close"] == 51000
        assert record.metadata == {}

    def test_with_metadata(self) -> None:
        """DataRecord should accept metadata."""
        record = DataRecord(
            source="test",
            symbol="TEST",
            timestamp=datetime.now(timezone.utc),
            payload={},
            metadata={"quality": "high"},
        )
        assert record.metadata["quality"] == "high"


class TestIndicatorResult:
    """Tests for IndicatorResult dataclass."""

    def test_creation(self) -> None:
        """IndicatorResult should accept all fields."""
        result = IndicatorResult(
            name="RSI",
            value=65.5,
            fingerprint="abc123",
            metadata={"period": 14},
        )
        assert result.name == "RSI"
        assert result.value == 65.5
        assert result.fingerprint == "abc123"
        assert result.metadata["period"] == 14
        assert result.timestamp is not None

    def test_default_values(self) -> None:
        """IndicatorResult should have sensible defaults."""
        result = IndicatorResult(name="test", value=0)
        assert result.fingerprint is None
        assert result.metadata == {}


class TestFeature:
    """Tests for Feature dataclass."""

    def test_creation(self) -> None:
        """Feature should accept all fields."""
        feature = Feature(
            name="momentum",
            value=0.75,
            version="2.0",
            metadata={"source": "computed"},
        )
        assert feature.name == "momentum"
        assert feature.value == 0.75
        assert feature.version == "2.0"

    def test_default_version(self) -> None:
        """Feature should default to version 1.0."""
        feature = Feature(name="test", value=0)
        assert feature.version == "1.0"


class TestEvent:
    """Tests for Event dataclass."""

    def test_creation(self) -> None:
        """Event should accept all fields."""
        event = Event(
            event_type="order.placed",
            payload={"order_id": "123", "quantity": 100},
            event_id="evt-001",
            correlation_id="corr-001",
            idempotency_key="idem-001",
        )
        assert event.event_type == "order.placed"
        assert event.payload["order_id"] == "123"
        assert event.event_id == "evt-001"
        assert event.correlation_id == "corr-001"
        assert event.idempotency_key == "idem-001"

    def test_default_timestamp(self) -> None:
        """Event should have a default timestamp."""
        event = Event(event_type="test", payload={}, event_id="1")
        assert event.timestamp is not None


class TestRiskAssessment:
    """Tests for RiskAssessment dataclass."""

    def test_approved(self) -> None:
        """RiskAssessment should handle approved decisions."""
        assessment = RiskAssessment(
            approved=True,
            risk_score=0.2,
            reason="Within limits",
        )
        assert assessment.approved is True
        assert assessment.risk_score == 0.2
        assert assessment.reason == "Within limits"

    def test_rejected(self) -> None:
        """RiskAssessment should handle rejected decisions."""
        assessment = RiskAssessment(
            approved=False,
            risk_score=0.9,
            reason="Exceeds position limit",
            constraints={"max_quantity": 100},
        )
        assert assessment.approved is False
        assert assessment.constraints["max_quantity"] == 100


class TestWallClock:
    """Tests for WallClock implementation."""

    def test_now_returns_utc(self) -> None:
        """WallClock.now should return UTC time."""
        clock = WallClock()
        now = clock.now()
        assert now.tzinfo == timezone.utc

    def test_is_not_simulated(self) -> None:
        """WallClock should not be simulated."""
        clock = WallClock()
        assert clock.is_simulated is False

    def test_implements_protocol(self) -> None:
        """WallClock should implement EngineClock protocol."""
        clock = WallClock()
        assert isinstance(clock, EngineClock)


class TestSimulatedClock:
    """Tests for SimulatedClock implementation."""

    def test_default_start_time(self) -> None:
        """SimulatedClock should default to epoch."""
        clock = SimulatedClock()
        assert clock.now() == datetime(1970, 1, 1, tzinfo=timezone.utc)

    def test_custom_start_time(self) -> None:
        """SimulatedClock should accept custom start time."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        clock = SimulatedClock(start_time=start)
        assert clock.now() == start

    def test_sleep_advances_time(self) -> None:
        """SimulatedClock.sleep should advance time."""
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        clock = SimulatedClock(start_time=start)
        clock.sleep(3600)  # 1 hour
        expected = start + timedelta(hours=1)
        assert clock.now() == expected

    def test_advance_method(self) -> None:
        """SimulatedClock.advance should work like sleep."""
        clock = SimulatedClock()
        clock.advance(60)
        assert clock.now() == datetime(1970, 1, 1, 0, 1, 0, tzinfo=timezone.utc)

    def test_set_time(self) -> None:
        """SimulatedClock.set_time should set absolute time."""
        clock = SimulatedClock()
        new_time = datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        clock.set_time(new_time)
        assert clock.now() == new_time

    def test_is_simulated(self) -> None:
        """SimulatedClock should be simulated."""
        clock = SimulatedClock()
        assert clock.is_simulated is True

    def test_implements_protocol(self) -> None:
        """SimulatedClock should implement EngineClock protocol."""
        clock = SimulatedClock()
        assert isinstance(clock, EngineClock)


class TestDataSourceProtocol:
    """Tests for DataSource protocol."""

    def test_protocol_check(self) -> None:
        """Classes implementing DataSource should pass isinstance check."""

        class MyDataSource:
            @property
            def source_id(self) -> str:
                return "my_source"

            def fetch(
                self,
                *,
                symbols: Iterable[str],
                start: datetime,
                end: datetime,
                **kwargs: Any,
            ) -> Iterable[DataRecord]:
                return []

            def validate_connection(self) -> bool:
                return True

        source = MyDataSource()
        assert isinstance(source, DataSource)


class TestIndicatorProtocol:
    """Tests for Indicator protocol."""

    def test_protocol_check(self) -> None:
        """Classes implementing Indicator should pass isinstance check."""

        class MyIndicator:
            @property
            def name(self) -> str:
                return "my_indicator"

            @property
            def parameters(self) -> Mapping[str, Any]:
                return {"period": 14}

            def compute(
                self,
                data: Any,
                *,
                seed: int | None = None,
                **kwargs: Any,
            ) -> IndicatorResult:
                return IndicatorResult(name=self.name, value=0.5)

            def fingerprint(self, data: Any, **kwargs: Any) -> str:
                return "fp-123"

        indicator = MyIndicator()
        assert isinstance(indicator, Indicator)


class TestFeatureStoreProtocol:
    """Tests for FeatureStore protocol."""

    def test_protocol_check(self) -> None:
        """Classes implementing FeatureStore should pass isinstance check."""

        class MyFeatureStore:
            def get(
                self,
                feature_name: str,
                entity_id: str,
                *,
                timestamp: datetime | None = None,
            ) -> Feature | None:
                return None

            def get_batch(
                self,
                feature_names: Iterable[str],
                entity_ids: Iterable[str],
                *,
                timestamp: datetime | None = None,
            ) -> Mapping[str, Mapping[str, Feature | None]]:
                return {}

            def put(
                self,
                feature_name: str,
                entity_id: str,
                value: Feature,
                *,
                timestamp: datetime | None = None,
            ) -> None:
                pass

            def put_batch(
                self,
                features: Iterable[tuple[str, str, Feature, datetime | None]],
            ) -> None:
                pass

        store = MyFeatureStore()
        assert isinstance(store, FeatureStore)


class TestEventBusProtocol:
    """Tests for EventBus protocol."""

    def test_protocol_check(self) -> None:
        """Classes implementing EventBus should pass isinstance check."""

        class MyEventBus:
            def publish(
                self,
                event_type: str,
                payload: Any,
                *,
                event_id: str | None = None,
                correlation_id: str | None = None,
                idempotency_key: str | None = None,
            ) -> str:
                return "evt-001"

            def subscribe(
                self,
                event_type: str,
                handler: EventHandler,
                *,
                group: str | None = None,
            ) -> str:
                return "sub-001"

            def unsubscribe(self, subscription_id: str) -> bool:
                return True

        bus = MyEventBus()
        assert isinstance(bus, EventBus)


class TestRiskSignalProtocol:
    """Tests for RiskSignal protocol."""

    def test_protocol_check(self) -> None:
        """Classes implementing RiskSignal should pass isinstance check."""

        class MyRiskSignal:
            def assess(
                self,
                action: Mapping[str, Any],
                *,
                context: Mapping[str, Any] | None = None,
            ) -> RiskAssessment:
                return RiskAssessment(approved=True)

            def check_budget(self, resource: str, requested: float) -> bool:
                return True

        risk = MyRiskSignal()
        assert isinstance(risk, RiskSignal)


class TestLifecycleComponent:
    """Tests for LifecycleComponent ABC."""

    def test_abstract_methods(self) -> None:
        """LifecycleComponent should require all abstract methods."""

        class MyComponent(LifecycleComponent):
            def __init__(self) -> None:
                self._started = False

            def start(self) -> None:
                self._started = True

            def stop(self) -> None:
                self._started = False

            def is_healthy(self) -> bool:
                return self._started

            @property
            def component_name(self) -> str:
                return "my_component"

        component = MyComponent()
        assert component.component_name == "my_component"
        assert not component.is_healthy()
        component.start()
        assert component.is_healthy()
        component.stop()
        assert not component.is_healthy()

    def test_cannot_instantiate_abstract(self) -> None:
        """Cannot instantiate LifecycleComponent directly."""
        with pytest.raises(TypeError):
            LifecycleComponent()  # type: ignore[abstract]
