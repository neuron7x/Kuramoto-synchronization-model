# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Service for regime modulation business logic with deterministic cache coherence."""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from math import log2
from typing import Callable, Protocol

from sqlalchemy.orm import Session

from ..config import RegimeSettings
from ..errors import ValidationError
from ..logger import get_logger
from ..memory.repository import MemoryRepository
from ..metrics import (
    DB_OPERATION_LATENCY,
    REGIME_CACHE_AGE_SECONDS,
    REGIME_CACHE_COHERENCE_ENTROPY,
    REGIME_CACHE_EVENTS_TOTAL,
    REGIME_CACHE_SHADOW_READS_TOTAL,
    REGIME_CACHE_STALE_HITS_TOTAL,
    REGIME_TRANSITIONS,
    REGIME_UPDATES,
)
from ..modulation.regime import RegimeModulator, RegimeState

logger = get_logger(__name__)

_CACHE_STALE_EPSILON_SECONDS = 0.250
_BASE_SHADOW_READ_RATIO = 0.10
_DIVERGENCE_WINDOW = 12
_DIVERGENCE_CRITICAL_THRESHOLD = 3
_LYAPUNOV_PREFETCH_THRESHOLD = 0.65
_MAX_HLC_BACKWARDS_DRIFT_MS = 5_000
_STATE_COMPARE_EPSILON = 1e-9
_ENTROPY_GAMMA = 1.0
_HLC_LOGICAL_BITS = 20
_HLC_LOGICAL_MAX = (1 << _HLC_LOGICAL_BITS) - 1


@dataclass(frozen=True, slots=True)
class CacheCoherenceConfig:
    """Tunable parameters controlling cache coherence behavior."""

    stale_epsilon_seconds: float = _CACHE_STALE_EPSILON_SECONDS
    shadow_read_ratio: float = _BASE_SHADOW_READ_RATIO
    divergence_window_size: int = _DIVERGENCE_WINDOW
    divergence_critical_threshold: int = _DIVERGENCE_CRITICAL_THRESHOLD
    lyapunov_prefetch_threshold: float = _LYAPUNOV_PREFETCH_THRESHOLD
    max_hlc_backwards_drift_ms: int = _MAX_HLC_BACKWARDS_DRIFT_MS
    state_compare_epsilon: float = _STATE_COMPARE_EPSILON
    entropy_gamma: float = _ENTROPY_GAMMA


class AuditEventLogger(Protocol):
    """Protocol for optional audit logging sink."""

    def log_event(
        self,
        *,
        event_type: str,
        actor: str,
        ip_address: str,
        details: dict[str, object],
    ) -> object:
        """Emit a structured audit event."""


@dataclass(frozen=True, slots=True)
class HybridLogicalTimestamp:
    """Hybrid logical timestamp for distributed monotonic causal ordering."""

    wall_time_ms: int
    logical: int

    def to_version(self) -> int:
        """Encode timestamp into a sortable integral version."""

        if self.logical > _HLC_LOGICAL_MAX:
            raise OverflowError(
                f"HLC logical counter overflow: {self.logical} > {_HLC_LOGICAL_MAX}"
            )
        return (self.wall_time_ms << _HLC_LOGICAL_BITS) | self.logical


class HybridLogicalClock:
    """Hybrid logical clock that composes physical and logical counters."""

    def __init__(self, *, wall_clock_ms: Callable[[], int] | None = None) -> None:
        self._wall_clock_ms = wall_clock_ms or (lambda: int(time.time() * 1000))
        self._last = HybridLogicalTimestamp(wall_time_ms=self._wall_clock_ms(), logical=0)

    def wall_now_ms(self) -> int:
        """Return current wall clock time in milliseconds."""

        return self._wall_clock_ms()

    @property
    def last_wall_time_ms(self) -> int:
        """Last HLC wall component used by this clock."""

        return self._last.wall_time_ms

    def send(self) -> HybridLogicalTimestamp:
        """Return next local timestamp for an emitted event."""

        wall_now = self._wall_clock_ms()
        if wall_now > self._last.wall_time_ms:
            self._last = HybridLogicalTimestamp(wall_time_ms=wall_now, logical=0)
        else:
            self._last = HybridLogicalTimestamp(
                wall_time_ms=self._last.wall_time_ms,
                logical=self._last.logical + 1,
            )
        return self._last

    def receive(self, remote: HybridLogicalTimestamp) -> HybridLogicalTimestamp:
        """Merge remote timestamp and return causally monotonic local timestamp."""

        wall_now = self._wall_clock_ms()
        local_wall = self._last.wall_time_ms
        remote_wall = remote.wall_time_ms
        max_wall = max(wall_now, local_wall, remote_wall)

        if max_wall == local_wall and max_wall == remote_wall:
            logical = max(self._last.logical, remote.logical) + 1
        elif max_wall == local_wall:
            logical = self._last.logical + 1
        elif max_wall == remote_wall:
            logical = remote.logical + 1
        else:  # wall clock dominates both local and remote
            logical = 0

        self._last = HybridLogicalTimestamp(wall_time_ms=max_wall, logical=logical)
        return self._last


