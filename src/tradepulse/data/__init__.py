# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""TradePulse data module - Unified data layer for market data.

This module provides the canonical data schemas, validation utilities,
and data access APIs for the entire TradePulse platform.

**Core Components**

- ``schema``: Unified market data models (Bar, Tick, FeatureVector, MarketSnapshot)
- ``validation``: Time series and OHLCV validation utilities
- ``quality``: Data quality checks and reporting
- ``api``: Unified data access layer for strategies

Example:
    >>> from tradepulse.data.schema import Bar, Timeframe
    >>> from tradepulse.data.validation import validate_ohlcv
    >>> from tradepulse.data.quality import validate_series
    >>> from tradepulse.data.api import load_historical_bars, get_historical_window
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

from importlib import import_module
from typing import Any

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

_SCHEMA_EXPORTS = {
    "Bar",
    "Candle",
    "DataQualityStatus",
    "FeatureVector",
    "MarketSnapshot",
    "OrderSide",
    "Tick",
    "Timeframe",
}
_VALIDATION_EXPORTS = {
    "OHLCVValidationResult",
    "TimeSeriesValidationConfig",
    "TimeSeriesValidationError",
    "ValueColumnConfig",
    "build_timeseries_schema",
    "validate_ohlcv",
    "validate_timeseries_frame",
}
_QUALITY_EXPORTS = {
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
}
_API_EXPORTS = {
    "DataSource",
    "DataSourceConfig",
    "get_feature_window",
    "get_historical_window",
    "get_latest_snapshot",
    "load_historical_bars",
    "normalize_bars",
}


def __getattr__(name: str) -> Any:
    if name in _SCHEMA_EXPORTS:
        module = import_module("tradepulse.data.schema")
        return getattr(module, name)
    if name in _VALIDATION_EXPORTS:
        module = import_module("core.data.validation")
        return getattr(module, name)
    if name in _QUALITY_EXPORTS:
        module = import_module("tradepulse.data.quality")
        return getattr(module, name)
    if name in _API_EXPORTS:
        module = import_module("tradepulse.data.api")
        return getattr(module, name)
    raise AttributeError(name)
