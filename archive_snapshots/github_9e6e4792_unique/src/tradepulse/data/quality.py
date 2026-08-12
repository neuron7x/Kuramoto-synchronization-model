# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Data quality validation module for TradePulse market data.

This module provides comprehensive data quality checks to ensure
market data meets the requirements for backtesting and live trading.

**Key Functions**

- ``validate_series``: Full validation of a bar series
- ``detect_gaps``: Find missing bars in time series
- ``detect_outliers``: Identify price/volume outliers
- ``check_monotonic_time``: Verify timestamp ordering
- ``detect_duplicates``: Find duplicate timestamps

**DataQualityReport**

All validation returns a ``DataQualityReport`` with:
- Overall status (OK, WARN, CRITICAL)
- Count of bars validated
- List of detected issues (gaps, outliers, duplicates)
- Actionable recommendations

Example:
    >>> from tradepulse.data.quality import validate_series
    >>> from tradepulse.data.schema import Bar
    >>>
    >>> bars = [...]  # list of Bar objects
    >>> report = validate_series(bars)
    >>> if report.status != DataQualityStatus.OK:
    ...     for issue in report.issues:
    ...         print(f"{issue.severity}: {issue.message}")
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from .schema import Bar, DataQualityStatus, Timeframe

__all__ = [
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
]


class IssueSeverity(str, Enum):
    """Severity level for data quality issues."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DataQualityIssue:
    """Represents a single data quality issue.

    Attributes:
        code: Short identifier (e.g., "GAP_DETECTED", "DUPLICATE_TIMESTAMP")
        message: Human-readable description
        severity: Issue severity level
        timestamp: When the issue was detected in the data
        details: Additional context (affected indices, values, etc.)
    """

    code: str
    message: str
    severity: IssueSeverity
    timestamp: Optional[datetime] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataQualityReport:
    """Result of data quality validation.

    Attributes:
        status: Overall validation status
        bar_count: Number of bars validated
        issues: List of detected issues
        gaps_count: Number of gaps found
        outliers_count: Number of outliers found
        duplicates_count: Number of duplicate timestamps
        validation_time_ms: Time taken for validation in milliseconds
        symbol: Symbol being validated (if single-symbol series)
        timeframe: Timeframe of the data (if consistent)
    """

    status: DataQualityStatus = DataQualityStatus.OK
    bar_count: int = 0
    issues: List[DataQualityIssue] = field(default_factory=list)
    gaps_count: int = 0
    outliers_count: int = 0
    duplicates_count: int = 0
    validation_time_ms: float = 0.0
    symbol: Optional[str] = None
    timeframe: Optional[Timeframe] = None

    def add_issue(self, issue: DataQualityIssue) -> None:
        """Add an issue and update status accordingly."""
        self.issues.append(issue)

        # Update status based on severity
        if issue.severity == IssueSeverity.CRITICAL:
            self.status = DataQualityStatus.CRITICAL
        elif (
            issue.severity == IssueSeverity.ERROR
            and self.status != DataQualityStatus.CRITICAL
        ):
            self.status = DataQualityStatus.CRITICAL
        elif (
            issue.severity == IssueSeverity.WARNING
            and self.status == DataQualityStatus.OK
        ):
            self.status = DataQualityStatus.WARN

    def is_valid(self) -> bool:
        """Return True if no critical issues found."""
        return self.status != DataQualityStatus.CRITICAL

    def has_warnings(self) -> bool:
        """Return True if there are warnings."""
        return self.status == DataQualityStatus.WARN or any(
            i.severity == IssueSeverity.WARNING for i in self.issues
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary for serialization."""
        return {
            "status": self.status.value,
            "bar_count": self.bar_count,
            "gaps_count": self.gaps_count,
            "outliers_count": self.outliers_count,
            "duplicates_count": self.duplicates_count,
            "validation_time_ms": self.validation_time_ms,
            "symbol": self.symbol,
            "timeframe": self.timeframe.value if self.timeframe else None,
            "issues": [
                {
                    "code": i.code,
                    "message": i.message,
                    "severity": i.severity.value,
                    "timestamp": i.timestamp.isoformat() if i.timestamp else None,
                    "details": i.details,
                }
                for i in self.issues
            ],
        }


def check_monotonic_time(bars: Sequence[Bar]) -> List[DataQualityIssue]:
    """Check that timestamps are strictly increasing.

    Args:
        bars: Sequence of bars to check

    Returns:
        List of issues found (empty if all OK)
    """
    issues: List[DataQualityIssue] = []

    if len(bars) < 2:
        return issues

    for i in range(1, len(bars)):
        if bars[i].timestamp <= bars[i - 1].timestamp:
            if bars[i].timestamp == bars[i - 1].timestamp:
                issues.append(
                    DataQualityIssue(
                        code="TIMESTAMP_EQUAL",
                        message=f"Duplicate timestamp at index {i}: {bars[i].timestamp}",
                        severity=IssueSeverity.ERROR,
                        timestamp=bars[i].timestamp,
                        details={"index": i, "prev_index": i - 1},
                    )
                )
            else:
                issues.append(
                    DataQualityIssue(
                        code="TIMESTAMP_NOT_MONOTONIC",
                        message=f"Timestamp at index {i} is earlier than previous: {bars[i].timestamp} < {bars[i-1].timestamp}",
                        severity=IssueSeverity.CRITICAL,
                        timestamp=bars[i].timestamp,
                        details={
                            "index": i,
                            "current_ts": bars[i].timestamp.isoformat(),
                            "prev_ts": bars[i - 1].timestamp.isoformat(),
                        },
                    )
                )

    return issues


