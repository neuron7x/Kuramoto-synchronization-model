"""Event-time watermark management for backlog coordination across streams."""

from __future__ import annotations

import heapq
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from statistics import fmean
from typing import Any, Callable, Deque, Dict, List, Mapping


def _ensure_aware(ts: datetime) -> datetime:
    """Validate that ``ts`` carries timezone information."""

    if ts.tzinfo is None or ts.tzinfo.utcoffset(ts) is None:
        raise ValueError("timestamps must be timezone-aware")
    return ts


def _percentile(samples: List[float], percentile: float) -> float:
    """Compute the linear interpolated percentile of ``samples``."""

    if not samples:
        return 0.0
    if not 0.0 <= percentile <= 1.0:
        raise ValueError("percentile must be in the [0.0, 1.0] interval")
    ordered = sorted(samples)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * percentile
    lower = math.floor(k)
    upper = math.ceil(k)
    if lower == upper:
        return ordered[int(k)]
    fraction = k - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


@dataclass(frozen=True, slots=True)
class DelaySample:
    """Sample capturing arrival lag for visualisation purposes."""

    event_time: datetime
    arrival_time: datetime
    delay_seconds: float


@dataclass(frozen=True, slots=True)
class LagSummary:
    """Aggregate lag statistics for a single stream."""

    count: int
    average_seconds: float
    max_seconds: float
    p95_seconds: float


@dataclass(frozen=True, slots=True)
class WatermarkProgress:
    """Progress marker emitted whenever backlog processing advances."""

    source: str
    last_event_time: datetime
    processed_index: int
    watermark: datetime | None


@dataclass(frozen=True, slots=True)
class BacklogEvent:
    """Event stored in the backlog awaiting watermark clearance."""

    source: str
    index: int
    event_time: datetime
    arrival_time: datetime
    payload: Any
    lateness_seconds: float


@dataclass
class _LagAccumulator:
    count: int = 0
    total: float = 0.0
    max_value: float = 0.0

    def update(self, value: float) -> None:
        self.count += 1
        self.total += value
        self.max_value = max(self.max_value, value)


