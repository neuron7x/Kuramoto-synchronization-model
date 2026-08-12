# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Chaos engineering experiment definitions.

This module provides a flexible abstraction for describing chaos experiments that
can be orchestrated inside the GeoSync test-suite.  The implementation is
framework agnostic and can be adapted to Chaos Toolkit style controls or custom
infrastructure adapters.  Each scenario focuses on a specific failure mode while
sharing common post-conditions that encode the project's resilience objectives.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, Sequence

# ---------------------------------------------------------------------------
# Controller protocols
# ---------------------------------------------------------------------------


class NetworkController(Protocol):
    """Controls traffic shaping for network related chaos."""

    def inject_latency(self, latency_ms: int, jitter_ms: int, duration_s: float) -> None:
        """Introduce latency with optional jitter for the provided duration."""

    def reset(self) -> None:
        """Remove previously configured network disruptions."""


class ExchangeController(Protocol):
    """Controls exchange level failure scenarios."""

    def inject_failure_rate(self, failure_ratio: float, duration_s: float) -> None:
        """Force the exchange API to fail for the provided share of requests."""

    def reset(self) -> None:
        """Restore exchange connectivity."""


class DatabaseController(Protocol):
    """Controls database connectivity chaos."""

    def drop_connections(self, drop_ratio: float, duration_s: float) -> None:
        """Forcefully drop a percentage of existing database connections."""

    def reset(self) -> None:
        """Restore normal database connectivity."""


class SystemResourceController(Protocol):
    """Controls host level resource pressure experiments."""

    def apply_memory_pressure(self, target_bytes: int, duration_s: float) -> None:
        """Consume approximately ``target_bytes`` memory for ``duration_s`` seconds."""

    def apply_cpu_throttle(self, throttle_percent: float, duration_s: float) -> None:
        """Throttle CPU availability by the provided percentage."""

    def reset(self) -> None:
        """Return the system resources to baseline conditions."""


class MonitoringClient(Protocol):
    """Observability interface used to validate experiment outcomes."""

    def record_event(self, name: str, **details: Any) -> None:
        """Persist experiment events for traceability."""

    def data_corruption_detected(self) -> bool:
        """Report whether any data corruption was observed."""

    def recovery_time_seconds(self) -> float:
        """Return the most recent recovery time in seconds."""

    def exchange_survival_ratio(self) -> float:
        """Return the percentage of requests that successfully reached an exchange."""

    def detect_cascading_failures(self) -> Sequence[str]:
        """Return a list of detected cascading failure signals."""


class SteadyStateVerifier(Protocol):
    """Interface for automated steady state verification."""

    def snapshot(self) -> Any:
        """Capture the current steady-state reference."""

    def verify(self, baseline: Any) -> bool:
        """Validate that the system remains consistent with the baseline."""


# ---------------------------------------------------------------------------
# Core data classes
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ChaosContext:
    """Runtime context supplied to experiment steps."""

    network: NetworkController
    exchange: ExchangeController
    database: DatabaseController
    system: SystemResourceController
    monitoring: MonitoringClient
    steady_state: SteadyStateVerifier
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], float] = time.perf_counter
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("chaos.experiments"))

    def log(self, message: str, **extra: Any) -> None:
        """Emit a structured log entry for the running experiment."""

        if extra:
            formatted = ", ".join(f"{key}={value}" for key, value in extra.items())
            message = f"{message} | {formatted}"
        self.logger.info(message)


@dataclass(slots=True)
class ScenarioStep:
    """Single executable action within a chaos scenario."""

    name: str
    action: Callable[[ChaosContext], None]
    description: str = ""

    def run(self, context: ChaosContext) -> None:
        context.log("Executing step", step=self.name, description=self.description)
        self.action(context)


@dataclass(slots=True)
class MetricResult:
    name: str
    success: bool
    description: str = ""


@dataclass(slots=True)
class MetricCheck:
    """Post-condition ensuring that resilience objectives were satisfied."""

    name: str
    evaluator: Callable[[ChaosContext], bool]
    description: str = ""

    def evaluate(self, context: ChaosContext) -> MetricResult:
        success = self.evaluator(context)
        context.log(
            "Metric evaluated",
            metric=self.name,
            success=success,
            description=self.description,
        )
        return MetricResult(name=self.name, success=success, description=self.description)


