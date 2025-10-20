"""Database connection helpers and high level data access abstractions."""

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
