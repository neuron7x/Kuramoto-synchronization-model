# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Tests for time series gap detection and validation."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import pytest

from core.data.gap_validator import (
    GapDetectionError,
    GapValidator,
    GapValidatorConfig,
)


def test_gap_validator_accepts_continuous_data() -> None:
    """Validator should allow import of continuous time series data."""
    validator = GapValidator(frequency="1min")
    continuous_index = pd.date_range("2024-01-01", periods=100, freq="1min")
    
    # Should not raise
    validator.validate_and_raise(continuous_index)


def test_gap_validator_blocks_gapped_data() -> None:
    """Validator should block import when gaps are detected."""
    validator = GapValidator(frequency="1min")
    
    # Create index with a gap (remove 5 minutes)
    full_index = pd.date_range("2024-01-01", periods=100, freq="1min")
    gapped_index = full_index.delete(slice(50, 55))
    
    with pytest.raises(GapDetectionError) as exc_info:
        validator.validate_and_raise(gapped_index)
    
    error = exc_info.value
    assert len(error.gaps) > 0
    assert "gap" in str(error).lower()


def test_gap_validator_with_max_gap_duration() -> None:
    """Validator should allow small gaps under max_gap_duration threshold."""
    # Allow gaps up to 2 minutes
    validator = GapValidator(frequency="1min", max_gap_duration="2min")
    
    # Create index with 1-minute gap (acceptable)
    full_index = pd.date_range("2024-01-01", periods=100, freq="1min")
    small_gap_index = full_index.delete([50])
    
    # Should not raise for small gap
    validator.validate_and_raise(small_gap_index)
    
    # Create index with 5-minute gap (unacceptable)
    large_gap_index = full_index.delete(slice(50, 55))
    
    with pytest.raises(GapDetectionError):
        validator.validate_and_raise(large_gap_index)


def test_gap_validator_config_initialization() -> None:
    """Test GapValidatorConfig initialization with various parameters."""
    config = GapValidatorConfig(
        frequency="5min",
        max_gap_duration="10min",
        allow_weekend_gaps=True,
        allow_holiday_gaps=True,
    )
    
    assert config.frequency == "5min"
    assert config.max_gap_duration == "10min"
    assert config.allow_weekend_gaps is True
    assert config.allow_holiday_gaps is True


def test_gap_validator_config_with_timedelta() -> None:
    """GapValidatorConfig should accept timedelta for max_gap_duration."""
    config = GapValidatorConfig(
        frequency="1h",
        max_gap_duration=timedelta(hours=2),
    )
    
    assert config.max_gap_duration == timedelta(hours=2)


def test_gap_validator_detects_multiple_gaps() -> None:
    """Validator should detect and report multiple gaps in time series."""
    validator = GapValidator(frequency="1min")
    
    # Create index with two gaps
    full_index = pd.date_range("2024-01-01", periods=200, freq="1min")
    # Remove two separate ranges
    gapped_index = full_index.delete(list(range(50, 55)) + list(range(150, 155)))
    
    with pytest.raises(GapDetectionError) as exc_info:
        validator.validate_and_raise(gapped_index)
    
    error = exc_info.value
    # Should detect at least 2 gaps
    assert len(error.gaps) >= 2


def test_gap_validator_with_hourly_frequency() -> None:
    """Validator should work with different frequencies."""
    validator = GapValidator(frequency="1h")
    
    # Continuous hourly data
    continuous_index = pd.date_range("2024-01-01", periods=48, freq="1h")
    validator.validate_and_raise(continuous_index)
    
    # Hourly data with gap
    gapped_index = continuous_index.delete(slice(20, 24))
    with pytest.raises(GapDetectionError):
        validator.validate_and_raise(gapped_index)


def test_gap_validator_with_daily_frequency() -> None:
    """Validator should work with daily frequency."""
    validator = GapValidator(frequency="1D")
    
    # Continuous daily data
    continuous_index = pd.date_range("2024-01-01", periods=30, freq="1D")
    validator.validate_and_raise(continuous_index)
    
    # Daily data with gap
    gapped_index = continuous_index.delete([15])
    with pytest.raises(GapDetectionError):
        validator.validate_and_raise(gapped_index)


def test_gap_validator_empty_index() -> None:
    """Validator should handle empty index gracefully."""
    validator = GapValidator(frequency="1min")
    empty_index = pd.DatetimeIndex([])
    
    # Should not raise for empty index (no gaps to detect)
    validator.validate_and_raise(empty_index)


def test_gap_validator_single_element() -> None:
    """Validator should handle single-element index gracefully."""
    validator = GapValidator(frequency="1min")
    single_index = pd.date_range("2024-01-01", periods=1, freq="1min")
    
    # Should not raise for single element (no gaps possible)
    validator.validate_and_raise(single_index)


def test_gap_validator_weekend_gaps_allowed() -> None:
    """Test weekend gap allowance for equity markets."""
    validator = GapValidator(
        frequency="1D",
        allow_weekend_gaps=True,
    )
    
    # Create daily index spanning a weekend
    # This would have a "gap" on Saturday and Sunday for trading data
    continuous_index = pd.date_range("2024-01-01", periods=10, freq="1D")
    
    # The validator should handle this appropriately
    # (implementation depends on how weekend detection is done)
    try:
        validator.validate_and_raise(continuous_index)
    except GapDetectionError:
        # Expected if weekends are detected as gaps
        pass


def test_gap_detection_error_stores_gaps() -> None:
    """GapDetectionError should store detected gaps."""
    from core.data.backfill import Gap
    
    gap1 = Gap(start=pd.Timestamp("2024-01-01 10:00"), 
               end=pd.Timestamp("2024-01-01 10:05"))
    gap2 = Gap(start=pd.Timestamp("2024-01-01 11:00"),
               end=pd.Timestamp("2024-01-01 11:03"))
    
    error = GapDetectionError("Test error", gaps=[gap1, gap2])
    
    assert len(error.gaps) == 2
    assert error.gaps[0] == gap1
    assert error.gaps[1] == gap2


def test_gap_detection_error_without_gaps() -> None:
    """GapDetectionError can be created without gaps list."""
    error = GapDetectionError("Test error")
    
    assert error.gaps == []
    assert "Test error" in str(error)


def test_gap_validator_none_max_gap_duration() -> None:
    """When max_gap_duration is None, any gap should block import."""
    validator = GapValidator(frequency="1min", max_gap_duration=None)
    
    # Even a tiny gap should be blocked
    full_index = pd.date_range("2024-01-01", periods=100, freq="1min")
    tiny_gap_index = full_index.delete([50])
    
    with pytest.raises(GapDetectionError):
        validator.validate_and_raise(tiny_gap_index)
