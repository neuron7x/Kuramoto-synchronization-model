"""Standardized degradation handling for HydroBrain v2 inference."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


def _default_fallback_payload() -> dict[str, Any]:
    return {
        "degraded": True,
        "flood_prob": [0.0, 0.0, 1.0],
        "hydrology": [],
        "water_quality": [],
        "sensor_anomaly_z": 0.0,
        "compliance": {"overall_compliance": False},
        "alerts": [
            {
                "type": "DEGRADED",
                "level": "HIGH",
                "message": "Inference degraded; fail-safe defaults applied",
            }
        ],
    }


@dataclass(frozen=True, slots=True)
class DegradationPolicy:
    """Policy for inference timeout + fallback behavior."""

    timeout_s: float | None = 0.5
    fallback_payload: Mapping[str, Any] = field(default_factory=_default_fallback_payload)


@dataclass(frozen=True, slots=True)
class DegradationReport:
    """Telemetry describing a degraded inference path."""

    degraded: bool
    reason: str
    elapsed_ms: float
    timeout_s: float | None


def apply_degradation(
    func: Callable[..., Mapping[str, Any]],
    *args: Any,
    policy: DegradationPolicy | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], DegradationReport]:
    """Run an inference callable with timeout + fallback handling."""

    active_policy = policy or DegradationPolicy()
    start = time.monotonic()
    timeout_s = active_policy.timeout_s

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func, *args, **kwargs)
            result = (
                future.result(timeout=timeout_s)
                if timeout_s and timeout_s > 0
                else future.result()
            )
        elapsed_ms = (time.monotonic() - start) * 1000.0
        return dict(result), DegradationReport(
            degraded=False,
            reason="ok",
            elapsed_ms=elapsed_ms,
            timeout_s=timeout_s,
        )
    except FuturesTimeoutError:
        elapsed_ms = (time.monotonic() - start) * 1000.0
        payload = dict(active_policy.fallback_payload)
        payload.update({"degraded": True, "degradation_reason": "timeout"})
        return payload, DegradationReport(
            degraded=True,
            reason="timeout",
            elapsed_ms=elapsed_ms,
            timeout_s=timeout_s,
        )
    except Exception:
        elapsed_ms = (time.monotonic() - start) * 1000.0
        payload = dict(active_policy.fallback_payload)
        payload.update({"degraded": True, "degradation_reason": "error"})
        return payload, DegradationReport(
            degraded=True,
            reason="error",
            elapsed_ms=elapsed_ms,
            timeout_s=timeout_s,
        )


__all__ = ["DegradationPolicy", "DegradationReport", "apply_degradation"]
