# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Data quality validation module for historical market data.

This module provides comprehensive validation checks for historical market data
before it enters the backtest pipeline. The goal is to catch data quality issues
that could lead to unrealistic backtest results or mask strategy flaws.

**Key Checks**

* Gap detection: identifies missing bars in time series
* Price validation: catches non-positive, NaN, or unrealistic price jumps
* Timezone consistency: detects unexpected timestep changes
* Duplicate detection: finds duplicate timestamps in the data

**Usage**

All backtest runs should validate data quality before execution:

    >>> report = validate_historical_data(df)
    >>> if not report.is_valid:
    ...     raise ValueError(f"Data quality issues: {report.issues}")

If you want to proceed with known data issues, use the skip flag:

    >>> report = validate_historical_data(df, skip_validation=True)

"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from numpy.typing import NDArray


class IssueSeverity(Enum):
    """Severity level for data quality issues."""

    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(slots=True)
class DataQualityIssue:
    """Represents a single data quality issue found during validation.

    Attributes:
        code: Short identifier for the issue type (e.g., "GAP_DETECTED")
        message: Human-readable description of the issue
        severity: How severe the issue is
        details: Additional context (e.g., affected indices, values)
    """

    code: str
    message: str
    severity: IssueSeverity
    details: Mapping[str, Any] | None = None


def _serialize_value(value: Any) -> Any:
    """Convert a value to a JSON-serializable type."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    # Handle pandas/numpy types
    if hasattr(value, "isoformat"):  # datetime-like
        return value.isoformat()
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return str(value)


def _serialize_details(details: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Serialize issue details to JSON-compatible format."""
    if details is None:
        return None
    return {str(k): _serialize_value(v) for k, v in details.items()}


