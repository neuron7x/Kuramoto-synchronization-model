# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Reusable health check probes for GeoSync subsystems."""

from __future__ import annotations

from typing import List

from application.system import GeoSyncSystem
from core.compat import utc_now

from .health_monitor import HealthCheck, HealthCheckResult


def evaluate_data_pipeline_health(
    system: GeoSyncSystem,
    *,
    stale_after_seconds: float = 300.0,
) -> HealthCheckResult:
    """Return health status for the ingestion pipeline."""

    now = utc_now()
    metrics: dict[str, object] = {}
    last_completed = system.last_ingestion_completed_at
    if last_completed is not None:
        age = (now - last_completed).total_seconds()
        metrics["seconds_since_last_ingest"] = round(age, 2)
        duration = system.last_ingestion_duration_seconds or 0.0
        metrics["last_duration_seconds"] = round(duration, 4)
        if system.last_ingestion_symbol:
            metrics["symbol"] = system.last_ingestion_symbol
    else:
        age = None

    if system.last_ingestion_error:
        metrics["last_error"] = system.last_ingestion_error
        return HealthCheckResult(False, "Last ingestion failed", metrics)

    if last_completed is None:
        return HealthCheckResult(False, "No ingestion has completed yet", metrics)

    assert age is not None
    if age > stale_after_seconds:
        return HealthCheckResult(False, f"Ingestion stale for {int(age)}s", metrics)

    return HealthCheckResult(True, metrics=metrics)


def evaluate_signal_pipeline_health(
    system: GeoSyncSystem,
    *,
    stale_after_seconds: float = 180.0,
) -> HealthCheckResult:
    """Return health status for signal generation."""

    now = utc_now()
    metrics: dict[str, object] = {}
    last_generated = system.last_signal_generated_at
    if last_generated is not None:
        age = (now - last_generated).total_seconds()
        metrics["seconds_since_last_signal"] = round(age, 2)
        latency = system.last_signal_latency_seconds or 0.0
        metrics["last_latency_seconds"] = round(latency, 4)
    else:
        age = None

    if system.last_signal_error:
        metrics["last_error"] = system.last_signal_error
        return HealthCheckResult(False, "Last signal generation failed", metrics)

    if last_generated is None:
        return HealthCheckResult(False, "No signals have been generated", metrics)

    assert age is not None
    if age > stale_after_seconds:
        return HealthCheckResult(False, f"Signals stale for {int(age)}s", metrics)

    return HealthCheckResult(True, metrics=metrics)


def evaluate_execution_health(
    system: GeoSyncSystem,
    *,
    stale_after_seconds: float = 90.0,
) -> HealthCheckResult:
    """Return health status for live execution."""

    loop = system.live_loop
    metrics: dict[str, object] = {}
    if loop is None:
        return HealthCheckResult(False, "Live execution loop not initialised", metrics)

    metrics["started"] = loop.started
    if not loop.started:
        return HealthCheckResult(False, "Live execution loop not started", metrics)

    if system.last_execution_error:
        metrics["last_error"] = system.last_execution_error
        return HealthCheckResult(False, "Last execution submission failed", metrics)

    snapshot = loop.watchdog_snapshot()
    if snapshot is not None:
        probe_ok = snapshot.get("live_probe_ok")
        if probe_ok is False:
            metrics["watchdog_live_probe_ok"] = probe_ok
            return HealthCheckResult(False, "Watchdog live probe failed", metrics)
        workers = snapshot.get("workers", {})
        worker_states = {name: bool(state.get("alive")) for name, state in workers.items()}
        worker_restarts = {name: int(state.get("restarts", 0)) for name, state in workers.items()}
        metrics["worker_alive"] = worker_states
        metrics["worker_restarts"] = worker_restarts
        unhealthy = [name for name, alive in worker_states.items() if not alive]
        if unhealthy:
            return HealthCheckResult(
                False, f"Workers not running: {', '.join(sorted(unhealthy))}", metrics
            )

    now = utc_now()
    last_submission = system.last_execution_submission_at
    if last_submission is not None:
        age = (now - last_submission).total_seconds()
        metrics["seconds_since_last_submission"] = round(age, 2)
        if age > stale_after_seconds:
            return HealthCheckResult(False, f"No order submissions in {int(age)}s", metrics)

    return HealthCheckResult(True, metrics=metrics)


def build_default_health_checks(
    system: GeoSyncSystem,
    *,
    data_stale_after: float = 300.0,
    signal_stale_after: float = 180.0,
    execution_stale_after: float = 90.0,
) -> List[HealthCheck]:
    """Return a curated set of periodic health checks for core subsystems."""

    checks: List[HealthCheck] = []

    checks.append(
        HealthCheck(
            name="data_pipeline",
            probe=lambda: evaluate_data_pipeline_health(
                system, stale_after_seconds=data_stale_after
            ),
            interval=max(15.0, data_stale_after / 3.0),
        )
    )

    checks.append(
        HealthCheck(
            name="signal_pipeline",
            probe=lambda: evaluate_signal_pipeline_health(
                system, stale_after_seconds=signal_stale_after
            ),
            interval=max(10.0, signal_stale_after / 3.0),
        )
    )

    checks.append(
        HealthCheck(
            name="execution",
            probe=lambda: evaluate_execution_health(
                system, stale_after_seconds=execution_stale_after
            ),
            interval=max(10.0, execution_stale_after / 3.0),
        )
    )

    return checks


__all__ = [
    "build_default_health_checks",
    "evaluate_data_pipeline_health",
    "evaluate_execution_health",
    "evaluate_signal_pipeline_health",
]
