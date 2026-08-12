# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Base primitives shared across GeoSync microservices."""

from __future__ import annotations

import math
import random
import time
from collections import deque
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Iterator, Mapping, MutableMapping, Sequence, TypeVar

from application.microservices.contracts import (
    RetryPolicy,
    ServiceInteractionContract,
    ServiceLevelAgreement,
)
from observability.tracing import Status, StatusCode, get_tracer

T = TypeVar("T")


class ServiceState(str, Enum):
    """Lifecycle states exposed by a microservice."""

    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


@dataclass(slots=True)
class ServiceHealth:
    """Lightweight health report emitted by a microservice."""

    name: str
    state: ServiceState
    healthy: bool
    detail: str | None = None
    metadata: Mapping[str, object] | None = None


class Microservice:
    """Canonical base class encapsulating lifecycle and health reporting."""

    def __init__(self, name: str) -> None:
        self._name = name
        self._state = ServiceState.STOPPED
        self._last_error: str | None = None
        self._tracer = get_tracer(f"geosync.microservice.{name}")
        self._operation_stats: MutableMapping[str, _OperationStats] = {}
        self._operation_contracts: MutableMapping[str, ServiceInteractionContract] = {}

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> ServiceState:
        return self._state

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def start(self) -> None:
        """Mark the service as ready to accept work."""

        self._state = ServiceState.RUNNING
        self._last_error = None

    def stop(self) -> None:
        """Transition the service into an idle state."""

        self._state = ServiceState.STOPPED

    def health(self) -> ServiceHealth:
        """Return a snapshot of the service's current health."""

        metadata = self._health_metadata()
        operation_metrics = self._operation_metrics_snapshot()
        if operation_metrics:
            merged: dict[str, object] = dict(metadata or {})
            merged["operations"] = operation_metrics
            metadata = merged
        return ServiceHealth(
            name=self._name,
            state=self._state,
            healthy=self._state is ServiceState.RUNNING and self._last_error is None,
            detail=self._last_error,
            metadata=metadata if metadata else None,
        )

    def _ensure_active(self) -> None:
        if self._state is ServiceState.STOPPED:
            raise RuntimeError(f"Service '{self._name}' is not running")

    def _mark_healthy(self) -> None:
        if self._state is not ServiceState.STOPPED:
            self._state = ServiceState.RUNNING
        self._last_error = None

    def _mark_error(self, error: Exception) -> None:
        self._state = ServiceState.ERROR
        self._last_error = str(error)

    def _health_metadata(self) -> Mapping[str, object] | None:
        """Hook allowing subclasses to attach observability metadata."""

        return None

    def _operation_contract(self, operation: str) -> ServiceInteractionContract | None:
        return self._operation_contracts.get(operation)

    @contextmanager
    def _operation_context(
        self,
        operation: str,
        *,
        attributes: Mapping[str, Any] | None = None,
    ) -> Iterator[Any]:
        tracer_cm = getattr(self._tracer, "start_as_current_span", None)
        context = tracer_cm(f"{self._name}.{operation}") if tracer_cm else nullcontext()
        start = time.perf_counter()
        success = False
        error: Exception | None = None
        with context as span:
            if attributes:
                setter = getattr(span, "set_attributes", None)
                if callable(setter):
                    try:
                        setter(dict(attributes))
                    except Exception:  # pragma: no cover - defensive
                        pass
            try:
                yield span
            except Exception as exc:
                error = exc
                recorder = getattr(span, "record_exception", None)
                if callable(recorder):
                    try:
                        recorder(exc)
                    except Exception:  # pragma: no cover - defensive
                        pass
                if Status and StatusCode:
                    setter = getattr(span, "set_status", None)
                    if callable(setter):
                        try:  # pragma: no cover - depends on otel install
                            setter(Status(StatusCode.ERROR, str(exc)))
                        except Exception:
                            pass
                raise
            else:
                success = True
                if Status and StatusCode:
                    setter = getattr(span, "set_status", None)
                    if callable(setter):
                        try:  # pragma: no cover - depends on otel install
                            setter(Status(StatusCode.OK))
                        except Exception:
                            pass
            finally:
                duration = time.perf_counter() - start
                self._record_operation_metrics(
                    operation,
                    duration,
                    success,
                    error=error,
                )

    def _mark_idempotent_replay(self, operation: str) -> None:
        stats = self._operation_stats.setdefault(operation, _OperationStats())
        stats.replays += 1

    def _record_operation_metrics(
        self,
        operation: str,
        duration_seconds: float,
        success: bool,
        *,
        error: Exception | None = None,
    ) -> None:
        stats = self._operation_stats.setdefault(operation, _OperationStats())
        stats.record(duration_seconds, success, error=error)

    def _execute_with_retries(
        self,
        func: Callable[[], T],
        policy: RetryPolicy | None,
    ) -> T:
        if policy is None or policy.max_attempts <= 1:
            return func()
        attempt = 0
        delay = max(policy.initial_interval_seconds, 0.0)
        max_interval = policy.max_interval_seconds or delay
        while True:
            attempt += 1
            try:
                return func()
            except Exception:
                if attempt >= policy.max_attempts:
                    raise
                sleep_for = delay + random.uniform(0.0, policy.jitter_seconds)
                time.sleep(max(sleep_for, 0.0))
                delay = min(delay * policy.backoff_multiplier, max_interval)

    def _operation_metrics_snapshot(self) -> Mapping[str, Mapping[str, Any]]:
        snapshot: dict[str, Mapping[str, Any]] = {}
        for operation, stats in self._operation_stats.items():
            contract = self._operation_contract(operation)
            sla = contract.sla if contract else None
            snapshot[operation] = stats.snapshot(sla)
        return snapshot

    @contextmanager
    def lifecycle(self) -> Iterator["Microservice"]:
        """Context manager that starts and stops the service automatically."""

        self.start()
        try:
            yield self
        finally:
            self.stop()


