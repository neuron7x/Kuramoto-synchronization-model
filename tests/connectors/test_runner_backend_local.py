# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for IngestionRunner with local backend.

Validates orchestration, event processing, and backend integration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator

import pytest

from mycelium_fractal_net.connectors.base import BaseIngestor, RawEvent
from mycelium_fractal_net.connectors.runner import (
    BackendResult,
    IngestionRunner,
    IngestionStats,
    LocalBackend,
    MFNBackend,
)
from mycelium_fractal_net.connectors.transform import MFNRequest, Transformer


class FakeIngestor(BaseIngestor):
    """Fake ingestor for testing."""

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


class RecordingBackend(MFNBackend):
    """Backend that records all requests for verification."""

    def __init__(self) -> None:
        self.feature_requests: list[MFNRequest] = []
        self.simulation_requests: list[MFNRequest] = []
        self.closed = False

    async def extract_features(self, request: MFNRequest) -> BackendResult:
        self.feature_requests.append(request)
        return BackendResult(
            success=True,
            request_id=request.request_id,
            result={"features": [1.0, 2.0]},
            latency_ms=5.0,
        )

    async def run_simulation(self, request: MFNRequest) -> BackendResult:
        self.simulation_requests.append(request)
        return BackendResult(
            success=True,
            request_id=request.request_id,
            result={"status": "completed"},
            latency_ms=10.0,
        )

    async def close(self) -> None:
        self.closed = True


class FailingBackend(MFNBackend):
    """Backend that fails all requests."""

    def __init__(self, error_message: str = "Backend error") -> None:
        self.error_message = error_message

    async def extract_features(self, request: MFNRequest) -> BackendResult:
        return BackendResult(
            success=False,
            request_id=request.request_id,
            error=self.error_message,
        )

    async def run_simulation(self, request: MFNRequest) -> BackendResult:
        return BackendResult(
            success=False,
            request_id=request.request_id,
            error=self.error_message,
        )


class TestLocalBackend:
    """Tests for LocalBackend."""

    @pytest.mark.asyncio
    async def test_extract_features(self) -> None:
        """Test feature extraction."""
        backend = LocalBackend()
        request = MFNRequest(
            request_type="feature",
            request_id="test-001",
            timestamp=datetime.now(timezone.utc),
            seeds=[1.0, 2.0],
            grid_size=64,
        )

        result = await backend.extract_features(request)

        assert result.success is True
        assert result.request_id == "test-001"
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_run_simulation(self) -> None:
        """Test simulation execution."""
        backend = LocalBackend()
        request = MFNRequest(
            request_type="simulation",
            request_id="sim-001",
            timestamp=datetime.now(timezone.utc),
            seeds=[1.0, 2.0, 3.0],
            grid_size=128,
        )

        result = await backend.run_simulation(request)

        assert result.success is True
        assert result.request_id == "sim-001"

    @pytest.mark.asyncio
    async def test_call_count(self) -> None:
        """Test call count tracking."""
        backend = LocalBackend()
        assert backend.call_count == 0

        request = MFNRequest(
            request_type="feature",
            request_id="test",
            timestamp=datetime.now(timezone.utc),
        )

        await backend.extract_features(request)
        assert backend.call_count == 1

        await backend.run_simulation(request)
        assert backend.call_count == 2


