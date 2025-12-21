# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Unified Data Access API for TradePulse strategies.

This module provides the single entry point for accessing market data
in TradePulse. All strategies, backtests, and live trading systems
should use this API instead of directly reading files or raw data sources.

**Key Functions**

- ``get_historical_window``: Retrieve historical bars for a symbol/timeframe
- ``get_latest_snapshot``: Get current market state for a symbol
- ``get_feature_window``: Retrieve computed features for a time window
- ``load_historical_bars``: Load bars from various sources (CSV, API, etc.)

**Design Principles**

1. Strategies never touch raw files - only normalized data through this API
2. All data is validated before being returned
3. Consistent interface for both backtest and live trading
4. Automatic timezone normalization (everything is UTC)

Example:
    >>> from tradepulse.data.api import get_historical_window, load_historical_bars
    >>>
    >>> # Load historical data from CSV
    >>> bars = load_historical_bars("data/btcusdt_1m.csv", symbol="BTCUSDT")
    >>>
    >>> # Get a time window
    >>> window = get_historical_window(
    ...     bars,
    ...     symbol="BTCUSDT",
    ...     timeframe=Timeframe.M1,
    ...     start=datetime(2024, 1, 1, tzinfo=timezone.utc),
    ...     end=datetime(2024, 1, 2, tzinfo=timezone.utc),
    ... )
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import (
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Union,
)

import pandas as pd

from .schema import Bar, FeatureVector, MarketSnapshot, Timeframe

__all__ = [
    "DataSource",
    "DataSourceConfig",
    "get_feature_window",
    "get_historical_window",
    "get_latest_snapshot",
    "load_historical_bars",
    "normalize_bars",
]

logger = logging.getLogger(__name__)


