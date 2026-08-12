# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""TimescaleDB integration for tick and rollup storage."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from psycopg import Connection, sql
from psycopg.rows import tuple_row

from core.data.models import PriceTick
from core.utils.logging import get_logger

from ._validators import ensure_identifier, literal
from .base import (
    BackupStep,
    BenchmarkScenario,
    MaintenanceTask,
    RollupJob,
    SLAQuery,
    TimeSeriesWarehouse,
    WarehouseStatement,
)

_LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class TimescaleConfig:
    """Configuration parameters for Timescale storage."""

    schema: str = "public"
    raw_table: str = "raw_ticks"
    rollup_table: str = "minute_bars"
    retention_days: int = 30
    rollup_retention_days: int = 180
    chunk_interval_hours: int = 24

    def __post_init__(self) -> None:
        ensure_identifier(self.schema, label="Timescale schema")
        ensure_identifier(self.raw_table, label="Timescale raw table")
        ensure_identifier(self.rollup_table, label="Timescale rollup table")


@dataclass(frozen=True)
class _TimescaleIdentifiers:
    schema: str
    raw_table: str
    rollup_table: str
    schema_prefix: str
    raw_qualified: str
    rollup_qualified: str

    @classmethod
    def from_config(cls, config: TimescaleConfig) -> "_TimescaleIdentifiers":
        schema = ensure_identifier(config.schema, label="Timescale schema")
        raw_table = ensure_identifier(config.raw_table, label="Timescale raw table")
        rollup_table = ensure_identifier(
            config.rollup_table, label="Timescale rollup table"
        )
        schema_prefix = "" if schema == "public" else schema + "."
        raw_qualified = schema_prefix + raw_table
        rollup_qualified = schema_prefix + rollup_table
        return cls(
            schema=schema,
            raw_table=raw_table,
            rollup_table=rollup_table,
            schema_prefix=schema_prefix,
            raw_qualified=raw_qualified,
            rollup_qualified=rollup_qualified,
        )


