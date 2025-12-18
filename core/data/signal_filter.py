# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Signal and data filtering module for removing invalid or unnecessary data.

This module provides utilities to filter out invalid, duplicate, or poor-quality
signals and data points from trading pipelines. The goal is to ensure only clean,
valid data flows through the system.

**Key Functions**

* ``filter_invalid_values``: Remove NaN, Inf, and out-of-bounds values
* ``filter_duplicates``: Remove duplicate entries based on timestamp or key
* ``filter_by_quality``: Filter based on quality score thresholds
* ``filter_signals``: Comprehensive signal filtering pipeline

**Usage**

    >>> import numpy as np
    >>> from core.data.signal_filter import filter_invalid_values, SignalFilterConfig
    >>>
    >>> signals = np.array([1.0, np.nan, 2.0, np.inf, 3.0, -np.inf])
    >>> clean = filter_invalid_values(signals)
    >>> print(clean)  # [1.0, 2.0, 3.0]
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Sequence, TypeVar

import numpy as np
import pandas as pd
from numpy.typing import NDArray

__all__ = [
    "FilterResult",
    "FilterStrategy",
    "SignalFilterConfig",
    "SignalFilterConfigError",
    "filter_by_quality",
    "filter_by_range",
    "filter_dataframe",
    "filter_duplicates",
    "filter_invalid_values",
    "filter_outliers_zscore",
    "filter_signals",
]


class FilterStrategy(str, Enum):
    """Strategy for handling filtered values."""

    REMOVE = "remove"  # Remove invalid values entirely
    REPLACE_NAN = "replace_nan"  # Replace with NaN (for later handling)
    REPLACE_ZERO = "replace_zero"  # Replace with zero
    REPLACE_PREVIOUS = "replace_previous"  # Forward-fill from previous valid value


T = TypeVar("T")


@dataclass(slots=True)
class FilterResult:
    """Result of a filtering operation with statistics.

    Attributes:
        data: The filtered data
        removed_count: Number of values removed or replaced
        removed_indices: Indices of removed/replaced values
        original_count: Original number of values
        removal_ratio: Ratio of removed values to original count
    """

    data: NDArray[np.floating[Any]] | pd.DataFrame | pd.Series
    removed_count: int
    removed_indices: NDArray[np.intp] | pd.Index
    original_count: int

    @property
    def removal_ratio(self) -> float:
        """Return the ratio of removed values to original count."""
        if self.original_count == 0:
            return 0.0
        return self.removed_count / self.original_count

    @property
    def retained_count(self) -> int:
        """Return the number of retained values."""
        return self.original_count - self.removed_count


class SignalFilterConfigError(ValueError):
    """Raised when SignalFilterConfig has invalid configuration."""

    pass


