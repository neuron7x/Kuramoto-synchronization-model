"""Incremental backfill helpers with hierarchical caching.

The ingestion layer maintains three logical cache tiers:

``raw``
    Tick-by-tick payloads before any transformation.  Useful for replays.
``ohlcv``
    Aggregated bars aligned to a canonical calendar.
``features``
    Derived indicator buffers that are expensive to recompute.

All caches expose the same interface so they can be stacked together.  Gap
detection is central to the incremental workflow: given an expected sampling
frequency the planner identifies missing ranges and only requests those slices
from the upstream provider.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC
from queue import Empty, PriorityQueue
from typing import Iterator, List, MutableMapping, Optional

import pandas as pd
from pandas.tseries.frequencies import to_offset

from core.data.timeutils import normalize_timestamp


@dataclass(frozen=True)
class CacheKey:
    """Compound cache key covering symbol, venue and timeframe."""

    layer: str
    symbol: str
    venue: str
    timeframe: str


@dataclass
class CacheEntry:
    """Cache metadata and payload."""

    frame: pd.DataFrame
    start: pd.Timestamp
    end: pd.Timestamp

    def slice(
        self, start: Optional[pd.Timestamp], end: Optional[pd.Timestamp]
    ) -> pd.DataFrame:
        view = self.frame
        if start is not None:
            view = view[view.index >= start]
        if end is not None:
            view = view[view.index <= end]
        return view.copy()


class LayerCache:
    """In-memory cache implementing the shared ingestion cache protocol."""

    def __init__(self) -> None:
        self._entries: MutableMapping[CacheKey, CacheEntry] = {}
        self._lock = threading.RLock()

    def _normalize_payload(
        self, frame: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.Timestamp, pd.Timestamp]:
        if frame.empty:
            raise ValueError("Cannot cache empty frame")
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise TypeError("Cache payload must be indexed by pd.DatetimeIndex")
        start = frame.index.min()
        end = frame.index.max()
        return frame.copy(), start, end

    def put(self, key: CacheKey, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        normalized, start, end = self._normalize_payload(frame)
        with self._lock:
            self._entries[key] = CacheEntry(frame=normalized, start=start, end=end)

    def merge(self, key: CacheKey, frame: pd.DataFrame) -> None:
        if frame.empty:
            return
        normalized, start, end = self._normalize_payload(frame)
        with self._lock:
            current = self._entries.get(key)
            if current is None or current.frame.empty:
                self._entries[key] = CacheEntry(frame=normalized, start=start, end=end)
                return
            combined = pd.concat([current.frame, normalized])
            combined = combined[~combined.index.duplicated(keep="last")]
            combined = combined.sort_index()
            combined_start = combined.index.min()
            combined_end = combined.index.max()
            self._entries[key] = CacheEntry(
                frame=combined,
                start=combined_start,
                end=combined_end,
            )

    def get(
        self,
        key: CacheKey,
        *,
        start: Optional[pd.Timestamp] = None,
        end: Optional[pd.Timestamp] = None,
    ) -> pd.DataFrame:
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return pd.DataFrame()
        return entry.slice(start, end)

    def coverage(self, key: CacheKey) -> Optional[pd.Interval]:
        with self._lock:
            entry = self._entries.get(key)
        if entry is None:
            return None
        return pd.Interval(entry.start, entry.end, closed="both")

    def delete(self, key: CacheKey) -> bool:
        """Remove ``key`` from the cache if present."""

        with self._lock:
            return self._entries.pop(key, None) is not None

    def iter_entries(self) -> Iterator[tuple[CacheKey, CacheEntry]]:
        """Yield a thread-safe snapshot of cached entries.

        Callers receive a stable view of the cache contents without holding the
        internal lock.  The returned :class:`CacheEntry` objects must be treated
        as read-only to preserve cache integrity.
        """

        with self._lock:
            snapshot = tuple(self._entries.items())
        for key, entry in snapshot:
            yield key, entry


@dataclass(frozen=True)
class Gap:
    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("Gap requires start < end")


def _resolve_cadence(
    expected_index: pd.DatetimeIndex,
    *,
    frequency: str | pd.Timedelta | pd.tseries.offsets.BaseOffset | None = None,
) -> pd.tseries.offsets.BaseOffset:
    """Return the sampling cadence of ``expected_index``.

    Parameters
    ----------
    expected_index:
        Datetime index describing the canonical sampling grid.
    frequency:
        Optional explicit frequency override.  When provided it takes
        precedence over the ``DatetimeIndex`` metadata.

    Notes
    -----
    Preference is given to an explicitly declared ``freq``.  When that is not
    available we fall back to the inferred frequency.  A clear error is raised
    if neither is defined so callers can correct the input before arithmetic is
    attempted.
    """

    if frequency is not None:
        return to_offset(frequency)

    freq = expected_index.freq or expected_index.inferred_freq
    if freq is None:
        raise ValueError(
            "Unable to determine expected_index frequency; set DatetimeIndex.freq "
            "or provide an index with an inferrable cadence."
        )
    return to_offset(freq)


def detect_gaps(
    expected_index: pd.DatetimeIndex,
    existing_index: pd.DatetimeIndex,
    *,
    frequency: str | pd.Timedelta | pd.tseries.offsets.BaseOffset | None = None,
) -> List[Gap]:
    """Return gaps between ``expected_index`` and ``existing_index``.

    ``frequency`` mirrors the parameter accepted by :func:`_resolve_cadence` and
    allows callers to supply a cadence when the ``DatetimeIndex`` has lost its
    ``freq`` metadata (for example after being filtered by a trading calendar).
    """

    cadence = _resolve_cadence(expected_index, frequency=frequency)
    missing = expected_index.difference(existing_index)
    if missing.empty:
        return []

    gaps: List[Gap] = []
    start = missing[0]
    prev = missing[0]
    for ts in missing[1:]:
        expected_next = prev + cadence
        if ts != expected_next:
            gaps.append(Gap(start=start, end=expected_next))
            start = ts
        prev = ts
    gaps.append(Gap(start=start, end=prev + cadence))
    return gaps


@dataclass
class BackfillPlan:
    """Description of the windows that need to be requested."""

    gaps: List[Gap] = field(default_factory=list)
    covered: Optional[pd.Interval] = None
    segments: List["BackfillSegment"] = field(default_factory=list)

    @property
    def is_full_refresh(self) -> bool:
        return not self.covered and bool(self.gaps)


class GapFillPlanner:
    """Analyse cache coverage and produce backfill plans."""

    def __init__(self, cache: LayerCache) -> None:
        self._cache = cache

    def plan(
        self,
        key: CacheKey,
        *,
        expected_index: pd.DatetimeIndex,
        frequency: str | pd.Timedelta | pd.tseries.offsets.BaseOffset | None = None,
    ) -> BackfillPlan:
        cadence = _resolve_cadence(expected_index, frequency=frequency)
        coverage = self._cache.coverage(key)
        existing = self._cache.get(key)
        if existing.empty:
            return BackfillPlan(
                gaps=[Gap(start=expected_index[0], end=expected_index[-1] + cadence)]
            )
        gaps = detect_gaps(expected_index, existing.index, frequency=frequency)
        return BackfillPlan(gaps=gaps, covered=coverage)

    def apply(
        self,
        key: CacheKey,
        frame: pd.DataFrame,
    ) -> None:
        if frame.empty:
            return
        self._cache.merge(key, frame)


@dataclass
class BackfillPayload:
    """Result returned by an upstream loader."""

    frame: pd.DataFrame
    checksum: Optional[str] = None


@dataclass
class BackfillSegment:
    """Atomic unit of work representing a backfill slice."""

    id: str
    gap: Gap
    start: pd.Timestamp
    end: pd.Timestamp
    priority: int
    attempts: int = 0
    checksum: Optional[str] = None

    def clone_for_retry(self) -> "BackfillSegment":
        return BackfillSegment(
            id=self.id,
            gap=self.gap,
            start=self.start,
            end=self.end,
            priority=self.priority,
            attempts=self.attempts,
            checksum=self.checksum,
        )


@dataclass(frozen=True)
class BackfillProgressSnapshot:
    """Immutable snapshot of the backfill execution progress."""

    total_segments: int
    completed_segments: int
    failed_segments: int
    bytes_transferred: int

    @property
    def remaining_segments(self) -> int:
        return max(
            self.total_segments - self.completed_segments - self.failed_segments, 0
        )

    @property
    def completion_ratio(self) -> float:
        if self.total_segments == 0:
            return 1.0
        return self.completed_segments / self.total_segments


class _BackfillProgressTracker:
    """Thread-safe tracker that produces :class:`BackfillProgressSnapshot`."""

    def __init__(self, total_segments: int) -> None:
        self._total_segments = total_segments
        self._completed_segments = 0
        self._failed_segments = 0
        self._bytes_transferred = 0
        self._lock = threading.RLock()

    def mark_success(self, bytes_transferred: int) -> BackfillProgressSnapshot:
        with self._lock:
            self._completed_segments += 1
            self._bytes_transferred += max(bytes_transferred, 0)
            return self.snapshot()

    def mark_failure(self) -> BackfillProgressSnapshot:
        with self._lock:
            self._failed_segments += 1
            return self.snapshot()

    def snapshot(self) -> BackfillProgressSnapshot:
        with self._lock:
            return BackfillProgressSnapshot(
                total_segments=self._total_segments,
                completed_segments=self._completed_segments,
                failed_segments=self._failed_segments,
                bytes_transferred=self._bytes_transferred,
            )


class _ThroughputLimiter:
    """Token bucket limiting the rate at which segments are executed."""

    def __init__(self, rate_per_second: float) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self._rate = rate_per_second
        self._allowance = rate_per_second
        self._last_check = time.monotonic()
        self._lock = threading.RLock()

    def acquire(self, tokens: float = 1.0) -> None:
        if tokens <= 0:
            return
        while True:
            with self._lock:
                current = time.monotonic()
                elapsed = current - self._last_check
                self._last_check = current
                self._allowance = min(
                    self._rate, self._allowance + elapsed * self._rate
                )
                if self._allowance >= tokens:
                    self._allowance -= tokens
                    return
                deficit = tokens - self._allowance
                wait_seconds = deficit / self._rate if self._rate > 0 else 0.0
            time.sleep(wait_seconds)


@dataclass(frozen=True)
class SegmentError:
    """Contextualised failure reason for a segment."""

    segment: BackfillSegment
    message: str


@dataclass
class BackfillResult:
    """Execution result returned by :class:`BackfillPlanner`."""

    plan: BackfillPlan
    completed_segments: List[BackfillSegment]
    failed_segments: List[BackfillSegment]
    errors: List[SegmentError]
    progress: BackfillProgressSnapshot

    @property
    def success(self) -> bool:
        return not self.failed_segments and not self.errors


def _default_checksum(frame: pd.DataFrame) -> str:
    hashed = pd.util.hash_pandas_object(frame, index=True).values
    return hashlib.sha256(hashed.tobytes()).hexdigest()


class BackfillPlanner:
    """End-to-end planner orchestrating detection, execution and validation."""

    def __init__(
        self,
        cache: LayerCache,
        *,
        max_workers: int = 4,
        segment_size: int = 10_000,
        max_retries: int = 3,
        throughput_per_second: float | None = None,
        checksum_func: Callable[[pd.DataFrame], str] = _default_checksum,
        logger: logging.Logger | None = None,
    ) -> None:
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        if segment_size <= 0:
            raise ValueError("segment_size must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        self._cache = cache
        self._gap_planner = GapFillPlanner(cache)
        self._max_workers = max_workers
        self._segment_size = segment_size
        self._max_retries = max_retries
        self._limiter = (
            _ThroughputLimiter(throughput_per_second)
            if throughput_per_second is not None
            else None
        )
        self._checksum_func = checksum_func
        self._logger = logger or logging.getLogger(__name__)

    def backfill(
        self,
        key: CacheKey,
        *,
        expected_index: pd.DatetimeIndex,
        loader: Callable[
            [CacheKey, pd.Timestamp, pd.Timestamp], BackfillPayload | pd.DataFrame
        ],
        frequency: str | pd.Timedelta | pd.tseries.offsets.BaseOffset | None = None,
        progress_callback: Callable[[BackfillProgressSnapshot], None] | None = None,
    ) -> BackfillResult:
        plan = self._gap_planner.plan(
            key, expected_index=expected_index, frequency=frequency
        )
        if not plan.gaps:
            snapshot = BackfillProgressSnapshot(
                total_segments=0,
                completed_segments=0,
                failed_segments=0,
                bytes_transferred=0,
            )
            plan.segments = []
            return BackfillResult(
                plan=plan,
                completed_segments=[],
                failed_segments=[],
                errors=[],
                progress=snapshot,
            )

        cadence = _resolve_cadence(expected_index, frequency=frequency)
        segments = self._build_segments(plan.gaps, expected_index, cadence)
        plan.segments = segments

        tracker = _BackfillProgressTracker(len(segments))
        completed: list[BackfillSegment] = []
        failed: list[BackfillSegment] = []
        errors: list[SegmentError] = []
        completed_lock = threading.Lock()
        failed_lock = threading.Lock()
        error_lock = threading.Lock()

        queue: PriorityQueue[tuple[int, str, Optional[BackfillSegment]]] = (
            PriorityQueue()
        )
        for segment in segments:
            queue.put((segment.priority, segment.id, segment))

        stop_event = threading.Event()

        def worker() -> None:
            while True:
                try:
                    priority, token, segment = queue.get(timeout=0.5)
                except Empty:
                    if stop_event.is_set():
                        break
                    continue

                if segment is None:
                    queue.task_done()
                    break

                try:
                    if self._limiter is not None:
                        self._limiter.acquire()
                    payload = loader(key, segment.start, segment.end)
                    if isinstance(payload, pd.DataFrame):
                        frame = payload
                        checksum = self._checksum_func(frame)
                    else:
                        frame = payload.frame
                        checksum = self._checksum_func(frame)
                        if (
                            payload.checksum is not None
                            and payload.checksum != checksum
                        ):
                            raise ValueError(
                                "Checksum mismatch for segment "
                                f"{segment.start.isoformat()} - {segment.end.isoformat()}"
                            )

                    expected_slice = expected_index[
                        (expected_index >= segment.start)
                        & (expected_index < segment.end)
                    ]
                    self._validate_payload(frame, expected_slice)
                    self._gap_planner.apply(key, frame)
                    segment.checksum = checksum
                    with completed_lock:
                        completed.append(segment)
                    snapshot = tracker.mark_success(
                        int(frame.memory_usage(index=True, deep=True).sum())
                    )
                    if progress_callback is not None:
                        progress_callback(snapshot)
                except Exception as exc:  # noqa: BLE001
                    segment.attempts += 1
                    message = (
                        f"Backfill segment failed ({segment.attempts} attempts): {exc}"
                    )
                    self._logger.exception(message)
                    if segment.attempts <= self._max_retries:
                        retry = segment.clone_for_retry()
                        retry.attempts = segment.attempts
                        retry.priority = self._retry_priority(segment)
                        queue.put((retry.priority, uuid.uuid4().hex, retry))
                    else:
                        with failed_lock:
                            failed.append(segment)
                        with error_lock:
                            errors.append(
                                SegmentError(segment=segment, message=str(exc))
                            )
                        snapshot = tracker.mark_failure()
                        if progress_callback is not None:
                            progress_callback(snapshot)
                finally:
                    queue.task_done()

        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = [executor.submit(worker) for _ in range(self._max_workers)]
            queue.join()
            stop_event.set()
            for _ in range(self._max_workers):
                queue.put((int(1e9), uuid.uuid4().hex, None))
            for future in futures:
                future.result()

        final_snapshot = tracker.snapshot()
        return BackfillResult(
            plan=plan,
            completed_segments=completed,
            failed_segments=failed,
            errors=errors,
            progress=final_snapshot,
        )

    def _build_segments(
        self,
        gaps: List[Gap],
        expected_index: pd.DatetimeIndex,
        cadence: pd.tseries.offsets.BaseOffset,
    ) -> List[BackfillSegment]:
        segments: list[BackfillSegment] = []
        for gap in gaps:
            gap_index = expected_index[
                (expected_index >= gap.start) & (expected_index < gap.end)
            ]
            if gap_index.empty:
                continue
            for chunk_start in range(0, len(gap_index), self._segment_size):
                chunk = gap_index[chunk_start : chunk_start + self._segment_size]
                segment_start = chunk[0]
                segment_end = chunk[-1] + cadence
                priority = self._segment_priority(segment_start, segment_end)
                segments.append(
                    BackfillSegment(
                        id=uuid.uuid4().hex,
                        gap=gap,
                        start=segment_start,
                        end=segment_end,
                        priority=priority,
                    )
                )
        segments.sort(key=lambda segment: segment.priority)
        return segments

    @staticmethod
    def _segment_priority(start: pd.Timestamp, end: pd.Timestamp) -> int:
        return -int(end.value)

    @staticmethod
    def _retry_priority(segment: BackfillSegment) -> int:
        return segment.priority - int(1e6) * segment.attempts

    @staticmethod
    def _validate_payload(
        frame: pd.DataFrame, expected_index: pd.DatetimeIndex
    ) -> None:
        if frame.empty:
            raise ValueError("Backfill loader returned an empty frame")
        if not isinstance(frame.index, pd.DatetimeIndex):
            raise TypeError("Backfill payload must use a DatetimeIndex")
        if not frame.index.is_monotonic_increasing:
            raise ValueError("Backfill payload index must be sorted in ascending order")
        if not frame.index.is_unique:
            raise ValueError("Backfill payload index must be unique")
        expected_set = pd.Index(expected_index)
        frame_index = pd.Index(frame.index)
        missing = expected_set.difference(frame_index)
        if not missing.empty:
            raise ValueError(
                "Backfill payload is missing timestamps: "
                + ", ".join(ts.isoformat() for ts in missing[:5])
            )
        extra = frame_index.difference(expected_set)
        if not extra.empty:
            raise ValueError(
                "Backfill payload contains unexpected timestamps: "
                + ", ".join(ts.isoformat() for ts in extra[:5])
            )


class CacheRegistry:
    """Facade aggregating raw/ohlcv/feature caches."""

    def __init__(self) -> None:
        self.raw = LayerCache()
        self.ohlcv = LayerCache()
        self.features = LayerCache()

    def cache_for(self, layer: str) -> LayerCache:
        if layer not in {"raw", "ohlcv", "features"}:
            raise ValueError(f"Unknown cache layer: {layer}")
        return getattr(self, layer)


def normalise_index(
    frame: pd.DataFrame, *, market: Optional[str] = None
) -> pd.DataFrame:
    """Ensure the index is tz-aware and normalised through ``normalize_timestamp``."""

    if frame.empty:
        return frame
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("frame must use a DatetimeIndex")
    normalized = [
        normalize_timestamp(ts.to_pydatetime(), market=market) for ts in frame.index
    ]
    result = frame.copy()
    result.index = pd.DatetimeIndex(normalized, tz=UTC)
    return result


__all__ = [
    "BackfillPayload",
    "BackfillPlan",
    "BackfillPlanner",
    "BackfillProgressSnapshot",
    "BackfillResult",
    "BackfillSegment",
    "CacheEntry",
    "CacheKey",
    "CacheRegistry",
    "Gap",
    "GapFillPlanner",
    "SegmentError",
    "LayerCache",
    "detect_gaps",
    "normalise_index",
]
