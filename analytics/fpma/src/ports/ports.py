# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Port definitions (interfaces) for FPM-A hexagonal architecture.

This module defines abstract interfaces (ports) that establish contracts between
FPM-A core logic and external adapters. Using Python's Protocol typing, ports
enable structural subtyping without explicit inheritance.

Ports represent the boundaries of the FPM-A domain. Core business logic depends
only on these abstractions, never on concrete implementations. This design
supports testing, modularity, and infrastructure flexibility.

Current ports:
    SumPort: Basic arithmetic interface (placeholder)

Planned ports:
    - DataRetrievalPort: Market data access
    - RiskModelPort: Risk computation interface
    - OptimizationPort: Portfolio optimization solver
    - PersistencePort: State storage and retrieval
"""
# abstract ports (interfaces)
from typing import Protocol


class SumPort(Protocol):
    def sum(self, a: int, b: int) -> int:
        ...
