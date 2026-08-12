# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Standardized degradation handling for TACL pre-action gating."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field, replace

from .risk_gating import PreActionDecision, PreActionFilter


@dataclass(frozen=True, slots=True)
class DegradationPolicy:
    """Policy for timeouts and fallback behavior."""

    timeout_s: float | None = 0.05
    fallback_decision: PreActionDecision = field(
        default_factory=lambda: PreActionDecision(
            allowed=False,
            reasons=("degraded",),
            safe_mode=True,
            rollback=True,
            policy_override="conservative",
        )
    )


@dataclass(frozen=True, slots=True)
class DegradationReport:
    """Telemetry describing a degraded execution path."""

    degraded: bool
    reason: str
    elapsed_ms: float
    timeout_s: float | None


def _fallback_with_reason(fallback: PreActionDecision, reason: str) -> PreActionDecision:
    reasons = (reason,) + tuple(r for r in fallback.reasons if r != reason)
    return replace(fallback, reasons=reasons)


def apply_degradation(
    gate: PreActionFilter,
    context: object,
    *,
    policy: DegradationPolicy | None = None,
) -> tuple[PreActionDecision, DegradationReport]:
    """Run the pre-action gate with timeout + fallback handling."""

    active_policy = policy or DegradationPolicy()
    start = time.monotonic()
    timeout_s = active_policy.timeout_s

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(gate.check, context)
            decision = (
                future.result(timeout=timeout_s) if timeout_s and timeout_s > 0 else future.result()
            )
        elapsed_ms = (time.monotonic() - start) * 1000.0
        return decision, DegradationReport(
            degraded=False,
            reason="ok",
            elapsed_ms=elapsed_ms,
            timeout_s=timeout_s,
        )
    except FuturesTimeoutError:
        elapsed_ms = (time.monotonic() - start) * 1000.0
        fallback = _fallback_with_reason(active_policy.fallback_decision, "timeout")
        return fallback, DegradationReport(
            degraded=True,
            reason="timeout",
            elapsed_ms=elapsed_ms,
            timeout_s=timeout_s,
        )
    except Exception:
        elapsed_ms = (time.monotonic() - start) * 1000.0
        fallback = _fallback_with_reason(active_policy.fallback_decision, "error")
        return fallback, DegradationReport(
            degraded=True,
            reason="error",
            elapsed_ms=elapsed_ms,
            timeout_s=timeout_s,
        )


__all__ = ["DegradationPolicy", "DegradationReport", "apply_degradation"]
