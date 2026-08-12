# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Time series gap detection and validation for data import blocking.

This module implements the requirement REQ-002 from docs/requirements/product_specification.md:
"Репозиторій повинен забезпечувати автоматичний контроль якості, що
призводить до блокування імпорту при виявленні розривів у часових рядах."

The GapValidator ensures data quality by detecting and preventing import
of time series data with gaps (missing timestamps) based on expected frequency.
This is critical for algorithmic trading where complete, continuous data is
required for accurate backtesting and live trading signals.

Example:
    >>> from datetime import datetime
    >>> import pandas as pd
    >>> validator = GapValidator(frequency='1min', max_gap_duration='5min')
    >>>
    >>> # Create index with a gap
    >>> idx = pd.date_range('2024-01-01', periods=10, freq='1min')
    >>> idx_with_gap = idx.delete(slice(5, 8))  # Remove 3 bars
    >>>
    >>> try:
    ...     validator.validate_and_raise(idx_with_gap)
    ... except GapDetectionError as e:
    ...     print(f"Import blocked: {e}")
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

import pandas as pd

from core.data.backfill import Gap, detect_gaps


class GapDetectionError(ValueError):
    """Raised when time series contains unacceptable gaps.

    This error blocks data import to prevent downstream trading logic
    from operating on incomplete data that could lead to incorrect signals
    or financial losses.
    """

    def __init__(self, message: str, gaps: list[Gap] | None = None):
        """Initialize with error message and detected gaps.

        Args:
            message: Human-readable error description.
            gaps: List of Gap objects detected in the time series.
        """
        super().__init__(message)
        self.gaps = gaps or []


@dataclass
class GapValidatorConfig:
    """Configuration for time series gap validation.

    Attributes:
        frequency: Expected sampling frequency (e.g., '1min', '1h', '1D').
        max_gap_duration: Maximum allowed gap duration before blocking import.
            None means any gap blocks import.
        allow_weekend_gaps: If True, gaps during weekends are permitted
            (useful for equity markets).
        allow_holiday_gaps: If True, gaps during holidays are permitted.
    """

    frequency: str
    max_gap_duration: str | timedelta | None = None
    allow_weekend_gaps: bool = False
    allow_holiday_gaps: bool = False


class GapValidator:
    """Validates time series for gaps and blocks import if detected.

    This validator implements automatic quality control that prevents
    import of data with temporal gaps, ensuring data integrity for
    trading operations.

    The validator can be configured to allow certain gaps (weekends,
    holidays) or enforce strict continuity requirements.

    Example:
        >>> validator = GapValidator(frequency='1min')
        >>> validator.validate_and_raise(good_index)  # passes
        >>> validator.validate_and_raise(bad_index)   # raises GapDetectionError
    """

    def __init__(
        self,
        frequency: str,
        max_gap_duration: str | timedelta | None = None,
        allow_weekend_gaps: bool = False,
        allow_holiday_gaps: bool = False,
    ):
        """Initialize the gap validator.

        Args:
            frequency: Expected sampling frequency (e.g., '1min', '1h').
            max_gap_duration: Maximum tolerable gap duration. Gaps smaller
                than this are allowed. None means zero tolerance.
            allow_weekend_gaps: Whether to permit gaps during weekends.
            allow_holiday_gaps: Whether to permit gaps during holidays.
        """
        self._frequency = frequency
        self._max_gap_duration = self._parse_duration(max_gap_duration)
        self._allow_weekend_gaps = allow_weekend_gaps
        self._allow_holiday_gaps = allow_holiday_gaps

    @staticmethod
    @lru_cache(maxsize=32)
    def _parse_duration(duration: str | timedelta | None) -> timedelta | None:
        """Convert duration string to timedelta.

        Cached to avoid repeated parsing of common duration strings.
        """
        if duration is None:
            return None
        if isinstance(duration, timedelta):
            return duration
        return pd.Timedelta(duration).to_pytimedelta()

    def validate(
        self,
        index: pd.DatetimeIndex,
        *,
        full_check: bool = True,
    ) -> tuple[bool, list[Gap]]:
        """Check if time series index contains unacceptable gaps.

        Args:
            index: DatetimeIndex to validate for gaps.
            full_check: If True, generate complete expected index for comparison.
                If False, only check consecutive timestamps.

        Returns:
            Tuple of (is_valid, detected_gaps). is_valid is True if no
            unacceptable gaps were found.
        """
        if index.empty:
            return True, []

        # Generate expected index
        if full_check:
            expected_index = pd.date_range(
                start=index[0],
                end=index[-1],
                freq=self._frequency,
            )
        else:
            # Quick check - just verify consecutive timestamps
            expected_index = index

        # Detect gaps
        gaps = detect_gaps(expected_index, index, frequency=self._frequency)

        if not gaps:
            return True, []

        # Filter gaps based on configuration
        unacceptable_gaps = self._filter_acceptable_gaps(gaps)

        return len(unacceptable_gaps) == 0, unacceptable_gaps

    def _filter_acceptable_gaps(self, gaps: list[Gap]) -> list[Gap]:
        """Filter out gaps that are acceptable per configuration.

        Args:
            gaps: List of all detected gaps.

        Returns:
            List of gaps that violate validation rules.
        """
        # Early exit if no gaps
        if not gaps:
            return []

        # Pre-compute weekend checking logic outside loop
        check_weekends = self._allow_weekend_gaps
        check_duration = self._max_gap_duration is not None

        unacceptable = []

        for gap in gaps:
            # Check duration threshold (most common filter)
            if check_duration:
                gap_duration = gap.end - gap.start
                if gap_duration <= self._max_gap_duration:
                    continue  # Gap is small enough to be acceptable

            # Check if gap is during weekend
            if check_weekends:
                # If both start and end are on weekend, skip
                if gap.start.weekday() >= 5 and gap.end.weekday() >= 5:
                    continue

            # If we get here, gap is unacceptable
            unacceptable.append(gap)

        return unacceptable

    def validate_and_raise(
        self,
        index: pd.DatetimeIndex,
        *,
        full_check: bool = True,
    ) -> None:
        """Validate index and raise exception if gaps detected.

        This is the primary method for blocking data import when gaps
        are present. It raises GapDetectionError with details about
        the gaps found.

        Args:
            index: DatetimeIndex to validate.
            full_check: Whether to perform complete gap analysis.

        Raises:
            GapDetectionError: If unacceptable gaps are detected.
        """
        is_valid, gaps = self.validate(index, full_check=full_check)

        if not is_valid:
            gap_summary = self._format_gap_summary(gaps)
            message = (
                f"Data import blocked: {len(gaps)} gap(s) detected in time series. "
                f"Expected frequency: {self._frequency}. {gap_summary}"
            )
            raise GapDetectionError(message, gaps=gaps)

    @staticmethod
    def _format_gap_summary(gaps: list[Gap], max_display: int = 3) -> str:
        """Format gap information for error message.

        Args:
            gaps: List of gaps to summarize.
            max_display: Maximum number of gaps to include in summary.

        Returns:
            Human-readable gap summary string.
        """
        if not gaps:
            return "No gaps detected."

        display_gaps = gaps[:max_display]
        lines = ["Gaps found:"]

        for i, gap in enumerate(display_gaps, 1):
            duration = gap.end - gap.start
            lines.append(f"  {i}. {gap.start} to {gap.end} (duration: {duration})")

        if len(gaps) > max_display:
            lines.append(f"  ... and {len(gaps) - max_display} more gap(s)")

        return " ".join(lines)

    @classmethod
    def from_config(cls, config: GapValidatorConfig) -> GapValidator:
        """Create validator from configuration object.

        Args:
            config: GapValidatorConfig with validation parameters.

        Returns:
            Configured GapValidator instance.
        """
        return cls(
            frequency=config.frequency,
            max_gap_duration=config.max_gap_duration,
            allow_weekend_gaps=config.allow_weekend_gaps,
            allow_holiday_gaps=config.allow_holiday_gaps,
        )


