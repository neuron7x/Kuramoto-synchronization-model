# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Database connection helpers and high level data access abstractions."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
    "Base",
    "DataAccessLayer",
    "DatabasePoolConfig",
    "DatabaseRuntimeConfig",
    "DatabaseSettings",
    "KillSwitchState",
    "KillSwitchStateRepository",
    "RetryPolicy",
    "SessionManager",
    "SqlAlchemyRepository",
    "AggregationSpec",
    "BenchmarkRunner",
    "BenchmarkWorkload",
    "ClickHouseBackupPlanner",
    "ClickHouseIndex",
    "ClickHouseIngestionConnector",
    "ClickHouseQueryBuilder",
    "ClickHouseSchemaManager",
    "ClickHouseSLAManager",
    "DimensionColumn",
    "IngestionConnectorConfig",
    "MeasureColumn",
    "RetentionPolicy",
    "RollupAggregation",
    "RollupMaterialization",
    "SLAMetric",
    "TimeSeriesSchema",
    "TimescaleBackupPlanner",
    "TimescaleIngestionConnector",
    "TimescaleQueryBuilder",
    "TimescaleSchemaManager",
    "TimescaleSLAManager",
    "create_engine_from_config",
    "create_postgres_connection",
    "warm_pool",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "Base": ("libs.db.models", "Base"),
    "DataAccessLayer": ("libs.db.access", "DataAccessLayer"),
    "DatabasePoolConfig": ("libs.db.config", "DatabasePoolConfig"),
    "DatabaseRuntimeConfig": ("libs.db.config", "DatabaseRuntimeConfig"),
    "DatabaseSettings": ("libs.db.config", "DatabaseSettings"),
    "KillSwitchState": ("libs.db.models", "KillSwitchState"),
    "KillSwitchStateRepository": ("libs.db.repository", "KillSwitchStateRepository"),
    "RetryPolicy": ("libs.db.retry", "RetryPolicy"),
    "SessionManager": ("libs.db.session", "SessionManager"),
    "SqlAlchemyRepository": ("libs.db.repository", "SqlAlchemyRepository"),
    "create_engine_from_config": ("libs.db.engine", "create_engine_from_config"),
    "create_postgres_connection": ("libs.db.postgres", "create_postgres_connection"),
    "warm_pool": ("libs.db.engine", "warm_pool"),
    "AggregationSpec": ("libs.db.timeseries.config", "AggregationSpec"),
    "BenchmarkRunner": ("libs.db.timeseries.benchmarks", "BenchmarkRunner"),
    "BenchmarkWorkload": ("libs.db.timeseries.config", "BenchmarkWorkload"),
    "ClickHouseBackupPlanner": (
        "libs.db.timeseries.clickhouse",
        "ClickHouseBackupPlanner",
    ),
    "ClickHouseIndex": ("libs.db.timeseries.clickhouse", "ClickHouseIndex"),
    "ClickHouseIngestionConnector": (
        "libs.db.timeseries.clickhouse",
        "ClickHouseIngestionConnector",
    ),
    "ClickHouseQueryBuilder": (
        "libs.db.timeseries.clickhouse",
        "ClickHouseQueryBuilder",
    ),
    "ClickHouseSchemaManager": (
        "libs.db.timeseries.clickhouse",
        "ClickHouseSchemaManager",
    ),
    "ClickHouseSLAManager": ("libs.db.timeseries.clickhouse", "ClickHouseSLAManager"),
    "DimensionColumn": ("libs.db.timeseries.config", "DimensionColumn"),
    "IngestionConnectorConfig": (
        "libs.db.timeseries.config",
        "IngestionConnectorConfig",
    ),
    "MeasureColumn": ("libs.db.timeseries.config", "MeasureColumn"),
    "RetentionPolicy": ("libs.db.timeseries.config", "RetentionPolicy"),
    "RollupAggregation": ("libs.db.timeseries.config", "RollupAggregation"),
    "RollupMaterialization": ("libs.db.timeseries.config", "RollupMaterialization"),
    "SLAMetric": ("libs.db.timeseries.config", "SLAMetric"),
    "TimeSeriesSchema": ("libs.db.timeseries.config", "TimeSeriesSchema"),
    "TimescaleBackupPlanner": (
        "libs.db.timeseries.timescale",
        "TimescaleBackupPlanner",
    ),
    "TimescaleIngestionConnector": (
        "libs.db.timeseries.timescale",
        "TimescaleIngestionConnector",
    ),
    "TimescaleQueryBuilder": ("libs.db.timeseries.timescale", "TimescaleQueryBuilder"),
    "TimescaleSchemaManager": (
        "libs.db.timeseries.timescale",
        "TimescaleSchemaManager",
    ),
    "TimescaleSLAManager": ("libs.db.timeseries.timescale", "TimescaleSLAManager"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _LAZY_IMPORTS[name]
    except KeyError as exc:  # pragma: no cover - defensive
        msg = f"module {__name__} has no attribute {name}"
        raise AttributeError(msg) from exc
    module = import_module(module_name)
    value = getattr(module, attribute)
    globals()[name] = value
    return value


if TYPE_CHECKING:  # pragma: no cover - import-time type checking only
    from .access import DataAccessLayer
    from .config import DatabasePoolConfig, DatabaseRuntimeConfig, DatabaseSettings
    from .engine import create_engine_from_config, warm_pool
    from .models import Base, KillSwitchState
    from .postgres import create_postgres_connection
    from .repository import KillSwitchStateRepository, SqlAlchemyRepository
    from .retry import RetryPolicy
    from .session import SessionManager
    from .timeseries import (
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
