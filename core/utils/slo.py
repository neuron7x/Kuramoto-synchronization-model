# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""SLO guardrails and automated rollback helpers."""

from __future__ import annotations

import logging
import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict, Iterable, Optional

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SLOBurnRateRule:
    """Configuration for evaluating multi-window error-budget burn rates."""

    window: timedelta
    max_burn_rate: float
    min_requests: int | None = None
    name: str | None = None

    def __post_init__(self) -> None:  # pragma: no cover - simple validation
        if self.window <= timedelta(0):
            raise ValueError("window must be a positive duration")
        if self.max_burn_rate <= 0:
            raise ValueError("max_burn_rate must be positive")
        if self.min_requests is not None and self.min_requests < 0:
            raise ValueError("min_requests must be non-negative when provided")

    @property
    def identifier(self) -> str:
        """Return a stable identifier for telemetry keys."""

        if self.name:
            return self.name
        seconds = int(self.window.total_seconds())
        if seconds % 3600 == 0:
            hours = seconds // 3600
            return f"{hours}h"
        if seconds % 60 == 0:
            minutes = seconds // 60
            return f"{minutes}m"
        return f"{seconds}s"


@dataclass(frozen=True)
class SLOConfig:
    """Configuration for evaluating service level objectives.

    Attributes:
        error_rate_threshold: Maximum acceptable error rate expressed as a
            fraction between 0 and 1.
        latency_threshold_ms: Maximum acceptable p95 latency in milliseconds.
        evaluation_period: Sliding window used when evaluating the SLO. Only
            samples newer than ``now - evaluation_period`` are considered.
        min_requests: Minimum amount of samples required before the SLO can be
            evaluated. This avoids triggering on sparse data.
        cooldown: Minimum amount of time that needs to elapse between
            consecutive rollbacks. Prevents flapping when the system is already
            in mitigation mode.
        burn_rate_rules: Optional set of multi-window burn-rate policies used to
            implement error-budget based alerting. Each rule defines an
            independent window and burn-rate ceiling that must not be
            exceeded.
    """

    error_rate_threshold: float = 0.02
    latency_threshold_ms: float = 500.0
    evaluation_period: timedelta = timedelta(minutes=5)
    min_requests: int = 50
    cooldown: timedelta = timedelta(minutes=5)
    burn_rate_rules: tuple[SLOBurnRateRule, ...] = ()


@dataclass
class RequestSample:
    """Individual request sample used for sliding-window evaluations."""

    timestamp: datetime
    latency_ms: float
    success: bool