@dataclass(slots=True)
class DetectionResult:
    """Outcome from running a cascading failure detection routine."""

    success: bool
    details: Sequence[str] = ()


@dataclass(slots=True)
class ChaosOutcome:
    """Result of executing a chaos scenario."""

    name: str
    elapsed_seconds: float
    steady_state_ok: bool
    metrics: Sequence[MetricResult]
    detection: Optional[DetectionResult]

    @property
    def success(self) -> bool:
        metric_success = all(metric.success for metric in self.metrics)
        detection_success = True if self.detection is None else self.detection.success
        return metric_success and detection_success and self.steady_state_ok


@dataclass(slots=True)
class ChaosScenario:
    """A named collection of steps, verifications, and optional detection hooks."""

    name: str
    steps: Sequence[ScenarioStep]
    verifications: Sequence[MetricCheck]
    description: str = ""
    detection: Optional[Callable[[ChaosContext], DetectionResult]] = None

    def execute(self, context: ChaosContext) -> ChaosOutcome:
        context.log("Starting scenario", scenario=self.name, description=self.description)
        baseline = context.steady_state.snapshot()
        start = context.clock()
        for step in self.steps:
            step.run(context)
        detection_result = self.detection(context) if self.detection else None
        metrics = [metric.evaluate(context) for metric in self.verifications]
        steady_state_ok = context.steady_state.verify(baseline)
        elapsed = context.clock() - start
        outcome = ChaosOutcome(
            name=self.name,
            elapsed_seconds=elapsed,
            steady_state_ok=steady_state_ok,
            metrics=metrics,
            detection=detection_result,
        )
        context.log(
            "Scenario completed",
            scenario=self.name,
            success=outcome.success,
            elapsed_seconds=f"{elapsed:.3f}",
        )
        return outcome


@dataclass(slots=True)
class ChaosExperimentSuite:
    """Collection of chaos scenarios that can be executed sequentially."""

    scenarios: Sequence[ChaosScenario]

    def run(self, context: ChaosContext) -> Sequence[ChaosOutcome]:
        context.log("Running chaos experiment suite", scenario_count=len(self.scenarios))
        return tuple(scenario.execute(context) for scenario in self.scenarios)


# ---------------------------------------------------------------------------
# Metric helpers aligned with the GeoSync resilience objectives
# ---------------------------------------------------------------------------


def zero_data_corruption_metric() -> MetricCheck:
    """Ensure that no data corruption signals were emitted."""

    return MetricCheck(
        name="zero-data-corruption",
        description="Data integrity must be preserved during chaos execution.",
        evaluator=lambda context: not context.monitoring.data_corruption_detected(),
    )


def recovery_time_metric(max_seconds: float = 300.0) -> MetricCheck:
    """Ensure the recovery time objective (RTO) is satisfied."""

    description = (
        "System must recover faster than the agreed Service Level Objective"
        f" ({max_seconds} seconds)."
    )
    return MetricCheck(
        name="recovery-time",
        description=description,
        evaluator=lambda context: context.monitoring.recovery_time_seconds() <= max_seconds,
    )


def exchange_survival_metric(min_ratio: float = 0.5) -> MetricCheck:
    """Ensure that at least ``min_ratio`` of exchange requests succeed."""

    description = (
        "The trading system must survive exchange degradation with at least"
        f" {int(min_ratio * 100)}% successful requests."
    )
    return MetricCheck(
        name="exchange-survival",
        description=description,
        evaluator=lambda context: context.monitoring.exchange_survival_ratio() >= min_ratio,
    )


# ---------------------------------------------------------------------------
# Scenario factories
# ---------------------------------------------------------------------------


def build_network_latency_experiment(
    latency_ms: int = 250,
    jitter_ms: int = 50,
    duration_s: float = 60.0,
) -> ChaosScenario:
    """Create a network latency injection scenario."""

    def disruption(context: ChaosContext) -> None:
        context.log(
            "Injecting network latency",
            latency_ms=latency_ms,
            jitter_ms=jitter_ms,
            duration_s=duration_s,
        )
        context.network.inject_latency(latency_ms, jitter_ms, duration_s)
        context.sleep(duration_s)
        context.network.reset()

    steps = (
        ScenarioStep(
            name="network-latency-injection",
            description="Introduce deterministic latency and verify graceful degradation.",
            action=disruption,
        ),
    )

    verifications: Sequence[MetricCheck] = (
        zero_data_corruption_metric(),
        recovery_time_metric(),
    )
    return ChaosScenario(
        name="network-latency-injection",
        description="Validates resilience against adverse network conditions.",
        steps=steps,
        verifications=verifications,
    )


