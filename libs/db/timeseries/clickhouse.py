# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""ClickHouse integration helpers for market data time-series."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Iterable, Mapping, Sequence

from .config import (
    IngestionConnectorConfig,
    RetentionPolicy,
    RollupMaterialization,
    SLAMetric,
    TimeSeriesSchema,
)

__all__ = [
    "ClickHouseBackupPlanner",
    "ClickHouseIndex",
    "ClickHouseIngestionConnector",
    "ClickHouseQueryBuilder",
    "ClickHouseSchemaManager",
    "ClickHouseSLAManager",
]


def _format_interval(value: timedelta) -> str:
    """Convert ``value`` to a ClickHouse INTERVAL expression."""

    total_seconds = int(value.total_seconds())
    if total_seconds % 86_400 == 0:
        days = total_seconds // 86_400
        return f"INTERVAL {days} DAY"
    if total_seconds % 3_600 == 0:
        hours = total_seconds // 3_600
        return f"INTERVAL {hours} HOUR"
    if total_seconds % 60 == 0:
        minutes = total_seconds // 60
        return f"INTERVAL {minutes} MINUTE"
    return f"INTERVAL {total_seconds} SECOND"


@dataclass(frozen=True, slots=True)
class ClickHouseIndex:
    """Secondary index definition used to accelerate selective queries."""

    name: str
    expression: str
    index_type: str = "minmax"
    granularity: int = 1

    def ddl(self) -> str:
        return f"INDEX {self.name} {self.expression} TYPE {self.index_type} GRANULARITY {self.granularity}"


@dataclass(frozen=True, slots=True)
class ClickHouseSchemaManager:
    """Builds DDL statements for ClickHouse tables and rollups."""

    schema: TimeSeriesSchema
    retention: RetentionPolicy
    indexes: tuple[ClickHouseIndex, ...] = field(default_factory=tuple)
    engine: str = "MergeTree"
    partition_by: str = "toYYYYMMDD(timestamp)"
    order_by: Sequence[str] = ("symbol", "venue", "timestamp")
    sample_by: str | None = None
    settings: Mapping[str, Any] = field(
        default_factory=lambda: {
            "index_granularity": 8192,
            "merge_with_ttl_timeout": 3600,
            "min_bytes_for_wide_part": 10_000_000,
            "allow_nullable_key": 0,
        }
    )

    def create_table_sql(self) -> str:
        """Return a fully fledged CREATE TABLE statement."""

        columns = [f"{self.schema.timestamp_column} {self.schema.timestamp_type}"]
        columns.extend(column.ddl() for column in self.schema.dimensions)
        columns.extend(measure.ddl() for measure in self.schema.measures)
        columns.extend(column.ddl() for column in self.schema.metadata)

        ttl_parts = [
            f"{self.schema.timestamp_column} + {_format_interval(self.retention.hot)} TO VOLUME 'hot'",
        ]
        if self.retention.warm:
            ttl_parts.append(
                f"{self.schema.timestamp_column} + {_format_interval(self.retention.warm)} TO VOLUME 'warm'"
            )
        if self.retention.cold:
            ttl_parts.append(
                f"{self.schema.timestamp_column} + {_format_interval(self.retention.cold)} TO VOLUME 'cold'"
            )
        if self.retention.drop:
            ttl_parts.append(
                f"{self.schema.timestamp_column} + {_format_interval(self.retention.drop)} DELETE"
            )

        parts = [
            f"CREATE TABLE IF NOT EXISTS {self.schema.fully_qualified_name}",
            "(",
            "    " + ",\n    ".join(columns),
        ]
        for index in self.indexes:
            parts.append(f"    ,{index.ddl()}")
        parts.append(")")
        parts.append(f"ENGINE = {self.engine}")
        parts.append(f"PARTITION BY {self.partition_by}")
        order_by = ", ".join(self.order_by)
        parts.append(f"ORDER BY ({order_by})")
        if self.sample_by:
            parts.append(f"SAMPLE BY {self.sample_by}")
        parts.append("TTL " + ", ".join(ttl_parts))
        if self.settings:
            rendered_settings = ", ".join(
                f"{key} = {value}" for key, value in self.settings.items()
            )
            parts.append(f"SETTINGS {rendered_settings}")
        return "\n".join(parts)

    def rollup_table_sql(self, rollup: RollupMaterialization) -> str:
        """Return SQL to create the destination table for ``rollup`` results."""

        target = self._qualified_rollup_name(rollup.name)
        columns = ["bucket DateTime64(6, 'UTC')"]
        columns.extend(column.ddl() for column in self.schema.dimensions)
        columns.extend(
            f"{aggregation.alias} {aggregation.data_type}" for aggregation in rollup.aggregations
        )
        order_by_columns = [
            "bucket",
            *(dimension.name for dimension in self.schema.dimensions),
        ]
        ttl_horizon = (
            self.retention.drop or self.retention.cold or self.retention.warm or self.retention.hot
        )
        parts = [
            f"CREATE TABLE IF NOT EXISTS {target}",
            "(",
            "    " + ",\n    ".join(columns),
            ")",
            "ENGINE = MergeTree()",
            "PARTITION BY toYYYYMMDD(bucket)",
            f"ORDER BY ({', '.join(order_by_columns)})",
            f"TTL bucket + {_format_interval(ttl_horizon)} DELETE",
        ]
        return "\n".join(parts)

    def materialized_view_sql(self, rollup: RollupMaterialization) -> str:
        """Return SQL to create a materialized view for ``rollup``."""

        bucket_expr = _format_interval(rollup.interval)
        select_columns = [
            f"toStartOfInterval({self.schema.timestamp_column}, {bucket_expr}) AS bucket"
        ]
        select_columns.extend(dimension.name for dimension in self.schema.dimensions)
        select_columns.extend(
            f"{aggregation.expression} AS {aggregation.alias}"
            for aggregation in rollup.aggregations
        )

        group_by = ["bucket", *(dimension.name for dimension in self.schema.dimensions)]
        source = self.schema.fully_qualified_name
        view_name = rollup.materialized_view_name or f"{rollup.name}_mv"
        qualified_view = self._qualified_rollup_name(view_name)
        target = self._qualified_rollup_name(rollup.name)
        return (
            "CREATE MATERIALIZED VIEW IF NOT EXISTS "
            f"{qualified_view}\n"
            f"TO {target}\n"
            "AS\nSELECT\n    "
            + ",\n    ".join(select_columns)
            + f"\nFROM {source}\nGROUP BY {', '.join(group_by)}"
        )

    def _qualified_rollup_name(self, name: str) -> str:
        if self.schema.database:
            return f"{self.schema.database}.{name}"
        return name

    def optimize_table_sql(self) -> str:
        """Return an OPTIMIZE statement to trigger background compaction."""

        return f"OPTIMIZE TABLE {self.schema.fully_qualified_name} FINAL"