class AutoRollbackGuard:
    """Evaluate SLO windows and trigger rollback callbacks when breached."""

    def __init__(
        self,
        config: SLOConfig | None = None,
        *,
        rollback_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.config = config or SLOConfig()
        self._rollback_callback = rollback_callback
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._events: Deque[RequestSample] = deque()
        self._last_triggered_at: Optional[datetime] = None
        self._last_summary: Dict[str, Any] | None = None
        self._retention_period = self._compute_retention_period()

    @property
    def last_triggered_at(self) -> Optional[datetime]:
        """Return the timestamp of the last rollback trigger."""

        return self._last_triggered_at

    @property
    def last_summary(self) -> Dict[str, Any] | None:
        """Return the metrics snapshot from the last evaluation."""

        return self._last_summary.copy() if self._last_summary is not None else None

    def record_outcome(
        self,
        latency_ms: float,
        success: bool,
        *,
        timestamp: Optional[datetime] = None,
    ) -> bool:
        """Record an individual request outcome.

        Args:
            latency_ms: Request latency in milliseconds.
            success: ``True`` for successful requests, ``False`` otherwise.
            timestamp: Optional timestamp (defaults to ``datetime.now``).

        Returns:
            ``True`` when a rollback should be triggered as the result of this
            sample, ``False`` otherwise.
        """

        if latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")

        event_time = timestamp or self._clock()
        if event_time.tzinfo is None:
            event_time = event_time.replace(tzinfo=timezone.utc)

        self._events.append(RequestSample(event_time, float(latency_ms), success))
        self._prune(event_time)
        summary = self._summarise_window(event_time)
        if summary is None:
            return False

        reason = self._breach_reason(summary)
        if reason is None:
            burn_reason = self._burn_rate_breach(event_time, summary)
            if burn_reason is None:
                self._last_summary = summary
                return False
            reason = burn_reason

        return self._trigger(reason, summary, event_time)

    def evaluate_snapshot(
        self,
        *,
        error_rate: float,
        latency_p95_ms: float,
        timestamp: Optional[datetime] = None,
        total_requests: Optional[int] = None,
        burn_window_totals: Optional[Dict[timedelta, tuple[int, int]]] = None,
    ) -> bool:
        """Evaluate the SLO guard using pre-aggregated metrics.

        This helper is useful when metrics are sourced from an external system
        such as Prometheus or Datadog and the agent receives aggregated error
        rate and latency data instead of individual request samples. When
        ``burn_window_totals`` are provided, the guard will enforce
        ``burn_rate_rules`` using the supplied ``(total_requests, error_count)``
        tuples for each configured window. Windows omitted from the mapping fall
        back to the internally retained request samples.
        """

        if latency_p95_ms < 0:
            raise ValueError("latency_p95_ms must be non-negative")
        if not 0.0 <= error_rate <= 1.0:
            raise ValueError("error_rate must be between 0 and 1")

        now = timestamp or self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        summary: Dict[str, float] = {
            "error_rate": float(error_rate),
            "latency_p95_ms": float(latency_p95_ms),
            "total_requests": (float(total_requests) if total_requests is not None else math.nan),
            "window_seconds": self.config.evaluation_period.total_seconds(),
            "error_budget": self.config.error_rate_threshold,
        }

        reason = self._breach_reason(summary)
        if reason is None:
            burn_reason = self._burn_rate_breach(
                now,
                summary,
                precomputed_windows=burn_window_totals,
            )
            if burn_reason is None:
                self._last_summary = summary
                return False
            reason = burn_reason

        return self._trigger(reason, summary, now)

    def _breach_reason(self, summary: Dict[str, Any]) -> Optional[str]:
        error_rate = float(summary.get("error_rate", 0.0))
        latency_p95 = float(summary.get("latency_p95_ms", 0.0))
        if error_rate >= self.config.error_rate_threshold:
            return "error_rate"
        if latency_p95 >= self.config.latency_threshold_ms:
            return "latency"
        return None

    def _trigger(self, reason: str, summary: Dict[str, Any], now: datetime) -> bool:
        if self._last_triggered_at is not None:
            elapsed = now - self._last_triggered_at
            if elapsed < self.config.cooldown:
                self._last_summary = summary
                return False

        self._last_triggered_at = now
        enriched_summary: Dict[str, Any] = dict(summary)
        enriched_summary.update(
            {
                "reason": reason,
                "triggered_at": now.timestamp(),
                "cooldown_seconds": self.config.cooldown.total_seconds(),
            }
        )
        self._last_summary = enriched_summary

        _logger.warning(
            "SLO breach detected — initiating rollback",
            extra={
                "reason": reason,
                "error_rate": enriched_summary.get("error_rate"),
                "latency_p95_ms": enriched_summary.get("latency_p95_ms"),
                "total_requests": enriched_summary.get("total_requests"),
            },
        )

        if self._rollback_callback is not None:
            self._rollback_callback(reason, enriched_summary)
        return True

    def _summarise_window(self, now: datetime) -> Optional[Dict[str, Any]]:
        stats_total, stats_errors, latencies = self._aggregate_window(
            now, self.config.evaluation_period, collect_latencies=True
        )
        if stats_total < self.config.min_requests:
            return None

        error_rate = stats_errors / stats_total if stats_total else 0.0
        latency_p95 = _percentile(latencies or [], 95.0)
        return {
            "error_rate": error_rate,
            "latency_p95_ms": latency_p95,
            "total_requests": float(stats_total),
            "window_seconds": self.config.evaluation_period.total_seconds(),
            "error_budget": self.config.error_rate_threshold,
        }

    def _prune(self, now: datetime) -> None:
        cutoff = now - self._retention_period
        while self._events and self._events[0].timestamp < cutoff:
            self._events.popleft()

    def _compute_retention_period(self) -> timedelta:
        retention = self.config.evaluation_period
        if self.config.burn_rate_rules:
            longest = max(rule.window for rule in self.config.burn_rate_rules)
            if longest > retention:
                retention = longest
        return retention

    def _aggregate_window(
        self,
        now: datetime,
        window: timedelta,
        *,
        collect_latencies: bool = False,
    ) -> tuple[int, int, list[float] | None]:
        cutoff = now - window
        total = 0
        errors = 0
        latencies: list[float] | None = [] if collect_latencies else None
        for event in reversed(self._events):
            if event.timestamp < cutoff:
                break
            total += 1
            if not event.success:
                errors += 1
            if latencies is not None:
                latencies.append(event.latency_ms)
        if latencies is not None:
            latencies.reverse()
        return total, errors, latencies

    def _burn_rate_breach(
        self,
        now: datetime,
        summary: Dict[str, Any],
        *,
        precomputed_windows: Optional[Dict[timedelta, tuple[int, int]]] = None,
    ) -> Optional[str]:
        if not self.config.burn_rate_rules:
            return None
        error_budget = self.config.error_rate_threshold
        if error_budget <= 0:
            return None

        for rule in self.config.burn_rate_rules:
            if precomputed_windows and rule.window in precomputed_windows:
                total_raw, errors_raw = precomputed_windows[rule.window]
                total = max(int(total_raw), 0)
                errors = max(int(errors_raw), 0)
                if errors > total:
                    errors = total
            else:
                total, errors, _ = self._aggregate_window(now, rule.window)
            label = rule.identifier
            minimum = (
                rule.min_requests if rule.min_requests is not None else self.config.min_requests
            )
            summary[f"requests[{label}]"] = float(total)
            if total < minimum:
                summary[f"burn_rate[{label}]"] = math.nan
                continue

            burn_rate = (errors / total) / error_budget if total else 0.0
            summary[f"burn_rate[{label}]"] = burn_rate
            if burn_rate >= rule.max_burn_rate:
                summary["burn_rate_window_seconds"] = rule.window.total_seconds()
                summary["burn_rate_threshold"] = rule.max_burn_rate
                summary["reason"] = f"burn_rate[{label}]"
                summary["error_budget"] = error_budget
                return f"burn_rate[{label}]"
        return None


def _percentile(values: Iterable[float], percentile: float) -> float:
    data = sorted(float(v) for v in values)
    if not data:
        return 0.0
    if percentile <= 0:
        return data[0]
    if percentile >= 100:
        return data[-1]

    rank = (percentile / 100) * (len(data) - 1)
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return data[int(rank)]

    fraction = rank - lower
    return data[lower] + (data[upper] - data[lower]) * fraction
