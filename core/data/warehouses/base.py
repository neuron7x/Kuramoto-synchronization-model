# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Abstractions for describing time-series warehouse integrations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Protocol, Sequence

if TYPE_CHECKING:  # pragma: no cover - import guard for typing only
    from core.data.models import PriceTick


@dataclass(frozen=True)
class WarehouseStatement:
    """Declarative SQL statement with an optional human readable description."""

    description: str
    sql: str


@dataclass(frozen=True)
class RollupJob:
    """Metadata describing a rollup/aggregation materialisation task."""

    name: str
    statement: WarehouseStatement
    schedule_hint: str


@dataclass(frozen=True)
class MaintenanceTask:
    """Operational maintenance commands that keep storage healthy."""

    name: str
    statement: WarehouseStatement
    cadence: str


@dataclass(frozen=True)
class SLAQuery:
    """Query powering SLO/SLA dashboards with latency and throughput metrics."""

    name: str
    sql: str
    description: str


@dataclass(frozen=True)
class BenchmarkScenario:
    """Benchmark blueprint describing load profiles executed in staging."""

    name: str
    description: str
    target_qps: int
    concurrency: int
    dataset_hint: str


@dataclass(frozen=True)
class BackupStep:
    """Ordered step in the backup & recovery runbook."""

    description: str
    command: str


class TimeSeriesWarehouse(Protocol):
    """Contract implemented by concrete warehouse integrations."""

    def bootstrap_statements(self) -> Sequence[WarehouseStatement]:
        """Return DDL statements required to provision the warehouse."""

    def rollup_jobs(self) -> Sequence[RollupJob]:
        """Return materialisation statements that produce rollups."""

    def maintenance_tasks(self) -> Sequence[MaintenanceTask]:
        """Return statements that should run on a cadence to keep storage healthy."""

    def sla_queries(self) -> Sequence[SLAQuery]:
        """Return reference queries used by dashboards and alerting."""

    def benchmark_scenarios(self) -> Sequence[BenchmarkScenario]:
        """Return benchmark profiles executed against realistic data volumes."""

    def backup_plan(self) -> Sequence[BackupStep]:
        """Return the ordered backup and recovery instructions."""

    def ingest_ticks(
        self, ticks: Sequence["PriceTick"], *, chunk_size: int = 10_000
    ) -> None:
        """Persist a batch of tick payloads into the warehouse."""

    def ingest_bars(
        self, bars: Iterable[dict], *, chunk_size: int = 2_000
    ) -> None:  # pragma: no cover - optional extension
        """Persist aggregated bars. Default implementation is optional."""
        raise NotImplementedError


__all__ = [
    "BackupStep",
    "BenchmarkScenario",
    "MaintenanceTask",
    "RollupJob",
    "SLAQuery",
    "TimeSeriesWarehouse",
    "WarehouseStatement",
]
