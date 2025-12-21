# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""High-level time series validation helpers built on ``pydantic`` and ``pandera``.

The validation pipeline is split into two layers:

* ``pydantic`` models capture declarative configuration for strict runtime validation
  (e.g. which columns are expected, the allowed timezone, sampling frequency).
* ``pandera`` materialises these rules against ``pandas`` ``DataFrame`` instances and
  raises actionable errors when the data set does not honour them.

Typical usages look like::

    config = TimeSeriesValidationConfig(
        timestamp_column="timestamp",
        value_columns=[ValueColumnConfig(name="close", dtype="float64")],
        frequency="1min",
    )
    cleaned_df = validate_timeseries_frame(raw_df, config)

The helpers below enforce several invariants that routinely bite real trading
pipelines: null values are rejected, duplicate timestamps are flagged, time
stamps must be strictly increasing with a fixed sampling cadence, and timezone
drift is prevented by requiring a consistent timezone across the whole series.

Additionally, this module provides OHLCV-specific validation through the
``validate_ohlcv`` function for quick trading data quality checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Iterable, List, Optional, Sequence

import pandas as pd

from core.data.timeutils import get_timezone

try:  # pragma: no cover - exercised when pandera is installed
    import pandera.pandas as pa
    from pandera.errors import SchemaError
except ModuleNotFoundError:  # pragma: no cover - fallback used in lightweight test envs
    pa = None  # type: ignore[assignment]

    class SchemaError(ValueError):
        """Lightweight substitute for ``pandera.errors.SchemaError``."""

    class Check:
        def __init__(self, func, error: str | None = None):
            self.func = func
            self.error = error or "pandera check failed"

        def __call__(self, series: pd.Series) -> bool:
            result = self.func(series)
            if isinstance(result, pd.Series):
                result = bool(result.all())
            return bool(result)

    class Column:
        def __init__(
            self, dtype, nullable: bool = False, unique: bool = False, checks=None
        ):
            self.dtype = dtype
            self.nullable = nullable
            self.unique = unique
            self.checks = [c for c in (checks or []) if c is not None]

    class DataFrameSchema:
        def __init__(self, columns: dict[str, "Column"], strict: bool = False):
            self.columns = columns
            self.strict = strict

        def validate(self, frame: pd.DataFrame, lazy: bool = False) -> pd.DataFrame:
            missing = [name for name in self.columns if name not in frame.columns]
            if missing:
                raise SchemaError(f"Missing columns: {missing}")
            if self.strict:
                extras = [name for name in frame.columns if name not in self.columns]
                if extras:
                    raise SchemaError(f"Unexpected columns: {extras}")
            for name, column in self.columns.items():
                series = frame[name]
                if not column.nullable and series.isna().any():
                    raise SchemaError(f"{name} contains NaN values")
                if column.unique and not series.is_unique:
                    raise SchemaError(f"{name} contains duplicate values")
                for check in column.checks:
                    if not check(series):
                        raise SchemaError(
                            getattr(check, "error", f"Check failed for {name}")
                        )
            return frame

else:  # pragma: no cover - alias for typing convenience when pandera is present
    Check = pa.Check
    Column = pa.Column
    DataFrameSchema = pa.DataFrameSchema


from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

try:  # Python >= 3.9 ships the ``zoneinfo`` module in the stdlib.
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover - fallback for very old Python versions
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

DEFAULT_TIMEZONE = "UTC"

__all__ = [
    "TimeSeriesValidationError",
    "TimeSeriesValidationConfig",
    "ValueColumnConfig",
    "build_timeseries_schema",
    "validate_timeseries_frame",
    "validate_ohlcv",
    "OHLCVValidationResult",
]


class TimeSeriesValidationError(ValueError):
    """Raised when a DataFrame payload fails the strict validation checks."""


@dataclass
class OHLCVValidationResult:
    """Result of OHLCV validation with detailed diagnostics."""

    valid: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    row_count: int = 0
    nan_count: int = 0
    negative_count: int = 0

    def summary(self) -> str:
        """Return a human-readable summary of validation results."""
        status = "PASSED" if self.valid else "FAILED"
        return (
            f"OHLCV Validation {status}: {self.row_count} rows, "
            f"{len(self.issues)} errors, {len(self.warnings)} warnings"
        )


