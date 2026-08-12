# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for geosync.data.quality module.

Tests for data quality validation functions:
- validate_series
- detect_gaps
- detect_outliers
- check_monotonic_time
- detect_duplicates
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

# Add src to path for proper imports
_src_path = Path(__file__).parent.parent.parent.parent / "src"
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

from geosync.data.quality import (  # noqa: E402
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
from geosync.data.schema import Bar, DataQualityStatus, Timeframe  # noqa: E402


def make_bar(
    ts: datetime,
    symbol: str = "BTCUSDT",
    timeframe: Timeframe = Timeframe.M1,
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: float = 1000.0,
) -> Bar:
    """Helper to create test bars."""
    return Bar(
        timestamp=ts,
        symbol=symbol,
        timeframe=timeframe,
        open=Decimal(str(open_)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


def make_bar_series(
    count: int,
    start_time: datetime,
    interval_seconds: int = 60,
    **kwargs,
) -> list[Bar]:
    """Create a series of bars with regular intervals."""
    return [
        make_bar(start_time + timedelta(seconds=i * interval_seconds), **kwargs)
        for i in range(count)
    ]


class TestValidateSeries:
    """Tests for validate_series function."""

    def test_empty_series_returns_ok(self) -> None:
        """Empty series should return OK status."""
        report = validate_series([])
        assert report.status == DataQualityStatus.OK
        assert report.bar_count == 0

    def test_valid_series_returns_ok(self) -> None:
        """Valid series should return OK status."""
        bars = make_bar_series(10, datetime.now(timezone.utc))
        report = validate_series(bars)

        assert report.status == DataQualityStatus.OK
        assert report.bar_count == 10
        assert report.is_valid()
        assert not report.has_warnings()

    def test_report_captures_symbol_and_timeframe(self) -> None:
        """Report should capture symbol and timeframe from bars."""
        bars = make_bar_series(5, datetime.now(timezone.utc), symbol="ETHUSDT")
        bars[0] = make_bar(bars[0].timestamp, symbol="ETHUSDT", timeframe=Timeframe.H1)

        report = validate_series([bars[0]])
        assert report.symbol == "ETHUSDT"
        assert report.timeframe == Timeframe.H1

    def test_report_to_dict(self) -> None:
        """Report should serialize to dictionary."""
        bars = make_bar_series(5, datetime.now(timezone.utc))
        report = validate_series(bars)

        data = report.to_dict()
        assert data["status"] == "OK"
        assert data["bar_count"] == 5
        assert isinstance(data["issues"], list)


class TestCheckMonotonicTime:
    """Tests for check_monotonic_time function."""

    def test_monotonic_timestamps_no_issues(self) -> None:
        """Monotonic timestamps should return no issues."""
        bars = make_bar_series(5, datetime.now(timezone.utc))
        issues = check_monotonic_time(bars)
        assert len(issues) == 0

    def test_equal_timestamps_detected(self) -> None:
        """Equal timestamps should be detected."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts),
            make_bar(ts),  # Same timestamp
        ]

        issues = check_monotonic_time(bars)
        assert len(issues) == 1
        assert issues[0].code == "TIMESTAMP_EQUAL"
        assert issues[0].severity == IssueSeverity.ERROR

    def test_decreasing_timestamps_detected(self) -> None:
        """Decreasing timestamps should be detected as critical."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts + timedelta(minutes=1)),
            make_bar(ts),  # Earlier than previous
        ]

        issues = check_monotonic_time(bars)
        assert len(issues) == 1
        assert issues[0].code == "TIMESTAMP_NOT_MONOTONIC"
        assert issues[0].severity == IssueSeverity.CRITICAL


class TestDetectGaps:
    """Tests for detect_gaps function."""

    def test_no_gaps_in_regular_series(self) -> None:
        """Regular series should have no gaps."""
        bars = make_bar_series(10, datetime.now(timezone.utc), interval_seconds=60)
        issues = detect_gaps(bars)
        assert len(issues) == 0

    def test_small_gap_detected_as_warning(self) -> None:
        """Small gap should be detected as warning."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts),
            make_bar(ts + timedelta(minutes=5)),  # 5 min gap (expecting 1 min)
        ]

        issues = detect_gaps(bars, expected_interval_seconds=60)
        assert len(issues) == 1
        assert issues[0].code == "GAP_DETECTED"
        assert issues[0].severity == IssueSeverity.WARNING

    def test_large_gap_detected_as_error(self) -> None:
        """Large gap (>10 bars) should be detected as error."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts),
            make_bar(ts + timedelta(minutes=15)),  # 15 min gap = ~14 bars missing
        ]

        issues = detect_gaps(bars, expected_interval_seconds=60)
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.ERROR

    def test_very_large_gap_detected_as_critical(self) -> None:
        """Very large gap (>100 bars) should be detected as critical."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts),
            make_bar(ts + timedelta(hours=3)),  # 3 hour gap = ~180 bars missing
        ]

        issues = detect_gaps(bars, expected_interval_seconds=60)
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.CRITICAL

    def test_uses_timeframe_when_interval_not_specified(self) -> None:
        """Should use timeframe to determine expected interval."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, timeframe=Timeframe.H1),
            make_bar(ts + timedelta(hours=3), timeframe=Timeframe.H1),  # 2 bar gap
        ]

        issues = detect_gaps(bars)
        assert len(issues) == 1
        assert "Gap of" in issues[0].message


