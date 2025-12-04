# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Ingestion runner and backend orchestration for MFN.

This module provides the orchestrator that connects ingestors to MFN backends,
handling event flow, normalization, and request dispatch.

Components:
- MFNBackend: Abstract interface for MFN core operations
- LocalBackend: Direct Python function calls to MFN core
- RemoteBackend: gRPC/REST client to MFN service
- IngestionRunner: Main orchestrator

Example:
    >>> runner = IngestionRunner(
    ...     ingestor=RestIngestor(url="https://api.example.com/data"),
    ...     backend=LocalBackend(),
    ...     mode="feature",
    ... )
    >>> await runner.run()
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .base import BaseIngestor, RawEvent
from .transform import MappingError, MFNRequest, NormalizationError, Transformer

__all__ = [
    "MFNBackend",
    "LocalBackend",
    "RemoteBackend",
    "IngestionRunner",
]

logger = logging.getLogger(__name__)


@dataclass
class BackendResult:
    """Result from MFN backend operation.

    Attributes:
        success: Whether the operation succeeded
        request_id: Original request identifier
        result: Operation result data (if successful)
        error: Error message (if failed)
        latency_ms: Processing time in milliseconds
    """

    success: bool
    request_id: str
    result: Any = None
    error: str | None = None
    latency_ms: float = 0.0


class MFNBackend(ABC):
    """Abstract interface for MFN core operations.

    Backends handle the actual execution of MFN requests, either
    locally (direct function calls) or remotely (via gRPC/REST).
    """

    @abstractmethod
    async def extract_features(self, request: MFNRequest) -> BackendResult:
        """Execute feature extraction request.

        Args:
            request: MFN feature extraction request

        Returns:
            BackendResult with extracted features
        """

    @abstractmethod
    async def run_simulation(self, request: MFNRequest) -> BackendResult:
        """Execute simulation request.

        Args:
            request: MFN simulation request

        Returns:
            BackendResult with simulation results
        """

    async def close(self) -> None:
        """Clean up backend resources."""
        pass


class LocalBackend(MFNBackend):
    """Direct Python function calls to MFN core.

    Uses local MFN module functions for processing.
    This backend is suitable for single-process deployments.

    Example:
        >>> backend = LocalBackend()
        >>> result = await backend.extract_features(request)
    """

    def __init__(self, *, core_module: Any = None) -> None:
        """Initialize local backend.

        Args:
            core_module: Optional MFN core module (for testing)
        """
        self._core = core_module
        self._call_count = 0

    async def extract_features(self, request: MFNRequest) -> BackendResult:
        """Extract fractal features locally.

        Args:
            request: Feature extraction request

        Returns:
            BackendResult with extracted features
        """
        start = datetime.now(timezone.utc)

        try:
            self._call_count += 1

            # Stub: Real implementation would call MFN core
            # from mycelium_fractal_net.core import extract_features
            # features = extract_features(request.seeds, request.grid_size, **request.params)

            features = {
                "request_id": request.request_id,
                "grid_size": request.grid_size,
                "seed_count": len(request.seeds),
                "params": request.params,
            }

            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            logger.debug(
                f"Feature extraction complete: {request.request_id} ({latency:.2f}ms)"
            )

            return BackendResult(
                success=True,
                request_id=request.request_id,
                result=features,
                latency_ms=latency,
            )

        except Exception as e:
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            logger.error(f"Feature extraction failed: {request.request_id}: {e}")
            return BackendResult(
                success=False,
                request_id=request.request_id,
                error=str(e),
                latency_ms=latency,
            )

    async def run_simulation(self, request: MFNRequest) -> BackendResult:
        """Run fractal simulation locally.

        Args:
            request: Simulation request

        Returns:
            BackendResult with simulation results
        """
        start = datetime.now(timezone.utc)

        try:
            self._call_count += 1

            # Stub: Real implementation would call MFN core
            # from mycelium_fractal_net.core import run_simulation
            # result = run_simulation(request.seeds, request.grid_size, **request.params)

            result = {
                "request_id": request.request_id,
                "grid_size": request.grid_size,
                "seed_count": len(request.seeds),
                "params": request.params,
                "status": "completed",
            }

            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            logger.debug(f"Simulation complete: {request.request_id} ({latency:.2f}ms)")

            return BackendResult(
                success=True,
                request_id=request.request_id,
                result=result,
                latency_ms=latency,
            )

        except Exception as e:
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            logger.error(f"Simulation failed: {request.request_id}: {e}")
            return BackendResult(
                success=False,
                request_id=request.request_id,
                error=str(e),
                latency_ms=latency,
            )

    @property
    def call_count(self) -> int:
        """Return total backend calls made."""
        return self._call_count


