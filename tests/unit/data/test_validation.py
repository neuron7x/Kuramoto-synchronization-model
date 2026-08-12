# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unit tests for the strict time series validation helpers."""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from core.data.validation import (
    OHLCVValidationResult,
    TimeSeriesValidationConfig,
    TimeSeriesValidationError,
    ValueColumnConfig,
    _coerce_timedelta,
    _find_duplicates,
    _resolve_timezone,
    build_timeseries_schema,
    validate_ohlcv,
    validate_timeseries_frame,
)


@pytest.fixture()
def base_config() -> TimeSeriesValidationConfig:
    return TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=(
            ValueColumnConfig(name="close", dtype="float64"),
            ValueColumnConfig(name="volume", dtype="float64"),
        ),
        frequency="1min",
        require_timezone="UTC",
    )


@pytest.fixture()
def valid_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2024-01-01 00:00:00",
                periods=4,
                freq="1min",
                tz="UTC",
            ),
            "close": [100.0, 101.5, 103.2, 104.8],
            "volume": [10.0, 12.0, 11.5, 13.0],
        }
    )


def test_validate_timeseries_frame_success(
    base_config: TimeSeriesValidationConfig, valid_frame: pd.DataFrame
) -> None:
    validated = validate_timeseries_frame(valid_frame, base_config)
    # The validator pins the timestamp dtype to ``datetime64[ns, UTC]`` so the
    # downstream contract is independent of pandas major versions (pandas 3
    # defaults to microsecond resolution).
    expected = valid_frame.copy()
    expected["timestamp"] = expected["timestamp"].astype("datetime64[ns, UTC]")
    pd.testing.assert_frame_equal(validated, expected)


def test_validate_timeseries_frame_rejects_nan(
    base_config: TimeSeriesValidationConfig, valid_frame: pd.DataFrame
) -> None:
    frame = valid_frame.copy()
    frame.loc[2, "close"] = float("nan")

    with pytest.raises(TimeSeriesValidationError) as err:
        validate_timeseries_frame(frame, base_config)

    assert "NaN" in str(err.value)


def test_validate_timeseries_frame_rejects_duplicate_timestamps(
    base_config: TimeSeriesValidationConfig, valid_frame: pd.DataFrame
) -> None:
    frame = valid_frame.copy()
    frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"]

    with pytest.raises(TimeSeriesValidationError) as err:
        validate_timeseries_frame(frame, base_config)

    assert "duplicate" in str(err.value).lower()


def test_validate_timeseries_frame_enforces_frequency(
    base_config: TimeSeriesValidationConfig, valid_frame: pd.DataFrame
) -> None:
    frame = valid_frame.copy()
    frame.loc[2, "timestamp"] = frame.loc[1, "timestamp"] + pd.Timedelta(minutes=2)
    frame.loc[3, "timestamp"] = frame.loc[2, "timestamp"] + pd.Timedelta(minutes=1)

    with pytest.raises(TimeSeriesValidationError) as err:
        validate_timeseries_frame(frame, base_config)

    assert "frequency" in str(err.value)


def test_validate_timeseries_frame_detects_timezone_drift(
    base_config: TimeSeriesValidationConfig, valid_frame: pd.DataFrame
) -> None:
    frame = valid_frame.copy()
    frame["timestamp"] = frame["timestamp"].dt.tz_convert("Europe/Berlin")

    with pytest.raises(TimeSeriesValidationError) as err:
        validate_timeseries_frame(frame, base_config)

    assert "utc" in str(err.value).lower()


def test_validate_timeseries_frame_rejects_non_monotonic(
    base_config: TimeSeriesValidationConfig, valid_frame: pd.DataFrame
) -> None:
    frame = valid_frame.iloc[[0, 2, 1, 3]].reset_index(drop=True)

    with pytest.raises(TimeSeriesValidationError) as err:
        validate_timeseries_frame(frame, base_config)

    assert "increasing" in str(err.value).lower()


def test_timeseries_config_rejects_duplicate_value_columns() -> None:
    with pytest.raises(ValidationError) as err:
        TimeSeriesValidationConfig(
            timestamp_column="timestamp",
            value_columns=(
                ValueColumnConfig(name="close"),
                ValueColumnConfig(name="close"),
            ),
        )

    assert "duplicates" in str(err.value).lower()


def test_timeseries_config_rejects_timestamp_column_overlap() -> None:
    with pytest.raises(ValidationError) as err:
        TimeSeriesValidationConfig(
            timestamp_column="timestamp",
            value_columns=(ValueColumnConfig(name="timestamp"),),
        )

    assert "timestamp column" in str(err.value).lower()


