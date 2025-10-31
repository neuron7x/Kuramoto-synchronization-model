# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Shared health monitoring primitives used across execution components."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Tuple

__all__ = [
    "HealthStatus",
    "HealthCheck",
    "ConnectorHealth",
    "health_status_from_checks",
]


class HealthStatus(str, Enum):
    """Trinary status conveying whether trading is considered safe."""

    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """Outcome of a single probe executed during venue health verification."""

    name: str
    status: HealthStatus
    detail: str | None = None
    latency_ms: float | None = None
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorHealth:
    """Aggregated health snapshot combining several :class:`HealthCheck`."""

    status: HealthStatus
    checks: Tuple[HealthCheck, ...]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def ok(self) -> bool:
        return self.status is HealthStatus.OK


def health_status_from_checks(checks: Iterable[HealthCheck]) -> HealthStatus:
    """Derive the dominant status from ``checks``."""

    has_warn = False
    for check in checks:
        if check.status is HealthStatus.FAIL:
            return HealthStatus.FAIL
        if check.status is HealthStatus.WARN:
            has_warn = True
    return HealthStatus.WARN if has_warn else HealthStatus.OK

