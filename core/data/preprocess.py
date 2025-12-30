# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Union

import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from ..utils.logging import get_logger
from .fingerprint import fingerprint_rows, record_transformation_trace

_logger = get_logger(__name__)


ArrayLike = Union[np.ndarray, pd.Series, Sequence[float], Iterable[float]]


__all__ = ["normalize_df", "scale_series", "normalize_numeric_columns"]


def normalize_df(
    df: pd.DataFrame,
    timestamp_col: str = "ts",
    *,
    use_float32: bool = False,
    trace: bool | str = False,
) -> pd.DataFrame:
    """Return a cleaned and chronologically ordered copy of ``df``.

    The helper performs a defensive copy, standardises the timestamp column
    (if present) to UTC-aware ``datetime64`` values, sorts the frame by that
    column, removes duplicate rows and performs linear interpolation on the
    numeric columns to fill minor gaps.

    Parameters
    ----------
    df:
        Input dataframe to normalise. The original dataframe is never mutated.
    timestamp_col:
        Optional name of the column that stores timestamps (defaults to ``"ts"``).
    use_float32:
        Convert numeric columns to float32 to reduce memory usage (default: False).

    Returns
    -------
    pandas.DataFrame
        A normalised dataframe with a reset index for predictable downstream
        usage.
    """
    trace_id = "normalize_df" if trace is True else (trace or None)
    input_fp = None
    input_columns = list(df.columns)

    if trace_id:
        input_fp = fingerprint_rows(
            df.to_dict("records"),
            columns=input_columns,
            dataset_id=f"{trace_id}-input",
            schema_version="dynamic",
        )

    with _logger.operation(
        "normalize_df",
        rows=len(df),
        columns=len(df.columns),
        use_float32=use_float32,
        trace=bool(trace_id),
    ):
        normalized = df.copy()

        if timestamp_col in normalized.columns:
            timestamps = normalized[timestamp_col]
            if np.issubdtype(timestamps.dtype, np.number):
                numeric_ts = pd.to_numeric(timestamps, errors="coerce")
                finite = numeric_ts[np.isfinite(numeric_ts)]

                unit = "s"
                if not finite.empty:
                    max_abs = float(np.nanmax(np.abs(finite)))
                    if max_abs >= 1e18:
                        unit = "ns"
                    elif max_abs >= 1e15:
                        unit = "us"
                    elif max_abs >= 1e12:
                        unit = "ms"

                normalized[timestamp_col] = pd.to_datetime(
                    numeric_ts, unit=unit, errors="coerce", utc=True
                )
            else:
                normalized[timestamp_col] = pd.to_datetime(
                    timestamps, errors="coerce", utc=True
                )
            normalized = normalized.sort_values(timestamp_col)

        normalized = normalized.drop_duplicates()

        numeric_cols = normalized.select_dtypes(include=["number"]).columns
        if not numeric_cols.empty:
            normalized[numeric_cols] = normalized[numeric_cols].interpolate(
                method="linear", limit_direction="both"
            )

            # Convert to float32 if requested
            if use_float32:
                for col in numeric_cols:
                    if col != timestamp_col:
                        normalized[col] = normalized[col].astype(np.float32)

        normalized = normalized.reset_index(drop=True)

        if trace_id and input_fp is not None:
            output_fp = fingerprint_rows(
                normalized.to_dict("records"),
                columns=list(normalized.columns),
                dataset_id=f"{trace_id}-output",
                schema_version="dynamic",
            )
            record_transformation_trace(
                transformation_id=trace_id,
                parameters={"timestamp_col": timestamp_col, "use_float32": use_float32},
                input_fingerprint=input_fp,
                output_fingerprint=output_fp,
            )
            post_fp = fingerprint_rows(
                df.to_dict("records"),
                columns=input_columns,
                dataset_id=f"{trace_id}-input",
                schema_version="dynamic",
            )
            if post_fp["content_hash"] != input_fp["content_hash"]:
                _logger.warning("%s mutated input dataframe", trace_id)

        return normalized


