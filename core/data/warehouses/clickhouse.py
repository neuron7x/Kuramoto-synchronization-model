# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""ClickHouse time-series warehouse integration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Sequence
from uuid import uuid4

import httpx

from core.data.models import PriceTick
from core.utils.logging import get_logger

from ._validators import ensure_identifier, ensure_timezone, literal
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
class ClickHouseConfig:
    """Runtime configuration for the ClickHouse integration."""

    database: str = "geosync"
    raw_table: str = "raw_ticks"
    rollup_table: str = "minute_bars"
    retention_days: int = 30
    rollup_retention_days: int = 180
    timezone_name: str = "UTC"
    write_path: str = "/"

    def __post_init__(self) -> None:
        ensure_identifier(self.database, label="ClickHouse database")
        ensure_identifier(self.raw_table, label="ClickHouse raw table")
        ensure_identifier(self.rollup_table, label="ClickHouse rollup table")
        ensure_timezone(self.timezone_name)


@dataclass(frozen=True)
class _ClickHouseIdentifiers:
    database: str
    raw_table: str
    rollup_table: str
    raw_qualified: str
    rollup_qualified: str
    mv_rollup: str
    timezone_literal: str

    @classmethod
    def from_config(cls, config: ClickHouseConfig) -> "_ClickHouseIdentifiers":
        database = ensure_identifier(config.database, label="ClickHouse database")
        raw_table = ensure_identifier(config.raw_table, label="ClickHouse raw table")
        rollup_table = ensure_identifier(
            config.rollup_table, label="ClickHouse rollup table"
        )
        timezone_value = ensure_timezone(config.timezone_name)
        timezone_literal = literal(timezone_value)
        raw_qualified = ".".join((database, raw_table))
        rollup_qualified = ".".join((database, rollup_table))
        mv_rollup = ".".join((database, "mv_" + rollup_table))
        return cls(
            database=database,
            raw_table=raw_table,
            rollup_table=rollup_table,
            raw_qualified=raw_qualified,
            rollup_qualified=rollup_qualified,
            mv_rollup=mv_rollup,
            timezone_literal=timezone_literal,
        )


