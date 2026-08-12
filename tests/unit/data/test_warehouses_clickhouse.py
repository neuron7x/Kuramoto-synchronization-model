# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for ClickHouse warehouse integration."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest
from pytest_httpx import HTTPXMock

from core.data.models import InstrumentType, MarketMetadata, PriceTick
from core.data.warehouses.clickhouse import (
    ClickHouseConfig,
    ClickHouseWarehouse,
    _chunk_iterable,
    _ClickHouseIdentifiers,
)


class TestClickHouseConfig:
    """Tests for ClickHouseConfig dataclass."""

    def test_default_config_values(self) -> None:
        """Verify default configuration values."""
        config = ClickHouseConfig()
        assert config.database == "geosync"
        assert config.raw_table == "raw_ticks"
        assert config.rollup_table == "minute_bars"
        assert config.retention_days == 30
        assert config.rollup_retention_days == 180
        assert config.timezone_name == "UTC"
        assert config.write_path == "/"

    def test_custom_config_values(self) -> None:
        """Verify custom configuration values are applied."""
        config = ClickHouseConfig(
            database="custom_db",
            raw_table="custom_ticks",
            rollup_table="custom_bars",
            retention_days=60,
            rollup_retention_days=365,
            timezone_name="America/New_York",
            write_path="/custom",
        )
        assert config.database == "custom_db"
        assert config.raw_table == "custom_ticks"
        assert config.rollup_table == "custom_bars"
        assert config.retention_days == 60
        assert config.rollup_retention_days == 365
        assert config.timezone_name == "America/New_York"
        assert config.write_path == "/custom"

    def test_invalid_database_name_raises(self) -> None:
        """Verify invalid database name raises ValueError."""
        with pytest.raises(ValueError, match="must match"):
            ClickHouseConfig(database="invalid-name")

    def test_invalid_raw_table_name_raises(self) -> None:
        """Verify invalid raw_table name raises ValueError."""
        with pytest.raises(ValueError, match="must match"):
            ClickHouseConfig(raw_table="drop; table")

    def test_invalid_rollup_table_name_raises(self) -> None:
        """Verify invalid rollup_table name raises ValueError."""
        with pytest.raises(ValueError, match="must match"):
            ClickHouseConfig(rollup_table="my table")

    def test_invalid_timezone_raises(self) -> None:
        """Verify invalid timezone raises ValueError."""
        with pytest.raises(ValueError, match="unexpected characters"):
            ClickHouseConfig(timezone_name="UTC;DROP")


class TestClickHouseIdentifiers:
    """Tests for _ClickHouseIdentifiers dataclass."""

    def test_from_config_creates_identifiers(self) -> None:
        """Verify identifiers are created from config."""
        config = ClickHouseConfig(
            database="test_db",
            raw_table="test_ticks",
            rollup_table="test_bars",
            timezone_name="UTC",
        )
        identifiers = _ClickHouseIdentifiers.from_config(config)
        assert identifiers.database == "test_db"
        assert identifiers.raw_table == "test_ticks"
        assert identifiers.rollup_table == "test_bars"
        assert identifiers.raw_qualified == "test_db.test_ticks"
        assert identifiers.rollup_qualified == "test_db.test_bars"
        assert identifiers.mv_rollup == "test_db.mv_test_bars"
        assert identifiers.timezone_literal == "'UTC'"

    def test_from_config_with_complex_timezone(self) -> None:
        """Verify identifiers with complex timezone."""
        config = ClickHouseConfig(timezone_name="America/New_York")
        identifiers = _ClickHouseIdentifiers.from_config(config)
        assert identifiers.timezone_literal == "'America/New_York'"


def _mock_only_test_clickhouse(request: httpx.Request) -> bool:
    """Confine httpx_mock to the warehouse's own `test-clickhouse` host.

    An `execution.watchdog.Watchdog` default-instantiated elsewhere in the
    process (default `health_url=http://127.0.0.1:8085/health/live`) races
    the strict mock and triggers AssertionError("request not expected")
    on ingest-error paths. Returning False for 127.0.0.1 lets the
    watchdog probe pass through; the warehouse's own INSERT requests
    still hit the mock.
    """
    return "test-clickhouse" in str(request.url)


