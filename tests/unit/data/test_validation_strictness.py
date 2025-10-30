# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

from datetime import UTC, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from core.data.validation import (
    TimeSeriesValidationConfig,
    TimeSeriesValidationError,
    ValueColumnConfig,
    _coerce_timedelta,
    validate_timeseries_frame,
)


def test_value_column_config_rejects_blank_name() -> None:
    with pytest.raises(ValidationError):
        ValueColumnConfig(name="   ")


def test_config_rejects_blank_timestamp_column() -> None:
    with pytest.raises(ValidationError):
        TimeSeriesValidationConfig(timestamp_column="   ")


def test_config_rejects_blank_timezone() -> None:
    with pytest.raises(ValidationError):
        TimeSeriesValidationConfig(require_timezone="   ")


def test_coerce_timedelta_handles_native_timedelta() -> None:
    value = _coerce_timedelta(timedelta(seconds=30))
    assert value == pd.Timedelta(seconds=30)


def test_coerce_timedelta_rejects_numeric() -> None:
    with pytest.raises(TimeSeriesValidationError):
        _coerce_timedelta(10)


def _build_config(frequency: pd.Timedelta | None = None) -> TimeSeriesValidationConfig:
    return TimeSeriesValidationConfig(
        value_columns=[ValueColumnConfig(name="value", nullable=False)],
        frequency=frequency,
        require_timezone="UTC",
    )


def test_validate_timeseries_frame_honours_frequency() -> None:
    index = pd.date_range("2024-01-01", periods=4, freq="5min", tz=UTC)
    frame = pd.DataFrame({"timestamp": index, "value": [1.0, 2.0, 3.0, 4.0]})
    config = _build_config(pd.Timedelta(minutes=5))
    result = validate_timeseries_frame(frame, config)
    pd.testing.assert_frame_equal(result, frame)


def test_validate_timeseries_frame_rejects_frequency_mismatch() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="3min", tz=UTC)
    frame = pd.DataFrame({"timestamp": index, "value": [1.0, 2.0, 3.0]})
    config = _build_config(pd.Timedelta(minutes=5))
    with pytest.raises(TimeSeriesValidationError, match="sampling frequency"):
        validate_timeseries_frame(frame, config)


def test_validate_timeseries_frame_rejects_timezone_mismatch() -> None:
    index = pd.date_range("2024-01-01", periods=3, freq="5min")
    frame = pd.DataFrame({"timestamp": index, "value": [1.0, 2.0, 3.0]})
    config = _build_config(pd.Timedelta(minutes=5))
    with pytest.raises(TimeSeriesValidationError, match="expected series 'timestamp'"):
        validate_timeseries_frame(frame, config)


def test_validate_timeseries_frame_rejects_non_datetime_timestamp() -> None:
    frame = pd.DataFrame({"timestamp": ["a", "b", "c"], "value": [1.0, 2.0, 3.0]})
    config = _build_config()
    with pytest.raises(TimeSeriesValidationError, match="expected series 'timestamp'"):
        validate_timeseries_frame(frame, config)


def test_validate_timeseries_frame_allows_empty_series() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.Series([], dtype="datetime64[ns, UTC]"),
            "value": pd.Series([], dtype="float64"),
        }
    )
    config = _build_config()
    result = validate_timeseries_frame(frame, config)
    pd.testing.assert_frame_equal(result, frame)