@dataclass(slots=True)
class SignalFilterConfig:
    """Configuration for signal filtering operations.

    Attributes:
        remove_nan: Remove NaN values
        remove_inf: Remove Inf values
        min_value: Minimum allowed value (None = no lower bound)
        max_value: Maximum allowed value (None = no upper bound)
        remove_duplicates: Remove duplicate values based on timestamp
        zscore_threshold: Z-score threshold for outlier detection (None = disabled)
        zscore_window: Rolling window size for z-score calculation
        quality_threshold: Minimum quality score to retain (None = disabled)
        strategy: Strategy for handling filtered values

    Raises:
        SignalFilterConfigError: If configuration parameters are invalid
    """

    remove_nan: bool = True
    remove_inf: bool = True
    min_value: float | None = None
    max_value: float | None = None
    remove_duplicates: bool = False
    zscore_threshold: float | None = None
    zscore_window: int = 20
    quality_threshold: float | None = None
    strategy: FilterStrategy = FilterStrategy.REMOVE

    def __post_init__(self) -> None:
        """Validate configuration parameters for security and correctness."""
        # Validate zscore_window is positive
        if self.zscore_window < 2:
            raise SignalFilterConfigError(
                f"zscore_window must be >= 2, got {self.zscore_window}"
            )
        if self.zscore_window > 10000:
            raise SignalFilterConfigError(
                f"zscore_window must be <= 10000 to prevent DoS, got {self.zscore_window}"
            )

        # Validate zscore_threshold if set
        if self.zscore_threshold is not None:
            if self.zscore_threshold <= 0:
                raise SignalFilterConfigError(
                    f"zscore_threshold must be positive, got {self.zscore_threshold}"
                )
            if not np.isfinite(self.zscore_threshold):
                raise SignalFilterConfigError(
                    "zscore_threshold must be a finite value"
                )

        # Validate quality_threshold if set
        if self.quality_threshold is not None:
            if not np.isfinite(self.quality_threshold):
                raise SignalFilterConfigError(
                    "quality_threshold must be a finite value"
                )

        # Validate min/max values are finite if set
        if self.min_value is not None and not np.isfinite(self.min_value):
            raise SignalFilterConfigError("min_value must be a finite value")
        if self.max_value is not None and not np.isfinite(self.max_value):
            raise SignalFilterConfigError("max_value must be a finite value")

        # Validate min <= max if both are set
        if (
            self.min_value is not None
            and self.max_value is not None
            and self.min_value > self.max_value
        ):
            raise SignalFilterConfigError(
                f"min_value ({self.min_value}) must be <= max_value ({self.max_value})"
            )


def filter_invalid_values(
    data: NDArray[np.floating[Any]] | Sequence[float],
    *,
    remove_nan: bool = True,
    remove_inf: bool = True,
    strategy: FilterStrategy = FilterStrategy.REMOVE,
    max_size: int = 100_000_000,  # 100M elements max by default
) -> FilterResult:
    """Filter out invalid values (NaN, Inf) from numeric data.

    Args:
        data: Input data array or sequence
        remove_nan: Whether to remove NaN values
        remove_inf: Whether to remove Inf values
        strategy: Strategy for handling invalid values
        max_size: Maximum allowed array size (DoS protection)

    Returns:
        FilterResult with cleaned data and statistics

    Raises:
        ValueError: If input array exceeds max_size

    Example:
        >>> import numpy as np
        >>> data = np.array([1.0, np.nan, 2.0, np.inf, 3.0])
        >>> result = filter_invalid_values(data)
        >>> print(result.data)  # [1.0, 2.0, 3.0]
        >>> print(result.removed_count)  # 2
    """
    arr = np.asarray(data, dtype=np.float64)
    original_count = arr.size

    # DoS protection: limit input size
    if arr.size > max_size:
        raise ValueError(
            f"Input array size ({arr.size}) exceeds maximum allowed size ({max_size})"
        )

    # Build mask of invalid values
    invalid_mask = np.zeros(arr.size, dtype=bool)

    if remove_nan:
        invalid_mask |= np.isnan(arr)

    if remove_inf:
        invalid_mask |= np.isinf(arr)

    removed_indices = np.where(invalid_mask)[0]
    removed_count = int(invalid_mask.sum())

    # Apply strategy
    if strategy == FilterStrategy.REMOVE:
        clean_data = arr[~invalid_mask]
    elif strategy == FilterStrategy.REPLACE_NAN:
        clean_data = arr.copy()
        clean_data[invalid_mask] = np.nan
    elif strategy == FilterStrategy.REPLACE_ZERO:
        clean_data = arr.copy()
        clean_data[invalid_mask] = 0.0
    elif strategy == FilterStrategy.REPLACE_PREVIOUS:
        clean_data = arr.copy()
        for idx in removed_indices:
            if idx > 0:
                clean_data[idx] = clean_data[idx - 1]
            else:
                # Find first valid value
                valid_indices = np.where(~invalid_mask)[0]
                if valid_indices.size > 0:
                    clean_data[idx] = arr[valid_indices[0]]
                else:
                    clean_data[idx] = 0.0
    else:
        clean_data = arr[~invalid_mask]

    return FilterResult(
        data=clean_data,
        removed_count=removed_count,
        removed_indices=removed_indices,
        original_count=original_count,
    )


