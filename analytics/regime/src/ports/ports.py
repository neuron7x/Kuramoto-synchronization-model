# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Port definitions (interfaces) for regime detection hexagonal architecture.

This module defines abstract interfaces that establish contracts between regime
detection core logic and external adapters. Using Protocol typing for structural
subtyping enables flexible adapter implementations without coupling.

Current ports:
    SumPort: Basic placeholder interface

Planned ports:
    - RegimeClassifierPort: Market regime classification interface
    - FeatureExtractionPort: Extract regime-relevant features
    - TransitionModelPort: Model regime transition dynamics
    - RegimePersistencePort: Store and retrieve regime history

The regime detection framework will support multiple classification schemes
including HMM-based, clustering-based, and neural approaches through these
unified interfaces.
"""
# abstract ports (interfaces)
from typing import Protocol


class SumPort(Protocol):
    def sum(self, a: int, b: int) -> int: ...