@dataclass(slots=True)
class DataQualityReport:
    """Result of data quality validation.

    Attributes:
        is_valid: True if no critical/error issues found
        issues: List of all detected issues
        warnings_count: Number of warning-level issues
        errors_count: Number of error-level issues
        critical_count: Number of critical-level issues
        validated_rows: Number of rows validated
        skipped: Whether validation was skipped
    """

    is_valid: bool
    issues: list[DataQualityIssue] = field(default_factory=list)
    warnings_count: int = 0
    errors_count: int = 0
    critical_count: int = 0
    validated_rows: int = 0
    skipped: bool = False

    def has_errors(self) -> bool:
        """Return True if there are any error or critical issues."""
        return self.errors_count > 0 or self.critical_count > 0

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary representation."""
        return {
            "is_valid": self.is_valid,
            "issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "severity": issue.severity.value,
                    "details": _serialize_details(issue.details),
                }
                for issue in self.issues
            ],
            "warnings_count": self.warnings_count,
            "errors_count": self.errors_count,
            "critical_count": self.critical_count,
            "validated_rows": self.validated_rows,
            "skipped": self.skipped,
        }


# Default OHLC column mapping used by ValidationConfig
_DEFAULT_OHLC_COLUMNS: Mapping[str, str] = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
}


@dataclass(slots=True)
class ValidationConfig:
    """Configuration for data quality validation.

    Attributes:
        max_price_jump_pct: Maximum allowed price change between consecutive bars (%)
        min_price: Minimum valid price (inclusive)
        max_gap_bars: Maximum number of missing bars before flagging
        expected_timestep_seconds: Expected time between bars in seconds (None = auto-detect)
        timestep_tolerance_pct: Allowed deviation from expected timestep (%)
        price_columns: Column names to check for price validation
        ohlc_columns: Specific OHLC column names for price relationship validation
    """

    max_price_jump_pct: float = 50.0
    min_price: float = 0.0
    max_gap_bars: int = 1
    expected_timestep_seconds: float | None = None
    timestep_tolerance_pct: float = 10.0
    price_columns: Sequence[str] = ("open", "high", "low", "close")
    ohlc_columns: Mapping[str, str] = field(
        default_factory=lambda: dict(_DEFAULT_OHLC_COLUMNS)
    )


def _detect_gaps(
    timestamps: pd.DatetimeIndex | pd.Series,
    config: ValidationConfig,
) -> list[DataQualityIssue]:
    """Detect gaps (missing bars) in the time series."""
    issues: list[DataQualityIssue] = []

    if len(timestamps) < 2:
        return issues

    ts_array = pd.to_datetime(timestamps)
    # Convert to Series for proper diff behavior
    ts_series = pd.Series(ts_array)
    diffs = ts_series.diff()[1:]  # Skip first NaT

    # Auto-detect expected timestep if not provided
    expected_step = config.expected_timestep_seconds
    if expected_step is None:
        # Use median diff as expected step
        median_diff = diffs.median()
        if pd.isna(median_diff):
            return issues
        expected_step = median_diff.total_seconds()

    expected_step_td = pd.Timedelta(seconds=expected_step)
    tolerance = expected_step * (config.timestep_tolerance_pct / 100.0)
    tolerance_td = pd.Timedelta(seconds=tolerance)

    # Find gaps larger than expected step + tolerance
    gap_threshold = expected_step_td + tolerance_td
    gap_indices = diffs > gap_threshold

    if gap_indices.any():
        gap_positions = gap_indices[gap_indices].index.tolist()
        for pos in gap_positions:
            gap_size = diffs.loc[pos]
            expected_bars = int(gap_size / expected_step_td) - 1
            if expected_bars > config.max_gap_bars:
                issues.append(
                    DataQualityIssue(
                        code="GAP_DETECTED",
                        message=f"Gap of ~{expected_bars} bars detected at index {pos}",
                        severity=IssueSeverity.ERROR,
                        details={
                            "index": pos,
                            "gap_duration_seconds": gap_size.total_seconds(),
                            "expected_bars_missing": expected_bars,
                        },
                    )
                )

    return issues


def _validate_prices(
    data: pd.DataFrame,
    config: ValidationConfig,
) -> list[DataQualityIssue]:
    """Validate price columns for non-positive values and unrealistic jumps."""
    issues: list[DataQualityIssue] = []

    for col in config.price_columns:
        if col not in data.columns:
            continue

        prices = data[col]

        # Check for NaN values
        nan_count = prices.isna().sum()
        if nan_count > 0:
            issues.append(
                DataQualityIssue(
                    code="NAN_PRICES",
                    message=f"Column '{col}' contains {nan_count} NaN values",
                    severity=IssueSeverity.ERROR,
                    details={"column": col, "nan_count": int(nan_count)},
                )
            )

        # Check for non-positive prices
        non_positive = prices <= config.min_price
        non_positive_count = non_positive.sum()
        if non_positive_count > 0:
            non_positive_indices = non_positive[non_positive].index.tolist()[:10]
            issues.append(
                DataQualityIssue(
                    code="NON_POSITIVE_PRICES",
                    message=f"Column '{col}' contains {non_positive_count} non-positive values",
                    severity=IssueSeverity.CRITICAL,
                    details={
                        "column": col,
                        "count": int(non_positive_count),
                        "sample_indices": non_positive_indices,
                    },
                )
            )

        # Check for unrealistic price jumps
        if len(prices) > 1:
            price_array = prices.dropna()
            if len(price_array) > 1:
                pct_changes = price_array.pct_change().abs() * 100
                large_jumps = pct_changes > config.max_price_jump_pct
                jump_count = large_jumps.sum()
                if jump_count > 0:
                    jump_indices = large_jumps[large_jumps].index.tolist()[:10]
                    issues.append(
                        DataQualityIssue(
                            code="LARGE_PRICE_JUMP",
                            message=(
                                f"Column '{col}' has {jump_count} jumps "
                                f"exceeding {config.max_price_jump_pct}%"
                            ),
                            severity=IssueSeverity.WARNING,
                            details={
                                "column": col,
                                "count": int(jump_count),
                                "sample_indices": jump_indices,
                                "threshold_pct": config.max_price_jump_pct,
                            },
                        )
                    )

    return issues


def _validate_ohlc_relationships(
    data: pd.DataFrame,
    config: ValidationConfig,
) -> list[DataQualityIssue]:
    """Validate OHLC price relationships (high >= low, high >= open/close, etc.)."""
    issues: list[DataQualityIssue] = []

    ohlc = config.ohlc_columns
    required = {"open", "high", "low", "close"}
    if not all(col in ohlc for col in required):
        return issues

    open_col = ohlc.get("open", "open")
    high_col = ohlc.get("high", "high")
    low_col = ohlc.get("low", "low")
    close_col = ohlc.get("close", "close")

    if not all(col in data.columns for col in [open_col, high_col, low_col, close_col]):
        return issues

    # Check high >= low
    invalid_hl = data[high_col] < data[low_col]
    if invalid_hl.any():
        count = invalid_hl.sum()
        indices = invalid_hl[invalid_hl].index.tolist()[:10]
        issues.append(
            DataQualityIssue(
                code="INVALID_HIGH_LOW",
                message=f"{count} bars have high < low",
                severity=IssueSeverity.CRITICAL,
                details={"count": int(count), "sample_indices": indices},
            )
        )

    # Check high >= open and high >= close
    invalid_high_open = data[high_col] < data[open_col]
    invalid_high_close = data[high_col] < data[close_col]
    invalid_high = invalid_high_open | invalid_high_close
    if invalid_high.any():
        count = invalid_high.sum()
        indices = invalid_high[invalid_high].index.tolist()[:10]
        issues.append(
            DataQualityIssue(
                code="INVALID_HIGH",
                message=f"{count} bars have high < open or high < close",
                severity=IssueSeverity.CRITICAL,
                details={"count": int(count), "sample_indices": indices},
            )
        )

    # Check low <= open and low <= close
    invalid_low_open = data[low_col] > data[open_col]
    invalid_low_close = data[low_col] > data[close_col]
    invalid_low = invalid_low_open | invalid_low_close
    if invalid_low.any():
        count = invalid_low.sum()
        indices = invalid_low[invalid_low].index.tolist()[:10]
        issues.append(
            DataQualityIssue(
                code="INVALID_LOW",
                message=f"{count} bars have low > open or low > close",
                severity=IssueSeverity.CRITICAL,
                details={"count": int(count), "sample_indices": indices},
            )
        )

    return issues


def _detect_duplicates(
    data: pd.DataFrame,
) -> list[DataQualityIssue]:
    """Detect duplicate timestamps in the data."""
    issues: list[DataQualityIssue] = []

    if isinstance(data.index, pd.DatetimeIndex):
        duplicates = data.index.duplicated()
        dup_count = duplicates.sum()
        if dup_count > 0:
            dup_indices = data.index[duplicates].tolist()[:10]
            issues.append(
                DataQualityIssue(
                    code="DUPLICATE_TIMESTAMPS",
                    message=f"Found {dup_count} duplicate timestamps",
                    severity=IssueSeverity.ERROR,
                    details={
                        "count": int(dup_count),
                        "sample_timestamps": [str(t) for t in dup_indices],
                    },
                )
            )

    # Also check for duplicate rows
    dup_rows = data.duplicated()
    dup_row_count = dup_rows.sum()
    if dup_row_count > 0:
        dup_row_indices = data.index[dup_rows].tolist()[:10]
        issues.append(
            DataQualityIssue(
                code="DUPLICATE_ROWS",
                message=f"Found {dup_row_count} duplicate rows",
                severity=IssueSeverity.WARNING,
                details={
                    "count": int(dup_row_count),
                    "sample_indices": list(dup_row_indices),
                },
            )
        )

    return issues


def _detect_timezone_issues(
    timestamps: pd.DatetimeIndex | pd.Series,
    config: ValidationConfig,
) -> list[DataQualityIssue]:
    """Detect unexpected timestep changes that might indicate timezone issues."""
    issues: list[DataQualityIssue] = []

    if len(timestamps) < 3:
        return issues

    ts_array = pd.to_datetime(timestamps)
    # Convert to Series to get proper diff behavior with index
    ts_series = pd.Series(ts_array)
    diffs = ts_series.diff()[1:]

    if len(diffs) == 0:
        return issues

    # Check for sudden timestep changes (e.g., 1h gaps that might be DST changes)
    expected_step = config.expected_timestep_seconds
    if expected_step is None:
        median_diff = diffs.median()
        if pd.isna(median_diff):
            return issues
        expected_step = median_diff.total_seconds()

    # Look for consistent patterns that might indicate DST or timezone issues
    expected_step_td = pd.Timedelta(seconds=expected_step)

    # Check for exactly 1-hour deviations (common DST issue)
    one_hour = pd.Timedelta(hours=1)
    deviations = (diffs - expected_step_td).abs()
    dst_like = deviations == one_hour

    if dst_like.sum() >= 2:  # Multiple hour deviations might indicate DST
        dst_indices = dst_like[dst_like].index.tolist()[:10]
        issues.append(
            DataQualityIssue(
                code="POSSIBLE_TIMEZONE_ISSUE",
                message=(
                    f"Detected {dst_like.sum()} instances of 1-hour timestep deviations "
                    "(possible DST or timezone issue)"
                ),
                severity=IssueSeverity.WARNING,
                details={
                    "count": int(dst_like.sum()),
                    "sample_indices": dst_indices,
                },
            )
        )

    return issues


def validate_historical_data(
    data: pd.DataFrame | NDArray[np.floating[Any]],
    *,
    config: ValidationConfig | None = None,
    skip_validation: bool = False,
) -> DataQualityReport:
    """Validate historical market data for quality issues.

    Args:
        data: Market data as a DataFrame (with DatetimeIndex) or numpy array.
            For DataFrames, expects columns like 'open', 'high', 'low', 'close'.
            For numpy arrays, assumes columns in OHLC order.
        config: Optional validation configuration. Uses defaults if not provided.
        skip_validation: If True, returns a report marked as skipped without
            performing validation. Use this when you want to proceed despite
            known data quality issues (at your own risk).

    Returns:
        DataQualityReport containing validation results.

    Raises:
        ValueError: If data format is not supported.

    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     'open': [100, 101, 102],
        ...     'high': [101, 102, 103],
        ...     'low': [99, 100, 101],
        ...     'close': [100.5, 101.5, 102.5],
        ... }, index=pd.date_range('2023-01-01', periods=3, freq='1h'))
        >>> report = validate_historical_data(df)
        >>> report.is_valid
        True
    """
    if skip_validation:
        warnings.warn(
            "Data quality validation was skipped. Backtest results may be unreliable.",
            UserWarning,
            stacklevel=2,
        )
        return DataQualityReport(
            is_valid=True,
            skipped=True,
            validated_rows=len(data) if hasattr(data, "__len__") else 0,
        )

    if config is None:
        config = ValidationConfig()

    # Convert numpy array to DataFrame if needed
    if isinstance(data, np.ndarray):
        if data.ndim == 1:
            data = pd.DataFrame({"close": data})
        elif data.ndim == 2:
            cols = list(config.price_columns)[: data.shape[1]]
            data = pd.DataFrame(data, columns=cols)
        else:
            raise ValueError("Numpy array must be 1D or 2D")

    if not isinstance(data, pd.DataFrame):
        raise ValueError("Data must be a pandas DataFrame or numpy array")

    issues: list[DataQualityIssue] = []

    # Run all validation checks
    if isinstance(data.index, pd.DatetimeIndex):
        issues.extend(_detect_gaps(data.index, config))
        issues.extend(_detect_timezone_issues(data.index, config))

    issues.extend(_validate_prices(data, config))
    issues.extend(_validate_ohlc_relationships(data, config))
    issues.extend(_detect_duplicates(data))

    # Count issues by severity
    warnings_count = sum(1 for i in issues if i.severity == IssueSeverity.WARNING)
    errors_count = sum(1 for i in issues if i.severity == IssueSeverity.ERROR)
    critical_count = sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL)

    # Data is valid only if no errors or critical issues
    is_valid = errors_count == 0 and critical_count == 0

    return DataQualityReport(
        is_valid=is_valid,
        issues=issues,
        warnings_count=warnings_count,
        errors_count=errors_count,
        critical_count=critical_count,
        validated_rows=len(data),
    )


def require_valid_data(
    data: pd.DataFrame | NDArray[np.floating[Any]],
    *,
    config: ValidationConfig | None = None,
    allow_warnings: bool = True,
) -> DataQualityReport:
    """Validate data and raise an exception if validation fails.

    This is a convenience wrapper around validate_historical_data that
    enforces validation before backtest execution.

    Args:
        data: Market data to validate.
        config: Optional validation configuration.
        allow_warnings: If False, also raises on warning-level issues.

    Returns:
        DataQualityReport if validation passes.

    Raises:
        DataQualityError: If validation fails.
    """
    report = validate_historical_data(data, config=config)

    if not report.is_valid:
        error_msgs = [
            f"[{i.severity.value.upper()}] {i.code}: {i.message}"
            for i in report.issues
            if i.severity in (IssueSeverity.ERROR, IssueSeverity.CRITICAL)
        ]
        raise DataQualityError(
            f"Data quality validation failed with {report.errors_count} errors "
            f"and {report.critical_count} critical issues:\n" + "\n".join(error_msgs),
            report=report,
        )

    if not allow_warnings and report.warnings_count > 0:
        warning_msgs = [
            f"[{i.severity.value.upper()}] {i.code}: {i.message}"
            for i in report.issues
            if i.severity == IssueSeverity.WARNING
        ]
        raise DataQualityError(
            f"Data quality validation found {report.warnings_count} warnings:\n"
            + "\n".join(warning_msgs),
            report=report,
        )

    return report


class DataQualityError(Exception):
    """Exception raised when data quality validation fails."""

    def __init__(self, message: str, report: DataQualityReport) -> None:
        super().__init__(message)
        self.report = report


__all__ = [
    "DataQualityError",
    "DataQualityIssue",
    "DataQualityReport",
    "IssueSeverity",
    "ValidationConfig",
    "require_valid_data",
    "validate_historical_data",
]
