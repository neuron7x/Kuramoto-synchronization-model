"""Cache warm-up orchestration and cold-start safeguards."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter
from typing import Callable, Iterable, Mapping, MutableMapping

from core.utils.metrics import get_metrics_collector

UTC = timezone.utc


def _infer_row_count(payload: object) -> int | None:
    """Best-effort inference of the number of records contained in ``payload``."""

    if payload is None:
        return None

    shape = getattr(payload, "shape", None)
    if isinstance(shape, tuple) and shape:
        try:
            return int(shape[0])
        except (TypeError, ValueError):
            pass

    if isinstance(payload, (list, tuple, set, frozenset, dict)):
        return int(len(payload))

    try:
        length = len(payload)  # type: ignore[arg-type]
    except TypeError:
        return None
    else:
        try:
            return int(length)
        except (TypeError, ValueError):
            return None


def _percentile(samples: Iterable[float], percentile: float) -> float | None:
    """Return the percentile value of ``samples`` using linear interpolation."""

    ordered = sorted(float(value) for value in samples)
    if not ordered:
        return None
    if len(ordered) == 1:
        return float(ordered[0])

    percentile = max(0.0, min(1.0, float(percentile)))
    position = percentile * (len(ordered) - 1)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    lower = ordered[lower_index]
    upper = ordered[upper_index]
    weight = position - lower_index
    return float(lower + (upper - lower) * weight)


CacheWarmupCallable = Callable[[], object]
ReadinessProbe = Callable[[], bool]
Clock = Callable[[], datetime]


@dataclass(slots=True, frozen=True)
class CacheWarmupSpec:
    """Describe how a cache should be primed and monitored."""

    name: str
    warmup: CacheWarmupCallable
    readiness_probe: ReadinessProbe | None = None
    critical: bool = True
    max_cold_requests: int | None = None
    target_hit_rate: float = 0.8
    max_cold_latency_seconds: float | None = None
    description: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Cache warmup spec name must be provided")
        if self.max_cold_requests is not None and self.max_cold_requests < 0:
            raise ValueError("max_cold_requests must be non-negative")
        if not 0.0 < self.target_hit_rate <= 1.0:
            raise ValueError("target_hit_rate must be in the (0.0, 1.0] interval")
        if (
            self.max_cold_latency_seconds is not None
            and self.max_cold_latency_seconds <= 0
        ):
            raise ValueError("max_cold_latency_seconds must be positive when set")


@dataclass(slots=True)
class CacheWarmupResult:
    """Outcome of a warm-up attempt."""

    name: str
    warmed: bool
    warmed_at: datetime
    duration_seconds: float
    rows: int | None = None
    detail: str | None = None
    strategy: str = "manual"
    metadata: Mapping[str, object] | None = None


@dataclass(slots=True)
class CacheUsageStats:
    """Runtime counters tracking cache effectiveness."""

    hits: int = 0
    misses: int = 0
    cold_allowed: int = 0
    cold_blocked: int = 0
    cold_latencies: deque[float] = field(default_factory=lambda: deque(maxlen=128))

    def total_accesses(self) -> int:
        return self.hits + self.misses


@dataclass(slots=True)
class CacheWarmupStatus:
    """Latest state observed for a cache managed by the controller."""

    spec: CacheWarmupSpec
    ready: bool = False
    last_result: CacheWarmupResult | None = None
    last_error: str | None = None
    hit_rate: float = 0.0
    cold_latency_p95: float | None = None
    stats: CacheUsageStats = field(default_factory=CacheUsageStats)
    history: deque[CacheWarmupResult] = field(default_factory=lambda: deque(maxlen=10))
    active_degradations: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "name": self.spec.name,
            "critical": self.spec.critical,
            "ready": self.ready,
            "hit_rate": round(self.hit_rate, 4),
            "cold_latency_p95": self.cold_latency_p95,
            "last_error": self.last_error,
            "cold_requests_allowed": self.stats.cold_allowed,
            "cold_requests_blocked": self.stats.cold_blocked,
            "hits": self.stats.hits,
            "misses": self.stats.misses,
            "active_degradations": tuple(sorted(self.active_degradations)),
        }
        if self.last_result is not None:
            payload.update(
                {
                    "warmed_at": self.last_result.warmed_at,
                    "last_duration_seconds": round(
                        self.last_result.duration_seconds, 4
                    ),
                    "last_rows": self.last_result.rows,
                    "last_strategy": self.last_result.strategy,
                    "last_detail": self.last_result.detail,
                }
            )
        if self.spec.description:
            payload["description"] = self.spec.description
        return payload


class CacheWarmupController:
    """Coordinate cache warm-up, readiness evaluation, and cold-start control."""

    def __init__(
        self,
        specs: Iterable[CacheWarmupSpec],
        *,
        clock: Clock | None = None,
        min_samples_for_hit_rate: int = 10,
    ) -> None:
        unique: dict[str, CacheWarmupSpec] = {}
        for spec in specs:
            if spec.name in unique:
                raise ValueError(f"Duplicate cache spec configured: {spec.name}")
            unique[spec.name] = spec

        if not unique:
            raise ValueError("At least one cache spec must be provided")

        self._specs: Mapping[str, CacheWarmupSpec] = unique
        self._order: tuple[str, ...] = tuple(unique)
        self._clock: Clock = clock or (lambda: datetime.now(UTC))
        self._metrics = get_metrics_collector()
        self._min_samples_for_hit_rate = max(1, int(min_samples_for_hit_rate))
        self._statuses: MutableMapping[str, CacheWarmupStatus] = {
            name: CacheWarmupStatus(spec=spec) for name, spec in self._specs.items()
        }

    # ------------------------------------------------------------------
    # Warm-up orchestration
    def warm_all(self, *, strategy: str = "release") -> list[CacheWarmupResult]:
        """Execute warm-up for every registered cache."""

        return [self.warmup(name, strategy=strategy) for name in self._order]

    def warmup(self, cache_name: str, *, strategy: str = "manual") -> CacheWarmupResult:
        """Execute the warm-up callable associated with ``cache_name``."""

        status = self._get_status(cache_name)
        spec = status.spec
        start = perf_counter()
        warmed = False
        rows: int | None = None
        detail: str | None = None
        metadata: Mapping[str, object] | None = None

        try:
            payload = spec.warmup()
        except Exception as exc:  # pragma: no cover - defensive path
            detail = str(exc)
            payload = None
        else:
            if isinstance(payload, CacheWarmupResult):
                result = payload
                # Ensure the spec name takes precedence for consistency
                warmed = result.warmed
                rows = result.rows
                detail = result.detail
                metadata = result.metadata
            else:
                warmed = True
                rows = _infer_row_count(payload)

        duration = perf_counter() - start
        timestamp = self._clock()
        if isinstance(payload, CacheWarmupResult):
            result = CacheWarmupResult(
                name=spec.name,
                warmed=warmed,
                warmed_at=timestamp,
                duration_seconds=duration,
                rows=rows if rows is not None else payload.rows,
                detail=detail if detail is not None else payload.detail,
                strategy=payload.strategy or strategy,
                metadata=metadata or payload.metadata,
            )
        else:
            result = CacheWarmupResult(
                name=spec.name,
                warmed=warmed,
                warmed_at=timestamp,
                duration_seconds=duration,
                rows=rows,
                detail=detail,
                strategy=strategy,
                metadata=metadata,
            )

        status.history.append(result)
        status.last_result = result

        if result.warmed:
            status.last_error = None
            ready, error_detail = self._evaluate_readiness(spec)
            status.ready = ready
            if not ready:
                status.last_error = error_detail
        else:
            status.ready = False
            status.last_error = result.detail or "Warm-up failed"

        self._metrics.observe_cache_warmup(
            spec.name, result.strategy, result.duration_seconds, rows=result.rows
        )
        self._metrics.set_cache_readiness(spec.name, status.ready)

        if not result.warmed and "warmup_failed" not in status.active_degradations:
            status.active_degradations.add("warmup_failed")
            self._metrics.record_cache_degradation(spec.name, "warmup_failed")
        self._evaluate_degradations(status)

        return result

    def _evaluate_readiness(self, spec: CacheWarmupSpec) -> tuple[bool, str | None]:
        probe = spec.readiness_probe
        if probe is None:
            return True, None
        try:
            ready = bool(probe())
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"Readiness probe failed: {exc}"
        if not ready:
            return False, "Readiness probe reported not ready"
        return True, None

    # ------------------------------------------------------------------
    # Cold-start controls
    def allow_cold_request(self, cache_name: str) -> bool:
        """Return whether a cold request should proceed for ``cache_name``."""

        status = self._get_status(cache_name)
        spec = status.spec
        limit = spec.max_cold_requests

        if status.ready:
            return True

        if limit is None or status.stats.cold_allowed < limit:
            status.stats.cold_allowed += 1
            self._metrics.increment_cache_cold_request(spec.name, "allowed")
            return True

        status.stats.cold_blocked += 1
        self._metrics.increment_cache_cold_request(spec.name, "blocked")
        self._evaluate_degradations(status)
        return False

    def record_cold_latency(self, cache_name: str, latency_seconds: float) -> None:
        """Record the observed latency for a cold request."""

        status = self._get_status(cache_name)
        status.stats.cold_latencies.append(max(0.0, float(latency_seconds)))
        percentile = _percentile(status.stats.cold_latencies, 0.95)
        status.cold_latency_p95 = percentile
        self._metrics.observe_cache_cold_latency(
            status.spec.name, float(latency_seconds)
        )
        self._evaluate_degradations(status)

    def record_access(
        self,
        cache_name: str,
        *,
        hit: bool,
        latency_seconds: float | None = None,
    ) -> None:
        """Track cache usage and update hit-rate diagnostics."""

        status = self._get_status(cache_name)
        if hit:
            status.stats.hits += 1
        else:
            status.stats.misses += 1

        total = status.stats.total_accesses()
        status.hit_rate = status.stats.hits / total if total else 0.0
        self._metrics.update_cache_hit_rate(status.spec.name, status.hit_rate)

        if latency_seconds is not None and not hit:
            self.record_cold_latency(cache_name, latency_seconds)
        else:
            self._evaluate_degradations(status)

    # ------------------------------------------------------------------
    # Reporting helpers
    def status(self, cache_name: str) -> CacheWarmupStatus:
        """Return the status object associated with ``cache_name``."""

        return self._get_status(cache_name)

    def snapshot(self) -> list[CacheWarmupStatus]:
        """Return statuses in configuration order."""

        return [self._statuses[name] for name in self._order]

    def summary(self) -> list[dict[str, object]]:
        """Return serialisable summary data for observability endpoints."""

        return [status.as_dict() for status in self.snapshot()]

    def degradation_report(self) -> dict[str, tuple[str, ...]]:
        """Return active degradation signals per cache."""

        report: dict[str, tuple[str, ...]] = {}
        for name, status in self._statuses.items():
            if status.active_degradations:
                report[name] = tuple(sorted(status.active_degradations))
        return report

    def overall_ready(self) -> bool:
        """Return ``True`` when all critical caches are ready."""

        return all(
            status.ready for status in self._statuses.values() if status.spec.critical
        )

    # ------------------------------------------------------------------
    # Internal helpers
    def _get_status(self, cache_name: str) -> CacheWarmupStatus:
        try:
            return self._statuses[cache_name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise KeyError(f"Unknown cache: {cache_name}") from exc

    def _evaluate_degradations(self, status: CacheWarmupStatus) -> None:
        spec = status.spec
        reasons: set[str] = set()

        if spec.critical and not status.ready:
            reasons.add("not_ready")

        if status.last_result is not None and not status.last_result.warmed:
            reasons.add("warmup_failed")

        total = status.stats.total_accesses()
        if (
            total >= self._min_samples_for_hit_rate
            and status.hit_rate < spec.target_hit_rate
        ):
            reasons.add("hit_rate")

        if (
            spec.max_cold_latency_seconds is not None
            and status.cold_latency_p95 is not None
            and status.cold_latency_p95 > spec.max_cold_latency_seconds
        ):
            reasons.add("cold_latency")

        if not status.ready and status.stats.cold_blocked > 0:
            reasons.add("cold_requests_blocked")

        if reasons != status.active_degradations:
            added = reasons - status.active_degradations
            for reason in added:
                self._metrics.record_cache_degradation(spec.name, reason)
            status.active_degradations = reasons


__all__ = [
    "CacheUsageStats",
    "CacheWarmupController",
    "CacheWarmupResult",
    "CacheWarmupSpec",
    "CacheWarmupStatus",
]
