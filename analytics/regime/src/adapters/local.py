# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Local adapter implementations for regime detection ports.

This module provides concrete implementations of regime detection port interfaces
for local (in-process) execution. The hexagonal architecture enables clean
separation between regime classification logic and infrastructure details.

Current implementations:
    LocalSum: Basic placeholder adapter

Planned adapters:
    - LocalRegimeClassifier: In-memory regime detection
    - CachedRegimeAdapter: Cached classification results
    - DistributedRegimeAdapter: Multi-node regime computation

The regime detection system will classify market states across multiple dimensions
including volatility, trend strength, and correlation structure to inform
adaptive portfolio management decisions.
"""
# concrete adapter for SumPort
from src.ports.ports import SumPort


class LocalSum(SumPort):
    def sum(self, a: int, b: int) -> int:
        return a + b