def scale_series(
    x: ArrayLike, method: str = "zscore", *, use_float32: bool = False
) -> np.ndarray:
    """Scale a 1-D array according to the requested ``method``.

    Currently supported scaling methods are ``"zscore"`` (default) and
    ``"minmax"``. The function always returns a NumPy ``ndarray`` and leaves
    constant or empty inputs untouched.

    Parameters
    ----------
    x:
        Input array-like data to scale.
    method:
        Scaling method: "zscore" (standardization) or "minmax" (normalization).
    use_float32:
        Use float32 precision to reduce memory usage (default: False).

    Returns
    -------
    np.ndarray
        Scaled array with the same shape as input.
    """
    with _logger.operation(
        "scale_series",
        method=method,
        use_float32=use_float32,
        level=logging.DEBUG,
        emit_start=False,
        emit_success=False,
    ):
        dtype = np.float32 if use_float32 else float

        if isinstance(x, (np.ndarray, pd.Series)):
            values = np.asarray(x, dtype=dtype)
        else:
            if isinstance(x, (str, bytes)):
                raise TypeError("scale_series does not support string-like inputs")
            values = np.asarray(list(x), dtype=dtype)

        if values.ndim != 1:
            raise ValueError("scale_series expects a one-dimensional input")

        if values.size == 0:
            return values

        method = method.lower()

        if method == "zscore":
            std = values.std()
            if std == 0:
                return np.zeros_like(values)
            mean = values.mean()
            return (values - mean) / std

        if method == "minmax":
            data_min = values.min()
            data_range = values.max() - data_min
            if data_range == 0:
                return np.zeros_like(values)
            return (values - data_min) / data_range

        raise ValueError(f"Unsupported scaling method: {method!r}")


def normalize_numeric_columns(
    df: pd.DataFrame,
    method: str = "zscore",
    *,
    columns: Sequence[str] | None = None,
    exclude: Sequence[str] | None = None,
    use_float32: bool = False,
) -> pd.DataFrame:
    """Return a copy of ``df`` with numeric columns scaled to a common range.

    The helper applies :func:`scale_series` column-wise to the selected numeric
    columns while preserving non-numeric data and ``NaN`` sentinels.  By
    default, all numeric columns are scaled; the ``columns`` and ``exclude``
    parameters provide fine-grained control when certain fields (e.g.
    timestamps) must be left untouched.

    Parameters
    ----------
    df:
        Input dataframe.  The original dataframe is never mutated in-place.
    method:
        Scaling method passed to :func:`scale_series` (``"zscore"`` by default).
    columns:
        Optional explicit list of column names to scale.  When omitted all
        numeric columns are considered.
    exclude:
        Optional list of column names to ignore even if they appear in
        ``columns`` or are detected as numeric.
    use_float32:
        Emit ``float32`` values instead of the default ``float64`` to reduce
        memory footprint.

    Returns
    -------
    pandas.DataFrame
        Copy of the original dataframe with selected numeric columns scaled.
    """

    exclude_set = set(exclude or ())

    with _logger.operation(
        "normalize_numeric_columns",
        method=method,
        use_float32=use_float32,
        columns="explicit" if columns is not None else "auto",
        exclude_count=len(exclude_set),
    ):
        normalized = df.copy()

        if columns is None:
            candidate_columns = list(
                normalized.select_dtypes(include=["number"], exclude=["bool"]).columns
            )
        else:
            candidate_columns = list(columns)

        target_columns = [
            column for column in candidate_columns if column not in exclude_set
        ]

        for column in target_columns:
            if column not in normalized.columns:
                raise KeyError(f"Column {column!r} not found in dataframe")

            series = normalized[column]
            if pd.api.types.is_bool_dtype(series.dtype):
                raise TypeError(f"Column {column!r} has boolean dtype which cannot be scaled")
            if not is_numeric_dtype(series.dtype):
                raise TypeError(
                    f"Column {column!r} has non-numeric dtype {series.dtype}"
                )

            values = series.to_numpy(
                dtype=np.float32 if use_float32 else float, copy=True
            )

            if values.size == 0:
                continue

            nan_mask = np.isnan(values)
            if nan_mask.all():
                normalized[column] = values
                continue

            scaled = scale_series(
                values[~nan_mask], method=method, use_float32=use_float32
            )
            values[~nan_mask] = scaled
            normalized[column] = values

        return normalized
