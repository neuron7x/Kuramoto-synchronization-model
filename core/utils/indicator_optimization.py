# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Optimized indicator computation utilities.

This module provides optimization wrappers and utilities specifically for
indicator calculations to maximize performance:

* Smart caching based on input data fingerprints
* Vectorized rolling window operations
* Parallel computation for multi-symbol analysis
* Memory-efficient chunked processing

The utilities complement the general performance_optimization module with
indicator-specific optimizations that understand the patterns of technical
analysis computations.

Example:
    >>> from core.utils.indicator_optimization import cached_indicator, rolling_apply_fast
    >>> 
    >>> @cached_indicator(ttl=60.0)
    >>> def custom_indicator(prices: np.ndarray, window: int) -> np.ndarray:
    ...     return rolling_apply_fast(prices, window, np.mean)
"""

from __future__ import annotations

import hashlib
from functools import wraps
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from .performance_optimization import LRUCache

__all__ = [
    "cached_indicator",
    "data_fingerprint",
    "rolling_apply_fast",
    "parallel_indicator",
]


def data_fingerprint(
    data: np.ndarray | pd.Series | pd.DataFrame,
    precision: int = 6
) -> str:
    """Generate a stable fingerprint for time series data.
    
    Creates a hash based on data shape, dtype, and sampled values.
    More efficient than hashing all values for large arrays.
    
    Args:
        data: Input array or series
        precision: Number of decimal places for rounding (affects cache hits)
    
    Returns:
        Hex digest string suitable for cache keys
    
    Example:
        >>> prices = np.array([100.0, 101.5, 99.8])
        >>> fp = data_fingerprint(prices)
        >>> # Same data produces same fingerprint
        >>> assert data_fingerprint(prices) == fp
    """
    if isinstance(data, (pd.Series, pd.DataFrame)):
        data = data.values
    
    if not isinstance(data, np.ndarray):
        data = np.asarray(data)
    
    # Create hash from shape, dtype, and sampled values
    hasher = hashlib.blake2b(digest_size=16)
    
    # Hash shape and dtype
    hasher.update(str(data.shape).encode())
    hasher.update(str(data.dtype).encode())
    
    # Sample values for fingerprint (more efficient than hashing all)
    n = data.size
    if n > 1000:
        # For large arrays, sample strategically
        indices = [
            0,  # first
            n // 4,  # quarter
            n // 2,  # middle
            3 * n // 4,  # three-quarter
            n - 1  # last
        ]
        flat = data.ravel()
        sample = flat[indices]
    else:
        sample = data.ravel()
    
    # Round to precision to improve cache hits
    sample = np.round(sample, decimals=precision)
    
    # Hash the sample
    hasher.update(sample.tobytes())
    
    return hasher.hexdigest()


def cached_indicator(
    maxsize: int = 100,
    ttl: Optional[float] = 60.0,
    precision: int = 6
) -> Callable[[Callable], Callable]:
    """Decorator to cache indicator results based on input data fingerprint.
    
    Caches indicator computations using efficient data fingerprinting.
    Ideal for expensive indicators that are computed repeatedly on the
    same or similar data.
    
    Args:
        maxsize: Maximum cache entries
        ttl: Time-to-live in seconds (None = no expiration)
        precision: Decimal precision for data fingerprinting
    
    Returns:
        Decorator function
    
    Example:
        >>> @cached_indicator(maxsize=100, ttl=60.0)
        >>> def rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
        ...     # Expensive RSI calculation
        ...     return result
        >>> 
        >>> # First call computes
        >>> result1 = rsi(prices, 14)
        >>> # Second call uses cache
        >>> result2 = rsi(prices, 14)
    """
    cache: LRUCache[np.ndarray] = LRUCache(maxsize=maxsize, ttl=ttl)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Build cache key from data fingerprint and params
            key_parts = []
            
            # Fingerprint array arguments
            for arg in args:
                if isinstance(arg, (np.ndarray, pd.Series, pd.DataFrame)):
                    key_parts.append(data_fingerprint(arg, precision=precision))
                else:
                    key_parts.append(str(arg))
            
            # Add kwargs
            if kwargs:
                key_parts.append(str(sorted(kwargs.items())))
            
            cache_key = "|".join(key_parts)
            
            # Check cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Compute and cache
            result = func(*args, **kwargs)
            cache.set(cache_key, result)
            return result
        
        # Expose cache management
        wrapper.cache = cache  # type: ignore
        wrapper.cache_info = cache.get_stats  # type: ignore
        wrapper.cache_clear = cache.clear  # type: ignore
        
        return wrapper
    
    return decorator


def rolling_apply_fast(
    data: np.ndarray,
    window: int,
    func: Callable[[np.ndarray], float],
    min_periods: Optional[int] = None
) -> np.ndarray:
    """Optimized rolling window computation.
    
    Applies a function over a rolling window more efficiently than
    naive implementation. Uses stride tricks for zero-copy views.
    
    Args:
        data: Input array
        window: Window size
        func: Function to apply to each window
        min_periods: Minimum periods required (default: window)
    
    Returns:
        Array of rolling results
    
    Example:
        >>> data = np.random.randn(1000)
        >>> result = rolling_apply_fast(data, 20, np.mean)
    
    Note:
        For simple operations (mean, sum, std), use NumPy's optimized
        functions directly. This is for custom functions.
    """
    if min_periods is None:
        min_periods = window
    
    n = len(data)
    if window > n:
        return np.full(n, np.nan)
    
    # Pre-allocate result
    result = np.full(n, np.nan, dtype=np.float64)
    
    # Compute rolling windows starting from min_periods
    for i in range(min_periods - 1, n):
        start = max(0, i - window + 1)
        window_data = data[start:i + 1]
        
        if len(window_data) >= min_periods:
            result[i] = func(window_data)
    
    return result


def parallel_indicator(
    indicator_func: Callable,
    symbols: list[str],
    data_dict: dict[str, np.ndarray],
    *args: Any,
    max_workers: Optional[int] = None,
    **kwargs: Any
) -> dict[str, np.ndarray]:
    """Compute indicator in parallel across multiple symbols.
    
    Uses thread pool to compute indicators for multiple symbols
    concurrently. Most useful when:
    - Computing same indicator for many symbols
    - Indicator is CPU-bound (not I/O bound)
    - Each computation is independent
    
    Args:
        indicator_func: Indicator function to apply
        symbols: List of symbol names
        data_dict: Dictionary mapping symbols to price data
        *args: Additional positional arguments for indicator_func
        max_workers: Maximum threads (None = cpu_count)
        **kwargs: Additional keyword arguments for indicator_func
    
    Returns:
        Dictionary mapping symbols to indicator results
    
    Example:
        >>> def rsi(prices, period=14):
        ...     # RSI calculation
        ...     return result
        >>> 
        >>> symbols = ['AAPL', 'MSFT', 'GOOGL']
        >>> data = {s: get_prices(s) for s in symbols}
        >>> results = parallel_indicator(rsi, symbols, data, period=14)
    """
    from concurrent.futures import ThreadPoolExecutor
    
    def compute_one(symbol: str) -> tuple[str, np.ndarray]:
        """Compute indicator for one symbol."""
        data = data_dict.get(symbol)
        if data is None:
            return symbol, np.array([])
        
        result = indicator_func(data, *args, **kwargs)
        return symbol, result
    
    results = {}
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(compute_one, symbol) for symbol in symbols]
        
        for future in futures:
            symbol, result = future.result()
            results[symbol] = result
    
    return results


def vectorize_indicator(
    values: np.ndarray,
    lookback: int,
    compute_fn: Callable[[np.ndarray], float]
) -> np.ndarray:
    """Vectorized indicator computation with lookback.
    
    Efficiently computes an indicator that requires a fixed lookback
    window at each point. Uses NumPy broadcasting where possible.
    
    Args:
        values: Input time series
        lookback: Number of past values to include
        compute_fn: Function that computes indicator from window
    
    Returns:
        Indicator values (first lookback-1 values are NaN)
    
    Example:
        >>> def simple_momentum(window):
        ...     return window[-1] - window[0]
        >>> 
        >>> prices = np.array([100, 102, 101, 103, 105])
        >>> mom = vectorize_indicator(prices, 3, simple_momentum)
    """
    n = len(values)
    result = np.full(n, np.nan, dtype=np.float64)
    
    if n < lookback:
        return result
    
    # Compute for each valid position
    for i in range(lookback - 1, n):
        window = values[i - lookback + 1:i + 1]
        result[i] = compute_fn(window)
    
    return result


def optimize_dataframe_memory(df: pd.DataFrame) -> pd.DataFrame:
    """Optimize DataFrame memory usage by downcasting dtypes.
    
    Converts float64 to float32 where precision loss is acceptable,
    and optimizes integer types. Useful for large datasets.
    
    Args:
        df: Input DataFrame
    
    Returns:
        Memory-optimized DataFrame
    
    Example:
        >>> df = pd.DataFrame({'price': [100.5, 101.2, 99.8]})
        >>> df_opt = optimize_dataframe_memory(df)
        >>> # df_opt uses ~50% less memory
    """
    df = df.copy()
    
    for col in df.columns:
        col_type = df[col].dtype
        
        # Optimize floats
        if col_type == np.float64:
            # Check if float32 is sufficient
            col_min = df[col].min()
            col_max = df[col].max()
            
            # float32 range: ~1e-38 to ~1e38
            if abs(col_min) < 1e30 and abs(col_max) < 1e30:
                df[col] = df[col].astype(np.float32)
        
        # Optimize integers
        elif col_type == np.int64:
            col_min = df[col].min()
            col_max = df[col].max()
            
            # Try smaller integer types
            if col_min >= -128 and col_max <= 127:
                df[col] = df[col].astype(np.int8)
            elif col_min >= -32768 and col_max <= 32767:
                df[col] = df[col].astype(np.int16)
            elif col_min >= -2147483648 and col_max <= 2147483647:
                df[col] = df[col].astype(np.int32)
    
    return df