@pytest.mark.httpx_mock(should_mock=_mock_only_test_clickhouse)
class TestClickHouseWarehouse:
    """Tests for ClickHouseWarehouse class."""

    @pytest.fixture
    def http_client(self) -> httpx.Client:
        """Create a test HTTP client."""
        return httpx.Client(base_url="http://test-clickhouse:8123")

    @pytest.fixture
    def warehouse(self, http_client: httpx.Client) -> ClickHouseWarehouse:
        """Create a test warehouse."""
        return ClickHouseWarehouse(http_client)

    @pytest.fixture
    def sample_tick(self) -> PriceTick:
        """Create a sample PriceTick for testing."""
        metadata = MarketMetadata(
            symbol="BTCUSD",
            venue="binance",
            instrument_type=InstrumentType.SPOT,
        )
        return PriceTick(
            metadata=metadata,
            timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            price=Decimal("50000.50"),
            volume=Decimal("1.5"),
            trade_id="trade123",
        )

    def test_bootstrap_statements_returns_correct_count(
        self, warehouse: ClickHouseWarehouse
    ) -> None:
        """Verify bootstrap returns expected number of statements."""
        statements = warehouse.bootstrap_statements()
        assert len(statements) == 4

    def test_bootstrap_statements_creates_database(self, warehouse: ClickHouseWarehouse) -> None:
        """Verify bootstrap creates database statement."""
        statements = warehouse.bootstrap_statements()
        db_statement = statements[0]
        assert "CREATE DATABASE IF NOT EXISTS" in db_statement.sql
        assert "geosync" in db_statement.sql

    def test_bootstrap_statements_creates_raw_table(self, warehouse: ClickHouseWarehouse) -> None:
        """Verify bootstrap creates raw table statement."""
        statements = warehouse.bootstrap_statements()
        raw_statement = statements[1]
        assert "CREATE TABLE IF NOT EXISTS" in raw_statement.sql
        assert "raw_ticks" in raw_statement.sql
        assert "MergeTree" in raw_statement.sql
        assert "TTL" in raw_statement.sql

    def test_bootstrap_statements_creates_rollup_table(
        self, warehouse: ClickHouseWarehouse
    ) -> None:
        """Verify bootstrap creates rollup table statement."""
        statements = warehouse.bootstrap_statements()
        rollup_statement = statements[2]
        assert "CREATE TABLE IF NOT EXISTS" in rollup_statement.sql
        assert "minute_bars" in rollup_statement.sql

    def test_bootstrap_statements_creates_materialized_view(
        self, warehouse: ClickHouseWarehouse
    ) -> None:
        """Verify bootstrap creates materialized view."""
        statements = warehouse.bootstrap_statements()
        mv_statement = statements[3]
        assert "MATERIALIZED VIEW" in mv_statement.sql
        assert "mv_minute_bars" in mv_statement.sql

    def test_rollup_jobs_returns_jobs(self, warehouse: ClickHouseWarehouse) -> None:
        """Verify rollup jobs are returned."""
        jobs = warehouse.rollup_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == "clickhouse-minute-bars-refresh"
        assert "OPTIMIZE" in jobs[0].statement.sql
        assert jobs[0].schedule_hint == "*/5 * * * *"

    def test_maintenance_tasks_returns_tasks(self, warehouse: ClickHouseWarehouse) -> None:
        """Verify maintenance tasks are returned."""
        tasks = warehouse.maintenance_tasks()
        assert len(tasks) == 2
        assert tasks[0].name == "clickhouse-raw-optimize"
        assert tasks[0].cadence == "hourly"
        assert tasks[1].name == "clickhouse-rollup-optimize"
        assert tasks[1].cadence == "daily"

    def test_sla_queries_returns_queries(self, warehouse: ClickHouseWarehouse) -> None:
        """Verify SLA queries are returned."""
        queries = warehouse.sla_queries()
        assert len(queries) == 3
        assert queries[0].name == "tick_ingest_latency"
        assert queries[1].name == "minute_bar_freshness"
        assert queries[2].name == "ingest_throughput"

    def test_benchmark_scenarios_returns_scenarios(self, warehouse: ClickHouseWarehouse) -> None:
        """Verify benchmark scenarios are returned."""
        scenarios = warehouse.benchmark_scenarios()
        assert len(scenarios) == 2
        assert scenarios[0].name == "clickhouse-tick-ingest-50k"
        assert scenarios[0].target_qps == 50000
        assert scenarios[1].name == "clickhouse-rollup-scan"
        assert scenarios[1].target_qps == 1000

    def test_backup_plan_returns_steps(self, warehouse: ClickHouseWarehouse) -> None:
        """Verify backup plan steps are returned."""
        steps = warehouse.backup_plan()
        assert len(steps) == 2
        assert "BACKUP TABLE" in steps[0].command
        assert "RESTORE" in steps[1].command

    def test_ingest_ticks_with_empty_list(self, warehouse: ClickHouseWarehouse) -> None:
        """Verify empty tick list is handled gracefully."""
        warehouse.ingest_ticks([])  # Should not raise

    def test_ingest_ticks_success(
        self, http_client: httpx.Client, sample_tick: PriceTick, httpx_mock: HTTPXMock
    ) -> None:
        """Verify tick ingestion sends correct request."""
        httpx_mock.add_response(status_code=200)

        warehouse = ClickHouseWarehouse(http_client)
        warehouse.ingest_ticks([sample_tick], chunk_size=10)

        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "INSERT INTO" in requests[0].url.params.get("query", "")
        assert "JSONEachRow" in requests[0].url.params.get("query", "")

    def test_ingest_ticks_failure_raises(
        self, http_client: httpx.Client, sample_tick: PriceTick, httpx_mock: HTTPXMock
    ) -> None:
        """Verify tick ingestion failure raises RuntimeError."""
        httpx_mock.add_response(status_code=500, text="Internal Server Error")

        warehouse = ClickHouseWarehouse(http_client)
        with pytest.raises(RuntimeError, match="ClickHouse ingest failed"):
            warehouse.ingest_ticks([sample_tick])