class RemoteBackend(MFNBackend):
    """gRPC/REST client for remote MFN service.

    Connects to MFN core via network protocol.

    Attributes:
        endpoint: MFN service endpoint URL
        protocol: Connection protocol ('grpc' or 'rest')
        api_key: Optional API key for authentication
    """

    def __init__(
        self,
        endpoint: str,
        *,
        protocol: str = "grpc",
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize remote backend.

        Args:
            endpoint: MFN service URL
            protocol: 'grpc' or 'rest'
            api_key: Optional authentication key
            timeout: Request timeout in seconds
        """
        self.endpoint = endpoint
        self.protocol = protocol.lower()
        self.api_key = api_key
        self.timeout = timeout

        self._client: Any = None
        self._call_count = 0

    async def _get_client(self) -> Any:
        """Get or create HTTP/gRPC client."""
        if self._client is None:
            import httpx

            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            self._client = httpx.AsyncClient(
                base_url=self.endpoint,
                headers=headers,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def extract_features(self, request: MFNRequest) -> BackendResult:
        """Extract features via remote service.

        Args:
            request: Feature extraction request

        Returns:
            BackendResult with extracted features
        """
        start = datetime.now(timezone.utc)

        try:
            self._call_count += 1
            client = await self._get_client()

            if self.protocol == "rest":
                response = await client.post(
                    "/api/v1/features/extract",
                    json={
                        "request_id": request.request_id,
                        "seeds": request.seeds,
                        "grid_size": request.grid_size,
                        "params": request.params,
                    },
                )
                response.raise_for_status()
                result = response.json()
            else:
                # gRPC stub - would use generated client
                raise NotImplementedError("gRPC client not implemented")

            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            return BackendResult(
                success=True,
                request_id=request.request_id,
                result=result,
                latency_ms=latency,
            )

        except Exception as e:
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            logger.error(f"Remote feature extraction failed: {e}")
            return BackendResult(
                success=False,
                request_id=request.request_id,
                error=str(e),
                latency_ms=latency,
            )

    async def run_simulation(self, request: MFNRequest) -> BackendResult:
        """Run simulation via remote service.

        Args:
            request: Simulation request

        Returns:
            BackendResult with simulation results
        """
        start = datetime.now(timezone.utc)

        try:
            self._call_count += 1
            client = await self._get_client()

            if self.protocol == "rest":
                response = await client.post(
                    "/api/v1/simulation/run",
                    json={
                        "request_id": request.request_id,
                        "seeds": request.seeds,
                        "grid_size": request.grid_size,
                        "params": request.params,
                    },
                )
                response.raise_for_status()
                result = response.json()
            else:
                # gRPC stub
                raise NotImplementedError("gRPC client not implemented")

            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000

            return BackendResult(
                success=True,
                request_id=request.request_id,
                result=result,
                latency_ms=latency,
            )

        except Exception as e:
            latency = (datetime.now(timezone.utc) - start).total_seconds() * 1000
            logger.error(f"Remote simulation failed: {e}")
            return BackendResult(
                success=False,
                request_id=request.request_id,
                error=str(e),
                latency_ms=latency,
            )

    async def close(self) -> None:
        """Close HTTP/gRPC client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None


@dataclass
class IngestionStats:
    """Statistics from ingestion run.

    Attributes:
        events_received: Total events from ingestor
        events_processed: Successfully processed events
        events_failed: Failed event count
        normalization_errors: Normalization failure count
        mapping_errors: Mapping failure count
        backend_errors: Backend call failures
        total_latency_ms: Cumulative processing time
    """

    events_received: int = 0
    events_processed: int = 0
    events_failed: int = 0
    normalization_errors: int = 0
    mapping_errors: int = 0
    backend_errors: int = 0
    total_latency_ms: float = 0.0
    start_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class IngestionRunner:
    """Orchestrator for MFN data ingestion pipeline.

    Connects an ingestor to an MFN backend, handling:
    - Event normalization and transformation
    - Request dispatch to backend
    - Micro-batching and backpressure
    - Graceful shutdown

    Attributes:
        ingestor: Data source connector
        backend: MFN processing backend
        transformer: Event transformation pipeline
        mode: Processing mode ('feature' or 'simulation')
        batch_size: Events per batch
    """

    def __init__(
        self,
        ingestor: BaseIngestor,
        backend: MFNBackend,
        *,
        transformer: Transformer | None = None,
        mode: str = "feature",
        batch_size: int = 10,
        max_queue_size: int = 1000,
    ) -> None:
        """Initialize ingestion runner.

        Args:
            ingestor: Data source connector
            backend: MFN processing backend
            transformer: Optional custom transformer
            mode: 'feature' or 'simulation'
            batch_size: Events to batch before processing
            max_queue_size: Maximum queue depth for backpressure
        """
        self.ingestor = ingestor
        self.backend = backend
        self.transformer = transformer or Transformer()
        self.mode = mode
        self.batch_size = batch_size
        self.max_queue_size = max_queue_size

        self._running = False
        self._stats = IngestionStats()
        self._queue: asyncio.Queue[RawEvent] = asyncio.Queue(maxsize=max_queue_size)
        self._results: list[BackendResult] = []

    async def run(self, *, max_events: int | None = None) -> IngestionStats:
        """Run the ingestion pipeline.

        Args:
            max_events: Optional limit on events to process

        Returns:
            IngestionStats with run statistics
        """
        self._running = True
        self._stats = IngestionStats()

        logger.info(
            f"Starting ingestion: mode={self.mode}, batch_size={self.batch_size}"
        )

        try:
            await self.ingestor.connect()

            batch: list[RawEvent] = []

            async for event in self.ingestor.fetch():
                if not self._running:
                    break

                if max_events and self._stats.events_received >= max_events:
                    break

                self._stats.events_received += 1
                batch.append(event)

                if len(batch) >= self.batch_size:
                    await self._process_batch(batch)
                    batch = []

            # Process remaining events
            if batch:
                await self._process_batch(batch)

        except asyncio.CancelledError:
            logger.info("Ingestion cancelled")
        except Exception as e:
            logger.error(f"Ingestion error: {e}")
            raise
        finally:
            await self._shutdown()

        return self._stats

    async def _process_batch(self, events: list[RawEvent]) -> None:
        """Process a batch of events.

        Args:
            events: Batch of raw events to process
        """
        tasks = []

        for event in events:
            try:
                normalized = self.transformer.normalize(event)

                if self.mode == "feature":
                    request = self.transformer.to_feature_request(normalized)
                else:
                    request = self.transformer.to_simulation_request(normalized)

                tasks.append(self._execute_request(request))

            except NormalizationError as e:
                self._stats.normalization_errors += 1
                self._stats.events_failed += 1
                logger.warning(f"Normalization error: {e}")

            except MappingError as e:
                self._stats.mapping_errors += 1
                self._stats.events_failed += 1
                logger.warning(f"Mapping error: {e}")

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    self._stats.backend_errors += 1
                    self._stats.events_failed += 1
                    logger.warning(f"Backend error during batch processing: {result}")
                elif isinstance(result, BackendResult):
                    self._results.append(result)
                    if result.success:
                        self._stats.events_processed += 1
                        self._stats.total_latency_ms += result.latency_ms
                    else:
                        self._stats.backend_errors += 1
                        self._stats.events_failed += 1

    async def _execute_request(self, request: MFNRequest) -> BackendResult:
        """Execute single request on backend.

        Args:
            request: MFN request to execute

        Returns:
            BackendResult from execution
        """
        if request.request_type == "feature":
            return await self.backend.extract_features(request)
        else:
            return await self.backend.run_simulation(request)

    async def _shutdown(self) -> None:
        """Graceful shutdown of pipeline."""
        self._running = False

        try:
            await self.ingestor.close()
        except Exception as e:
            logger.warning(f"Error closing ingestor: {e}")

        try:
            await self.backend.close()
        except Exception as e:
            logger.warning(f"Error closing backend: {e}")

        logger.info(
            f"Ingestion complete: received={self._stats.events_received}, "
            f"processed={self._stats.events_processed}, "
            f"failed={self._stats.events_failed}"
        )

    def stop(self) -> None:
        """Signal the runner to stop."""
        self._running = False

    @property
    def stats(self) -> IngestionStats:
        """Return current ingestion statistics."""
        return self._stats

    @property
    def results(self) -> list[BackendResult]:
        """Return collected backend results."""
        return self._results
