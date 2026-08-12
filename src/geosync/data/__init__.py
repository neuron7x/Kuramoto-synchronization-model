# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync data module - Unified data layer for market data.

This module provides the canonical data schemas, validation utilities,
and data access APIs for the entire GeoSync platform.

**Core Components**

- ``schema``: Unified market data models (Bar, Tick, FeatureVector, MarketSnapshot)
- ``validation``: Time series and OHLCV validation utilities
- ``quality``: Data quality checks and reporting
- ``api``: Unified data access layer for strategies

Example:
    >>> from geosync.data.schema import Bar, Timeframe
    >>> from geosync.data.validation import validate_ohlcv
    >>> from geosync.data.quality import validate_series
    >>> from geosync.data.api import load_historical_bars, get_historical_window
    >>>
    >>> # Load historical data from CSV
    >>> bars = load_historical_bars("data/btcusdt.csv", symbol="BTCUSDT")
    >>>
    >>> # Get a time window
    >>> window = get_historical_window(
    ...     bars,
    ...     start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    ...     end=datetime(2024, 1, 31, tzinfo=timezone.utc),
    ... )
    >>>
    >>> # Validate a series of bars
    >>> report = validate_series(bars)
    >>> if not report.is_valid():
    ...     print(report.issues)
"""

__CANONICAL__ = True

# Validation utilities from core
from core.data.validation import (
    OHLCVValidationResult,
    TimeSeriesValidationConfig,
    TimeSeriesValidationError,
    ValueColumnConfig,
    build_timeseries_schema,
    validate_ohlcv,
    validate_timeseries_frame,
)

# Data access API
from .api import (
    DataSource,
    DataSourceConfig,
    get_feature_window,
    get_historical_window,
    get_latest_snapshot,
    load_historical_bars,
    normalize_bars,
)

# Data quality validation
from .quality import (
    DataQualityError,
    DataQualityIssue,
    DataQualityReport,
    IssueSeverity,
    check_monotonic_time,
    detect_duplicates,
    detect_gaps,
    detect_outliers,
    require_valid_data,
    validate_series,
)

# Unified schema models
from .schema import (
    Bar,
    Candle,
    DataQualityStatus,
    FeatureVector,
    MarketSnapshot,
    OrderSide,
    Tick,
    Timeframe,
)

__all__ = [
    # Schema models
    "Bar",
    "Candle",
    "DataQualityStatus",
    "FeatureVector",
    "MarketSnapshot",
    "OrderSide",
    "Tick",
    "Timeframe",
    # Validation utilities
    "OHLCVValidationResult",
    "TimeSeriesValidationConfig",
    "TimeSeriesValidationError",
    "ValueColumnConfig",
    "build_timeseries_schema",
    "validate_ohlcv",
    "validate_timeseries_frame",
    # Quality validation
    "DataQualityError",
    "DataQualityIssue",
    "DataQualityReport",
    "IssueSeverity",
    "check_monotonic_time",
    "detect_duplicates",
    "detect_gaps",
    "detect_outliers",
    "require_valid_data",
    "validate_series",
    # Data API
    "DataSource",
    "DataSourceConfig",
    "get_feature_window",
    "get_historical_window",
    "get_latest_snapshot",
    "load_historical_bars",
    "normalize_bars",
]