class TestChunkIterable:
    """Tests for _chunk_iterable utility function."""

    def test_chunk_iterable_single_chunk(self) -> None:
        """Verify single chunk when items fit."""
        items = [1, 2, 3]
        chunks = list(_chunk_iterable(items, 10))
        assert len(chunks) == 1
        assert chunks[0] == (1, 2, 3)

    def test_chunk_iterable_multiple_chunks(self) -> None:
        """Verify multiple chunks are created."""
        items = [1, 2, 3, 4, 5]
        chunks = list(_chunk_iterable(items, 2))
        assert len(chunks) == 3
        assert chunks[0] == (1, 2)
        assert chunks[1] == (3, 4)
        assert chunks[2] == (5,)

    def test_chunk_iterable_exact_size(self) -> None:
        """Verify chunks when items exactly fit."""
        items = [1, 2, 3, 4]
        chunks = list(_chunk_iterable(items, 2))
        assert len(chunks) == 2
        assert chunks[0] == (1, 2)
        assert chunks[1] == (3, 4)

    def test_chunk_iterable_empty_list(self) -> None:
        """Verify empty list produces no chunks."""
        chunks = list(_chunk_iterable([], 10))
        assert len(chunks) == 0

    def test_chunk_iterable_invalid_size_raises(self) -> None:
        """Verify invalid chunk size raises ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be positive"):
            list(_chunk_iterable([1, 2], 0))

        with pytest.raises(ValueError, match="chunk_size must be positive"):
            list(_chunk_iterable([1, 2], -1))