def validate_ohlcv(
    df: pd.DataFrame,
    *,
    price_col: str = "close",
    open_col: str | None = "open",
    high_col: str | None = "high",
    low_col: str | None = "low",
    volume_col: str | None = "volume",
    raise_on_error: bool = False,
) -> OHLCVValidationResult:
    """Validate OHLCV data for trading analysis.

    This is a lightweight validation function for quick data quality checks
    before running analysis or backtests.

    Args:
        df: DataFrame containing OHLCV data
        price_col: Name of the close/price column (required)
        open_col: Name of the open column (optional)
        high_col: Name of the high column (optional)
        low_col: Name of the low column (optional)
        volume_col: Name of the volume column (optional)
        raise_on_error: Whether to raise TimeSeriesValidationError on failure

    Returns:
        OHLCVValidationResult with validation details

    Raises:
        TimeSeriesValidationError: If validation fails and raise_on_error=True

    Example:
        >>> result = validate_ohlcv(df)
        >>> if not result.valid:
        ...     print(result.issues)
    """
    result = OHLCVValidationResult(valid=True, row_count=len(df))

    # Check if DataFrame is empty
    if df.empty:
        result.valid = False
        result.issues.append("DataFrame is empty")
        if raise_on_error:
            raise TimeSeriesValidationError("DataFrame is empty")
        return result

    # Check minimum data points
    if len(df) < 10:
        result.warnings.append(f"Only {len(df)} rows - analysis may be unreliable")

    # Check required price column
    if price_col not in df.columns:
        result.valid = False
        result.issues.append(f"Required column '{price_col}' not found")
        if raise_on_error:
            raise TimeSeriesValidationError(f"Required column '{price_col}' not found")
        return result

    # Validate price column
    price_series = df[price_col]
    nan_count = price_series.isna().sum()
    result.nan_count = int(nan_count)

    if nan_count > 0:
        nan_ratio = nan_count / len(df)
        if nan_ratio > 0.05:
            result.valid = False
            result.issues.append(
                f"{nan_count} NaN values in {price_col} ({nan_ratio:.1%})"
            )
        else:
            result.warnings.append(f"{nan_count} NaN values in {price_col}")

    # Check for non-positive prices
    valid_prices = price_series.dropna()
    negative = (valid_prices <= 0).sum()
    result.negative_count = int(negative)

    if negative > 0:
        result.valid = False
        result.issues.append(f"{negative} non-positive values in {price_col}")

    # Check for constant prices
    if valid_prices.nunique() == 1:
        result.valid = False
        result.issues.append(f"All values in {price_col} are identical")

    # Validate OHLC relationships if all columns present
    ohlc_cols = [
        (open_col, "open"),
        (high_col, "high"),
        (low_col, "low"),
        (price_col, "close"),
    ]
    available_cols = {
        name: label for name, label in ohlc_cols if name and name in df.columns
    }

    if len(available_cols) == 4 and high_col and low_col:
        # Check high >= low
        violations = (df[high_col] < df[low_col]).sum()
        if violations > 0:
            result.valid = False
            result.issues.append(f"{violations} rows where high < low")

        # Check high >= close, open
        if open_col and open_col in df.columns:
            high_open_violations = (df[high_col] < df[open_col]).sum()
            if high_open_violations > 0:
                result.warnings.append(f"{high_open_violations} rows where high < open")

        high_close_violations = (df[high_col] < df[price_col]).sum()
        if high_close_violations > 0:
            result.warnings.append(f"{high_close_violations} rows where high < close")

        # Check low <= close, open
        if open_col and open_col in df.columns:
            low_open_violations = (df[low_col] > df[open_col]).sum()
            if low_open_violations > 0:
                result.warnings.append(f"{low_open_violations} rows where low > open")

        low_close_violations = (df[low_col] > df[price_col]).sum()
        if low_close_violations > 0:
            result.warnings.append(f"{low_close_violations} rows where low > close")

    # Validate volume if present
    if volume_col and volume_col in df.columns:
        vol_series = df[volume_col]
        neg_volume = (vol_series < 0).sum()
        if neg_volume > 0:
            result.valid = False
            result.issues.append(f"{neg_volume} negative volume values")

    if raise_on_error and not result.valid:
        raise TimeSeriesValidationError("; ".join(result.issues))

    return result