def build_exchange_api_failure_experiment(
    failure_ratio: float = 0.5,
    duration_s: float = 120.0,
) -> ChaosScenario:
    """Simulate exchange API failures to confirm graceful degradation."""

    if not 0.0 < failure_ratio <= 1.0:
        raise ValueError("failure_ratio must be within (0.0, 1.0].")

    def disruption(context: ChaosContext) -> None:
        context.log(
            "Injecting exchange API failures",
            failure_ratio=failure_ratio,
            duration_s=duration_s,
        )
        context.exchange.inject_failure_rate(failure_ratio, duration_s)
        context.sleep(duration_s)
        context.exchange.reset()

    steps = (
        ScenarioStep(
            name="exchange-api-failure",
            description="Simulate exchange outages to assess failover strategies.",
            action=disruption,
        ),
    )

    verifications = (
        zero_data_corruption_metric(),
        recovery_time_metric(),
        exchange_survival_metric(min_ratio=failure_ratio),
    )

    return ChaosScenario(
        name="exchange-api-failure",
        description="Ensures the trading stack survives exchange level disruptions.",
        steps=steps,
        verifications=verifications,
    )


def build_database_connection_drop_experiment(
    drop_ratio: float = 0.4,
    duration_s: float = 90.0,
) -> ChaosScenario:
    """Test behaviour when database connections are abruptly terminated."""

    if not 0.0 < drop_ratio <= 1.0:
        raise ValueError("drop_ratio must be within (0.0, 1.0].")

    def disruption(context: ChaosContext) -> None:
        context.log(
            "Dropping database connections",
            drop_ratio=drop_ratio,
            duration_s=duration_s,
        )
        context.database.drop_connections(drop_ratio, duration_s)
        context.sleep(duration_s)
        context.database.reset()

    steps = (
        ScenarioStep(
            name="database-connection-drop",
            description="Force termination of pooled connections to test resilience.",
            action=disruption,
        ),
    )

    verifications = (
        zero_data_corruption_metric(),
        recovery_time_metric(),
    )

    return ChaosScenario(
        name="database-connection-drop",
        description="Validates recovery from transient database connectivity issues.",
        steps=steps,
        verifications=verifications,
    )


def build_memory_pressure_experiment(
    target_bytes: int = 2 * 1024 * 1024 * 1024,
    duration_s: float = 45.0,
) -> ChaosScenario:
    """Generate controlled memory pressure within the application host."""

    if target_bytes <= 0:
        raise ValueError("target_bytes must be positive.")

    def disruption(context: ChaosContext) -> None:
        context.log(
            "Applying memory pressure",
            target_bytes=target_bytes,
            duration_s=duration_s,
        )
        context.system.apply_memory_pressure(target_bytes, duration_s)
        context.sleep(duration_s)
        context.system.reset()

    steps = (
        ScenarioStep(
            name="memory-pressure",
            description="Allocate large working sets to observe GC and paging behaviour.",
            action=disruption,
        ),
    )

    verifications = (
        zero_data_corruption_metric(),
        recovery_time_metric(),
    )

    return ChaosScenario(
        name="memory-pressure",
        description="Assesses system performance under constrained memory resources.",
        steps=steps,
        verifications=verifications,
    )


def build_cpu_throttling_experiment(
    throttle_percent: float = 0.7,
    duration_s: float = 60.0,
) -> ChaosScenario:
    """Throttle CPU availability to validate autoscaling and prioritisation."""

    if not 0.0 < throttle_percent <= 1.0:
        raise ValueError("throttle_percent must be within (0.0, 1.0].")

    def disruption(context: ChaosContext) -> None:
        context.log(
            "Applying CPU throttling",
            throttle_percent=throttle_percent,
            duration_s=duration_s,
        )
        context.system.apply_cpu_throttle(throttle_percent, duration_s)
        context.sleep(duration_s)
        context.system.reset()

    steps = (
        ScenarioStep(
            name="cpu-throttling",
            description="Reduce CPU headroom to evaluate scheduling fairness.",
            action=disruption,
        ),
    )

    verifications = (
        zero_data_corruption_metric(),
        recovery_time_metric(),
    )

    return ChaosScenario(
        name="cpu-throttling",
        description="Ensures services remain stable under CPU contention.",
        steps=steps,
        verifications=verifications,
    )


