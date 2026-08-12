# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from datetime import timedelta
from typing import Any, Mapping, Sequence

import pytest

from libs.db.timeseries import (
    AggregationSpec,
    BenchmarkRunner,
    BenchmarkWorkload,
    ClickHouseBackupPlanner,
    ClickHouseIndex,
    ClickHouseIngestionConnector,
    ClickHouseQueryBuilder,
    ClickHouseSchemaManager,
    ClickHouseSLAManager,
    DimensionColumn,
    IngestionConnectorConfig,
    MeasureColumn,
    RetentionPolicy,
    RollupAggregation,
    RollupMaterialization,
    SLAMetric,
    TimescaleBackupPlanner,
    TimescaleIngestionConnector,
    TimescaleQueryBuilder,
    TimescaleSchemaManager,
    TimescaleSLAManager,
    TimeSeriesSchema,
)


@pytest.fixture
def schema() -> TimeSeriesSchema:
    return TimeSeriesSchema(
        database="marketdata",
        table="ticks",
        timestamp_column="timestamp",
        dimensions=(DimensionColumn("symbol"), DimensionColumn("venue")),
        measures=(
            MeasureColumn(
                "price",
                "Float64",
                aggregations=(AggregationSpec("avg_price", "avg(price)"),),
            ),
            MeasureColumn("volume", "Float64"),
        ),
        metadata=(DimensionColumn("ingestion_id", data_type="UUID", nullable=True),),
    )


@pytest.fixture
def retention() -> RetentionPolicy:
    return RetentionPolicy(
        hot=timedelta(days=7),
        warm=timedelta(days=30),
        cold=timedelta(days=90),
        drop=timedelta(days=365),
    )


@pytest.fixture
def rollup() -> RollupMaterialization:
    return RollupMaterialization(
        name="ticks_1h",
        interval=timedelta(hours=1),
        aggregations=(
            RollupAggregation(alias="avg_price", expression="avg(price)", data_type="Float64"),
            RollupAggregation(alias="total_volume", expression="sum(volume)", data_type="Float64"),
        ),
        refresh_lag=timedelta(minutes=5),
    )


class FakeClickHouseClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[list[Any]], list[str]]] = []

    def insert(self, table: str, rows: list[list[Any]], column_names: list[str]) -> None:
        self.calls.append((table, rows, column_names))


def test_clickhouse_create_table(schema: TimeSeriesSchema, retention: RetentionPolicy) -> None:
    manager = ClickHouseSchemaManager(
        schema=schema,
        retention=retention,
        indexes=(ClickHouseIndex(name="idx_symbol", expression="symbol"),),
    )
    ddl = manager.create_table_sql()
    assert "CREATE TABLE IF NOT EXISTS marketdata.ticks" in ddl
    assert "PARTITION BY toYYYYMMDD(timestamp)" in ddl
    assert "TTL timestamp + INTERVAL 7 DAY TO VOLUME 'hot'" in ddl
    assert "DELETE" in ddl


def test_clickhouse_rollup_table_and_mv(
    schema: TimeSeriesSchema, retention: RetentionPolicy, rollup: RollupMaterialization
) -> None:
    manager = ClickHouseSchemaManager(schema=schema, retention=retention)
    table_sql = manager.rollup_table_sql(rollup)
    mv_sql = manager.materialized_view_sql(rollup)
    assert "CREATE TABLE IF NOT EXISTS marketdata.ticks_1h" in table_sql
    assert "avg_price Float64" in table_sql
    assert "CREATE MATERIALIZED VIEW IF NOT EXISTS marketdata.ticks_1h_mv" in mv_sql
    assert "TO marketdata.ticks_1h" in mv_sql
    assert "GROUP BY bucket, symbol, venue" in mv_sql


def test_clickhouse_ingestion_connector(schema: TimeSeriesSchema) -> None:
    client = FakeClickHouseClient()
    connector = ClickHouseIngestionConnector(
        client=client,
        schema=schema,
        config=IngestionConnectorConfig(batch_size=2, flush_interval=timedelta(seconds=1)),
    )
    records = [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "symbol": "BTC",
            "venue": "CME",
            "price": 10.0,
            "volume": 1.0,
        },
        {
            "timestamp": "2024-01-01T00:00:01Z",
            "symbol": "BTC",
            "venue": "CME",
            "price": 11.0,
            "volume": 2.0,
        },
        {
            "timestamp": "2024-01-01T00:00:02Z",
            "symbol": "BTC",
            "venue": "CME",
            "price": 12.0,
            "volume": 3.0,
        },
    ]
    flushed = connector.ingest_many(records)
    assert flushed == 2
    assert len(client.calls) == 1
    assert client.calls[0][2][0] == "timestamp"
    connector.flush()
    assert len(client.calls) == 2


def test_clickhouse_query_builder(schema: TimeSeriesSchema, rollup: RollupMaterialization) -> None:
    builder = ClickHouseQueryBuilder(schema)
    query = builder.ohlcv_query(filters={"symbol": "BTC"})
    assert "toStartOfInterval(timestamp" in query
    assert "PREWHERE symbol = %(symbol)s" in query
    assert "sum(volume) AS volume" in query

    rollup_query = builder.ohlcv_query(rollup=rollup)
    assert "FROM marketdata.ticks_1h" in rollup_query
    assert "GROUP BY bucket, symbol, venue" in rollup_query