class CacheCoherenceStatus(str, Enum):
    """Coherence status between cache and persistence state."""

    COHERENT = "coherent"
    DIVERGENT = "divergent"
    CRITICAL_DIVERGENT = "critical_divergent"


@dataclass(frozen=True, slots=True)
class CachedRegimeState:
    """Immutable RCU cache entry."""

    state: RegimeState
    version: int
    cached_at_monotonic: float


@dataclass(frozen=True, slots=True)
class _CacheSnapshot:
    """Single immutable cache snapshot for atomic pointer replacement."""

    entry: CachedRegimeState | None
    status: CacheCoherenceStatus


class RegimeCache:
    """Lock-free RCU cache using atomic reference replacement semantics."""

    def __init__(
        self,
        *,
        monotonic_clock: Callable[[], float] | None = None,
        hlc: HybridLogicalClock | None = None,
    ) -> None:
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._write_lock = threading.Lock()
        self._snapshot = _CacheSnapshot(
            entry=None,
            status=CacheCoherenceStatus.COHERENT,
        )
        self._hlc = hlc or HybridLogicalClock()

    def get(self, *, min_version: int | None = None) -> CachedRegimeState | None:
        """Wait-free O(1) read of current immutable cache entry."""

        entry = self._snapshot.entry
        if entry is None:
            REGIME_CACHE_EVENTS_TOTAL.labels(event="miss").inc()
            return None

        if min_version is not None and entry.version < min_version:
            REGIME_CACHE_EVENTS_TOTAL.labels(event="version_miss").inc()
            return None

        REGIME_CACHE_EVENTS_TOTAL.labels(event="hit").inc()
        return entry

    def write_through(self, state: RegimeState, *, version: int | None = None) -> CachedRegimeState:
        """Write-through update with atomic pointer swap."""

        if version is None:
            version = self._hlc.send().to_version()

        entry = CachedRegimeState(
            state=state,
            version=version,
            cached_at_monotonic=self._monotonic_clock(),
        )
        with self._write_lock:
            self._snapshot = _CacheSnapshot(
                entry=entry,
                status=CacheCoherenceStatus.COHERENT,
            )
        REGIME_CACHE_EVENTS_TOTAL.labels(event="write_through").inc()
        return entry

    def absorb_remote_version(self, remote_timestamp: HybridLogicalTimestamp) -> int:
        """Advance local HLC from remote gossip state and return encoded version."""

        merged = self._hlc.receive(remote_timestamp)
        version = merged.to_version()
        REGIME_CACHE_EVENTS_TOTAL.labels(event="hlc_receive").inc()
        return version

    def invalidate(self) -> None:
        """Invalidate cache entry via atomic pointer reset."""

        with self._write_lock:
            self._snapshot = _CacheSnapshot(
                entry=None,
                status=self._snapshot.status,
            )
        REGIME_CACHE_EVENTS_TOTAL.labels(event="invalidate").inc()

    def mark_divergent(self, *, critical: bool = False) -> None:
        """Mark cache as divergent/critical divergent."""

        with self._write_lock:
            self._snapshot = _CacheSnapshot(
                entry=self._snapshot.entry,
                status=(
                    CacheCoherenceStatus.CRITICAL_DIVERGENT
                    if critical
                    else CacheCoherenceStatus.DIVERGENT
                ),
            )
        REGIME_CACHE_EVENTS_TOTAL.labels(event="mark_divergent").inc()

    @property
    def status(self) -> CacheCoherenceStatus:
        return self._snapshot.status


