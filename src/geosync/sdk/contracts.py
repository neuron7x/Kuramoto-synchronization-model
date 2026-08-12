# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Public data contracts for the GeoSync SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping
from uuid import uuid4

import numpy as np
import pandas as pd

from domain import Order, Signal


def _uuid_hex_factory() -> Callable[[], str]:
    """Return a callable that generates random hexadecimal identifiers."""

    return lambda: uuid4().hex


__all__ = [
    "MarketState",
    "SuggestedOrder",
    "RiskCheckResult",
    "ExecutionResult",
    "AuditEvent",
    "SDKConfig",
]


@dataclass(slots=True)
class MarketState:
    """Container describing the observable market environment."""

    symbol: str
    venue: str
    market_frame: pd.DataFrame
    strategy: Callable[[np.ndarray], np.ndarray] | None = None


@dataclass(slots=True)
class SuggestedOrder:
    """Order proposal produced by :meth:`GeoSyncSDK.propose_trade`."""

    order: Order
    session_id: str
    venue: str
    rationale: str | None = None


@dataclass(slots=True)
class RiskCheckResult:
    """Outcome of :meth:`GeoSyncSDK.risk_check`."""

    approved: bool
    reason: str | None
    session_id: str


@dataclass(slots=True)
class ExecutionResult:
    """Result of :meth:`GeoSyncSDK.execute`."""

    session_id: str
    order: Order
    correlation_id: str
    venue: str


@dataclass(slots=True)
class AuditEvent:
    """Structured audit trail entry emitted by the SDK."""

    session_id: str
    event: str
    timestamp: datetime
    payload: Mapping[str, object]


@dataclass(slots=True)
class SDKConfig:
    """Runtime configuration for :class:`GeoSyncSDK`."""

    default_venue: str
    signal_strategy: Callable[[np.ndarray], np.ndarray]
    position_sizer: Callable[[Signal], float]
    venue_overrides: Mapping[str, str] = field(default_factory=dict)
    correlation_id_factory: Callable[[], str] = field(default_factory=_uuid_hex_factory)
    session_id_factory: Callable[[], str] = field(default_factory=_uuid_hex_factory)

    def __post_init__(self) -> None:  # pragma: no cover - defensive defaults
        if not callable(self.correlation_id_factory):
            self.correlation_id_factory = _uuid_hex_factory()
        if not callable(self.session_id_factory):
            self.session_id_factory = _uuid_hex_factory()


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(timezone.utc)