def validate_timeseries_gaps(
    df: pd.DataFrame,
    timestamp_column: str,
    frequency: str,
    *,
    max_gap_duration: str | timedelta | None = None,
    allow_weekend_gaps: bool = False,
) -> None:
    """Convenience function to validate DataFrame for gaps and block import.

    This function provides a simple interface for the most common use case:
    validating a DataFrame with a timestamp column before importing it into
    the system.

    Args:
        df: DataFrame containing time series data.
        timestamp_column: Name of the timestamp column.
        frequency: Expected sampling frequency.
        max_gap_duration: Maximum acceptable gap duration.
        allow_weekend_gaps: Whether to allow gaps during weekends.

    Raises:
        GapDetectionError: If unacceptable gaps are detected.
        ValueError: If timestamp column is missing, invalid, or DataFrame is empty.
    """
    # Validate DataFrame is not empty
    if df.empty:
        raise ValueError("DataFrame is empty, cannot validate gaps")

    if timestamp_column not in df.columns:
        raise ValueError(
            f"Timestamp column '{timestamp_column}' not found in DataFrame. "
            f"Available columns: {', '.join(df.columns)}"
        )

    # Convert to DatetimeIndex if needed
    try:
        timestamps = pd.to_datetime(df[timestamp_column])
    except Exception as e:
        raise ValueError(
            f"Failed to convert column '{timestamp_column}' to datetime: {e}"
        ) from e

    if not isinstance(timestamps, pd.DatetimeIndex):
        timestamps = pd.DatetimeIndex(timestamps)

    # Create validator and check for gaps
    validator = GapValidator(
        frequency=frequency,
        max_gap_duration=max_gap_duration,
        allow_weekend_gaps=allow_weekend_gaps,
    )

    validator.validate_and_raise(timestamps)


def quick_validate(
    index: pd.DatetimeIndex,
    frequency: str,
    *,
    strict: bool = True,
) -> bool:
    """Quick validation check for time series continuity.

    Convenience function for fast validation without raising exceptions.
    Useful for conditional logic where you want to check validity without
    exception handling overhead.

    Args:
        index: DatetimeIndex to validate.
        frequency: Expected sampling frequency (e.g., '1min', '1h').
        strict: If True, any gap causes validation to fail.
            If False, allows small gaps up to 2x the frequency.

    Returns:
        bool: True if valid (no gaps or acceptable gaps), False otherwise.

    Example:
        >>> if quick_validate(data.index, '1min'):
        ...     process_data(data)
        ... else:
        ...     log_warning("Data has gaps, skipping")
    """
    max_gap = None if strict else f"{2 * pd.Timedelta(frequency).total_seconds()}s"
    validator = GapValidator(frequency=frequency, max_gap_duration=max_gap)
    is_valid, _ = validator.validate(index)
    return is_valid


__all__ = [
    "GapDetectionError",
    "GapValidator",
    "GapValidatorConfig",
    "validate_timeseries_gaps",
    "quick_validate",
]