def test_clickhouse_sla_metrics(schema: TimeSeriesSchema) -> None:
    sla = ClickHouseSLAManager(schema).latency_metrics()
    assert {metric.name for metric in sla} == {
        "ohlcv_latency_p99",
        "ingest_lag_seconds",
    }
    for metric in sla:
        assert isinstance(metric, SLAMetric)


def test_clickhouse_backup_plan(schema: TimeSeriesSchema) -> None:
    planner = ClickHouseBackupPlanner(schema=schema, retention_days=21)
    assert "clickhouse-backup create --tables marketdata.ticks" in planner.full_backup_command()
    assert "retain 21 days" == planner.retention_policy()


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def executemany(self, statement: str, rows: list[tuple[Any, ...]]) -> None:
        self.connection.statements.append((statement, rows))

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.commits = 0

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1


def test_timescale_schema_manager(
    schema: TimeSeriesSchema, retention: RetentionPolicy, rollup: RollupMaterialization
) -> None:
    manager = TimescaleSchemaManager(schema=schema, retention=retention)
    assert "CREATE TABLE IF NOT EXISTS ticks" in manager.create_table_sql()
    assert "create_hypertable" in manager.hypertable_sql()
    indexes = manager.indexes_sql()
    assert any("symbol" in index for index in indexes)
    compression = manager.compression_sql()
    assert any("add_compression_policy" in stmt for stmt in compression)
    retention_stmt = manager.retention_sql()
    assert "add_retention_policy" in retention_stmt
    definition, refresh = manager.continuous_aggregate_sql(rollup)
    assert "CREATE MATERIALIZED VIEW" in definition
    assert "add_continuous_aggregate_policy" in refresh


def test_timescale_ingestion_connector(schema: TimeSeriesSchema) -> None:
    connection = FakeConnection()
    connector = TimescaleIngestionConnector(
        connection=connection,
        schema=schema,
        config=IngestionConnectorConfig(batch_size=2, flush_interval=timedelta(seconds=1)),
    )
    rows = [
        {
            "timestamp": "2024-01-01T00:00:00Z",
            "symbol": "BTC",
            "venue": "CME",
            "price": 10.0,
            "volume": 1.0,
        },
        {
            "timestamp": "2024-01-01T00:00:01Z",
            "symbol": "BTC",
            "venue": "CME",
            "price": 11.0,
            "volume": 2.0,
        },
    ]
    inserted = connector.ingest_many(rows)
    assert inserted == 2
    assert connection.commits == 1
    statement, parameters = connection.statements[0]
    assert "INSERT INTO ticks" in statement
    assert len(parameters) == 2


def test_timescale_query_builder(schema: TimeSeriesSchema, rollup: RollupMaterialization) -> None:
    builder = TimescaleQueryBuilder(schema)
    query = builder.ohlcv_query(filters={"symbol": "BTC"})
    assert "time_bucket(" in query
    assert "WHERE timestamp >= %(start_ts)s" in query
    assert "GROUP BY bucket, symbol, venue" in query

    rollup_query = builder.ohlcv_query(rollup=rollup)
    assert "FROM ticks_1h_cagg" in rollup_query


def test_timescale_sla(schema: TimeSeriesSchema) -> None:
    sla = TimescaleSLAManager(schema).latency_metrics()
    assert {metric.name for metric in sla} == {
        "timescale_ohlcv_latency_p99",
        "timescale_ingest_lag_seconds",
    }


def test_timescale_backup_plan(schema: TimeSeriesSchema) -> None:
    planner = TimescaleBackupPlanner(schema=schema, retention_days=45)
    assert "pg_dump" in planner.full_backup_command()
    assert "retain 45 days" == planner.retention_policy()


def test_benchmark_runner(schema: TimeSeriesSchema) -> None:
    workload = BenchmarkWorkload(
        name="smoke", ingest_batches=(2, 3), query_iterations=2, warmup_iterations=1
    )
    times = iter([0.0, 0.001, 0.002, 0.004, 0.005, 0.007, 0.008, 0.011])

    def clock() -> float:
        return next(times)

    ingested_batches: list[list[Mapping[str, Any]]] = []
    queries: list[Mapping[str, Any]] = []

    def ingest(records: Sequence[Mapping[str, Any]]) -> None:
        ingested_batches.append(list(records))

    def query(params: Mapping[str, Any]) -> None:
        queries.append(dict(params))

    runner = BenchmarkRunner(schema, clock=clock)
    metrics = runner.run(workload=workload, ingestion_callable=ingest, query_callable=query)

    assert metrics.rows_ingested == 5
    assert len(ingested_batches) == 2
    assert len(queries) == workload.warmup_iterations + workload.query_iterations
    assert metrics.ingest_p50_ms > 0
    assert metrics.query_p95_ms > 0
    assert metrics.ingest_throughput_rows_s > 0
    assert metrics.query_throughput_qps > 0