def filter_by_range(
    data: NDArray[np.floating[Any]] | Sequence[float],
    *,
    min_value: float | None = None,
    max_value: float | None = None,
    inclusive_min: bool = True,
    inclusive_max: bool = True,
    strategy: FilterStrategy = FilterStrategy.REMOVE,
    max_size: int = 100_000_000,  # 100M elements max by default
) -> FilterResult:
    """Filter values outside a specified range.

    Args:
        data: Input data array or sequence
        min_value: Minimum allowed value (None = no lower bound)
        max_value: Maximum allowed value (None = no upper bound)
        inclusive_min: Whether to include min_value
        inclusive_max: Whether to include max_value
        strategy: Strategy for handling out-of-range values
        max_size: Maximum allowed array size (DoS protection)

    Returns:
        FilterResult with filtered data and statistics

    Raises:
        ValueError: If input array exceeds max_size or range values are invalid

    Example:
        >>> data = np.array([1.0, 5.0, 10.0, 15.0, 20.0])
        >>> result = filter_by_range(data, min_value=5.0, max_value=15.0)
        >>> print(result.data)  # [5.0, 10.0, 15.0]
    """
    # Validate range values
    if min_value is not None and not np.isfinite(min_value):
        raise ValueError("min_value must be a finite number")
    if max_value is not None and not np.isfinite(max_value):
        raise ValueError("max_value must be a finite number")
    if min_value is not None and max_value is not None and min_value > max_value:
        raise ValueError(f"min_value ({min_value}) must be <= max_value ({max_value})")

    arr = np.asarray(data, dtype=np.float64)
    original_count = arr.size

    # DoS protection: limit input size
    if arr.size > max_size:
        raise ValueError(
            f"Input array size ({arr.size}) exceeds maximum allowed size ({max_size})"
        )

    # Build mask of out-of-range values
    out_of_range = np.zeros(arr.size, dtype=bool)

    if min_value is not None:
        if inclusive_min:
            out_of_range |= arr < min_value
        else:
            out_of_range |= arr <= min_value

    if max_value is not None:
        if inclusive_max:
            out_of_range |= arr > max_value
        else:
            out_of_range |= arr >= max_value

    removed_indices = np.where(out_of_range)[0]
    removed_count = int(out_of_range.sum())

    # Apply strategy
    if strategy == FilterStrategy.REMOVE:
        clean_data = arr[~out_of_range]
    elif strategy == FilterStrategy.REPLACE_NAN:
        clean_data = arr.copy()
        clean_data[out_of_range] = np.nan
    elif strategy == FilterStrategy.REPLACE_ZERO:
        clean_data = arr.copy()
        clean_data[out_of_range] = 0.0
    elif strategy == FilterStrategy.REPLACE_PREVIOUS:
        clean_data = arr.copy()
        for idx in removed_indices:
            if idx > 0:
                clean_data[idx] = clean_data[idx - 1]
            else:
                valid_indices = np.where(~out_of_range)[0]
                if valid_indices.size > 0:
                    clean_data[idx] = arr[valid_indices[0]]
                else:
                    clean_data[idx] = 0.0
    else:
        clean_data = arr[~out_of_range]

    return FilterResult(
        data=clean_data,
        removed_count=removed_count,
        removed_indices=removed_indices,
        original_count=original_count,
    )


