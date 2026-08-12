# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.events.sourcing module."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.events.sourcing import (
    AggregateRoot,
    AggregateSnapshot,
    EventEnvelope,
)


class TestEventEnvelope:
    def test_creation(self):
        env = EventEnvelope(
            aggregate_id="agg-1",
            aggregate_type="Order",
            version=1,
            event_type="OrderCreated",
            payload=None,
            metadata={},
            correlation_id="corr-1",
            causation_id=None,
            stored_at=datetime.now(timezone.utc),
        )
        assert env.aggregate_id == "agg-1"
        assert env.version == 1
        assert env.event_type == "OrderCreated"

    def test_with_metadata(self):
        env = EventEnvelope(
            aggregate_id="agg-2",
            aggregate_type="Position",
            version=5,
            event_type="PositionOpened",
            payload=None,
            metadata={"user": "admin", "source": "api"},
            correlation_id=None,
            causation_id=None,
            stored_at=datetime.now(timezone.utc),
        )
        assert env.metadata["user"] == "admin"


class TestAggregateSnapshot:
    def test_creation(self):
        snap = AggregateSnapshot(
            aggregate_id="agg-1",
            aggregate_type="Order",
            version=10,
            state={"status": "filled", "quantity": 100},
            taken_at=datetime.now(timezone.utc),
        )
        assert snap.aggregate_id == "agg-1"
        assert snap.version == 10
        assert snap.state["status"] == "filled"


class TestAggregateRoot:
    def test_missing_type_raises(self):
        with pytest.raises(ValueError, match="aggregate_type"):
            AggregateRoot("agg-1")

    def test_concrete_aggregate(self):
        class MyAggregate(AggregateRoot):
            aggregate_type = "MyType"

        agg = MyAggregate("agg-1")
        assert agg.id == "agg-1"
        assert agg.version == 0

    def test_with_version(self):
        class TestAgg(AggregateRoot):
            aggregate_type = "TestAgg"

        agg = TestAgg("agg-1", version=5)
        assert agg.version == 5

    def test_pending_events_empty(self):
        class PendingAgg(AggregateRoot):
            aggregate_type = "PendingAgg"

        agg = PendingAgg("agg-1")
        assert agg._pending_events == []
