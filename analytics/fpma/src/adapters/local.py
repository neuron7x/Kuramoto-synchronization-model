# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Local adapter implementations for FPM-A ports.

This module provides concrete implementations of FPM-A port interfaces for
local (in-process) execution. Adapters implement the ports defined in the
ports module, enabling dependency inversion and testability.

The hexagonal architecture pattern allows FPM-A core logic to remain independent
of infrastructure details. Alternative adapters could target cloud services,
distributed computing, or external analytics engines without changing core code.

Current implementations:
    LocalSum: Local implementation of SumPort interface

Future adapters may include:
    - Remote computation adapters
    - Cached/memoized versions
    - GPU-accelerated implementations
"""
# concrete adapter for SumPort
from src.ports.ports import SumPort


class LocalSum(SumPort):
    def sum(self, a: int, b: int) -> int:
        return a + b