class TimescaleWarehouse(TimeSeriesWarehouse):
    """Encapsulates DDL, ingestion and maintenance for TimescaleDB."""

    def __init__(
        self,
        connection: Connection,
        *,
        config: TimescaleConfig | None = None,
        batch_size: int = 5_000,
    ) -> None:
        self._connection = connection
        self._config = config or TimescaleConfig()
        self._identifiers = _TimescaleIdentifiers.from_config(self._config)
        self._batch_size = batch_size

    # -- DDL -----------------------------------------------------------------
    def bootstrap_statements(self) -> Sequence[WarehouseStatement]:
        cfg = self._config
        ids = self._identifiers
        raw_literal = literal(ids.raw_qualified)
        rollup_literal = literal(ids.rollup_qualified)

        extensions_sql = (
            "CREATE EXTENSION IF NOT EXISTS timescaledb;\n"
            "CREATE EXTENSION IF NOT EXISTS pgcrypto;"
        )
        create_extensions = WarehouseStatement(
            "enable extensions",
            extensions_sql,
        )

        raw_table_lines = [
            "CREATE TABLE IF NOT EXISTS " + ids.raw_qualified + " (",
            "    ts TIMESTAMPTZ NOT NULL,",
            "    symbol TEXT NOT NULL,",
            "    venue TEXT NOT NULL,",
            "    instrument_type TEXT NOT NULL,",
            "    price NUMERIC(18,10) NOT NULL,",
            "    volume NUMERIC(18,10) NOT NULL,",
            "    trade_id TEXT,",
            "    ingest_id UUID NOT NULL DEFAULT gen_random_uuid(),",
            "    ingest_ts TIMESTAMPTZ NOT NULL DEFAULT now()",
            ");",
        ]
        create_raw_table = WarehouseStatement(
            "create raw tick table",
            "\n".join(raw_table_lines),
        )

        hypertable_lines = [
            "SELECT create_hypertable(" + raw_literal + ", 'ts',",
            " partitioning_column => 'symbol',",
            " chunk_time_interval => INTERVAL '"
            + str(cfg.chunk_interval_hours)
            + " hour',",
            " if_not_exists => TRUE);",
        ]
        create_hypertable = WarehouseStatement(
            "convert raw table to hypertable",
            "\n".join(hypertable_lines),
        )

        policy_lines = [
            "CREATE INDEX IF NOT EXISTS " + ids.raw_table + "_symbol_ts_idx",
            "    ON " + ids.raw_qualified + " (symbol, ts DESC);",
            "SELECT add_retention_policy("
            + raw_literal
            + ", INTERVAL '"
            + str(cfg.retention_days)
            + " days');",
            "ALTER TABLE " + ids.raw_qualified + " SET (timescaledb.compress);",
            "ALTER TABLE "
            + ids.raw_qualified
            + " SET (timescaledb.compress_segmentby = 'symbol');",
            "SELECT add_compression_policy(" + raw_literal + ", INTERVAL '7 days');",
        ]
        raw_policies = WarehouseStatement(
            "raw table indexes and policies",
            "\n".join(policy_lines),
        )

        rollup_lines = [
            "CREATE MATERIALIZED VIEW IF NOT EXISTS " + ids.rollup_qualified,
            "WITH (timescaledb.continuous) AS",
            "SELECT time_bucket('1 minute', ts) AS window_start,",
            "       symbol,",
            "       venue,",
            "       instrument_type,",
            "       first(price, ts) AS open_price,",
            "       max(price) AS high_price,",
            "       min(price) AS low_price,",
            "       last(price, ts) AS close_price,",
            "       sum(volume) AS volume,",
            "       count(*) AS trade_count",
            "FROM " + ids.raw_qualified,
            "GROUP BY window_start, symbol, venue, instrument_type;",
        ]
        create_rollup = WarehouseStatement(
            "create rollup table",
            "\n".join(rollup_lines),
        )

        rollup_policy_lines = [
            "SELECT add_continuous_aggregate_policy(" + rollup_literal + ",",
            "    start_offset => INTERVAL '2 days',",
            "    end_offset => INTERVAL '5 minutes',",
            "    schedule_interval => INTERVAL '1 minute');",
            "SELECT add_retention_policy("
            + rollup_literal
            + ", INTERVAL '"
            + str(cfg.rollup_retention_days)
            + " days');",
        ]
        rollup_policy = WarehouseStatement(
            "rollup policy",
            "\n".join(rollup_policy_lines),
        )

        return (
            create_extensions,
            create_raw_table,
            create_hypertable,
            raw_policies,
            create_rollup,
            rollup_policy,
        )

    def rollup_jobs(self) -> Sequence[RollupJob]:
        ids = self._identifiers
        statement = WarehouseStatement(
            "refresh continuous aggregate",
            "CALL refresh_continuous_aggregate("
            + literal(ids.rollup_qualified)
            + ", NULL, NULL);",
        )
        return (
            RollupJob(
                name="timescale-minute-bars-refresh",
                statement=statement,
                schedule_hint="*/5 * * * *",
            ),
        )

    def maintenance_tasks(self) -> Sequence[MaintenanceTask]:
        ids = self._identifiers
        return (
            MaintenanceTask(
                name="timescale-reorder-chunks",
                statement=WarehouseStatement(
                    "reorder chunks by symbol",
                    "CALL reorder_chunks("
                    + literal(ids.raw_qualified)
                    + ", 'symbol, ts DESC');",
                ),
                cadence="daily",
            ),
            MaintenanceTask(
                name="timescale-analyze",
                statement=WarehouseStatement(
                    "analyze hypertable statistics",
                    "ANALYZE " + ids.raw_qualified + ";",
                ),
                cadence="daily",
            ),
        )

    def sla_queries(self) -> Sequence[SLAQuery]:
        ids = self._identifiers
        tick_latency = "\n".join(
            [
                "SELECT symbol, venue,",
                "       max(ts) AS latest_ts,",
                "       now() - max(ts) AS ingest_lag",
                "FROM " + ids.raw_qualified,
                "GROUP BY symbol, venue;",
            ]
        )
        rollup_freshness = "\n".join(
            [
                "SELECT symbol, venue,",
                "       max(window_start) AS latest_window,",
                "       now() - max(window_start) AS lag",
                "FROM " + ids.rollup_qualified,
                "GROUP BY symbol, venue;",
            ]
        )
        ingest_throughput = "\n".join(
            [
                "SELECT date_trunc('minute', ingest_ts) AS window,",
                "       count(*) / 60.0 AS ticks_per_second",
                "FROM " + ids.raw_qualified,
                "WHERE ingest_ts >= now() - INTERVAL '2 hours'",
                "GROUP BY window",
                "ORDER BY window;",
            ]
        )
        return (
            SLAQuery(
                name="tick_ingest_latency",
                sql=tick_latency,
                description="Latency between live clock and newest tick",
            ),
            SLAQuery(
                name="rollup_freshness",
                sql=rollup_freshness,
                description="Freshness of continuous aggregates",
            ),
            SLAQuery(
                name="ingest_throughput",
                sql=ingest_throughput,
                description="Ticks per second aggregated per minute",
            ),
        )

    def benchmark_scenarios(self) -> Sequence[BenchmarkScenario]:
        return (
            BenchmarkScenario(
                name="timescale-binary-copy-40k",
                description="COPY ingest sustaining 40k ticks per second",
                target_qps=40_000,
                concurrency=6,
                dataset_hint="synthetic_ticks_40k",
            ),
            BenchmarkScenario(
                name="timescale-dashboard-rollup",
                description="Query 90 days of minute bars under sub-second latency",
                target_qps=750,
                concurrency=4,
                dataset_hint="minute_bars_90d",
            ),
        )

    def backup_plan(self) -> Sequence[BackupStep]:
        ids = self._identifiers
        checksum_query = "\n".join(
            [
                "SELECT relname, checksum_failures FROM timescaledb_information.hypertables",
                "WHERE schema_name = "
                + literal(ids.schema)
                + " AND relname IN ("
                + literal(ids.raw_table)
                + ", "
                + literal(ids.rollup_table)
                + ");",
            ]
        )
        return (
            BackupStep(
                description="Perform base backup using pg_basebackup",
                command="pg_basebackup -h $PGHOST -D /backups/timescale -U $PGUSER -Fp -Xs -P",
            ),
            BackupStep(
                description="Verify logical checksums for critical tables",
                command=checksum_query,
            ),
            BackupStep(
                description="Restore via point-in-time recovery",
                command="pg_ctl restore -D /var/lib/postgresql/data --target='last backup timestamp'",
            ),
        )

    # -- Ingestion ------------------------------------------------------------
    def ingest_ticks(
        self, ticks: Sequence[PriceTick], *, chunk_size: int | None = None
    ) -> None:
        if not ticks:
            return
        chunk_limit = self._batch_size if chunk_size is None else chunk_size
        if chunk_limit <= 0:
            raise ValueError("chunk_size must be positive")
        ids = self._identifiers
        table_identifier = sql.Identifier(ids.schema, ids.raw_table)
        insert_sql = sql.SQL(
            "INSERT INTO {} (ts, symbol, venue, instrument_type, price, volume, trade_id)\n"
            "VALUES (%s, %s, %s, %s, %s, %s, %s);"
        ).format(table_identifier)
        try:
            with self._connection.cursor(row_factory=tuple_row) as cursor:
                for chunk in _chunk_iterable(ticks, chunk_limit):
                    payload = [
                        (
                            tick.timestamp,
                            tick.symbol,
                            tick.venue,
                            tick.instrument_type.value,
                            tick.price,
                            tick.volume,
                            tick.trade_id,
                        )
                        for tick in chunk
                    ]
                    cursor.executemany(insert_sql, payload)
                    _LOGGER.debug(
                        "timescale_ingest_batch",
                        rows=len(payload),
                        table=ids.raw_qualified,
                    )
            self._connection.commit()
        except Exception:
            self._connection.rollback()
            raise


def _chunk_iterable(
    items: Iterable[PriceTick], size: int
) -> Iterable[Sequence[PriceTick]]:
    batch: list[PriceTick] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


__all__ = ["TimescaleWarehouse", "TimescaleConfig"]