@dataclass(slots=True)
class _OperationStats:
    latencies: deque[float] = field(default_factory=lambda: deque(maxlen=256))
    successes: int = 0
    failures: int = 0
    replays: int = 0
    last_error: str | None = None

    def record(self, duration: float, success: bool, *, error: Exception | None) -> None:
        self.latencies.append(duration)
        if success:
            self.successes += 1
            self.last_error = None
        else:
            self.failures += 1
            if error is not None:
                self.last_error = str(error)

    def snapshot(self, sla: ServiceLevelAgreement | None) -> dict[str, Any]:
        total = self.successes + self.failures
        success_rate = self.successes / total if total else 1.0
        latencies_ms = [value * 1000.0 for value in self.latencies]
        last_latency_ms = latencies_ms[-1] if latencies_ms else None
        p95_latency_ms = _percentile(latencies_ms, 0.95)
        payload: dict[str, Any] = {
            "successes": self.successes,
            "failures": self.failures,
            "replays": self.replays,
            "success_rate": round(success_rate, 6),
            "last_latency_ms": last_latency_ms,
            "p95_latency_ms": p95_latency_ms,
            "last_error": self.last_error,
        }
        if sla:
            payload["sla"] = _evaluate_sla(sla, payload)
        return payload


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    if not 0.0 <= percentile <= 1.0:
        raise ValueError("percentile must be within [0.0, 1.0]")
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[min(index, len(ordered) - 1)]


def _evaluate_sla(
    sla: ServiceLevelAgreement,
    metrics: Mapping[str, Any],
) -> dict[str, Any]:
    indicators: list[dict[str, Any]] = []
    for indicator in sla.indicators:
        observed = metrics.get(indicator.metric)
        breached = False
        if observed is None:
            status = "insufficient_data"
        elif indicator.threshold_type == "lte":
            breached = bool(observed > indicator.target)
            status = "breached" if breached else "healthy"
        else:
            breached = bool(observed < indicator.target)
            status = "breached" if breached else "healthy"
        indicators.append(
            {
                "name": indicator.name,
                "metric": indicator.metric,
                "target": indicator.target,
                "observed": observed,
                "status": status,
                "description": indicator.description,
            }
        )
    return {"name": sla.name, "description": sla.description, "indicators": indicators}
