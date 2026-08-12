# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Configuration primitives shared by ClickHouse and Timescale adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Sequence

__all__ = [
    "AggregationSpec",
    "BenchmarkWorkload",
    "DimensionColumn",
    "IngestionConnectorConfig",
    "MeasureColumn",
    "RetentionPolicy",
    "RollupAggregation",
    "RollupMaterialization",
    "SLAMetric",
    "TimeSeriesSchema",
]


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _ensure_identifier(value: str, *, label: str) -> str:
    if not value:
        raise ValueError(f"{label} must be a non-empty identifier")
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} must match {_IDENTIFIER_RE.pattern!r}: {value!r}")
    return value


def _validate_positive_timedelta(value: timedelta, *, field_name: str) -> None:
    if value <= timedelta(0):  # pragma: no cover - defensive guard
        msg = f"{field_name} must be a positive duration"
        raise ValueError(msg)


def _ensure_monotonic(sequence: Sequence[timedelta], *, field_name: str) -> None:
    for previous, current in zip(sequence, sequence[1:]):
        if current < previous:
            msg = f"{field_name} values must be monotonically non-decreasing"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class DimensionColumn:
    """Describes an entity or metadata column stored with time-series rows."""

    name: str
    data_type: str = "LowCardinality(String)"
    nullable: bool = False
    codec: str | None = None

    def ddl(self) -> str:
        """Return the column definition suitable for ClickHouse."""

        constraint = "" if self.nullable else " NOT NULL"
        codec_clause = f" CODEC({self.codec})" if self.codec else ""
        return f"{self.name} {self.data_type}{constraint}{codec_clause}"

    def __post_init__(self) -> None:
        _ensure_identifier(self.name, label="dimension column name")


@dataclass(frozen=True, slots=True)
class AggregationSpec:
    """Defines how a measure should be aggregated in rollups."""

    target_column: str
    expression: str


@dataclass(frozen=True, slots=True)
class MeasureColumn:
    """Quantitative column accompanied by optional aggregation hints."""

    name: str
    data_type: str
    codec: str | None = None
    aggregations: tuple[AggregationSpec, ...] = field(default_factory=tuple)

    def ddl(self) -> str:
        codec_clause = f" CODEC({self.codec})" if self.codec else ""
        return f"{self.name} {self.data_type}{codec_clause}"

    def __post_init__(self) -> None:
        _ensure_identifier(self.name, label="measure column name")


@dataclass(frozen=True, slots=True)
class TimeSeriesSchema:
    """Canonical representation of a GeoSync time-series table."""

    table: str
    timestamp_column: str
    dimensions: tuple[DimensionColumn, ...]
    measures: tuple[MeasureColumn, ...]
    metadata: tuple[DimensionColumn, ...] = field(default_factory=tuple)
    timestamp_type: str = "DateTime64(6, 'UTC')"
    database: str | None = None

    def __post_init__(self) -> None:
        _ensure_identifier(self.table, label="table name")
        _ensure_identifier(self.timestamp_column, label="timestamp column")
        if not self.measures:
            raise ValueError("At least one measure column is required")
        if self.database is not None:
            _ensure_identifier(self.database, label="database name")
        for column in (*self.dimensions, *self.metadata):
            _ensure_identifier(column.name, label="dimension column name")
        for measure in self.measures:
            _ensure_identifier(measure.name, label="measure column name")

    @property
    def fully_qualified_name(self) -> str:
        if self.database:
            return f"{self.database}.{self.table}"
        return self.table

    def column_order(self) -> tuple[str, ...]:
        """Return the deterministic column ordering used for ingestion."""

        return (
            self.timestamp_column,
            *(dimension.name for dimension in self.dimensions),
            *(measure.name for measure in self.measures),
            *(column.name for column in self.metadata),
        )


@dataclass(frozen=True, slots=True)
class RetentionPolicy:
    """Tiered retention policy used to drive TTL and compression settings."""

    hot: timedelta
    warm: timedelta | None = None
    cold: timedelta | None = None
    drop: timedelta | None = None

    def __post_init__(self) -> None:
        _validate_positive_timedelta(self.hot, field_name="hot")
        durations: list[timedelta] = [self.hot]
        for label, value in (
            ("warm", self.warm),
            ("cold", self.cold),
            ("drop", self.drop),
        ):
            if value is None:
                continue
            if value <= timedelta(0):
                msg = f"{label} must be a positive duration"
                raise ValueError(msg)
            durations.append(value)
        _ensure_monotonic(durations, field_name="retention policy")


@dataclass(frozen=True, slots=True)
class RollupAggregation:
    """Single aggregated column exposed by a rollup materialization."""

    alias: str
    expression: str
    data_type: str

    def __post_init__(self) -> None:
        _ensure_identifier(self.alias, label="rollup aggregation alias")


@dataclass(frozen=True, slots=True)
class RollupMaterialization:
    """Configuration describing a rollup/continuous aggregate."""

    name: str
    interval: timedelta
    aggregations: tuple[RollupAggregation, ...]
    refresh_lag: timedelta = timedelta(minutes=1)
    include_empty: bool = False
    materialized_view_name: str | None = None

    def __post_init__(self) -> None:
        _ensure_identifier(self.name, label="rollup materialization name")
        _validate_positive_timedelta(self.interval, field_name="interval")
        if self.refresh_lag <= timedelta(0):
            raise ValueError("refresh_lag must be a positive duration")
        if not self.aggregations:
            raise ValueError("At least one aggregation must be provided")
        if self.materialized_view_name is not None:
            if not self.materialized_view_name:
                raise ValueError("materialized_view_name must be a non-empty string when provided")
            _ensure_identifier(
                self.materialized_view_name,
                label="materialized view name",
            )


@dataclass(frozen=True, slots=True)
class IngestionConnectorConfig:
    """Controls batching, retries, and flush cadence for ingestion connectors."""

    batch_size: int = 50_000
    flush_interval: timedelta = timedelta(seconds=2)
    max_retries: int = 3

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        if self.flush_interval <= timedelta(0):
            raise ValueError("flush_interval must be a positive duration")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")


@dataclass(frozen=True, slots=True)
class SLAMetric:
    """Describes a dashboard query enforced in service-level objectives."""

    name: str
    query: str
    threshold_ms: float
    description: str | None = None

    def __post_init__(self) -> None:
        if self.threshold_ms <= 0:
            raise ValueError("threshold_ms must be greater than zero")


@dataclass(frozen=True, slots=True)
class BenchmarkWorkload:
    """Synthetic workload definition used for regression benchmarks."""

    name: str
    ingest_batches: tuple[int, ...]
    query_iterations: int = 5
    warmup_iterations: int = 1

    def __post_init__(self) -> None:
        if not self.ingest_batches:
            raise ValueError("ingest_batches must contain at least one batch size")
        if any(size <= 0 for size in self.ingest_batches):
            raise ValueError("All batch sizes must be positive integers")
        if self.query_iterations <= 0:
            raise ValueError("query_iterations must be positive")
        if self.warmup_iterations < 0:
            raise ValueError("warmup_iterations must be non-negative")