class TestDetectOutliers:
    """Tests for detect_outliers function."""

    def test_no_outliers_in_stable_series(self) -> None:
        """Stable price series should have no outliers."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, close=100),
            make_bar(ts + timedelta(minutes=1), close=101),
            make_bar(ts + timedelta(minutes=2), close=102),
        ]

        issues = detect_outliers(bars)
        assert len(issues) == 0

    def test_large_price_change_detected(self) -> None:
        """Large price change should be detected."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, open_=100, high=105, low=95, close=100),
            make_bar(
                ts + timedelta(minutes=1), open_=130, high=135, low=125, close=130
            ),  # 30% change
        ]

        issues = detect_outliers(bars, price_change_threshold_pct=20.0)
        assert len(issues) == 1
        assert issues[0].code == "PRICE_OUTLIER"
        assert issues[0].severity == IssueSeverity.WARNING

    def test_very_large_price_change_is_error(self) -> None:
        """Very large price change should be error."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, open_=100, high=105, low=95, close=100),
            make_bar(
                ts + timedelta(minutes=1), open_=160, high=165, low=155, close=160
            ),  # 60% change
        ]

        issues = detect_outliers(bars, price_change_threshold_pct=20.0)
        assert len(issues) == 1
        assert issues[0].severity == IssueSeverity.ERROR

    def test_volume_spike_detected(self) -> None:
        """Volume spike should be detected."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, volume=100),
            make_bar(ts + timedelta(minutes=1), volume=100),
            make_bar(ts + timedelta(minutes=2), volume=100),
            make_bar(ts + timedelta(minutes=3), volume=5000),  # 50x spike
        ]

        issues = detect_outliers(bars, volume_spike_multiplier=10.0)
        volume_issues = [i for i in issues if i.code == "VOLUME_OUTLIER"]
        assert len(volume_issues) == 1


class TestDetectDuplicates:
    """Tests for detect_duplicates function."""

    def test_no_duplicates_in_unique_series(self) -> None:
        """Unique timestamps should return no duplicates."""
        bars = make_bar_series(10, datetime.now(timezone.utc))
        issues = detect_duplicates(bars)
        assert len(issues) == 0

    def test_duplicate_timestamps_detected(self) -> None:
        """Duplicate timestamps should be detected."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts),
            make_bar(ts + timedelta(minutes=1)),
            make_bar(ts),  # Duplicate of first
        ]

        issues = detect_duplicates(bars)
        assert len(issues) == 1
        assert issues[0].code == "DUPLICATE_TIMESTAMP"
        assert issues[0].severity == IssueSeverity.ERROR
        assert issues[0].details["first_index"] == 0
        assert issues[0].details["duplicate_index"] == 2


class TestRequireValidData:
    """Tests for require_valid_data function."""

    def test_valid_data_returns_report(self) -> None:
        """Valid data should return report without raising."""
        bars = make_bar_series(10, datetime.now(timezone.utc))
        report = require_valid_data(bars)

        assert report.is_valid()
        assert report.bar_count == 10

    def test_invalid_data_raises_error(self) -> None:
        """Invalid data should raise DataQualityError."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts + timedelta(minutes=1)),
            make_bar(ts),  # Not monotonic
        ]

        with pytest.raises(DataQualityError) as exc_info:
            require_valid_data(bars)

        assert "validation failed" in str(exc_info.value)
        assert exc_info.value.report is not None

    def test_allow_warnings_false_raises_on_warnings(self) -> None:
        """With allow_warnings=False, warnings should raise error."""
        ts = datetime.now(timezone.utc)
        bars = [
            make_bar(ts, open_=100, high=105, low=95, close=100),
            make_bar(
                ts + timedelta(minutes=5), open_=130, high=135, low=125, close=130
            ),  # Gap + price outlier
        ]

        # Should not raise with allow_warnings=True
        report = require_valid_data(bars, allow_warnings=True)
        assert report.has_warnings()

        # Should raise with allow_warnings=False
        with pytest.raises(DataQualityError):
            require_valid_data(bars, allow_warnings=False)


class TestDataQualityReport:
    """Tests for DataQualityReport dataclass."""

    def test_add_issue_updates_status(self) -> None:
        """Adding issues should update status correctly."""
        report = DataQualityReport()
        assert report.status == DataQualityStatus.OK

        report.add_issue(
            DataQualityIssue(
                code="TEST",
                message="Test warning",
                severity=IssueSeverity.WARNING,
            )
        )
        assert report.status == DataQualityStatus.WARN

        # Add error - should become critical
        report.add_issue(
            DataQualityIssue(
                code="TEST",
                message="Test error",
                severity=IssueSeverity.ERROR,
            )
        )
        assert report.status == DataQualityStatus.CRITICAL

    def test_is_valid_and_has_warnings(self) -> None:
        """is_valid and has_warnings should work correctly."""
        report = DataQualityReport()
        assert report.is_valid()
        assert not report.has_warnings()

        report.add_issue(
            DataQualityIssue(
                code="TEST",
                message="Test warning",
                severity=IssueSeverity.WARNING,
            )
        )
        assert report.is_valid()
        assert report.has_warnings()

        report.add_issue(
            DataQualityIssue(
                code="TEST",
                message="Test critical",
                severity=IssueSeverity.CRITICAL,
            )
        )
        assert not report.is_valid()
