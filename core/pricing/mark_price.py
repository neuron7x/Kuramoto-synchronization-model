# SPDX-License-Identifier: MIT
"""Robust mark price calibration utilities."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import fsum, isfinite
from statistics import median
from threading import RLock
from typing import Iterable, Sequence


@dataclass(slots=True, frozen=True)
class MarkPriceSample:
    """Single price observation supplied to the mark price engine."""

    price: float
    weight: float
    timestamp: datetime
    source: str = "unknown"

    def __post_init__(self) -> None:  # pragma: no cover - dataclass hook
        if not isfinite(self.price):
            raise ValueError("price must be a finite float")
        if not isfinite(self.weight):
            raise ValueError("weight must be a finite float")
        if self.weight < 0.0:
            raise ValueError("weight must be non-negative")
        if not isinstance(self.timestamp, datetime):
            raise TypeError("timestamp must be a datetime instance")
        if not self.source:
            raise ValueError("source must be a non-empty string")


@dataclass(slots=True, frozen=True)
class MarkPriceContributor:
    """Price input that participated in the final mark price."""

    sample: MarkPriceSample
    effective_weight: float

    def __post_init__(self) -> None:  # pragma: no cover - dataclass hook
        if self.effective_weight <= 0.0:
            raise ValueError("effective_weight must be strictly positive")


@dataclass(slots=True, frozen=True)
class MarkPriceRejection:
    """Sample that was excluded from the mark price calculation."""

    sample: MarkPriceSample
    reason: str

    def __post_init__(self) -> None:  # pragma: no cover - dataclass hook
        if not self.reason:
            raise ValueError("reason must be a non-empty string")


@dataclass(slots=True, frozen=True)
class MarkPriceResult:
    """Outcome of the mark price calibration routine."""

    mark_price: float
    timestamp: datetime
    contributors: tuple[MarkPriceContributor, ...]
    rejections: tuple[MarkPriceRejection, ...]
    fallback_used: bool

    @property
    def contributor_count(self) -> int:
        """Return the number of inputs that influenced the mark price."""

        return len(self.contributors)

    @property
    def total_effective_weight(self) -> float:
        """Return the aggregate effective weight of all contributors."""

        return fsum(contributor.effective_weight for contributor in self.contributors)


def _resolve_now(samples: Sequence[MarkPriceSample], now: datetime | None) -> datetime:
    if now is not None:
        return now
    if not samples:
        raise ValueError("Cannot infer current time without any samples")
    return max(sample.timestamp for sample in samples)


def compute_mark_price(
    samples: Sequence[MarkPriceSample],
    *,
    now: datetime | None = None,
    max_staleness: timedelta | None = timedelta(seconds=30),
    max_deviation_bps: float | None = 500.0,
    min_samples: int = 1,
    fallback_price: float | None = None,
    time_decay_half_life: timedelta | None = None,
) -> MarkPriceResult:
    """Compute a manipulation-resistant mark price.

    Parameters
    ----------
    samples:
        Price observations coming from heterogeneous sources (spot, index, futures).
    now:
        Reference timestamp. Defaults to the most recent sample.
    max_staleness:
        Discard observations older than this threshold.
    max_deviation_bps:
        Remove samples deviating from the robust centre by more than this amount.
    min_samples:
        Minimum number of valid samples required before accepting the result.
    fallback_price:
        Price returned when there are insufficient valid observations.
    time_decay_half_life:
        Optional exponential half-life applied on the effective weights.
    """

    timestamp = _resolve_now(samples, now)
    filtered: list[MarkPriceSample] = []
    rejections: list[MarkPriceRejection] = []

    if max_staleness is not None:
        if max_staleness <= timedelta(0):
            raise ValueError("max_staleness must be positive when provided")
        cutoff = timestamp - max_staleness
    else:
        cutoff = None

    for sample in samples:
        if cutoff is not None and sample.timestamp < cutoff:
            rejections.append(MarkPriceRejection(sample=sample, reason="stale"))
            continue
        if sample.weight <= 0.0:
            rejections.append(MarkPriceRejection(sample=sample, reason="zero_weight"))
            continue
        filtered.append(sample)

    if not filtered:
        if fallback_price is None:
            raise ValueError("No valid samples for mark price calculation")
        return MarkPriceResult(
            mark_price=float(fallback_price),
            timestamp=timestamp,
            contributors=tuple(),
            rejections=tuple(rejections),
            fallback_used=True,
        )

    centre = median(sample.price for sample in filtered)
    if max_deviation_bps is not None:
        if max_deviation_bps <= 0.0:
            raise ValueError("max_deviation_bps must be positive when provided")
        accepted: list[MarkPriceSample] = []
        for sample in filtered:
            if centre == 0.0:
                deviation_bps = float("inf") if sample.price != 0.0 else 0.0
            else:
                deviation_bps = abs(sample.price - centre) / abs(centre) * 1e4
            if deviation_bps > max_deviation_bps:
                rejections.append(MarkPriceRejection(sample=sample, reason="outlier"))
            else:
                accepted.append(sample)
        filtered = accepted

    if len(filtered) < min_samples:
        if fallback_price is None:
            raise ValueError(
                "Insufficient valid samples for mark price calculation"
            )
        return MarkPriceResult(
            mark_price=float(fallback_price),
            timestamp=timestamp,
            contributors=tuple(),
            rejections=tuple(rejections),
            fallback_used=True,
        )

    half_life_seconds: float | None = None
    if time_decay_half_life is not None:
        if time_decay_half_life <= timedelta(0):
            raise ValueError("time_decay_half_life must be positive when provided")
        half_life_seconds = time_decay_half_life.total_seconds()

    contributors: list[MarkPriceContributor] = []
    weighted_price_sum = 0.0
    weight_sum = 0.0
    for sample in filtered:
        effective_weight = sample.weight
        if half_life_seconds is not None:
            age = (timestamp - sample.timestamp).total_seconds()
            if age < 0.0:
                age = 0.0
            decay = 0.5 ** (age / half_life_seconds)
            effective_weight *= decay
        if effective_weight <= 0.0:
            rejections.append(MarkPriceRejection(sample=sample, reason="zero_weight"))
            continue
        contributors.append(
            MarkPriceContributor(sample=sample, effective_weight=effective_weight)
        )
        weighted_price_sum += sample.price * effective_weight
        weight_sum += effective_weight

    if weight_sum <= 0.0:
        if fallback_price is None:
            raise ValueError("Effective weights sum to zero; cannot compute mark price")
        return MarkPriceResult(
            mark_price=float(fallback_price),
            timestamp=timestamp,
            contributors=tuple(),
            rejections=tuple(rejections),
            fallback_used=True,
        )

    mark_price = weighted_price_sum / weight_sum
    return MarkPriceResult(
        mark_price=mark_price,
        timestamp=timestamp,
        contributors=tuple(contributors),
        rejections=tuple(rejections),
        fallback_used=False,
    )


class MarkPriceCalibrator:
    """Stateful mark price engine with rolling window semantics."""

    def __init__(
        self,
        *,
        max_samples: int = 120,
        max_staleness: timedelta | None = timedelta(seconds=30),
        max_deviation_bps: float | None = 500.0,
        min_samples: int = 1,
        fallback_price: float | None = None,
        time_decay_half_life: timedelta | None = None,
    ) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        if min_samples <= 0:
            raise ValueError("min_samples must be positive")
        self._samples: deque[MarkPriceSample] = deque()
        self._lock = RLock()
        self._max_samples = int(max_samples)
        self._max_staleness = max_staleness
        self._max_deviation_bps = max_deviation_bps
        self._min_samples = int(min_samples)
        self._fallback_price = fallback_price
        self._time_decay_half_life = time_decay_half_life

    def add_samples(self, samples: Iterable[MarkPriceSample]) -> None:
        """Add a batch of samples to the calibrator."""

        with self._lock:
            latest_timestamp: datetime | None = None
            for sample in samples:
                self._samples.append(sample)
                if latest_timestamp is None or sample.timestamp > latest_timestamp:
                    latest_timestamp = sample.timestamp
            if latest_timestamp is None:
                return
            self._prune_locked(now=latest_timestamp)

    def add_sample(self, sample: MarkPriceSample) -> None:
        """Add a single sample to the calibrator."""

        self.add_samples((sample,))

    def compute(self, *, now: datetime | None = None) -> MarkPriceResult:
        """Compute the current mark price using buffered samples."""

        reference_time = now if now is not None else datetime.now(timezone.utc)
        with self._lock:
            self._prune_locked(now=reference_time)
            snapshot = tuple(self._samples)
        return compute_mark_price(
            snapshot,
            now=reference_time,
            max_staleness=self._max_staleness,
            max_deviation_bps=self._max_deviation_bps,
            min_samples=self._min_samples,
            fallback_price=self._fallback_price,
            time_decay_half_life=self._time_decay_half_life,
        )

    def reset(self) -> None:
        """Clear all buffered samples."""

        with self._lock:
            self._samples.clear()

    def _prune_locked(self, *, now: datetime | None) -> None:
        if not self._samples:
            return
        if now is None:
            now = datetime.now(timezone.utc)
        if self._max_staleness is not None:
            cutoff = now - self._max_staleness
            while self._samples and self._samples[0].timestamp < cutoff:
                self._samples.popleft()
        while len(self._samples) > self._max_samples:
            self._samples.popleft()


__all__ = [
    "MarkPriceCalibrator",
    "MarkPriceContributor",
    "MarkPriceRejection",
    "MarkPriceResult",
    "MarkPriceSample",
    "compute_mark_price",
]