def filter_outliers_zscore(
    data: NDArray[np.floating[Any]] | Sequence[float],
    *,
    threshold: float = 3.0,
    window: int = 20,
    strategy: FilterStrategy = FilterStrategy.REMOVE,
    max_size: int = 100_000_000,  # 100M elements max by default
) -> FilterResult:
    """Filter outliers based on rolling z-score.

    Args:
        data: Input data array or sequence
        threshold: Z-score threshold for outlier detection
        window: Rolling window size for calculating mean and std
        strategy: Strategy for handling outliers
        max_size: Maximum allowed array size (DoS protection)

    Returns:
        FilterResult with filtered data and statistics

    Raises:
        ValueError: If parameters are invalid or input exceeds max_size

    Example:
        >>> data = np.array([1.0, 1.1, 1.0, 100.0, 1.0, 1.1])  # 100.0 is outlier
        >>> result = filter_outliers_zscore(data, threshold=2.0, window=3)
        >>> print(100.0 in result.data)  # False (outlier removed)
    """
    # Validate parameters
    if threshold <= 0:
        raise ValueError(f"threshold must be positive, got {threshold}")
    if not np.isfinite(threshold):
        raise ValueError("threshold must be a finite value")
    if window < 2:
        raise ValueError(f"window must be >= 2, got {window}")
    if window > 10000:
        raise ValueError(f"window must be <= 10000 to prevent DoS, got {window}")

    arr = np.asarray(data, dtype=np.float64)
    original_count = arr.size

    # DoS protection: limit input size
    if arr.size > max_size:
        raise ValueError(
            f"Input array size ({arr.size}) exceeds maximum allowed size ({max_size})"
        )

    if arr.size < window:
        # Not enough data for z-score calculation
        return FilterResult(
            data=arr.copy(),
            removed_count=0,
            removed_indices=np.array([], dtype=np.intp),
            original_count=original_count,
        )

    # Calculate rolling z-score
    series = pd.Series(arr)
    rolling = series.rolling(window=window, min_periods=window)
    mean = rolling.mean().shift(1)
    std = rolling.std(ddof=0).shift(1)

    # Handle zero std
    std_safe = std.replace(0, np.nan)
    zscore = np.abs((series - mean) / std_safe)

    # Mark outliers (NaN z-scores are not outliers)
    outlier_mask = zscore.fillna(0) > threshold
    outlier_mask = outlier_mask.to_numpy()

    removed_indices = np.where(outlier_mask)[0]
    removed_count = int(outlier_mask.sum())

    # Apply strategy
    if strategy == FilterStrategy.REMOVE:
        clean_data = arr[~outlier_mask]
    elif strategy == FilterStrategy.REPLACE_NAN:
        clean_data = arr.copy()
        clean_data[outlier_mask] = np.nan
    elif strategy == FilterStrategy.REPLACE_ZERO:
        clean_data = arr.copy()
        clean_data[outlier_mask] = 0.0
    elif strategy == FilterStrategy.REPLACE_PREVIOUS:
        clean_data = arr.copy()
        for idx in removed_indices:
            if idx > 0:
                clean_data[idx] = clean_data[idx - 1]
            else:
                valid_indices = np.where(~outlier_mask)[0]
                if valid_indices.size > 0:
                    clean_data[idx] = arr[valid_indices[0]]
                else:
                    clean_data[idx] = 0.0
    else:
        clean_data = arr[~outlier_mask]

    return FilterResult(
        data=clean_data,
        removed_count=removed_count,
        removed_indices=removed_indices,
        original_count=original_count,
    )


def filter_duplicates(
    data: pd.DataFrame | pd.Series,
    *,
    subset: Sequence[str] | str | None = None,
    keep: str = "first",
) -> FilterResult:
    """Filter duplicate rows or values from a DataFrame or Series.

    Args:
        data: Input DataFrame or Series
        subset: Column(s) to consider for duplicates (DataFrame only)
        keep: Which duplicate to keep ('first', 'last', or False for none)

    Returns:
        FilterResult with deduplicated data and statistics

    Example:
        >>> df = pd.DataFrame({'a': [1, 1, 2], 'b': [1, 2, 3]})
        >>> result = filter_duplicates(df, subset='a')
        >>> print(len(result.data))  # 2
    """
    original_count = len(data)

    if isinstance(data, pd.Series):
        duplicate_mask = data.duplicated(keep=keep)  # type: ignore[call-arg]
        clean_data = data[~duplicate_mask]
        removed_indices = data.index[duplicate_mask]
    else:
        if subset is not None:
            if isinstance(subset, str):
                subset = [subset]
            duplicate_mask = data.duplicated(subset=list(subset), keep=keep)
        else:
            duplicate_mask = data.duplicated(keep=keep)
        clean_data = data[~duplicate_mask]
        removed_indices = data.index[duplicate_mask]

    removed_count = int(duplicate_mask.sum())

    return FilterResult(
        data=clean_data,
        removed_count=removed_count,
        removed_indices=removed_indices,
        original_count=original_count,
    )


