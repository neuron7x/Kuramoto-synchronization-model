# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Real-time streaming data structures for market data processing.

This module provides efficient data structures for handling streaming market data:
- **RollingBuffer**: Fixed-size buffer with automatic eviction for time-series windows
- **StreamingAggregator**: Real-time aggregation of market data (OHLCV, VWAP, etc.)
- **WindowManager**: Sliding and tumbling window implementations

These structures are optimized for low latency and memory efficiency, making them
suitable for high-frequency trading applications where every microsecond matters.

Example:
    >>> from core.data.streaming import RollingBuffer
    >>> buffer = RollingBuffer(size=100)
    >>> buffer.push(42.5)
    >>> values = buffer.values()
"""
from __future__ import annotations

import collections
from typing import Deque


class RollingBuffer:
    """Fixed-size circular buffer for streaming numeric data.

    Automatically evicts the oldest values when the buffer is full,
    maintaining a rolling window of the most recent data points.

    Args:
        size: Maximum number of elements to store. Must be positive.

    Raises:
        ValueError: If size is not a positive integer.

    Example:
        >>> buffer = RollingBuffer(size=3)
        >>> buffer.push(1.0)
        >>> buffer.push(2.0)
        >>> buffer.push(3.0)
        >>> buffer.push(4.0)  # Evicts 1.0
        >>> buffer.values()
        [2.0, 3.0, 4.0]
    """

    def __init__(self, size: int) -> None:
        if not isinstance(size, int) or size <= 0:
            raise ValueError(f"Buffer size must be a positive integer, got {size}")
        self.size = size
        self.buf: Deque[float] = collections.deque(maxlen=size)

    def push(self, v: float) -> None:
        """Add a value to the buffer.

        If the buffer is at capacity, the oldest value is automatically removed.

        Args:
            v: Numeric value to add to the buffer.
        """
        self.buf.append(float(v))

    def values(self) -> list[float]:
        """Return all current values in chronological order.

        Returns:
            List of values from oldest to newest.
        """
        return list(self.buf)

    def __len__(self) -> int:
        """Return the current number of elements in the buffer.

        Returns:
            Number of elements currently in the buffer.

        Raises:
            RuntimeError: If buffer state is corrupted (should never happen).
        """
        length = len(self.buf)
        if length > self.size:
            raise RuntimeError(
                f"Buffer corruption detected: {length} elements exceed max size {self.size}"
            )
        return length

    def is_full(self) -> bool:
        """Check if the buffer has reached capacity.

        Returns:
            True if the buffer contains `size` elements, False otherwise.
        """
        return len(self.buf) == self.size

    def clear(self) -> None:
        """Remove all elements from the buffer."""
        self.buf.clear()