class BayesianShadowSampler:
    """Adaptive Bayesian shadow-read controller."""

    def __init__(
        self,
        *,
        base_rate: float,
        rng: random.Random | None = None,
        decay: float = 0.99,
        decay_interval: int = 256,
    ) -> None:
        self._base_rate = base_rate
        self._rng = rng or random.Random()
        self._lock = threading.RLock()
        self._alpha = 1.0
        self._beta = 1.0
        self._decay = decay
        self._decay_interval = decay_interval
        self._updates = 0

    @property
    def divergence_probability(self) -> float:
        with self._lock:
            return self._alpha / (self._alpha + self._beta)

    @property
    def entropy(self) -> float:
        p = min(max(self.divergence_probability, 1e-9), 1 - 1e-9)

        return -(p * log2(p) + (1 - p) * log2(1 - p))

    def sample_rate(self) -> float:
        adaptive = self._base_rate + 0.5 * self.divergence_probability
        return min(1.0, max(0.01, adaptive))

    def should_sample(self) -> bool:
        with self._lock:
            return self._rng.random() <= self.sample_rate()

    def observe(self, *, divergent: bool) -> None:
        with self._lock:
            if divergent:
                self._alpha += 1.0
            else:
                self._beta += 1.0
            self._updates += 1
            if self._updates % self._decay_interval == 0:
                self._alpha = max(1.0, self._alpha * self._decay)
                self._beta = max(1.0, self._beta * self._decay)


