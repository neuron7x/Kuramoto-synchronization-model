# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from __future__ import annotations

import collections
from typing import Deque


class RollingBuffer:
    def __init__(self, size: int) -> None:
        self.size = size
        self.buf: Deque[float] = collections.deque(maxlen=size)

    def push(self, v: float) -> None:
        self.buf.append(v)

    def values(self) -> list[float]:
        return list(self.buf)