def detect_gaps(
    bars: Sequence[Bar],
    expected_interval_seconds: Optional[int] = None,
    tolerance_factor: float = 1.5,
) -> List[DataQualityIssue]:
    """Detect missing bars (gaps) in time series.

    Args:
        bars: Sequence of bars to check
        expected_interval_seconds: Expected interval between bars.
            If None, will be inferred from timeframe or median diff.
        tolerance_factor: Multiplier for expected interval to flag as gap.
            Default 1.5 means 50% longer than expected triggers warning.

    Returns:
        List of gap issues found
    """
    issues: List[DataQualityIssue] = []

    if len(bars) < 2:
        return issues

    # Determine expected interval
    if expected_interval_seconds is not None:
        expected_td = timedelta(seconds=expected_interval_seconds)
    elif bars[0].timeframe:
        expected_td = timedelta(seconds=bars[0].timeframe.seconds)
    else:
        # Infer from median difference
        diffs = []
        for i in range(1, len(bars)):
            diff = (bars[i].timestamp - bars[i - 1].timestamp).total_seconds()
            if diff > 0:
                diffs.append(diff)
        if not diffs:
            return issues
        median_diff = sorted(diffs)[len(diffs) // 2]
        expected_td = timedelta(seconds=median_diff)

    gap_threshold = expected_td * tolerance_factor

    for i in range(1, len(bars)):
        diff = bars[i].timestamp - bars[i - 1].timestamp

        if diff > gap_threshold:
            # Calculate how many bars are missing
            expected_bars = int(diff.total_seconds() / expected_td.total_seconds()) - 1

            severity = IssueSeverity.WARNING
            if expected_bars > 10:
                severity = IssueSeverity.ERROR
            if expected_bars > 100:
                severity = IssueSeverity.CRITICAL

            issues.append(
                DataQualityIssue(
                    code="GAP_DETECTED",
                    message=f"Gap of ~{expected_bars} bar(s) between index {i-1} and {i}",
                    severity=severity,
                    timestamp=bars[i - 1].timestamp,
                    details={
                        "gap_start_index": i - 1,
                        "gap_end_index": i,
                        "gap_start_ts": bars[i - 1].timestamp.isoformat(),
                        "gap_end_ts": bars[i].timestamp.isoformat(),
                        "gap_duration_seconds": diff.total_seconds(),
                        "expected_bars_missing": expected_bars,
                    },
                )
            )

    return issues


def detect_outliers(
    bars: Sequence[Bar],
    price_change_threshold_pct: float = 20.0,
    volume_spike_multiplier: float = 10.0,
) -> List[DataQualityIssue]:
    """Detect price and volume outliers in bar series.

    Args:
        bars: Sequence of bars to check
        price_change_threshold_pct: Maximum allowed % price change between bars.
            Default 20% - larger moves are flagged.
        volume_spike_multiplier: Maximum volume relative to median.
            Default 10x - larger spikes are flagged.

    Returns:
        List of outlier issues found
    """
    issues: List[DataQualityIssue] = []

    if len(bars) < 2:
        return issues

    # Calculate price changes
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        curr_close = bars[i].close

        if prev_close > 0:
            pct_change = abs(float((curr_close - prev_close) / prev_close * 100))

            if pct_change > price_change_threshold_pct:
                severity = IssueSeverity.WARNING
                if pct_change > price_change_threshold_pct * 2:
                    severity = IssueSeverity.ERROR

                issues.append(
                    DataQualityIssue(
                        code="PRICE_OUTLIER",
                        message=f"Large price change of {pct_change:.1f}% at index {i}",
                        severity=severity,
                        timestamp=bars[i].timestamp,
                        details={
                            "index": i,
                            "prev_close": str(prev_close),
                            "curr_close": str(curr_close),
                            "pct_change": pct_change,
                        },
                    )
                )

    # Calculate volume outliers
    volumes = [float(b.volume) for b in bars if b.volume > 0]
    if len(volumes) > 1:
        sorted_volumes = sorted(volumes)
        median_volume = sorted_volumes[len(sorted_volumes) // 2]

        if median_volume > 0:
            for i, bar in enumerate(bars):
                if bar.volume > 0:
                    volume_ratio = float(bar.volume) / median_volume

                    if volume_ratio > volume_spike_multiplier:
                        issues.append(
                            DataQualityIssue(
                                code="VOLUME_OUTLIER",
                                message=f"Volume spike of {volume_ratio:.1f}x median at index {i}",
                                severity=IssueSeverity.WARNING,
                                timestamp=bar.timestamp,
                                details={
                                    "index": i,
                                    "volume": str(bar.volume),
                                    "median_volume": median_volume,
                                    "ratio": volume_ratio,
                                },
                            )
                        )

    return issues


def detect_duplicates(bars: Sequence[Bar]) -> List[DataQualityIssue]:
    """Detect duplicate timestamps in bar series.

    Args:
        bars: Sequence of bars to check

    Returns:
        List of duplicate issues found
    """
    issues: List[DataQualityIssue] = []

    seen: Dict[datetime, int] = {}

    for i, bar in enumerate(bars):
        if bar.timestamp in seen:
            issues.append(
                DataQualityIssue(
                    code="DUPLICATE_TIMESTAMP",
                    message=f"Duplicate timestamp {bar.timestamp} at indices {seen[bar.timestamp]} and {i}",
                    severity=IssueSeverity.ERROR,
                    timestamp=bar.timestamp,
                    details={
                        "first_index": seen[bar.timestamp],
                        "duplicate_index": i,
                    },
                )
            )
        else:
            seen[bar.timestamp] = i

    return issues


def validate_series(
    bars: Sequence[Bar],
    *,
    check_gaps: bool = True,
    check_outliers: bool = True,
    check_duplicates: bool = True,
    check_monotonic: bool = True,
    expected_interval_seconds: Optional[int] = None,
    price_change_threshold_pct: float = 20.0,
    volume_spike_multiplier: float = 10.0,
) -> DataQualityReport:
    """Validate a series of bars for data quality issues.

    This is the main entry point for comprehensive data quality validation.

    Args:
        bars: Sequence of bars to validate
        check_gaps: Whether to detect missing bars
        check_outliers: Whether to detect price/volume outliers
        check_duplicates: Whether to detect duplicate timestamps
        check_monotonic: Whether to verify monotonic timestamps
        expected_interval_seconds: Expected bar interval (auto-detected if None)
        price_change_threshold_pct: Max % price change before flagging
        volume_spike_multiplier: Max volume ratio before flagging

    Returns:
        DataQualityReport with all findings

    Example:
        >>> report = validate_series(bars)
        >>> if not report.is_valid():
        ...     raise ValueError(f"Data quality issues: {report.status}")
    """
    import time

    start_time = time.time()

    report = DataQualityReport(bar_count=len(bars))

    if not bars:
        return report

    # Extract symbol and timeframe from first bar
    report.symbol = bars[0].symbol
    report.timeframe = bars[0].timeframe

    # Run all enabled checks
    if check_monotonic:
        monotonic_issues = check_monotonic_time(bars)
        for issue in monotonic_issues:
            report.add_issue(issue)

    if check_duplicates:
        dup_issues = detect_duplicates(bars)
        report.duplicates_count = len(dup_issues)
        for issue in dup_issues:
            report.add_issue(issue)

    if check_gaps:
        gap_issues = detect_gaps(bars, expected_interval_seconds)
        report.gaps_count = len(gap_issues)
        for issue in gap_issues:
            report.add_issue(issue)

    if check_outliers:
        outlier_issues = detect_outliers(
            bars,
            price_change_threshold_pct=price_change_threshold_pct,
            volume_spike_multiplier=volume_spike_multiplier,
        )
        report.outliers_count = len(outlier_issues)
        for issue in outlier_issues:
            report.add_issue(issue)

    report.validation_time_ms = (time.time() - start_time) * 1000

    return report


def require_valid_data(
    bars: Sequence[Bar],
    *,
    allow_warnings: bool = True,
    **kwargs: Any,
) -> DataQualityReport:
    """Validate data and raise exception if validation fails.

    Convenience wrapper around validate_series that enforces data quality
    before proceeding with backtests or live trading.

    Args:
        bars: Bars to validate
        allow_warnings: If False, also raises on warning-level issues
        **kwargs: Additional arguments passed to validate_series

    Returns:
        DataQualityReport if validation passes

    Raises:
        DataQualityError: If validation fails
    """
    report = validate_series(bars, **kwargs)

    if not report.is_valid():
        error_msgs = [
            f"[{i.severity.value}] {i.code}: {i.message}"
            for i in report.issues
            if i.severity in (IssueSeverity.ERROR, IssueSeverity.CRITICAL)
        ]
        raise DataQualityError(
            f"Data quality validation failed with {len(error_msgs)} errors:\n"
            + "\n".join(error_msgs),
            report=report,
        )

    if not allow_warnings and report.has_warnings():
        warning_msgs = [
            f"[{i.severity.value}] {i.code}: {i.message}"
            for i in report.issues
            if i.severity == IssueSeverity.WARNING
        ]
        raise DataQualityError(
            f"Data quality validation found {len(warning_msgs)} warnings:\n"
            + "\n".join(warning_msgs),
            report=report,
        )

    return report


class DataQualityError(Exception):
    """Exception raised when data quality validation fails."""

    def __init__(self, message: str, report: DataQualityReport) -> None:
        super().__init__(message)
        self.report = report
