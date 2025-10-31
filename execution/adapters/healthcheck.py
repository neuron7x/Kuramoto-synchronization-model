# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Utilities supporting exchange connector health checks.

The module provides a small set of primitives shared between individual
exchange adapters.  It is intentionally lightweight to keep health checks
purely functional and easily testable.  Exchange specific self-tests can rely
on :class:`HealthCheckOverrides` to inject deterministic transports during unit
tests while production code falls back to the real HTTP/WebSocket clients.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from dataclasses import dataclass
from typing import (Any, Awaitable, Callable, Dict, Iterable, Iterator, Mapping,
                    MutableMapping, Optional, Tuple)

import httpx

from execution.health import (
    ConnectorHealth,
    HealthCheck,
    HealthStatus,
    health_status_from_checks,
)

__all__ = [
    "ConnectorHealth",
    "HealthCheck",
    "HealthStatus",
    "HealthCheckOverrides",
    "diagnostic_from_health",
    "get_overrides",
    "override_healthcheck",
    "probe_websocket_stream",
]

def _map_health_to_check_status(status: HealthStatus) -> str:
    if status is HealthStatus.OK:
        return "passed"
    if status is HealthStatus.FAIL:
        return "failed"
    return "warn"


def diagnostic_from_health(
    adapter_id: str,
    health: ConnectorHealth,
    *,
    adapter_check_cls: Callable[[str, str, Optional[str]], Any],
    adapter_diag_cls: Callable[..., Any],
) -> Any:
    """Convert :class:`ConnectorHealth` into :class:`AdapterDiagnostic`.

    ``adapter_check_cls`` and ``adapter_diag_cls`` are injected to decouple the
    helper from the adapters plugin module and avoid circular imports.
    """

    checks = [
        adapter_check_cls(
            name=check.name,
            status=_map_health_to_check_status(check.status),
            detail=check.detail,
        )
        for check in health.checks
    ]
    metadata = dict(health.metadata)
    metadata.setdefault("status", health.status.value)
    metadata.setdefault(
        "checks",
        [
            {
                "name": check.name,
                "status": check.status.value,
                **({"latency_ms": check.latency_ms} if check.latency_ms is not None else {}),
            }
            for check in health.checks
        ],
    )
    return adapter_diag_cls(adapter_id=adapter_id, checks=tuple(checks), metadata=metadata)


@dataclass(slots=True)
class HealthCheckOverrides:
    """Overrides used to stub network probes during unit tests."""

    http_client_factory: Callable[[], httpx.Client] | None = None
    websocket_probe: Callable[[str, int, float], Awaitable[Tuple[list[str], list[float]]]] | None = None


_OVERRIDES: MutableMapping[str, HealthCheckOverrides] = {}


def get_overrides(adapter_id: str) -> HealthCheckOverrides | None:
    """Return overrides registered for ``adapter_id`` if any."""

    return _OVERRIDES.get(adapter_id)


@contextlib.contextmanager
def override_healthcheck(adapter_id: str, overrides: HealthCheckOverrides) -> Iterator[None]:
    """Context manager installing temporary overrides for ``adapter_id``."""

    previous = _OVERRIDES.get(adapter_id)
    _OVERRIDES[adapter_id] = overrides
    try:
        yield
    finally:  # pragma: no cover - trivial branch
        if previous is None:
            _OVERRIDES.pop(adapter_id, None)
        else:
            _OVERRIDES[adapter_id] = previous


async def probe_websocket_stream(
    url: str,
    *,
    message_count: int = 3,
    message_timeout: float = 5.0,
) -> tuple[list[str], list[float]]:
    """Collect a handful of messages from ``url`` for stability assessment."""

    import websockets

    timestamps: list[float] = []
    payloads: list[str] = []
    async with websockets.connect(url, close_timeout=1.0) as websocket:
        for _ in range(message_count):
            start = time.perf_counter()
            raw = await asyncio.wait_for(websocket.recv(), timeout=message_timeout)
            payloads.append(raw)
            timestamps.append(time.perf_counter())
    intervals = [
        (timestamps[idx] - timestamps[idx - 1]) * 1000.0
        for idx in range(1, len(timestamps))
    ]
    return payloads, intervals


def evaluate_price_stability(messages: Iterable[str]) -> HealthStatus:
    """Crude validation that stream payloads include price-like fields."""

    def _has_price(payload: str) -> bool:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return False
        if isinstance(data, Mapping):
            for key in ("price", "p", "c", "last", "close"):
                value = data.get(key)
                if isinstance(value, (int, float)):
                    return True
                if isinstance(value, str):
                    try:
                        float(value)
                    except ValueError:
                        continue
                    else:
                        return True
        return False

    payloads = list(messages)
    if not payloads:
        return HealthStatus.FAIL
    prices = sum(1 for message in payloads if _has_price(message))
    if prices == 0:
        return HealthStatus.FAIL
    if prices < len(payloads):
        return HealthStatus.WARN
    return HealthStatus.OK

