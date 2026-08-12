# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for BaseIngestor interface and RawEvent model.

Validates the contract that all connectors must implement.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

import pytest

from mycelium_fractal_net.connectors.base import BaseIngestor, RawEvent


class TestRawEvent:
    """Tests for RawEvent pydantic model."""

    def test_create_minimal_event(self) -> None:
        """Test creating a RawEvent with minimal fields."""
        event = RawEvent(
            source="test_source",
            timestamp=datetime.now(timezone.utc),
            payload={"key": "value"},
        )
        assert event.source == "test_source"
        assert event.payload == {"key": "value"}
        assert event.meta == {}

    def test_create_event_with_meta(self) -> None:
        """Test creating a RawEvent with metadata."""
        ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        event = RawEvent(
            source="api_source",
            timestamp=ts,
            payload={"data": [1, 2, 3]},
            meta={"request_id": "req-123", "index": 0},
        )
        assert event.timestamp == ts
        assert event.meta["request_id"] == "req-123"

    def test_timestamp_coercion_from_epoch(self) -> None:
        """Test timestamp conversion from epoch seconds."""
        epoch = 1704067200.0  # 2024-01-01 00:00:00 UTC
        event = RawEvent(
            source="test",
            timestamp=epoch,  # type: ignore[arg-type]
            payload={},
        )
        assert event.timestamp.year == 2024
        assert event.timestamp.tzinfo is not None

    def test_timestamp_coercion_from_iso_string(self) -> None:
        """Test timestamp conversion from ISO string."""
        event = RawEvent(
            source="test",
            timestamp="2024-01-15T10:30:00Z",  # type: ignore[arg-type]
            payload={},
        )
        assert event.timestamp.year == 2024
        assert event.timestamp.month == 1
        assert event.timestamp.day == 15

    def test_timestamp_property(self) -> None:
        """Test ts property returns epoch seconds."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        event = RawEvent(source="test", timestamp=ts, payload={})
        assert event.ts == 1704067200.0

    def test_source_validation_strips_whitespace(self) -> None:
        """Test that source is stripped of whitespace."""
        event = RawEvent(
            source="  my_source  ",
            timestamp=datetime.now(timezone.utc),
            payload={},
        )
        assert event.source == "my_source"

    def test_source_validation_rejects_empty(self) -> None:
        """Test that empty source raises validation error."""
        with pytest.raises(Exception):  # Pydantic validation error
            RawEvent(
                source="   ",
                timestamp=datetime.now(timezone.utc),
                payload={},
            )

    def test_event_is_frozen(self) -> None:
        """Test that RawEvent is immutable."""
        event = RawEvent(
            source="test",
            timestamp=datetime.now(timezone.utc),
            payload={"key": "value"},
        )
        with pytest.raises(Exception):
            event.source = "changed"  # type: ignore[misc]


class MockIngestor(BaseIngestor):
    """Mock implementation of BaseIngestor for testing."""

    def __init__(self, events: list[RawEvent] | None = None) -> None:
        self.events = events or []
        self.connected = False
        self.closed = False

    async def connect(self) -> None:
        self.connected = True

    async def fetch(self) -> AsyncIterator[RawEvent]:
        for event in self.events:
            yield event

    async def close(self) -> None:
        self.closed = True


class TestBaseIngestor:
    """Tests for BaseIngestor abstract interface."""

    @pytest.mark.asyncio
    async def test_context_manager_calls_connect_and_close(self) -> None:
        """Test async context manager protocol."""
        ingestor = MockIngestor()
        assert not ingestor.connected
        assert not ingestor.closed

        async with ingestor:
            assert ingestor.connected
            assert not ingestor.closed

        assert ingestor.closed

    @pytest.mark.asyncio
    async def test_fetch_yields_events(self) -> None:
        """Test that fetch yields configured events."""
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"id": i},
            )
            for i in range(3)
        ]
        ingestor = MockIngestor(events=events)
        await ingestor.connect()

        fetched = []
        async for event in ingestor.fetch():
            fetched.append(event)

        assert len(fetched) == 3
        assert fetched[0].payload["id"] == 0
        assert fetched[2].payload["id"] == 2

    @pytest.mark.asyncio
    async def test_empty_fetch(self) -> None:
        """Test fetch with no events."""
        ingestor = MockIngestor(events=[])
        await ingestor.connect()

        fetched = []
        async for event in ingestor.fetch():
            fetched.append(event)

        assert len(fetched) == 0


class TestBaseIngestorContract:
    """Tests verifying the contract requirements."""

    def test_abstract_methods_defined(self) -> None:
        """Test that BaseIngestor defines required abstract methods."""
        assert hasattr(BaseIngestor, "connect")
        assert hasattr(BaseIngestor, "fetch")
        assert hasattr(BaseIngestor, "close")

    def test_cannot_instantiate_base_class(self) -> None:
        """Test that BaseIngestor cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseIngestor()  # type: ignore[abstract]

    def test_subclass_must_implement_methods(self) -> None:
        """Test that subclass without implementations fails."""

        class IncompleteIngestor(BaseIngestor):
            pass

        with pytest.raises(TypeError):
            IncompleteIngestor()  # type: ignore[abstract]

    def test_complete_subclass_can_be_instantiated(self) -> None:
        """Test that complete subclass can be instantiated."""
        ingestor = MockIngestor()
        assert isinstance(ingestor, BaseIngestor)