class ClickHouseIngestionConnector:
    """Buffered ingestion connector built on top of clickhouse-connect semantics."""

    def __init__(
        self,
        *,
        client: Any,
        schema: TimeSeriesSchema,
        config: IngestionConnectorConfig | None = None,
    ) -> None:
        if not hasattr(client, "insert"):
            raise TypeError("client must expose an insert method")
        self._client = client
        self._schema = schema
        self._config = config or IngestionConnectorConfig()
        self._buffer: list[Mapping[str, Any]] = []

    @property
    def batch_size(self) -> int:
        return self._config.batch_size

    def ingest_many(self, records: Iterable[Mapping[str, Any]]) -> int:
        """Buffer ``records`` and flush in batches."""

        flushed = 0
        for record in records:
            self._buffer.append(record)
            if len(self._buffer) >= self.batch_size:
                flushed += self.flush()
        return flushed

    def flush(self) -> int:
        """Flush the internal buffer to ClickHouse."""

        if not self._buffer:
            return 0
        columns = self._schema.column_order()
        rows = [[record.get(column) for column in columns] for record in self._buffer]
        self._client.insert(
            self._schema.fully_qualified_name,
            rows,
            column_names=list(columns),
        )
        flushed = len(self._buffer)
        self._buffer.clear()
        return flushed