def test_timeseries_config_validates_timezone_identifier() -> None:
    with pytest.raises(ValidationError) as err:
        TimeSeriesValidationConfig(require_timezone="Invalid/Zone")

    assert "unknown timezone" in str(err.value).lower()


def test_timeseries_config_coerces_frequency_strings() -> None:
    config = TimeSeriesValidationConfig(frequency="5min")

    assert isinstance(config.frequency, pd.Timedelta)
    assert config.frequency == pd.Timedelta(minutes=5)


# Additional comprehensive tests for improved coverage


class TestOHLCVValidationResult:
    """Tests for OHLCVValidationResult dataclass."""

    def test_default_values(self) -> None:
        """Verify default values are set correctly."""
        result = OHLCVValidationResult(valid=True)
        assert result.valid is True
        assert result.issues == []
        assert result.warnings == []
        assert result.row_count == 0
        assert result.nan_count == 0
        assert result.negative_count == 0

    def test_summary_passed(self) -> None:
        """Verify summary output for passed validation."""
        result = OHLCVValidationResult(valid=True, row_count=100)
        summary = result.summary()
        assert "PASSED" in summary
        assert "100 rows" in summary
        assert "0 errors" in summary
        assert "0 warnings" in summary

    def test_summary_failed(self) -> None:
        """Verify summary output for failed validation."""
        result = OHLCVValidationResult(
            valid=False, row_count=50, issues=["error1", "error2"], warnings=["warn1"]
        )
        summary = result.summary()
        assert "FAILED" in summary
        assert "50 rows" in summary
        assert "2 errors" in summary
        assert "1 warnings" in summary