def filter_by_quality(
    data: pd.DataFrame,
    quality_column: str,
    *,
    threshold: float = 0.5,
    keep_above: bool = True,
) -> FilterResult:
    """Filter data based on a quality score column.

    Args:
        data: Input DataFrame with a quality score column
        quality_column: Name of the quality score column
        threshold: Threshold value for filtering
        keep_above: If True, keep values above threshold; otherwise below

    Returns:
        FilterResult with filtered data and statistics

    Example:
        >>> df = pd.DataFrame({'value': [1, 2, 3], 'quality': [0.3, 0.6, 0.8]})
        >>> result = filter_by_quality(df, 'quality', threshold=0.5)
        >>> print(len(result.data))  # 2 (rows with quality >= 0.5)
    """
    if quality_column not in data.columns:
        raise ValueError(f"Quality column '{quality_column}' not found in DataFrame")

    original_count = len(data)
    quality_series = data[quality_column]

    if keep_above:
        keep_mask = quality_series >= threshold
    else:
        keep_mask = quality_series <= threshold

    clean_data = data[keep_mask]
    removed_indices = data.index[~keep_mask]
    removed_count = int((~keep_mask).sum())

    return FilterResult(
        data=clean_data,
        removed_count=removed_count,
        removed_indices=removed_indices,
        original_count=original_count,
    )


def filter_dataframe(
    df: pd.DataFrame,
    config: SignalFilterConfig,
    *,
    value_columns: Sequence[str] | None = None,
    timestamp_column: str | None = None,
    quality_column: str | None = None,
) -> FilterResult:
    """Apply comprehensive filtering to a DataFrame.

    Args:
        df: Input DataFrame
        config: Filter configuration
        value_columns: Columns to filter for invalid/out-of-range values
        timestamp_column: Column to use for duplicate detection
        quality_column: Column containing quality scores

    Returns:
        FilterResult with filtered DataFrame and statistics
    """
    if df.empty:
        return FilterResult(
            data=df.copy(),
            removed_count=0,
            removed_indices=pd.Index([]),
            original_count=0,
        )

    original_count = len(df)
    working = df.copy()
    total_removed = 0
    all_removed_indices: list[Any] = []

    # Filter invalid values in value columns
    if value_columns:
        for col in value_columns:
            if col not in working.columns:
                continue

            invalid_mask = pd.Series(False, index=working.index)

            if config.remove_nan:
                invalid_mask |= working[col].isna()

            if config.remove_inf:
                invalid_mask |= np.isinf(working[col].astype(float))

            if config.min_value is not None:
                invalid_mask |= working[col] < config.min_value

            if config.max_value is not None:
                invalid_mask |= working[col] > config.max_value

            if invalid_mask.any():
                all_removed_indices.extend(working.index[invalid_mask].tolist())
                working = working[~invalid_mask]

    # Filter duplicates
    if config.remove_duplicates and timestamp_column and timestamp_column in working.columns:
        dup_result = filter_duplicates(working, subset=timestamp_column, keep="first")
        working = dup_result.data  # type: ignore[assignment]
        all_removed_indices.extend(dup_result.removed_indices.tolist())

    # Filter by z-score
    if config.zscore_threshold is not None and value_columns:
        for col in value_columns:
            if col not in working.columns or working.empty:
                continue

            values = working[col].to_numpy()
            zscore_result = filter_outliers_zscore(
                values,
                threshold=config.zscore_threshold,
                window=config.zscore_window,
                strategy=FilterStrategy.REPLACE_NAN,
            )

            if zscore_result.removed_count > 0:
                # Mark outlier rows
                outlier_indices = working.index[zscore_result.removed_indices]
                all_removed_indices.extend(outlier_indices.tolist())
                working = working.drop(outlier_indices, errors="ignore")

    # Filter by quality
    if config.quality_threshold is not None and quality_column and quality_column in working.columns:
        quality_result = filter_by_quality(
            working,
            quality_column,
            threshold=config.quality_threshold,
            keep_above=True,
        )
        working = quality_result.data  # type: ignore[assignment]
        all_removed_indices.extend(quality_result.removed_indices.tolist())

    total_removed = original_count - len(working)
    unique_removed = list(set(all_removed_indices))

    return FilterResult(
        data=working,
        removed_count=total_removed,
        removed_indices=pd.Index(unique_removed),
        original_count=original_count,
    )