class WatermarkBacklog:
    """Coordinate multi-source backlog processing using event-time watermarks."""

    def __init__(
        self,
        *,
        allowed_lateness: timedelta,
        expiration: timedelta,
        max_delay_samples: int = 512,
        max_progress_markers: int = 512,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if allowed_lateness <= timedelta(0):
            raise ValueError("allowed_lateness must be positive")
        if expiration <= timedelta(0):
            raise ValueError("expiration must be positive")
        if max_delay_samples <= 0:
            raise ValueError("max_delay_samples must be positive")
        if max_progress_markers <= 0:
            raise ValueError("max_progress_markers must be positive")
        self._allowed_lateness = allowed_lateness
        self._expiration = expiration
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._heap: List[tuple[datetime, int, BacklogEvent]] = []
        self._latest_event_time: Dict[str, datetime] = {}
        self._progress: Dict[str, datetime] = {}
        self._last_index: Dict[str, int] = {}
        self._progress_history: Deque[WatermarkProgress] = deque(
            maxlen=max_progress_markers
        )
        self._delay_samples: Dict[str, Deque[DelaySample]] = defaultdict(
            lambda: deque(maxlen=max_delay_samples)
        )
        self._lag_stats: Dict[str, _LagAccumulator] = defaultdict(_LagAccumulator)
        self._watermark: datetime | None = None
        self._global_index = 0
        self._dropped_events = 0

    @property
    def watermark(self) -> datetime | None:
        """Return the current global watermark."""

        return self._watermark

    @property
    def dropped_events(self) -> int:
        """Count how many events were discarded as stale."""

        return self._dropped_events

    @property
    def backlog_size(self) -> int:
        """Return the number of buffered events awaiting processing."""

        return len(self._heap)

    def observe(
        self,
        source: str,
        event_time: datetime,
        *,
        payload: Any,
        arrival_time: datetime | None = None,
    ) -> BacklogEvent | None:
        """Register a new event and return its backlog envelope if accepted."""

        event_time = _ensure_aware(event_time)
        arrival_time = _ensure_aware(arrival_time or self._clock())
        lateness_seconds = (arrival_time - event_time).total_seconds()
        if lateness_seconds > self._expiration.total_seconds():
            self._dropped_events += 1
            return None
        latest = self._latest_event_time.get(source)
        if latest is None or event_time > latest:
            self._latest_event_time[source] = event_time
        # Watermark must be updated before we decide whether the event is stale.
        self._update_watermark()
        if self._watermark is not None:
            cutoff = self._watermark - self._expiration
            if event_time < cutoff:
                self._dropped_events += 1
                return None
        envelope = BacklogEvent(
            source=source,
            index=self._global_index,
            event_time=event_time,
            arrival_time=arrival_time,
            payload=payload,
            lateness_seconds=lateness_seconds,
        )
        self._global_index += 1
        heapq.heappush(self._heap, (envelope.event_time, envelope.index, envelope))
        self._delay_samples[source].append(
            DelaySample(
                event_time=envelope.event_time,
                arrival_time=envelope.arrival_time,
                delay_seconds=envelope.lateness_seconds,
            )
        )
        self._lag_stats[source].update(envelope.lateness_seconds)
        self._expire_stale()
        return envelope

    def drain_ready(self) -> List[BacklogEvent]:
        """Release events whose timestamps are cleared by the watermark."""

        self._update_watermark()
        self._expire_stale()
        if self._watermark is None:
            return []
        ready: List[BacklogEvent] = []
        while self._heap and self._heap[0][0] <= self._watermark:
            _, _, event = heapq.heappop(self._heap)
            ready.append(event)
            self._progress[event.source] = event.event_time
            self._last_index[event.source] = event.index
            self._progress_history.append(
                WatermarkProgress(
                    source=event.source,
                    last_event_time=event.event_time,
                    processed_index=event.index,
                    watermark=self._watermark,
                )
            )
        return ready

    def progress_snapshot(self) -> Mapping[str, WatermarkProgress]:
        """Return the latest progress marker per source."""

        snapshot: Dict[str, WatermarkProgress] = {}
        for source, last_time in self._progress.items():
            snapshot[source] = WatermarkProgress(
                source=source,
                last_event_time=last_time,
                processed_index=self._last_index[source],
                watermark=self._watermark,
            )
        return snapshot

    def progress_history(self) -> List[WatermarkProgress]:
        """Return the chronological history of progress markers."""

        return list(self._progress_history)

    def lag_summary(self) -> Mapping[str, LagSummary]:
        """Summarise lag characteristics across all observed sources."""

        summary: Dict[str, LagSummary] = {}
        for source, stats in self._lag_stats.items():
            if stats.count == 0:
                summary[source] = LagSummary(0, 0.0, 0.0, 0.0)
                continue
            samples = [sample.delay_seconds for sample in self._delay_samples[source]]
            summary[source] = LagSummary(
                count=stats.count,
                average_seconds=(
                    fmean(samples) if samples else stats.total / stats.count
                ),
                max_seconds=stats.max_value,
                p95_seconds=_percentile(samples, 0.95) if samples else 0.0,
            )
        return summary

    def delay_series(self) -> Mapping[str, List[DelaySample]]:
        """Return the retained delay samples suitable for charting."""

        return {
            source: list(samples) for source, samples in self._delay_samples.items()
        }

    def _update_watermark(self) -> None:
        self._prune_inactive_sources()
        if not self._latest_event_time:
            self._watermark = None
            return
        candidate = min(self._latest_event_time.values()) - self._allowed_lateness
        if self._watermark is None or candidate > self._watermark:
            self._watermark = candidate

    def _expire_stale(self) -> None:
        if self._watermark is None or not self._heap:
            return
        cutoff = self._watermark - self._expiration
        retained: List[tuple[datetime, int, BacklogEvent]] = []
        dropped = 0
        while self._heap:
            event_time, index, event = heapq.heappop(self._heap)
            if event_time < cutoff:
                dropped += 1
                continue
            retained.append((event_time, index, event))
        if dropped:
            self._dropped_events += dropped
        if retained:
            heapq.heapify(retained)
        self._heap = retained

    def _prune_inactive_sources(self) -> None:
        if len(self._latest_event_time) <= 1:
            return
        newest_event_time = max(self._latest_event_time.values())
        cutoff = newest_event_time - self._expiration
        stale_sources = [
            source
            for source, last_event_time in self._latest_event_time.items()
            if last_event_time < cutoff
        ]
        if not stale_sources:
            return
        for source in stale_sources:
            self._latest_event_time.pop(source, None)
            self._progress.pop(source, None)
            self._last_index.pop(source, None)
            self._delay_samples.pop(source, None)
            self._lag_stats.pop(source, None)


__all__ = [
    "BacklogEvent",
    "DelaySample",
    "LagSummary",
    "WatermarkBacklog",
    "WatermarkProgress",
]
