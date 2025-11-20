# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
# abstract ports (interfaces)
from typing import Protocol


class SumPort(Protocol):
    def sum(self, a: int, b: int) -> int:
        ...
