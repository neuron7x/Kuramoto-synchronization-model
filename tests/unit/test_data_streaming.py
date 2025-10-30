# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

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
