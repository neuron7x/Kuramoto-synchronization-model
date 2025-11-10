# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import pytest

from core.data.streaming import RollingBuffer


def test_rolling_buffer_retains_last_elements() -> None:
    buf = RollingBuffer(size=3)
    for value in [1.0, 2.0, 3.0, 4.0]:
        buf.push(value)
    assert buf.values() == [2.0, 3.0, 4.0]


def test_rolling_buffer_handles_smaller_sequences() -> None:
    buf = RollingBuffer(size=5)
    buf.push(1.0)
    assert buf.values() == [1.0]


def test_rolling_buffer_invalid_size_raises() -> None:
    """RollingBuffer should reject invalid size parameters."""
    with pytest.raises(ValueError, match="positive integer"):
        RollingBuffer(size=0)
    
    with pytest.raises(ValueError, match="positive integer"):
        RollingBuffer(size=-5)


def test_rolling_buffer_len() -> None:
    """RollingBuffer should track its length correctly."""
    buf = RollingBuffer(size=5)
    assert len(buf) == 0
    
    buf.push(1.0)
    assert len(buf) == 1
    
    buf.push(2.0)
    buf.push(3.0)
    assert len(buf) == 3
    
    # Fill to capacity
    buf.push(4.0)
    buf.push(5.0)
    assert len(buf) == 5
    
    # Adding more should maintain size
    buf.push(6.0)
    assert len(buf) == 5


def test_rolling_buffer_is_full() -> None:
    """is_full should indicate when buffer is at capacity."""
    buf = RollingBuffer(size=3)
    assert not buf.is_full()
    
    buf.push(1.0)
    assert not buf.is_full()
    
    buf.push(2.0)
    assert not buf.is_full()
    
    buf.push(3.0)
    assert buf.is_full()
    
    buf.push(4.0)
    assert buf.is_full()


def test_rolling_buffer_clear() -> None:
    """clear should remove all elements from buffer."""
    buf = RollingBuffer(size=3)
    buf.push(1.0)
    buf.push(2.0)
    buf.push(3.0)
    assert len(buf) == 3
    
    buf.clear()
    assert len(buf) == 0
    assert buf.values() == []
    assert not buf.is_full()


def test_rolling_buffer_type_conversion() -> None:
    """RollingBuffer should convert values to float."""
    buf = RollingBuffer(size=3)
    buf.push(1)  # int
    buf.push(2)  # int
    assert buf.values() == [1.0, 2.0]
