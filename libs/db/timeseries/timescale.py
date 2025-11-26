"""TimescaleDB integration helpers for long-term market data storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Iterable, Mapping

from .config import (
    IngestionConnectorConfig,
    RetentionPolicy,
    RollupMaterialization,
    SLAMetric,
    TimeSeriesSchema,
)

__all__ = [
    "TimescaleBackupPlanner",
    "TimescaleIngestionConnector",
    "TimescaleQueryBuilder",
    "TimescaleSchemaManager",
    "TimescaleSLAManager",
]


def _format_interval(value: timedelta) -> str:
    """Render a PostgreSQL interval literal."""

    total_seconds = int(value.total_seconds())
    if total_seconds % 86_400 == 0:
        days = total_seconds // 86_400
        return f"INTERVAL '{days} days'"
    if total_seconds % 3_600 == 0:
        hours = total_seconds // 3_600
        return f"INTERVAL '{hours} hours'"
    if total_seconds % 60 == 0:
        minutes = total_seconds // 60
        return f"INTERVAL '{minutes} minutes'"
    return f"INTERVAL '{total_seconds} seconds'"


@dataclass(frozen=True, slots=True)
class TimescaleSchemaManager:
    """Generates DDL for hypertables, compression, and policies."""

    schema: TimeSeriesSchema
    retention: RetentionPolicy
    chunk_interval: timedelta = timedelta(hours=6)

    def create_table_sql(self) -> str:
        columns = [f"{self.schema.timestamp_column} TIMESTAMPTZ NOT NULL"]
        columns.extend(
            f"{dimension.name} {self._normalize_type(dimension.data_type)}"
            + ("" if dimension.nullable else " NOT NULL")
            for dimension in self.schema.dimensions
        )
        columns.extend(
            f"{measure.name} {self._postgres_type(measure.data_type)}"
            for measure in self.schema.measures
        )
        columns.extend(
            f"{column.name} {self._normalize_type(column.data_type)}"
            + ("" if column.nullable else " NOT NULL")
            for column in self.schema.metadata
        )
        return (
            f"CREATE TABLE IF NOT EXISTS {self.schema.table} ("
            "\n    " + ",\n    ".join(columns) + "\n);"
        )

    def hypertable_sql(self) -> str:
        return (
            "SELECT create_hypertable("
            f"'{self.schema.table}', '{self.schema.timestamp_column}',"
            " chunk_time_interval => "
            + _format_interval(self.chunk_interval)
            + ", if_not_exists => TRUE, create_default_indexes => TRUE);"
        )

    def indexes_sql(self) -> tuple[str, ...]:
        statements = []
        for dimension in self.schema.dimensions:
            statements.append(
                f"CREATE INDEX IF NOT EXISTS ON {self.schema.table} ({dimension.name}, {self.schema.timestamp_column} DESC);"
            )
        statements.append(
            f"CREATE INDEX IF NOT EXISTS ON {self.schema.table} ({self.schema.timestamp_column});"
        )
        return tuple(statements)

    def compression_sql(self) -> tuple[str, ...]:
        statements: list[str] = []
        if self.retention.warm:
            statements.append(
                f"ALTER TABLE {self.schema.table} SET (timescaledb.compress, timescaledb.compress_segmentby = '"
                + ",".join(dimension.name for dimension in self.schema.dimensions)
                + "');"
            )
            statements.append(
                "SELECT add_compression_policy("
                f"'{self.schema.table}', {_format_interval(self.retention.warm)});"
            )
        return tuple(statements)

    def retention_sql(self) -> str:
        horizon = (
            self.retention.drop
            or self.retention.cold
            or self.retention.warm
            or self.retention.hot
        )
        return (
            "SELECT add_retention_policy("
            f"'{self.schema.table}', {_format_interval(horizon)});"
        )

    def continuous_aggregate_sql(
        self, rollup: RollupMaterialization
    ) -> tuple[str, ...]:
        bucket_interval = _format_interval(rollup.interval)
        bucket_select = (
            f"time_bucket({bucket_interval}, {self.schema.timestamp_column}) AS bucket"
        )
        select_columns = [bucket_select]
        select_columns.extend(dimension.name for dimension in self.schema.dimensions)
        select_columns.extend(
            f"{aggregation.expression} AS {aggregation.alias}"
            for aggregation in rollup.aggregations
        )
        group_by = ["bucket", *(dimension.name for dimension in self.schema.dimensions)]
        view_name = rollup.materialized_view_name or f"{rollup.name}_cagg"
        definition = (
            f"CREATE MATERIALIZED VIEW IF NOT EXISTS {view_name} WITH (timescaledb.continuous) AS\n"
            "SELECT\n    "
            + ",\n    ".join(select_columns)
            + f"\nFROM {self.schema.table}\nGROUP BY {', '.join(group_by)}\nWITH NO DATA;"
        )
        refresh = (
            "SELECT add_continuous_aggregate_policy("
            f"'{view_name}',"
            " start_offset => " + _format_interval(rollup.refresh_lag) + ","
            " end_offset => INTERVAL '0 seconds',"
            " schedule_interval => " + _format_interval(rollup.interval) + ");"
        )
        return (definition, refresh)

    @staticmethod
    def _normalize_type(data_type: str) -> str:
        if "LowCardinality" in data_type:
            return "TEXT"
        return data_type

    @staticmethod
    def _postgres_type(data_type: str) -> str:
        mapping = {
            "Float64": "DOUBLE PRECISION",
            "Float32": "REAL",
            "UInt64": "BIGINT",
            "UInt32": "INTEGER",
        }
        return mapping.get(data_type, data_type)


class TimescaleIngestionConnector:
    """Thin wrapper around psycopg connections optimized for batch ingest."""

    def __init__(
        self,
        *,
        connection: Any,
        schema: TimeSeriesSchema,
        config: IngestionConnectorConfig | None = None,
    ) -> None:
        if not hasattr(connection, "cursor"):
            raise TypeError("connection must expose a cursor() method")
        self._connection = connection
        self._schema = schema
        self._config = config or IngestionConnectorConfig()

    def ingest_many(self, records: Iterable[Mapping[str, Any]]) -> int:
        rows = list(records)
        if not rows:
            return 0
        columns = self._schema.column_order()
        placeholders = ", ".join(["%s"] * len(columns))
        statement = (
            f"INSERT INTO {self._schema.table} ("
            + ", ".join(columns)
            + f") VALUES ({placeholders})"
        )
        with self._connection.cursor() as cursor:
            cursor.executemany(
                statement,
                [tuple(row.get(column) for column in columns) for row in rows],
            )
        self._connection.commit()
        return len(rows)


class TimescaleQueryBuilder:
    """Construct optimized aggregations leveraging time_bucket and compression."""

    def __init__(self, schema: TimeSeriesSchema) -> None:
        self._schema = schema

    def ohlcv_query(
        self,
        *,
        rollup: RollupMaterialization | None = None,
        limit: int = 10_000,
        filters: Mapping[str, str] | None = None,
    ) -> str:
        source = (
            rollup.materialized_view_name or f"{rollup.name}_cagg"
            if rollup
            else self._schema.table
        )
        interval = _format_interval(rollup.interval if rollup else timedelta(minutes=1))
        dims = [dimension.name for dimension in self._schema.dimensions]
        filters = filters or {}
        where_clauses = [
            f"{self._schema.timestamp_column} >= %(start_ts)s",
            f"{self._schema.timestamp_column} < %(end_ts)s",
        ]
        where_clauses.extend(f"{key} = %({key})s" for key in filters)
        price_column = self._resolve_measure("price", "last_price", "close")
        volume_column = self._try_resolve_measure("volume", "qty", "quantity")
        select_lines = [
            f"    time_bucket({interval}, {self._schema.timestamp_column}) AS bucket",
        ]
        select_lines.extend(f"    {dimension}" for dimension in dims)
        select_lines.extend(
            [
                f"    min({price_column}) AS low",
                f"    max({price_column}) AS high",
                f"    first({price_column}, {self._schema.timestamp_column}) AS open",
                f"    last({price_column}, {self._schema.timestamp_column}) AS close",
            ]
        )
        if volume_column:
            select_lines.append(f"    sum({volume_column}) AS volume")
        group_by = ["bucket", *dims] if dims else ["bucket"]
        query = ["SELECT", ",\n".join(select_lines), f"FROM {source}"]
        query.append("WHERE " + " AND ".join(where_clauses))
        query.append(f"GROUP BY {', '.join(group_by)}")
        query.append("ORDER BY bucket ASC")
        query.append(f"LIMIT {limit}")
        return "\n".join(query)

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


class TimescaleSLAManager:
    """Produce SLA dashboards for Timescale-backed datasets."""

    def __init__(self, schema: TimeSeriesSchema) -> None:
        self._schema = schema

    def latency_metrics(self) -> tuple[SLAMetric, ...]:
        builder = TimescaleQueryBuilder(self._schema)
        ohlcv = builder.ohlcv_query(filters={"symbol": "{symbol}"})
        return (
            SLAMetric(
                name="timescale_ohlcv_latency_p99",
                query=ohlcv,
                threshold_ms=950.0,
                description="P99 latency for continuous aggregate backed OHLCV",
            ),
            SLAMetric(
                name="timescale_ingest_lag_seconds",
                query=(
                    "SELECT EXTRACT(EPOCH FROM now() - max("
                    + self._schema.timestamp_column
                    + ")) * 1000 AS ingest_lag_ms "
                    f"FROM {self._schema.table}"
                ),
                threshold_ms=6_000.0,
                description="Ingestion lag must remain below six seconds",
            ),
        )


@dataclass(frozen=True, slots=True)
class TimescaleBackupPlanner:
    """Produce pg_dump based backup playbooks."""

    schema: TimeSeriesSchema
    retention_days: int = 30

    def full_backup_command(self) -> str:
        return f"pg_dump --no-owner --clean --table={self.schema.table} --file=/backups/{self.schema.table}_full.sql"

    def incremental_backup_command(self) -> str:
        return (
            "pg_dump --no-owner --clean --table="
            f"{self.schema.table} --snapshot=consistent --file=/backups/{self.schema.table}_incremental.sql"
        )

    def verify_command(self) -> str:
        return f"pg_restore --list /backups/{self.schema.table}_full.sql"

    def retention_policy(self) -> str:
        return f"retain {self.retention_days} days"
