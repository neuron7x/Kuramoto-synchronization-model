# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""TradePulse data module - Data validation and processing utilities.

This module provides convenient access to data validation and quality control
functionality through the tradepulse namespace, as documented in the README.

Example:
    >>> from tradepulse.data.validation import validate_ohlcv
    >>> result = validate_ohlcv(df)
    >>> if not result.valid:
    ...     print(result.issues)
"""

from core.data.validation import (
    OHLCVValidationResult,
    TimeSeriesValidationConfig,
    TimeSeriesValidationError,
    ValueColumnConfig,
    build_timeseries_schema,
    validate_ohlcv,
    validate_timeseries_frame,
)

__all__ = [
    "OHLCVValidationResult",
    "TimeSeriesValidationConfig",
    "TimeSeriesValidationError",
    "ValueColumnConfig",
    "build_timeseries_schema",
    "validate_ohlcv",
    "validate_timeseries_frame",
]