class ValueColumnConfig(BaseModel):
    """Declarative schema for value columns in a time series payload."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, strict=True)

    name: StrictStr = Field(
        ..., min_length=1, description="Column name in the dataframe"
    )
    dtype: Optional[StrictStr] = Field(
        default=None,
        description="Optional pandas-compatible dtype string enforced by pandera.",
    )
    nullable: bool = Field(
        default=False,
        description="Allow null values in the column. Defaults to the strict setting (False).",
    )

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise TimeSeriesValidationError("Column names must not be blank")
        return stripped


class TimeSeriesValidationConfig(BaseModel):
    """Configuration describing the shape and quality guarantees of a time series frame."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, strict=True)

    timestamp_column: StrictStr = Field(
        default="timestamp",
        min_length=1,
        description="Name of the datetime column used as chronological anchor.",
    )
    value_columns: Sequence[ValueColumnConfig] = Field(
        default_factory=list,
        description="Collection of value column descriptors enforced by pandera.",
    )
    frequency: Optional[pd.Timedelta] = Field(
        default=None,
        description="Expected sampling cadence expressed as a pandas-compatible timedelta.",
    )
    require_timezone: StrictStr = Field(
        default=DEFAULT_TIMEZONE,
        description="Canonical timezone every timestamp must share (defaults to UTC).",
    )
    allow_extra_columns: bool = Field(
        default=False,
        description="Allow columns outside of ``value_columns`` to be present in the frame.",
    )

    @field_validator("timestamp_column")
    @classmethod
    def _strip_timestamp_column(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise TimeSeriesValidationError("Timestamp column name must not be blank")
        return stripped

    @field_validator("frequency", mode="before")
    @classmethod
    def _coerce_frequency(cls, value: Optional[object]) -> Optional[pd.Timedelta]:
        return _coerce_timedelta(value)

    @field_validator("require_timezone")
    @classmethod
    def _ensure_timezone(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise TimeSeriesValidationError("Timezone requirement must not be blank")
        _resolve_timezone(stripped)
        return stripped

    @model_validator(mode="after")
    def _ensure_unique_columns(self) -> "TimeSeriesValidationConfig":
        names = [col.name for col in self.value_columns]
        duplicates = _find_duplicates(names)
        if duplicates:
            joined = ", ".join(sorted(duplicates))
            raise TimeSeriesValidationError(
                f"Value columns must be unique, duplicates found for: {joined}"
            )
        if self.timestamp_column in names:
            raise TimeSeriesValidationError(
                "Timestamp column cannot also be declared as a value column"
            )
        return self


def _coerce_timedelta(value: Optional[object]) -> Optional[pd.Timedelta]:
    """Normalise arbitrary timedelta representations to ``pd.Timedelta``."""

    if value is None:
        return None
    if isinstance(value, pd.Timedelta):
        return value
    if isinstance(value, timedelta):
        return pd.Timedelta(value)
    if isinstance(value, (int, float)):
        raise TimeSeriesValidationError(
            "Numeric frequencies are ambiguous; provide a pandas-compatible timedelta string"
        )
    try:
        return pd.Timedelta(str(value))
    except (ValueError, TypeError) as exc:  # pragma: no cover - defensive guard
        raise TimeSeriesValidationError(
            f"Unable to coerce frequency {value!r} to Timedelta"
        ) from exc


def _resolve_timezone(name: str) -> ZoneInfo:
    """Resolve the provided timezone name into a :class:`~zoneinfo.ZoneInfo` instance."""

    try:
        return get_timezone(name)
    except ValueError as exc:
        raise TimeSeriesValidationError(f"Unknown timezone identifier: {name}") from exc


def _find_duplicates(values: Iterable[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def build_timeseries_schema(config: TimeSeriesValidationConfig) -> DataFrameSchema:
    """Construct a strict :class:`pandera.DataFrameSchema` for the provided configuration."""

    def _check_monotonic(series: pd.Series) -> bool:
        if series.size <= 1:
            return True
        try:
            deltas = series.diff().dropna()
        except TypeError:
            return False
        return bool((deltas > pd.Timedelta(0)).all())

    timestamp_checks: List[Check] = [
        Check(_check_monotonic, error="timestamps must be strictly increasing"),
    ]

    if config.frequency is not None:

        def _check_frequency(series: pd.Series) -> bool:
            if series.size <= 1:
                return True
            deltas = series.diff().dropna()
            try:
                # ``pd.Timedelta`` comparisons work across timezone aware and naive series.
                return bool((deltas == config.frequency).all())
            except TypeError:
                return False

        timestamp_checks.append(
            Check(
                _check_frequency,
                error=(
                    "timestamp differences must match the configured sampling frequency "
                    f"({config.frequency})"
                ),
            )
        )

    timezone_name = config.require_timezone
    timezone_obj = _resolve_timezone(timezone_name)
    timezone_key = getattr(timezone_obj, "key", None) or str(timezone_obj)

    def _check_timezone(series: pd.Series) -> bool:
        if series.empty:
            return True
        try:
            tz = series.dt.tz
        except AttributeError:
            return False
        if tz is None:
            return False
        tz_name = getattr(tz, "key", None) or str(tz)
        return tz_name == timezone_key

    timestamp_checks.append(
        Check(
            _check_timezone,
            error=(
                f"expected series '{config.timestamp_column}' to be timezone-aware "
                f"({timezone_key})"
            ),
        )
    )

    columns: dict[str, Column] = {
        config.timestamp_column: Column(
            f"datetime64[ns, {timezone_key}]",
            nullable=False,
            unique=True,
            checks=timestamp_checks,
        )
    }

    for column in config.value_columns:
        columns[column.name] = Column(
            column.dtype or "float64",
            nullable=column.nullable,
            checks=(
                [
                    Check(
                        lambda s: not s.isna().any(),
                        error=f"{column.name} contains NaN values",
                    )
                ]
                if not column.nullable
                else None
            ),
        )

    return DataFrameSchema(columns=columns, strict=not config.allow_extra_columns)


def validate_timeseries_frame(
    frame: pd.DataFrame, config: TimeSeriesValidationConfig
) -> pd.DataFrame:
    """Validate a ``pandas`` DataFrame according to the provided configuration."""

    timestamp_col = config.timestamp_column
    if timestamp_col not in frame.columns:
        raise TimeSeriesValidationError(
            f"expected series '{timestamp_col}' to exist in payload"
        )

    raw_series = frame[timestamp_col]
    if not pd.api.types.is_datetime64_any_dtype(raw_series):
        raise TimeSeriesValidationError(
            f"expected series '{timestamp_col}' to be timezone-aware ({config.require_timezone})"
        )

    try:
        tz = raw_series.dt.tz  # type: ignore[attr-defined]
    except AttributeError:
        tz = None

    required_tz = _resolve_timezone(config.require_timezone)
    required_key = getattr(required_tz, "key", None) or str(required_tz)
    current_key = getattr(tz, "key", None) or str(tz) if tz is not None else None

    if tz is None or current_key != required_key:
        raise TimeSeriesValidationError(
            f"expected series '{timestamp_col}' to be timezone-aware ({config.require_timezone})"
        )

    normalized = frame.copy()
    normalized[timestamp_col] = raw_series.dt.tz_convert("UTC")

    schema = build_timeseries_schema(config)
    try:
        return schema.validate(normalized, lazy=False)
    except SchemaError as exc:  # pragma: no cover - exercised in unit tests
        raise TimeSeriesValidationError(str(exc)) from exc