class TestValidateOHLCV:
    """Tests for validate_ohlcv function."""

    @pytest.fixture
    def valid_ohlcv_df(self) -> pd.DataFrame:
        """Create a valid OHLCV DataFrame."""
        return pd.DataFrame(
            {
                "open": [100.0, 101.0, 102.0, 103.0, 104.0] * 10,
                "high": [105.0, 106.0, 107.0, 108.0, 109.0] * 10,
                "low": [95.0, 96.0, 97.0, 98.0, 99.0] * 10,
                "close": [102.0, 103.0, 104.0, 105.0, 106.0] * 10,
                "volume": [1000.0, 1100.0, 1200.0, 1300.0, 1400.0] * 10,
            }
        )

    def test_valid_ohlcv_passes(self, valid_ohlcv_df: pd.DataFrame) -> None:
        """Verify valid OHLCV data passes validation."""
        result = validate_ohlcv(valid_ohlcv_df)
        assert result.valid is True
        assert len(result.issues) == 0

    def test_empty_dataframe_fails(self) -> None:
        """Verify empty DataFrame fails validation."""
        df = pd.DataFrame()
        result = validate_ohlcv(df)
        assert result.valid is False
        assert "empty" in result.issues[0].lower()

    def test_empty_dataframe_raises_with_flag(self) -> None:
        """Verify empty DataFrame raises error when flag is set."""
        df = pd.DataFrame()
        with pytest.raises(TimeSeriesValidationError, match="empty"):
            validate_ohlcv(df, raise_on_error=True)

    def test_missing_price_column_fails(self) -> None:
        """Verify missing price column fails validation."""
        df = pd.DataFrame({"other": [1, 2, 3]})
        result = validate_ohlcv(df)
        assert result.valid is False
        assert "close" in result.issues[0]

    def test_missing_price_column_raises_with_flag(self) -> None:
        """Verify missing price column raises error when flag is set."""
        df = pd.DataFrame({"other": [1, 2, 3] * 10})
        with pytest.raises(TimeSeriesValidationError, match="close"):
            validate_ohlcv(df, raise_on_error=True)

    def test_custom_price_column(self) -> None:
        """Verify custom price column name works."""
        df = pd.DataFrame({"price": [100.0, 101.0, 102.0] * 10})
        result = validate_ohlcv(df, price_col="price")
        assert result.valid is True

    def test_few_rows_warning(self) -> None:
        """Verify warning for few data points."""
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0]})
        result = validate_ohlcv(df)
        assert any("rows" in w.lower() for w in result.warnings)

    def test_nan_values_above_threshold_fails(self) -> None:
        """Verify high NaN ratio fails validation."""
        df = pd.DataFrame({"close": [100.0] * 10 + [np.nan] * 10})
        result = validate_ohlcv(df)
        assert result.valid is False
        assert result.nan_count == 10
        assert any("nan" in issue.lower() for issue in result.issues)

    def test_nan_values_below_threshold_warns(self) -> None:
        """Verify low NaN ratio produces warning only."""
        df = pd.DataFrame({"close": list(range(99)) + [np.nan]})
        df["close"] = df["close"] + 100.0  # Make sure values are positive
        result = validate_ohlcv(df)
        assert result.valid is True  # Still valid with low NaN
        assert result.nan_count == 1
        assert any("nan" in w.lower() for w in result.warnings)

    def test_negative_prices_fail(self) -> None:
        """Verify negative prices fail validation."""
        df = pd.DataFrame({"close": [100.0, -5.0, 102.0] * 10})
        result = validate_ohlcv(df)
        assert result.valid is False
        assert result.negative_count == 10
        assert any("non-positive" in issue.lower() for issue in result.issues)

    def test_zero_prices_fail(self) -> None:
        """Verify zero prices fail validation."""
        df = pd.DataFrame({"close": [100.0, 0.0, 102.0] * 10})
        result = validate_ohlcv(df)
        assert result.valid is False
        assert result.negative_count == 10

    def test_constant_prices_fail(self) -> None:
        """Verify constant prices fail validation."""
        df = pd.DataFrame({"close": [100.0] * 50})
        result = validate_ohlcv(df)
        assert result.valid is False
        assert any("identical" in issue.lower() for issue in result.issues)

    def test_high_low_violation_fails(self) -> None:
        """Verify high < low fails validation."""
        df = pd.DataFrame(
            {
                "open": [100.0] * 20,
                "high": [95.0] * 20,  # High is lower than low!
                "low": [100.0] * 20,
                "close": [98.0] * 20,
            }
        )
        result = validate_ohlcv(df)
        assert result.valid is False
        assert any("high < low" in issue.lower() for issue in result.issues)

    def test_high_open_violation_warns(self) -> None:
        """Verify high < open produces warning."""
        df = pd.DataFrame(
            {
                "open": [110.0] * 20,  # Open higher than high!
                "high": [105.0] * 20,
                "low": [95.0] * 20,
                "close": [102.0] * 20,
            }
        )
        result = validate_ohlcv(df)
        assert any("high < open" in w.lower() for w in result.warnings)

    def test_high_close_violation_warns(self) -> None:
        """Verify high < close produces warning."""
        df = pd.DataFrame(
            {
                "open": [100.0] * 20,
                "high": [105.0] * 20,
                "low": [95.0] * 20,
                "close": [110.0] * 20,  # Close higher than high!
            }
        )
        result = validate_ohlcv(df)
        assert any("high < close" in w.lower() for w in result.warnings)

    def test_low_open_violation_warns(self) -> None:
        """Verify low > open produces warning."""
        df = pd.DataFrame(
            {
                "open": [90.0] * 20,  # Open lower than low!
                "high": [105.0] * 20,
                "low": [95.0] * 20,
                "close": [102.0] * 20,
            }
        )
        result = validate_ohlcv(df)
        assert any("low > open" in w.lower() for w in result.warnings)

    def test_low_close_violation_warns(self) -> None:
        """Verify low > close produces warning."""
        df = pd.DataFrame(
            {
                "open": [100.0] * 20,
                "high": [105.0] * 20,
                "low": [95.0] * 20,
                "close": [90.0] * 20,  # Close lower than low!
            }
        )
        result = validate_ohlcv(df)
        assert any("low > close" in w.lower() for w in result.warnings)

    def test_negative_volume_fails(self) -> None:
        """Verify negative volume fails validation."""
        df = pd.DataFrame(
            {
                "close": [100.0, 101.0, 102.0] * 10,
                "volume": [1000.0, -500.0, 1200.0] * 10,
            }
        )
        result = validate_ohlcv(df)
        assert result.valid is False
        assert any("negative volume" in issue.lower() for issue in result.issues)

    def test_raise_on_error_with_multiple_issues(self) -> None:
        """Verify raise_on_error combines issues into error message."""
        df = pd.DataFrame({"close": [-1.0, -2.0] * 10})
        with pytest.raises(TimeSeriesValidationError) as exc_info:
            validate_ohlcv(df, raise_on_error=True)
        assert "non-positive" in str(exc_info.value)

    def test_optional_columns_not_required(self) -> None:
        """Verify optional columns are not required."""
        df = pd.DataFrame({"close": [100.0, 101.0, 102.0] * 10})
        result = validate_ohlcv(df, open_col=None, high_col=None, low_col=None, volume_col=None)
        assert result.valid is True