class DataSourceConfig:
    """Configuration for a data source.

    Attributes:
        source_type: Type of source ("csv", "parquet", "api", "memory")
        path: File path for file-based sources
        symbol: Symbol to load (optional, can be in data)
        timeframe: Expected timeframe of the data
        timestamp_column: Name of timestamp column
        ohlcv_columns: Mapping of OHLCV column names
        timezone: Source timezone (data will be converted to UTC)
        skip_validation: Whether to skip quality validation
    """

    def __init__(
        self,
        source_type: str = "csv",
        path: Optional[Union[str, Path]] = None,
        symbol: Optional[str] = None,
        timeframe: Optional[Timeframe] = None,
        timestamp_column: str = "timestamp",
        ohlcv_columns: Optional[Dict[str, str]] = None,
        source_timezone: str = "UTC",
        skip_validation: bool = False,
    ):
        self.source_type = source_type
        self.path = Path(path) if path else None
        self.symbol = symbol
        self.timeframe = timeframe
        self.timestamp_column = timestamp_column
        self.ohlcv_columns = ohlcv_columns or {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
        self.source_timezone = source_timezone
        self.skip_validation = skip_validation


class DataSource(Protocol):
    """Protocol for data sources.

    Custom data sources should implement this protocol.
    """

    def load_bars(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> List[Bar]:
        """Load bars from the data source."""
        ...

    def get_latest_snapshot(self, symbol: str) -> Optional[MarketSnapshot]:
        """Get the latest market snapshot for a symbol."""
        ...


def _parse_timestamp(value: str, tz_name: str = "UTC") -> datetime:
    """Parse timestamp string to UTC datetime."""
    try:
        # Try ISO format first
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        # Try common formats
        for fmt in [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y/%m/%d %H:%M:%S",
        ]:
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            # Try epoch seconds/milliseconds
            try:
                ts_float = float(value)
                if ts_float > 1e12:  # Likely milliseconds
                    ts_float = ts_float / 1000
                dt = datetime.fromtimestamp(ts_float, tz=timezone.utc)
                return dt
            except (ValueError, OSError):
                raise ValueError(f"Unable to parse timestamp: {value}")

    # Handle timezone
    if dt.tzinfo is None:
        # Assume source timezone
        try:
            from zoneinfo import ZoneInfo

            dt = dt.replace(tzinfo=ZoneInfo(tz_name))
        except ImportError:
            # Fallback to UTC
            dt = dt.replace(tzinfo=timezone.utc)

    # Convert to UTC
    return dt.astimezone(timezone.utc)


def _load_csv_bars(
    path: Path,
    config: DataSourceConfig,
) -> List[Bar]:
    """Load bars from a CSV file."""
    bars: List[Bar] = []

    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    with open(path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Get column names for better error messages
        ohlcv = config.ohlcv_columns
        ts_col = config.timestamp_column
        open_col = ohlcv.get("open", "open")
        high_col = ohlcv.get("high", "high")
        low_col = ohlcv.get("low", "low")
        close_col = ohlcv.get("close", "close")
        volume_col = ohlcv.get("volume", "volume")

        for row_num, row in enumerate(reader, start=2):
            try:
                # Parse timestamp
                ts_str = row.get(ts_col, "")
                if not ts_str:
                    logger.warning(
                        f"Row {row_num}: Missing timestamp column '{ts_col}'. "
                        f"Available columns: {list(row.keys())}. Skipping row."
                    )
                    continue

                timestamp = _parse_timestamp(ts_str, config.source_timezone)

                # Get OHLCV values with validation
                open_val = row.get(open_col, "")
                high_val = row.get(high_col, "")
                low_val = row.get(low_col, "")
                close_val = row.get(close_col, "")
                volume_val = row.get(volume_col, "0")

                # Check for missing required values
                if not all([open_val, high_val, low_val, close_val]):
                    missing = [
                        name
                        for name, val in [
                            (open_col, open_val),
                            (high_col, high_val),
                            (low_col, low_val),
                            (close_col, close_val),
                        ]
                        if not val
                    ]
                    logger.warning(
                        f"Row {row_num}: Missing OHLC columns: {missing}. "
                        f"Expected columns: open='{open_col}', high='{high_col}', "
                        f"low='{low_col}', close='{close_col}'. Skipping row."
                    )
                    continue

                # Determine symbol
                symbol = config.symbol
                if not symbol:
                    symbol = row.get("symbol", "UNKNOWN")

                # Determine timeframe
                timeframe = config.timeframe
                if not timeframe:
                    timeframe = Timeframe.M1  # Default

                bar = Bar(
                    timestamp=timestamp,
                    symbol=symbol,
                    timeframe=timeframe,
                    open=Decimal(open_val),
                    high=Decimal(high_val),
                    low=Decimal(low_val),
                    close=Decimal(close_val),
                    volume=Decimal(volume_val) if volume_val else Decimal("0"),
                )
                bars.append(bar)

            except (ValueError, KeyError) as e:
                logger.warning(
                    f"Row {row_num}: Error parsing row - {type(e).__name__}: {e}. "
                    f"Row data: {dict(row)}. Skipping row."
                )
                continue

    return bars


def _load_parquet_bars(path: Path, config: DataSourceConfig) -> List[Bar]:
    """Load bars from a Parquet file."""
    if not path.exists():
        raise FileNotFoundError(f"Parquet file not found: {path}")

    df = pd.read_parquet(path)
    ohlcv = config.ohlcv_columns
    ts_col = config.timestamp_column
    open_col = ohlcv.get("open", "open")
    high_col = ohlcv.get("high", "high")
    low_col = ohlcv.get("low", "low")
    close_col = ohlcv.get("close", "close")
    volume_col = ohlcv.get("volume", "volume")

    bars: List[Bar] = []
    for row_num, (_, row) in enumerate(df.iterrows(), start=2):
        try:
            ts_val = row.get(ts_col, "")
            if ts_val in (None, ""):
                logger.warning(
                    f"Row {row_num}: Missing timestamp column '{ts_col}'. "
                    f"Available columns: {list(df.columns)}. Skipping row."
                )
                continue

            timestamp = _parse_timestamp(ts_val, config.source_timezone)

            open_val = row.get(open_col, "")
            high_val = row.get(high_col, "")
            low_val = row.get(low_col, "")
            close_val = row.get(close_col, "")
            volume_val = row.get(volume_col, "0")

            def _is_missing(value: object) -> bool:
                return value is None or value == "" or pd.isna(value)

            if any(_is_missing(val) for val in [open_val, high_val, low_val, close_val]):
                missing = [
                    name
                    for name, val in (
                        (open_col, open_val),
                        (high_col, high_val),
                        (low_col, low_val),
                        (close_col, close_val),
                    )
                    if _is_missing(val)
                ]
                logger.warning(
                    f"Row {row_num}: Missing OHLC columns: {missing}. "
                    f"Expected columns: open='{open_col}', high='{high_col}', "
                    f"low='{low_col}', close='{close_col}'. Skipping row."
                )
                continue

            symbol = config.symbol or row.get("symbol", "UNKNOWN")
            timeframe = config.timeframe or Timeframe.M1

            bars.append(
                Bar(
                    timestamp=timestamp,
                    symbol=symbol,
                    timeframe=timeframe,
                    open=Decimal(str(open_val)),
                    high=Decimal(str(high_val)),
                    low=Decimal(str(low_val)),
                    close=Decimal(str(close_val)),
                    volume=Decimal(str(volume_val)) if volume_val else Decimal("0"),
                )
            )
        except (ValueError, KeyError) as exc:
            logger.warning(
                f"Row {row_num}: Error parsing row - {type(exc).__name__}: {exc}. "
                f"Row data: {row}. Skipping row."
            )
            continue

    return bars


def normalize_bars(
    bars: Sequence[Bar],
    *,
    sort_by_time: bool = True,
    remove_duplicates: bool = True,
    fill_gaps: bool = False,
) -> List[Bar]:
    """Normalize a sequence of bars.

    Args:
        bars: Input bars to normalize
        sort_by_time: Whether to sort bars by timestamp
        remove_duplicates: Whether to remove duplicate timestamps (keeps first)
        fill_gaps: Whether to fill gaps with interpolated bars (not implemented)

    Returns:
        Normalized list of bars
    """
    if not bars:
        return []

    result = list(bars)

    # Sort by timestamp
    if sort_by_time:
        result.sort(key=lambda b: b.timestamp)

    # Remove duplicates
    if remove_duplicates:
        seen_timestamps: set[datetime] = set()
        unique_bars: List[Bar] = []
        for bar in result:
            if bar.timestamp not in seen_timestamps:
                seen_timestamps.add(bar.timestamp)
                unique_bars.append(bar)
        result = unique_bars

    # Gap filling is not implemented yet
    if fill_gaps:
        logger.warning("Gap filling is not yet implemented")

    return result


def load_historical_bars(
    source: Union[str, Path, DataSourceConfig],
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[Timeframe] = None,
    validate: bool = True,
    normalize: bool = True,
) -> List[Bar]:
    """Load historical bars from a data source.

    This is the primary entry point for loading historical data.
    It handles CSV files, parquet files (future), and API sources (future).

    Args:
        source: Path to data file or DataSourceConfig
        symbol: Symbol name (overrides config if provided)
        timeframe: Timeframe (overrides config if provided)
        validate: Whether to validate data quality
        normalize: Whether to normalize (sort, dedupe) the bars

    Returns:
        List of validated, normalized Bar objects

    Raises:
        FileNotFoundError: If file source doesn't exist
        ValueError: If data format is invalid
        DataQualityError: If validation fails (when validate=True)

    Example:
        >>> bars = load_historical_bars(
        ...     "data/btcusdt_1m.csv",
        ...     symbol="BTCUSDT",
        ...     timeframe=Timeframe.M1,
        ... )
        >>> print(f"Loaded {len(bars)} bars")
    """
    # Create config if path provided
    if isinstance(source, (str, Path)):
        path = Path(source)
        config = DataSourceConfig(
            source_type="csv" if path.suffix.lower() == ".csv" else "parquet",
            path=path,
            symbol=symbol,
            timeframe=timeframe,
        )
    else:
        config = source
        if symbol:
            config.symbol = symbol
        if timeframe:
            config.timeframe = timeframe

    # Load based on source type
    if config.source_type == "csv" and config.path:
        bars = _load_csv_bars(config.path, config)
    elif config.source_type == "parquet" and config.path:
        bars = _load_parquet_bars(config.path, config)
    else:
        raise ValueError(f"Unknown source type: {config.source_type}")

    # Normalize
    if normalize:
        bars = normalize_bars(bars, sort_by_time=True, remove_duplicates=True)

    # Validate
    if validate and not config.skip_validation:
        from .quality import require_valid_data

        require_valid_data(bars, allow_warnings=True)

    logger.info(f"Loaded {len(bars)} bars from {config.path or config.source_type}")
    return bars


def get_historical_window(
    bars: Sequence[Bar],
    *,
    symbol: Optional[str] = None,
    timeframe: Optional[Timeframe] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> List[Bar]:
    """Get a time window of historical bars.

    Args:
        bars: Source bars to filter
        symbol: Filter by symbol (optional)
        timeframe: Filter by timeframe (optional)
        start: Window start time (inclusive)
        end: Window end time (inclusive)

    Returns:
        Filtered and sorted list of bars within the window

    Example:
        >>> window = get_historical_window(
        ...     all_bars,
        ...     symbol="BTCUSDT",
        ...     start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ...     end=datetime(2024, 1, 31, tzinfo=timezone.utc),
        ... )
    """
    result: List[Bar] = []

    for bar in bars:
        # Filter by symbol
        if symbol and bar.symbol != symbol.upper():
            continue

        # Filter by timeframe
        if timeframe and bar.timeframe != timeframe:
            continue

        # Filter by time range
        if start and bar.timestamp < start:
            continue
        if end and bar.timestamp > end:
            continue

        result.append(bar)

    # Sort by timestamp
    result.sort(key=lambda b: b.timestamp)

    return result


def get_latest_snapshot(
    bars: Sequence[Bar],
    symbol: str,
    *,
    include_bar: bool = True,
) -> Optional[MarketSnapshot]:
    """Get the latest market snapshot for a symbol.

    Args:
        bars: Source bars
        symbol: Symbol to get snapshot for
        include_bar: Whether to include the last bar in snapshot

    Returns:
        MarketSnapshot with latest data, or None if no bars found
    """
    symbol = symbol.upper()

    # Find latest bar for symbol
    latest_bar: Optional[Bar] = None
    for bar in bars:
        if bar.symbol == symbol:
            if latest_bar is None or bar.timestamp > latest_bar.timestamp:
                latest_bar = bar

    if latest_bar is None:
        return None

    return MarketSnapshot(
        timestamp=latest_bar.timestamp,
        symbol=symbol,
        last_price=latest_bar.close,
        last_bar=latest_bar if include_bar else None,
    )


def get_feature_window(
    features: Sequence[FeatureVector],
    *,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    feature_names: Optional[Sequence[str]] = None,
) -> List[FeatureVector]:
    """Get a time window of feature vectors.

    Args:
        features: Source feature vectors
        symbol: Filter by symbol (optional)
        start: Window start time (inclusive)
        end: Window end time (inclusive)
        feature_names: Only include these features (optional)

    Returns:
        Filtered and sorted list of feature vectors
    """
    result: List[FeatureVector] = []

    for fv in features:
        # Filter by symbol
        if symbol and fv.symbol != symbol.upper():
            continue

        # Filter by time range
        if start and fv.timestamp < start:
            continue
        if end and fv.timestamp > end:
            continue

        # Filter features if specified
        if feature_names:
            filtered_features = {
                k: v for k, v in fv.features.items() if k in feature_names
            }
            # Create new FeatureVector with filtered features
            fv = FeatureVector(
                timestamp=fv.timestamp,
                symbol=fv.symbol,
                features=filtered_features,
                metadata=fv.metadata,
            )

        result.append(fv)

    # Sort by timestamp
    result.sort(key=lambda f: f.timestamp)

    return result