class ClickHouseWarehouse(TimeSeriesWarehouse):
    """Manage ClickHouse schemas, ingestion and operational tasks."""

    def __init__(
        self,
        client: httpx.Client,
        *,
        config: ClickHouseConfig | None = None,
        insert_timeout: float = 10.0,
    ) -> None:
        self._client = client
        self._config = config or ClickHouseConfig()
        self._identifiers = _ClickHouseIdentifiers.from_config(self._config)
        self._insert_timeout = insert_timeout

    # -- DDL -----------------------------------------------------------------
    def bootstrap_statements(self) -> Sequence[WarehouseStatement]:
        cfg = self._config
        ids = self._identifiers
        timezone_literal = ids.timezone_literal

        create_database = WarehouseStatement(
            "create database",
            "CREATE DATABASE IF NOT EXISTS " + ids.database,
        )

        raw_table_lines = [
            "CREATE TABLE IF NOT EXISTS " + ids.raw_qualified + " (",
            "    ts DateTime64(6, " + timezone_literal + ") CODEC(Delta, ZSTD),",
            "    symbol LowCardinality(String),",
            "    venue LowCardinality(String),",
            "    instrument_type LowCardinality(String),",
            "    price Decimal64(10),",
            "    volume Decimal64(10),",
            "    trade_id String DEFAULT '',",
            "    ingest_id UUID DEFAULT generateUUIDv4(),",
            "    ingest_ts DateTime64(6, "
            + timezone_literal
            + ") DEFAULT now("
            + timezone_literal
            + ")",
            "    , INDEX idx_symbol symbol TYPE set(0) GRANULARITY 1",
            ")",
            "ENGINE = MergeTree",
            "PARTITION BY toDate(ts)",
            "ORDER BY (symbol, ts)",
            "TTL ts + INTERVAL " + str(cfg.retention_days) + " DAY DELETE",
            "SETTINGS index_granularity = 8192, allow_nullable_key = 0",
            "COMMENT 'Tick level market data'",
        ]
        create_raw_table = WarehouseStatement(
            "create raw tick table",
            "\n".join(raw_table_lines),
        )

        rollup_table_lines = [
            "CREATE TABLE IF NOT EXISTS " + ids.rollup_qualified + " (",
            "    window_start DateTime64(6, " + timezone_literal + "),",
            "    symbol LowCardinality(String),",
            "    venue LowCardinality(String),",
            "    instrument_type LowCardinality(String),",
            "    open_price Decimal64(10),",
            "    high_price Decimal64(10),",
            "    low_price Decimal64(10),",
            "    close_price Decimal64(10),",
            "    volume Decimal64(12),",
            "    trade_count UInt64,",
            "    ingest_ts DateTime64(6, "
            + timezone_literal
            + ") DEFAULT now("
            + timezone_literal
            + ")",
            "    , INDEX idx_rollup_symbol symbol TYPE set(0) GRANULARITY 1",
            ")",
            "ENGINE = MergeTree",
            "PARTITION BY toYYYYMM(window_start)",
            "ORDER BY (symbol, window_start)",
            "TTL window_start + INTERVAL "
            + str(cfg.rollup_retention_days)
            + " DAY DELETE",
            "SETTINGS index_granularity = 2048",
            "COMMENT 'One minute rollups from ticks'",
        ]
        create_rollup_table = WarehouseStatement(
            "create minute bar table",
            "\n".join(rollup_table_lines),
        )

        mv_lines = [
            "CREATE MATERIALIZED VIEW IF NOT EXISTS " + ids.mv_rollup,
            "TO " + ids.rollup_qualified + " AS",
            "SELECT",
            "    toStartOfInterval(ts, INTERVAL 1 MINUTE, "
            + timezone_literal
            + ") AS window_start,",
            "    symbol,",
            "    venue,",
            "    instrument_type,",
            "    argMin(price, ts) AS open_price,",
            "    argMax(price, ts) AS close_price,",
            "    max(price) AS high_price,",
            "    min(price) AS low_price,",
            "    sum(volume) AS volume,",
            "    count() AS trade_count",
            "FROM " + ids.raw_qualified,
            "GROUP BY",
            "    window_start, symbol, venue, instrument_type",
        ]
        materialized_view = WarehouseStatement(
            "create minute bar materialized view",
            "\n".join(mv_lines),
        )

        return (
            create_database,
            create_raw_table,
            create_rollup_table,
            materialized_view,
        )

    def rollup_jobs(self) -> Sequence[RollupJob]:
        ids = self._identifiers
        statement = WarehouseStatement(
            "force refresh materialized view",
            "OPTIMIZE TABLE " + ids.mv_rollup + " FINAL",
        )
        return (
            RollupJob(
                name="clickhouse-minute-bars-refresh",
                statement=statement,
                schedule_hint="*/5 * * * *",
            ),
        )

    def maintenance_tasks(self) -> Sequence[MaintenanceTask]:
        ids = self._identifiers
        return (
            MaintenanceTask(
                name="clickhouse-raw-optimize",
                statement=WarehouseStatement(
                    "compact raw tick partitions",
                    "OPTIMIZE TABLE " + ids.raw_qualified + " FINAL DEDUPLICATE",
                ),
                cadence="hourly",
            ),
            MaintenanceTask(
                name="clickhouse-rollup-optimize",
                statement=WarehouseStatement(
                    "compact rollup partitions",
                    "OPTIMIZE TABLE " + ids.rollup_qualified + " FINAL",
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
                "GROUP BY symbol, venue",
            ]
        )
        rollup_freshness = "\n".join(
            [
                "SELECT symbol, venue,",
                "       max(window_start) AS latest_window,",
                "       now() - max(window_start) AS lag",
                "FROM " + ids.rollup_qualified,
                "GROUP BY symbol, venue",
            ]
        )
        ingest_throughput = "\n".join(
            [
                "SELECT toStartOfInterval(ingest_ts, INTERVAL 5 MINUTE) AS window,",
                "       count() / 300 AS ticks_per_second",
                "FROM " + ids.raw_qualified,
                "WHERE ingest_ts >= now() - INTERVAL 2 HOUR",
                "GROUP BY window",
                "ORDER BY window",
            ]
        )
        return (
            SLAQuery(
                name="tick_ingest_latency",
                sql=tick_latency,
                description="Latency between newest tick and current time",
            ),
            SLAQuery(
                name="minute_bar_freshness",
                sql=rollup_freshness,
                description="Freshness of minute rollups",
            ),
            SLAQuery(
                name="ingest_throughput",
                sql=ingest_throughput,
                description="Ingestion throughput over the last two hours",
            ),
        )

    def benchmark_scenarios(self) -> Sequence[BenchmarkScenario]:
        return (
            BenchmarkScenario(
                name="clickhouse-tick-ingest-50k",
                description="Sustain 50k ticks/s via JSONEachRow inserts",
                target_qps=50_000,
                concurrency=8,
                dataset_hint="synthetic_ticks_50k",
            ),
            BenchmarkScenario(
                name="clickhouse-rollup-scan",
                description="Scan 180 days of rollups for dashboard workloads",
                target_qps=1_000,
                concurrency=4,
                dataset_hint="minute_bars_180d",
            ),
        )

    def backup_plan(self) -> Sequence[BackupStep]:
        ids = self._identifiers
        backup_tables = (
            "BACKUP TABLE "
            + ids.raw_qualified
            + ", "
            + ids.rollup_qualified
            + " TO 's3://geosync-clickhouse-backups/{date}/' SETTINGS compression='zstd'"
        )
        return (
            BackupStep(
                description="Snapshot raw and rollup tables to S3",
                command=backup_tables,
            ),
            BackupStep(
                description="Validate backup metadata",
                command="SYSTEM RESTORE FROM 's3://geosync-clickhouse-backups/{date}/' DRY RUN",
            ),
        )

    # -- Ingestion ------------------------------------------------------------
    def ingest_ticks(
        self, ticks: Sequence[PriceTick], *, chunk_size: int = 10_000
    ) -> None:
        if not ticks:
            return
        ids = self._identifiers
        table = ids.raw_qualified
        insert_query = "INSERT INTO " + table + " FORMAT JSONEachRow"
        for chunk in _chunk_iterable(ticks, chunk_size):
            payload = "\n".join(self._serialise_tick(tick) for tick in chunk)
            response = self._client.post(
                self._config.write_path,
                params={"query": insert_query},
                content=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=self._insert_timeout,
            )
            if response.status_code >= 300:
                raise RuntimeError(
                    "ClickHouse ingest failed with status "
                    + str(response.status_code)
                    + ": "
                    + response.text
                )
            _LOGGER.debug(
                "clickhouse_ingest_batch",
                rows=len(chunk),
                table=table,
                status=response.status_code,
            )

    def ingest_bars(
        self, bars: Iterable[dict], *, chunk_size: int = 2_000
    ) -> None:  # pragma: no cover - exercised in integration
        rows = list(bars)
        if not rows:
            return
        ids = self._identifiers
        table = ids.rollup_qualified
        insert_query = "INSERT INTO " + table + " FORMAT JSONEachRow"
        for chunk in _chunk_iterable(rows, chunk_size):
            payload = "\n".join(json.dumps(row, separators=(",", ":")) for row in chunk)
            response = self._client.post(
                self._config.write_path,
                params={"query": insert_query},
                content=payload.encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=self._insert_timeout,
            )
            if response.status_code >= 300:
                raise RuntimeError(
                    "ClickHouse bar ingest failed with status "
                    + str(response.status_code)
                    + ": "
                    + response.text
                )
            _LOGGER.debug(
                "clickhouse_bar_ingest_batch",
                rows=len(chunk),
                table=table,
                status=response.status_code,
            )

    def _serialise_tick(self, tick: PriceTick) -> str:
        payload = {
            "ts": tick.timestamp.astimezone(timezone.utc).isoformat(),
            "symbol": tick.symbol,
            "venue": tick.venue,
            "instrument_type": tick.instrument_type.value,
            "price": str(tick.price),
            "volume": str(tick.volume),
            "trade_id": tick.trade_id or "",
            "ingest_id": str(uuid4()),
            "ingest_ts": datetime.now(timezone.utc).isoformat(),
        }
        return json.dumps(payload, separators=(",", ":"))


def _chunk_iterable(items: Iterable, size: int) -> Iterable[Sequence]:
    if size <= 0:
        raise ValueError("chunk_size must be positive")
    batch: list = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield tuple(batch)
            batch.clear()
    if batch:
        yield tuple(batch)


__all__ = ["ClickHouseWarehouse", "ClickHouseConfig"]