def filter_signals(
    signals: NDArray[np.floating[Any]] | Sequence[float] | pd.Series,
    config: SignalFilterConfig | None = None,
) -> FilterResult:
    """Comprehensive signal filtering pipeline.

    Applies multiple filtering steps in sequence:
    1. Remove invalid values (NaN, Inf)
    2. Remove out-of-range values
    3. Remove outliers (if z-score threshold configured)

    Args:
        signals: Input signal array
        config: Filter configuration (uses defaults if None)

    Returns:
        FilterResult with filtered signals and statistics

    Example:
        >>> signals = np.array([1.0, np.nan, 2.0, 100.0, 3.0, np.inf])
        >>> config = SignalFilterConfig(min_value=0.0, max_value=10.0)
        >>> result = filter_signals(signals, config)
        >>> print(result.data)  # [1.0, 2.0, 3.0]
    """
    if config is None:
        config = SignalFilterConfig()

    # Convert to numpy array
    if isinstance(signals, pd.Series):
        arr = signals.to_numpy()
    else:
        arr = np.asarray(signals, dtype=np.float64)

    original_count = arr.size

    # Track which indices from the original array are removed
    # Use a boolean mask for accurate tracking
    removed_mask = np.zeros(original_count, dtype=bool)

    # For non-REMOVE strategies, we modify in place
    working = arr.copy()

    # Step 1: Filter invalid values
    invalid_result = filter_invalid_values(
        working,
        remove_nan=config.remove_nan,
        remove_inf=config.remove_inf,
        strategy=config.strategy,
    )

    if config.strategy == FilterStrategy.REMOVE:
        # Mark removed indices in original array
        removed_mask[invalid_result.removed_indices] = True
        # Create mapping from current to original indices
        current_to_original = np.where(~removed_mask)[0]
        working = invalid_result.data
    else:
        working = invalid_result.data

    # Step 2: Filter by range
    if config.min_value is not None or config.max_value is not None:
        range_result = filter_by_range(
            working,
            min_value=config.min_value,
            max_value=config.max_value,
            strategy=config.strategy,
        )

        if config.strategy == FilterStrategy.REMOVE:
            # Map back to original indices and mark as removed
            original_indices = current_to_original[range_result.removed_indices]
            removed_mask[original_indices] = True
            # Update mapping
            current_to_original = np.where(~removed_mask)[0]
            working = range_result.data
        else:
            working = range_result.data

    # Step 3: Filter outliers by z-score
    if config.zscore_threshold is not None:
        zscore_result = filter_outliers_zscore(
            working,
            threshold=config.zscore_threshold,
            window=config.zscore_window,
            strategy=config.strategy,
        )

        if config.strategy == FilterStrategy.REMOVE:
            if zscore_result.removed_count > 0:
                # Map back to original indices and mark as removed
                original_indices = current_to_original[zscore_result.removed_indices]
                removed_mask[original_indices] = True
            working = zscore_result.data
        else:
            working = zscore_result.data

    # Get all removed indices
    all_removed_indices = np.where(removed_mask)[0]

    return FilterResult(
        data=working,
        removed_count=int(removed_mask.sum()) if config.strategy == FilterStrategy.REMOVE else int(removed_mask.sum()),
        removed_indices=all_removed_indices,
        original_count=original_count,
    )
