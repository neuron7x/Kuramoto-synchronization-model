# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Utilities for sampling runtime metrics for the API service."""

from __future__ import annotations

import asyncio
import logging
import math
import os
import sys
from contextlib import suppress
from typing import Any

from core.utils.metrics import MetricsCollector

try:  # pragma: no cover - psutil is optional in certain environments
    import psutil
except ImportError:  # pragma: no cover - defensive fallback when psutil missing
    psutil = None

try:  # pragma: no cover - resource is POSIX-only
    import resource
except ImportError:  # pragma: no cover - gracefully degrade on non-POSIX systems
    resource = None  # type: ignore[assignment]


LOGGER = logging.getLogger("geosync.api.metrics")


class MetricsSampler:
    """Background sampler that publishes process and queue metrics."""

    def __init__(
        self,
        collector: MetricsCollector,
        *,
        process_label: str = "inference_api",
        sample_interval: float | None = None,
    ) -> None:
        self._collector = collector
        self._process_label = process_label
        default_interval = float(os.getenv("GEOSYNC_METRICS_SAMPLER_INTERVAL", "5"))
        interval = sample_interval if sample_interval is not None else default_interval
        self._interval = max(1.0, float(interval))
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._psutil_process = self._initialise_psutil_process()

    def start(self) -> None:
        """Start the sampler if metrics are enabled."""

        if not self._collector.enabled:
            return
        if self._task is not None and not self._task.done():
            return

        loop = asyncio.get_running_loop()
        self._stopped.clear()
        self._task = loop.create_task(self._run(), name="metrics-sampler")

    async def stop(self) -> None:
        """Stop the sampler and wait for shutdown."""

        if self._task is None:
            return

        self._stopped.set()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def sample_once(self) -> None:
        """Collect a single sample immediately (useful for tests)."""

        if not self._collector.enabled:
            return
        loop = asyncio.get_running_loop()
        self._collect_metrics(loop)

    @property
    def interval(self) -> float:
        """Return the configured sampling interval in seconds."""

        return self._interval

    @property
    def is_running(self) -> bool:
        """Indicate whether the sampler task is active."""

        return self._task is not None and not self._task.done()

    async def _run(self) -> None:
        loop = asyncio.get_running_loop()
        while not self._stopped.is_set():
            try:
                self._collect_metrics(loop)
            except Exception:  # pragma: no cover - defensive guard
                LOGGER.exception("Failed to sample runtime metrics")
            try:
                await asyncio.wait_for(self._stopped.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                continue

    def _collect_metrics(self, loop: asyncio.AbstractEventLoop) -> None:
        self._sample_process_metrics()
        self._sample_event_loop_metrics(loop)

    def _initialise_psutil_process(self) -> Any | None:
        if psutil is None:
            return None
        try:
            process = psutil.Process()
            process.cpu_percent(interval=None)  # Prime measurement window
            return process
        except Exception:  # pragma: no cover - psutil quirks should not abort startup
            LOGGER.debug("Failed to initialise psutil process", exc_info=True)
            return None

    def _sample_process_metrics(self) -> None:
        cpu_percent: float | None = None
        memory_bytes: float | None = None
        memory_percent: float | None = None

        if self._psutil_process is not None:
            try:
                cpu_percent = float(self._psutil_process.cpu_percent(interval=None))
                mem_info = self._psutil_process.memory_info()
                memory_bytes = float(mem_info.rss)
                memory_percent = float(self._psutil_process.memory_percent())
            except Exception:  # pragma: no cover - psutil failures should not crash
                LOGGER.debug("psutil sampling failed", exc_info=True)

        if memory_bytes is None and resource is not None:
            try:
                usage = resource.getrusage(resource.RUSAGE_SELF)
                # ru_maxrss is KiB on Linux, bytes on macOS. Normalise to bytes.
                memory_bytes = float(usage.ru_maxrss)
                if os.name == "posix" and sys.platform != "darwin":
                    memory_bytes *= 1024.0
            except Exception:  # pragma: no cover - defensive
                LOGGER.debug("resource sampling failed", exc_info=True)

        self._collector.set_process_resource_usage(
            self._process_label,
            cpu_percent=cpu_percent,
            memory_bytes=memory_bytes,
            memory_percent=memory_percent,
        )

    def _sample_event_loop_metrics(self, loop: asyncio.AbstractEventLoop) -> None:
        ready = getattr(loop, "_ready", None)
        if ready is not None:
            self._collector.set_queue_depth("event_loop_ready", len(ready))

        scheduled = getattr(loop, "_scheduled", None)
        max_overdue = 0.0
        if scheduled is not None:
            handles = list(scheduled)
            self._collector.set_queue_depth("event_loop_scheduled", len(handles))
            now = loop.time()
            for handle in handles:
                when = getattr(handle, "_when", None)
                if when is None:
                    continue
                overdue = now - float(when)
                if overdue > max_overdue:
                    max_overdue = overdue

        tasks = asyncio.all_tasks(loop=loop)
        current = asyncio.current_task(loop=loop)
        if current in tasks:
            tasks.discard(current)
        self._collector.set_queue_depth("event_loop_tasks", len(tasks))

        if max_overdue > 0.0 and math.isfinite(max_overdue):
            self._collector.observe_queue_latency("event_loop_scheduled", max_overdue)


__all__ = ["MetricsSampler"]