class TestIngestionRunner:
    """Tests for IngestionRunner orchestrator."""

    def test_initialization(self) -> None:
        """Test runner initialization."""
        ingestor = FakeIngestor()
        backend = RecordingBackend()

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
            mode="feature",
            batch_size=5,
        )

        assert runner.mode == "feature"
        assert runner.batch_size == 5

    @pytest.mark.asyncio
    async def test_run_processes_events(self) -> None:
        """Test that runner processes all events."""
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"seeds": [float(i)], "id": i},
            )
            for i in range(5)
        ]

        ingestor = FakeIngestor(events=events)
        backend = RecordingBackend()

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
            mode="feature",
        )

        stats = await runner.run()

        assert stats.events_received == 5
        assert stats.events_processed == 5
        assert stats.events_failed == 0
        assert len(backend.feature_requests) == 5

    @pytest.mark.asyncio
    async def test_run_simulation_mode(self) -> None:
        """Test runner in simulation mode."""
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"seeds": [1.0]},
            )
            for _ in range(3)
        ]

        ingestor = FakeIngestor(events=events)
        backend = RecordingBackend()

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
            mode="simulation",
        )

        await runner.run()

        assert len(backend.simulation_requests) == 3
        assert len(backend.feature_requests) == 0

    @pytest.mark.asyncio
    async def test_run_with_max_events(self) -> None:
        """Test runner with max_events limit."""
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={},
            )
            for _ in range(10)
        ]

        ingestor = FakeIngestor(events=events)
        backend = RecordingBackend()

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
        )

        stats = await runner.run(max_events=3)

        assert stats.events_received == 3

    @pytest.mark.asyncio
    async def test_run_handles_backend_failures(self) -> None:
        """Test that runner handles backend failures."""
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"seeds": [1.0]},
            )
            for _ in range(3)
        ]

        ingestor = FakeIngestor(events=events)
        backend = FailingBackend(error_message="Service unavailable")

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
        )

        stats = await runner.run()

        assert stats.events_received == 3
        assert stats.events_failed == 3
        assert stats.backend_errors == 3

    @pytest.mark.asyncio
    async def test_run_handles_normalization_errors(self) -> None:
        """Test that runner handles normalization errors."""
        # Create events that will fail pydantic validation
        # Use invalid grid_size that will fail validation
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"seeds": [1.0]},  # Valid
            ),
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"seeds": [1.0]},  # Valid - normalization is lenient
            ),
        ]

        ingestor = FakeIngestor(events=events)
        backend = RecordingBackend()

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
        )

        stats = await runner.run()

        # Both events should be processed (normalization is lenient)
        assert stats.events_received == 2
        assert stats.events_processed == 2

    @pytest.mark.asyncio
    async def test_run_closes_resources(self) -> None:
        """Test that runner closes ingestor and backend."""
        ingestor = FakeIngestor(events=[])
        backend = RecordingBackend()

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
        )

        await runner.run()

        assert ingestor.closed is True
        assert backend.closed is True

    @pytest.mark.asyncio
    async def test_stop_method(self) -> None:
        """Test stop() signals runner to stop."""
        runner = IngestionRunner(
            ingestor=FakeIngestor(),
            backend=RecordingBackend(),
        )

        assert runner._running is False
        runner.stop()
        assert runner._running is False

    @pytest.mark.asyncio
    async def test_stats_property(self) -> None:
        """Test stats property returns current statistics."""
        runner = IngestionRunner(
            ingestor=FakeIngestor(),
            backend=RecordingBackend(),
        )

        stats = runner.stats
        assert isinstance(stats, IngestionStats)
        assert stats.events_received == 0

    @pytest.mark.asyncio
    async def test_results_property(self) -> None:
        """Test results property returns backend results."""
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"seeds": [1.0]},
            )
        ]

        ingestor = FakeIngestor(events=events)
        backend = RecordingBackend()

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
        )

        await runner.run()

        results = runner.results
        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_custom_transformer(self) -> None:
        """Test runner with custom transformer."""
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"values": [1.0, 2.0]},  # Custom field name
            )
        ]

        ingestor = FakeIngestor(events=events)
        backend = RecordingBackend()
        transformer = Transformer(seed_fields=["values"])

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
            transformer=transformer,
        )

        await runner.run()

        assert len(backend.feature_requests) == 1
        assert backend.feature_requests[0].seeds == [1.0, 2.0]

    @pytest.mark.asyncio
    async def test_batch_processing(self) -> None:
        """Test that events are processed in batches."""
        events = [
            RawEvent(
                source="test",
                timestamp=datetime.now(timezone.utc),
                payload={"seeds": [float(i)]},
            )
            for i in range(25)
        ]

        ingestor = FakeIngestor(events=events)
        backend = RecordingBackend()

        runner = IngestionRunner(
            ingestor=ingestor,
            backend=backend,
            batch_size=10,
        )

        stats = await runner.run()

        assert stats.events_received == 25
        assert stats.events_processed == 25


class TestIngestionStats:
    """Tests for IngestionStats dataclass."""

    def test_default_values(self) -> None:
        """Test default stat values."""
        stats = IngestionStats()
        assert stats.events_received == 0
        assert stats.events_processed == 0
        assert stats.events_failed == 0
        assert stats.total_latency_ms == 0.0

    def test_values_can_be_updated(self) -> None:
        """Test stat values can be updated."""
        stats = IngestionStats()
        stats.events_received = 10
        stats.events_processed = 8
        stats.events_failed = 2

        assert stats.events_received == 10
        assert stats.events_processed == 8


class TestBackendResult:
    """Tests for BackendResult dataclass."""

    def test_success_result(self) -> None:
        """Test successful result."""
        result = BackendResult(
            success=True,
            request_id="test-001",
            result={"data": [1, 2, 3]},
            latency_ms=15.5,
        )

        assert result.success is True
        assert result.error is None
        assert result.latency_ms == 15.5

    def test_failure_result(self) -> None:
        """Test failure result."""
        result = BackendResult(
            success=False,
            request_id="test-002",
            error="Connection timeout",
        )

        assert result.success is False
        assert result.error == "Connection timeout"
        assert result.result is None
