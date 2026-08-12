# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Time-series data management primitives for GeoSync."""

from .benchmarks import BenchmarkRunner
from .clickhouse import (
    ClickHouseBackupPlanner,
    ClickHouseIndex,
    ClickHouseIngestionConnector,
    ClickHouseQueryBuilder,
    ClickHouseSchemaManager,
    ClickHouseSLAManager,
)
from .config import (
    AggregationSpec,
    BenchmarkWorkload,
    DimensionColumn,
    IngestionConnectorConfig,
    MeasureColumn,
    RetentionPolicy,
    RollupAggregation,
    RollupMaterialization,
    SLAMetric,
    TimeSeriesSchema,
)
from .timescale import (
    TimescaleBackupPlanner,
    TimescaleIngestionConnector,
    TimescaleQueryBuilder,
    TimescaleSchemaManager,
    TimescaleSLAManager,
)

__all__ = [
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
]