class RegimeService:
    """Service layer for regime modulation operations."""

    def __init__(
        self,
        settings: RegimeSettings,
        *,
        cache: RegimeCache | None = None,
        coherence_config: CacheCoherenceConfig | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        rng: random.Random | None = None,
        stale_epsilon_seconds: float = _CACHE_STALE_EPSILON_SECONDS,
        shadow_read_ratio: float = _BASE_SHADOW_READ_RATIO,
        divergence_window_size: int = _DIVERGENCE_WINDOW,
        divergence_critical_threshold: int = _DIVERGENCE_CRITICAL_THRESHOLD,
        lyapunov_prefetch_threshold: float = _LYAPUNOV_PREFETCH_THRESHOLD,
        max_hlc_backwards_drift_ms: int = _MAX_HLC_BACKWARDS_DRIFT_MS,
        state_compare_epsilon: float = _STATE_COMPARE_EPSILON,
        audit_logger: AuditEventLogger | None = None,
    ) -> None:
        cfg = coherence_config or CacheCoherenceConfig(
            stale_epsilon_seconds=stale_epsilon_seconds,
            shadow_read_ratio=shadow_read_ratio,
            divergence_window_size=divergence_window_size,
            divergence_critical_threshold=divergence_critical_threshold,
            lyapunov_prefetch_threshold=lyapunov_prefetch_threshold,
            max_hlc_backwards_drift_ms=max_hlc_backwards_drift_ms,
            state_compare_epsilon=state_compare_epsilon,
        )
        stale_epsilon_seconds = cfg.stale_epsilon_seconds
        shadow_read_ratio = cfg.shadow_read_ratio
        divergence_window_size = cfg.divergence_window_size
        divergence_critical_threshold = cfg.divergence_critical_threshold
        lyapunov_prefetch_threshold = cfg.lyapunov_prefetch_threshold
        max_hlc_backwards_drift_ms = cfg.max_hlc_backwards_drift_ms
        state_compare_epsilon = cfg.state_compare_epsilon
        if stale_epsilon_seconds <= 0:
            raise ValueError("stale_epsilon_seconds must be positive")
        if not 0 <= shadow_read_ratio <= 1:
            raise ValueError("shadow_read_ratio must be between 0 and 1")
        if divergence_window_size <= 0:
            raise ValueError("divergence_window_size must be positive")
        if divergence_critical_threshold <= 0:
            raise ValueError("divergence_critical_threshold must be positive")
        if max_hlc_backwards_drift_ms <= 0:
            raise ValueError("max_hlc_backwards_drift_ms must be positive")
        if state_compare_epsilon <= 0:
            raise ValueError("state_compare_epsilon must be positive")

        self._settings = settings
        self._modulator = RegimeModulator(settings)
        self._monotonic_clock = monotonic_clock or time.monotonic
        self._cache = cache or RegimeCache(monotonic_clock=self._monotonic_clock)
        self._hlc = HybridLogicalClock()
        self._stale_epsilon_seconds = stale_epsilon_seconds
        self._latest_version = 0
        self._audit_logger = audit_logger
        self._shadow_sampler = BayesianShadowSampler(base_rate=shadow_read_ratio, rng=rng)
        self._divergence_window: deque[bool] = deque(maxlen=divergence_window_size)
        self._divergence_critical_threshold = divergence_critical_threshold
        self._lyapunov_prefetch_threshold = lyapunov_prefetch_threshold
        self._max_hlc_backwards_drift_ms = max_hlc_backwards_drift_ms
        self._state_compare_epsilon = state_compare_epsilon
        self._entropy_gamma = cfg.entropy_gamma

    @staticmethod
    def _from_row(row: object) -> RegimeState:
        """Materialize ``RegimeState`` from a repository ORM object."""
        required_fields = ("label", "valence", "confidence", "as_of")
        missing = [field for field in required_fields if not hasattr(row, field)]
        if missing:
            raise ValueError(f"Regime row is missing required fields: {', '.join(missing)}")
        return RegimeState(
            label=getattr(row, "label"),
            valence=getattr(row, "valence"),
            confidence=getattr(row, "confidence"),
            as_of=getattr(row, "as_of"),
        )

    def _timestamp_from_datetime(self, as_of: datetime) -> HybridLogicalTimestamp:
        wall_ms = int(as_of.astimezone(timezone.utc).timestamp() * 1000)
        return HybridLogicalTimestamp(wall_time_ms=wall_ms, logical=0)

    def _compute_version(self, as_of: datetime) -> int:
        wall_now_ms = self._hlc.wall_now_ms()
        last_wall_ms = self._hlc.last_wall_time_ms
        backwards_drift_ms = max(last_wall_ms - wall_now_ms, 0)
        if backwards_drift_ms > self._max_hlc_backwards_drift_ms:
            self._cache.mark_divergent(critical=True)
            self._record_divergence(divergent=True, reason="hlc_drift")
            self._audit_cache_event(
                "regime.cache.hlc_drift",
                {
                    "backwards_drift_ms": backwards_drift_ms,
                    "threshold_ms": self._max_hlc_backwards_drift_ms,
                },
            )

        merged = self._hlc.receive(self._timestamp_from_datetime(as_of))
        return merged.to_version()

    def _state_equals(self, left: RegimeState, right: RegimeState) -> bool:
        return (
            left.label == right.label
            and abs(left.valence - right.valence) <= self._state_compare_epsilon
            and abs(left.confidence - right.confidence) <= self._state_compare_epsilon
            and left.as_of == right.as_of
        )

    def _audit_cache_event(self, event_type: str, details: dict[str, object]) -> None:
        if self._audit_logger is None:
            return
        details = dict(details)
        details.setdefault(
            "trace_id",
            f"regime-cache-{int(time.time() * 1_000_000)}",
        )
        try:
            self._audit_logger.log_event(
                event_type=event_type,
                actor="cortex.regime_service",
                ip_address="127.0.0.1",
                details=details,
            )
        except Exception:
            logger.warning("Failed to emit regime cache audit event", exc_info=True)

    def _record_divergence(self, *, divergent: bool, reason: str) -> None:
        self._shadow_sampler.observe(divergent=divergent)
        self._divergence_window.append(divergent)

        if divergent:
            REGIME_CACHE_STALE_HITS_TOTAL.labels(reason=reason).inc()

        recent_divergences = sum(1 for event in self._divergence_window if event)
        critical = recent_divergences >= self._divergence_critical_threshold
        if critical:
            self._cache.mark_divergent(critical=True)
            self._audit_cache_event(
                "regime.cache.critical_divergent",
                {
                    "recent_divergences": recent_divergences,
                    "window_size": self._divergence_window.maxlen,
                    "entropy": self._shadow_sampler.entropy,
                },
            )

    def _coherence_entropy_signal(self, *, volatility: float) -> float:
        """Return coherence entropy coupled to incoming volatility.

        Coupling keeps output in [0, 1] while increasing sensitivity during
        high-volatility regimes where coherence drift is more consequential.
        """

        base_entropy = self._shadow_sampler.entropy
        scaled = base_entropy * ((1.0 + max(volatility, 0.0)) ** self._entropy_gamma)
        return min(1.0, scaled)

    def _fetch_latest_state(self, repository: MemoryRepository) -> tuple[RegimeState | None, int]:
        start = time.perf_counter()
        previous = repository.latest_regime()
        DB_OPERATION_LATENCY.labels(operation="fetch_regime").observe(time.perf_counter() - start)

        if previous is None:
            return None, self._latest_version

        try:
            state = self._from_row(previous)
        except ValueError as exc:
            logger.error("Invalid regime row returned from repository", exc_info=exc)
            raise
        version = self._compute_version(previous.as_of)
        self._latest_version = max(self._latest_version, version)
        return state, version

    def _validate_cached_freshness(self, cached: CachedRegimeState) -> bool:
        age_seconds = max(self._monotonic_clock() - cached.cached_at_monotonic, 0.0)
        REGIME_CACHE_AGE_SECONDS.observe(age_seconds)
        if age_seconds <= self._stale_epsilon_seconds:
            return True

        self._cache.mark_divergent()
        self._record_divergence(divergent=True, reason="age_exceeded")
        self._audit_cache_event(
            "regime.cache.stale",
            {
                "age_seconds": age_seconds,
                "threshold_seconds": self._stale_epsilon_seconds,
                "version": cached.version,
            },
        )
        return False

    def _shadow_compare(self, repository: MemoryRepository, cached: CachedRegimeState) -> None:
        """Validate cached entry against repository truth via adaptive shadow reads."""

        if not self._shadow_sampler.should_sample():
            return

        db_state, db_version = self._fetch_latest_state(repository)
        if db_state is None:
            REGIME_CACHE_SHADOW_READS_TOTAL.labels(result="db_empty").inc()
            return
        if not isinstance(db_version, int):
            raise TypeError("db_version must be int")

        is_divergent = False
        reason = "coherent"
        if db_version > cached.version:
            is_divergent = True
            reason = "version_drift"
        elif db_version == cached.version and not self._state_equals(db_state, cached.state):
            is_divergent = True
            reason = "data_drift"

        self._record_divergence(divergent=is_divergent, reason=reason)
        REGIME_CACHE_SHADOW_READS_TOTAL.labels(result=reason).inc()
        if is_divergent:
            self._audit_cache_event(
                "regime.cache.divergent",
                {
                    "cache_version": cached.version,
                    "db_version": db_version,
                    "reason": reason,
                    "entropy": self._shadow_sampler.entropy,
                },
            )
            self._cache.write_through(db_state, version=db_version)

    def get_current_regime(self, repository: MemoryRepository) -> RegimeState:
        """Get current regime using fast-path cache and deterministic slow-path recovery."""

        cached_entry = self._cache.get()
        if cached_entry is not None:
            if self._validate_cached_freshness(cached_entry):
                self._shadow_compare(repository, cached_entry)
                REGIME_CACHE_COHERENCE_ENTROPY.observe(
                    self._coherence_entropy_signal(volatility=cached_entry.state.valence)
                )
                return cached_entry.state

        db_state, db_version = self._fetch_latest_state(repository)
        if db_state is None:
            raise ValidationError("No regime state found in repository")
        if not isinstance(db_version, int):
            raise TypeError("db_version must be int")

        new_entry = self._cache.write_through(db_state, version=db_version)
        REGIME_CACHE_COHERENCE_ENTROPY.observe(
            self._coherence_entropy_signal(volatility=new_entry.state.valence)
        )
        return new_entry.state

    def _load_previous_state(self, repository: MemoryRepository) -> RegimeState | None:
        cached = self._cache.get(min_version=self._latest_version)
        if cached is None:
            state, version = self._fetch_latest_state(repository)
            if state is not None:
                self._cache.write_through(state, version=version)
            return state

        if self._cache.status in {
            CacheCoherenceStatus.DIVERGENT,
            CacheCoherenceStatus.CRITICAL_DIVERGENT,
        }:
            state, version = self._fetch_latest_state(repository)
            if state is None:
                return None
            self._cache.write_through(state, version=version)
            return state

        if not self._validate_cached_freshness(cached):
            state, version = self._fetch_latest_state(repository)
            if state is None:
                return None
            self._cache.write_through(state, version=version)
            return state

        self._shadow_compare(repository, cached)
        if self._cache.status in {
            CacheCoherenceStatus.DIVERGENT,
            CacheCoherenceStatus.CRITICAL_DIVERGENT,
        }:
            state, version = self._fetch_latest_state(repository)
            if state is None:
                return None
            self._cache.write_through(state, version=version)
            return state

        return cached.state

    def _maybe_prefetch_for_lyapunov(
        self,
        repository: MemoryRepository,
        *,
        lyapunov_exponent: float | None,
    ) -> None:
        if lyapunov_exponent is None:
            return
        if lyapunov_exponent < self._lyapunov_prefetch_threshold:
            return

        self._cache.invalidate()
        state, version = self._fetch_latest_state(repository)
        if state is not None:
            self._cache.write_through(state, version=version)
        self._audit_cache_event(
            "regime.cache.lyapunov_prefetch",
            {
                "lyapunov_exponent": lyapunov_exponent,
                "threshold": self._lyapunov_prefetch_threshold,
            },
        )

    def update_regime(
        self,
        session: Session,
        feedback: float,
        volatility: float,
        as_of: datetime,
        *,
        lyapunov_exponent: float | None = None,
    ) -> RegimeState:
        """Update market regime based on feedback.

        Cache characteristics:
        - Wait-free O(1) reads from immutable RCU cache pointer.
        - O(1) write-through pointer swap per update.
        - O(N) invalidation complexity for N external replicas/watchers.
        """
        if volatility < 0:
            raise ValidationError(
                "Volatility must be non-negative", details={"volatility": volatility}
            )

        repository = MemoryRepository(session)
        self._maybe_prefetch_for_lyapunov(
            repository,
            lyapunov_exponent=lyapunov_exponent,
        )
        previous_state = self._load_previous_state(repository)

        updated_state = self._modulator.update(previous_state, feedback, volatility, as_of)

        start = time.perf_counter()
        repository.store_regime(
            updated_state.label,
            updated_state.valence,
            updated_state.confidence,
            updated_state.as_of,
        )
        DB_OPERATION_LATENCY.labels(operation="store_regime").observe(time.perf_counter() - start)

        version = self._compute_version(updated_state.as_of)
        self._latest_version = max(self._latest_version, version)
        self._cache.write_through(updated_state, version=version)
        coherence_entropy = self._coherence_entropy_signal(volatility=volatility)
        REGIME_CACHE_COHERENCE_ENTROPY.observe(coherence_entropy)

        REGIME_UPDATES.labels(regime=updated_state.label).inc()
        if previous_state and previous_state.label != updated_state.label:
            REGIME_TRANSITIONS.labels(
                from_regime=previous_state.label, to_regime=updated_state.label
            ).inc()

        self._audit_cache_event(
            "regime.cache.write_through",
            {
                "version": version,
                "label": updated_state.label,
                "coherence_status": self._cache.status.value,
                "coherence_entropy": coherence_entropy,
                "shadow_sample_rate": self._shadow_sampler.sample_rate(),
            },
        )

        logger.debug(
            "Updated regime",
            extra={
                "previous_label": previous_state.label if previous_state else None,
                "new_label": updated_state.label,
                "valence": updated_state.valence,
                "confidence": updated_state.confidence,
                "cache_status": self._cache.status.value,
                "coherence_entropy": coherence_entropy,
            },
        )

        return updated_state


__all__ = [
    "RegimeService",
    "RegimeCache",
    "CachedRegimeState",
    "CacheCoherenceStatus",
    "HybridLogicalClock",
    "HybridLogicalTimestamp",
    "BayesianShadowSampler",
    "CacheCoherenceConfig",
]