def build_cascading_failure_detection_experiment(
    exchange_failure_ratio: float = 0.6,
    database_drop_ratio: float = 0.3,
    duration_s: float = 75.0,
) -> ChaosScenario:
    """Stress combined failure modes and ensure cascading issues are detected."""

    if not 0.0 < exchange_failure_ratio <= 1.0:
        raise ValueError("exchange_failure_ratio must be within (0.0, 1.0].")
    if not 0.0 < database_drop_ratio <= 1.0:
        raise ValueError("database_drop_ratio must be within (0.0, 1.0].")

    def exchange_step(context: ChaosContext) -> None:
        context.log(
            "Escalating exchange failures for cascading test",
            failure_ratio=exchange_failure_ratio,
            duration_s=duration_s / 2,
        )
        context.exchange.inject_failure_rate(exchange_failure_ratio, duration_s / 2)
        context.sleep(duration_s / 2)
        context.exchange.reset()

    def database_step(context: ChaosContext) -> None:
        context.log(
            "Dropping database connections for cascading test",
            drop_ratio=database_drop_ratio,
            duration_s=duration_s / 2,
        )
        context.database.drop_connections(database_drop_ratio, duration_s / 2)
        context.sleep(duration_s / 2)
        context.database.reset()

    def detection(context: ChaosContext) -> DetectionResult:
        signals = tuple(context.monitoring.detect_cascading_failures())
        success = len(signals) > 0
        context.log(
            "Cascading failure detection",
            success=success,
            signal_count=len(signals),
        )
        return DetectionResult(success=success, details=signals)

    steps = (
        ScenarioStep(
            name="cascading-exchange-failure",
            description="Amplify exchange errors to trigger dependency stress.",
            action=exchange_step,
        ),
        ScenarioStep(
            name="cascading-database-drop",
            description="Reduce database capacity following exchange instability.",
            action=database_step,
        ),
    )

    verifications = (
        zero_data_corruption_metric(),
        recovery_time_metric(),
        exchange_survival_metric(min_ratio=0.5),
    )

    return ChaosScenario(
        name="cascading-failure-detection",
        description="Validates observability for multi-component cascading failures.",
        steps=steps,
        verifications=verifications,
        detection=detection,
    )


def build_steady_state_verification_experiment() -> ChaosScenario:
    """Pure steady-state verification with no explicit disruption."""

    def verify_only(context: ChaosContext) -> None:
        context.log("Steady-state verification checkpoint")
        context.sleep(0.1)

    steps = (
        ScenarioStep(
            name="steady-state-check",
            description="Confirm baseline measurements without disruption.",
            action=verify_only,
        ),
    )

    verifications = (
        zero_data_corruption_metric(),
        recovery_time_metric(),
    )

    return ChaosScenario(
        name="steady-state-verification",
        description="Ensures the automated steady-state verifier remains reliable.",
        steps=steps,
        verifications=verifications,
    )


# ---------------------------------------------------------------------------
# Suite constructor used by the tests
# ---------------------------------------------------------------------------


def build_geosync_chaos_suite() -> ChaosExperimentSuite:
    """Return the canonical chaos experiment suite for GeoSync."""

    scenarios: Sequence[ChaosScenario] = (
        build_steady_state_verification_experiment(),
        build_network_latency_experiment(),
        build_exchange_api_failure_experiment(),
        build_database_connection_drop_experiment(),
        build_memory_pressure_experiment(),
        build_cpu_throttling_experiment(),
        build_cascading_failure_detection_experiment(),
    )
    return ChaosExperimentSuite(scenarios=scenarios)


__all__ = [
    "ChaosContext",
    "ScenarioStep",
    "MetricCheck",
    "MetricResult",
    "DetectionResult",
    "ChaosOutcome",
    "ChaosScenario",
    "ChaosExperimentSuite",
    "build_geosync_chaos_suite",
    "build_network_latency_experiment",
    "build_exchange_api_failure_experiment",
    "build_database_connection_drop_experiment",
    "build_memory_pressure_experiment",
    "build_cpu_throttling_experiment",
    "build_cascading_failure_detection_experiment",
    "build_steady_state_verification_experiment",
]