class TestCoerceTimedelta:
    """Tests for _coerce_timedelta function."""

    def test_none_returns_none(self) -> None:
        """Verify None input returns None."""
        assert _coerce_timedelta(None) is None

    def test_pd_timedelta_passthrough(self) -> None:
        """Verify pd.Timedelta passes through."""
        td = pd.Timedelta("1h")
        assert _coerce_timedelta(td) is td

    def test_timedelta_converted(self) -> None:
        """Verify datetime.timedelta is converted."""
        td = timedelta(hours=2)
        result = _coerce_timedelta(td)
        assert result == pd.Timedelta("2h")

    def test_string_converted(self) -> None:
        """Verify string is converted."""
        result = _coerce_timedelta("30min")
        assert result == pd.Timedelta("30min")

    def test_numeric_raises(self) -> None:
        """Verify numeric input raises error."""
        with pytest.raises(TimeSeriesValidationError, match="ambiguous"):
            _coerce_timedelta(60)

        with pytest.raises(TimeSeriesValidationError, match="ambiguous"):
            _coerce_timedelta(1.5)


class TestResolveTimezone:
    """Tests for _resolve_timezone function."""

    def test_utc_resolved(self) -> None:
        """Verify UTC is resolved."""
        tz = _resolve_timezone("UTC")
        assert tz is not None

    def test_named_timezone_resolved(self) -> None:
        """Verify named timezone is resolved."""
        tz = _resolve_timezone("America/New_York")
        assert tz is not None

    def test_invalid_timezone_raises(self) -> None:
        """Verify invalid timezone raises error."""
        with pytest.raises(TimeSeriesValidationError, match="Unknown timezone"):
            _resolve_timezone("Invalid/Zone")


class TestFindDuplicates:
    """Tests for _find_duplicates function."""

    def test_no_duplicates(self) -> None:
        """Verify no duplicates returns empty set."""
        result = _find_duplicates(["a", "b", "c"])
        assert result == set()

    def test_with_duplicates(self) -> None:
        """Verify duplicates are found."""
        result = _find_duplicates(["a", "b", "a", "c", "b"])
        assert result == {"a", "b"}

    def test_empty_input(self) -> None:
        """Verify empty input returns empty set."""
        result = _find_duplicates([])
        assert result == set()


class TestBuildTimeseriesSchema:
    """Tests for build_timeseries_schema function."""

    def test_basic_schema(self) -> None:
        """Verify basic schema creation."""
        config = TimeSeriesValidationConfig(
            timestamp_column="ts",
            value_columns=[ValueColumnConfig(name="value")],
        )
        schema = build_timeseries_schema(config)
        assert "ts" in schema.columns
        assert "value" in schema.columns

    def test_schema_with_frequency(self) -> None:
        """Verify schema with frequency check."""
        config = TimeSeriesValidationConfig(
            timestamp_column="ts",
            frequency="1min",
        )
        schema = build_timeseries_schema(config)
        assert "ts" in schema.columns


class TestValidateTimeseriesFrameExtended:
    """Additional tests for validate_timeseries_frame function."""

    def test_extra_columns_fail_when_strict(self) -> None:
        """Verify extra columns fail when strict mode is on."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="1min", tz="UTC"),
                "close": [100.0] * 10,
                "extra": [0] * 10,
            }
        )
        config = TimeSeriesValidationConfig(
            value_columns=[ValueColumnConfig(name="close")],
            allow_extra_columns=False,
        )
        with pytest.raises(TimeSeriesValidationError):
            validate_timeseries_frame(df, config)

    def test_extra_columns_allowed_when_not_strict(self) -> None:
        """Verify extra columns allowed when strict mode is off."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=10, freq="1min", tz="UTC"),
                "close": [100.0] * 10,
                "extra": [0] * 10,
            }
        )
        config = TimeSeriesValidationConfig(
            value_columns=[ValueColumnConfig(name="close")],
            allow_extra_columns=True,
        )
        result = validate_timeseries_frame(df, config)
        assert len(result) == 10

    def test_nullable_column_allows_nan(self) -> None:
        """Verify nullable column allows NaN values."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-01", periods=5, freq="1min", tz="UTC"),
                "close": [100.0, np.nan, 102.0, np.nan, 104.0],
            }
        )
        config = TimeSeriesValidationConfig(
            value_columns=[ValueColumnConfig(name="close", nullable=True)],
        )
        result = validate_timeseries_frame(df, config)
        assert len(result) == 5