class ClickHouseQueryBuilder:
    """Construct latency-aware analytical queries for ClickHouse."""

    def __init__(self, schema: TimeSeriesSchema) -> None:
        self._schema = schema

    def _resolve_measure(self, *preferred: str, default_index: int = 0) -> str:
        for candidate in preferred:
            if any(measure.name == candidate for measure in self._schema.measures):
                return candidate
        return self._schema.measures[default_index].name

    def _try_resolve_measure(self, *preferred: str) -> str | None:
        for candidate in preferred:
            if any(measure.name == candidate for measure in self._schema.measures):
                return candidate
        return None

    def ohlcv_query(
        self,
        *,
        rollup: RollupMaterialization | None = None,
        limit: int = 10_000,
        filters: Mapping[str, str] | None = None,
    ) -> str:
        table = (
            self._schema.fully_qualified_name
            if rollup is None
            else self._qualified_rollup_name(rollup.name)
        )
        timeframe = _format_interval(rollup.interval if rollup else timedelta(minutes=1))
        dims = [dimension.name for dimension in self._schema.dimensions]
        filters = filters or {}
        prewhere_clauses = [f"{key} = %({key})s" for key in filters]
        prewhere = "\nPREWHERE " + " AND ".join(prewhere_clauses) if prewhere_clauses else ""
        timestamp_column = self._schema.timestamp_column
        price_column = self._resolve_measure("price", "last_price", "close")
        volume_column = self._try_resolve_measure("volume", "qty", "quantity")

        select_lines = [
            f"    toStartOfInterval({timestamp_column}, {timeframe}) AS bucket",
        ]
        select_lines.extend(f"    {dimension}" for dimension in dims)
        select_lines.extend(
            [
                f"    min({price_column}) AS low",
                f"    max({price_column}) AS high",
                f"    argMax({price_column}, {timestamp_column}) AS close",
                f"    argMin({price_column}, {timestamp_column}) AS open",
            ]
        )
        if volume_column:
            select_lines.append(f"    sum({volume_column}) AS volume")

        group_by_columns = ["bucket", *dims] if dims else ["bucket"]
        group_by_clause = ", ".join(group_by_columns)

        query = ["SELECT", ",\n".join(select_lines), f"FROM {table}{prewhere}"]
        query.append(
            f"WHERE {timestamp_column} >= %(start_ts)s AND {timestamp_column} < %(end_ts)s"
        )
        query.append(f"GROUP BY {group_by_clause}")
        query.append("ORDER BY bucket ASC")
        query.append(f"LIMIT {limit}")
        query.append("SETTINGS max_threads = 8, max_block_size = 65536")
        return "\n".join(query)

    def _qualified_rollup_name(self, name: str) -> str:
        if self._schema.database:
            return f"{self._schema.database}.{name}"
        return name


class ClickHouseSLAManager:
    """Provide opinionated dashboard queries and thresholds."""

    def __init__(self, schema: TimeSeriesSchema) -> None:
        self._schema = schema

    def latency_metrics(self) -> tuple[SLAMetric, ...]:
        builder = ClickHouseQueryBuilder(self._schema)
        ohlcv = builder.ohlcv_query(filters={"symbol": "{symbol}"})
        return (
            SLAMetric(
                name="ohlcv_latency_p99",
                query=ohlcv,
                threshold_ms=850.0,
                description="P99 latency for OHLCV aggregation with symbol filter",
            ),
            SLAMetric(
                name="ingest_lag_seconds",
                query=(
                    "SELECT max(toUnixTimestamp(now64(6)) - toUnixTimestamp(timestamp)) AS ingest_lag "
                    f"FROM {self._schema.fully_qualified_name}"
                ),
                threshold_ms=5_000.0,
                description="Ingestion lag must remain under five seconds",
            ),
        )


@dataclass(frozen=True, slots=True)
class ClickHouseBackupPlanner:
    """Generates backup commands compatible with clickhouse-backup."""

    schema: TimeSeriesSchema
    retention_days: int = 14

    def full_backup_command(self) -> str:
        return (
            f"clickhouse-backup create --tables {self.schema.fully_qualified_name} market-data-full"
        )

    def incremental_backup_command(self) -> str:
        return (
            "clickhouse-backup create --diff-from latest --tables "
            f"{self.schema.fully_qualified_name} market-data-incremental"
        )

    def verify_command(self) -> str:
        return "clickhouse-backup validate market-data-full"

    def retention_policy(self) -> str:
        return f"retain {self.retention_days} days"
