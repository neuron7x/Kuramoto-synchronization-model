# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Coordinate historical backfills and live tick streams with metadata checks.

The aggregator validates symbol and venue metadata when ingesting sequences of
``PriceTick`` instances.  When callers provide pre-aggregated ``pandas``
``DataFrame`` objects the values are assumed to be correct, and the caller is
responsible for ensuring their metadata coherence before invoking the
aggregator.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable, Iterable, Sequence

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BaseOffset

from core.data.backfill import (
    BackfillPlan,
    CacheKey,
    Gap,
    GapFillPlanner,
    normalise_index,
)
from core.data.catalog import normalize_symbol, normalize_venue
from core.data.models import InstrumentType, PriceTick
from core.data.timeutils import get_market_calendar, normalize_timestamp

from .ingestion_service import DataIngestionCacheService

TickPayload = Iterable[PriceTick] | pd.DataFrame | None
GapFetcher = Callable[[datetime, datetime], TickPayload]


@dataclass(frozen=True)
class AggregationResult:
    """Result returned by :class:`TickStreamAggregator` operations."""

    key: CacheKey
    frame: pd.DataFrame
    backfill_plan: BackfillPlan

    @property
    def gaps(self) -> list[Gap]:
        """Convenience accessor to the gaps contained in ``backfill_plan``."""

        return list(self.backfill_plan.gaps)


class TickStreamAggregator:
    """Unify historical datasets with live tick buffers using cache backfills.

    The aggregator consumes pre-recorded tick batches (for example loaded from
    CSV files) and live streams delivered via websocket adapters.  All ticks are
    normalised to UTC, validated for metadata consistency and merged into the
    ingestion cache.  Once the cache has been updated the component evaluates
    the resulting coverage, produces backfill plans for any uncovered windows
    and optionally hydrates those gaps through a user-provided callback.
    """

    def __init__(
        self,
        *,
        cache_service: DataIngestionCacheService | None = None,
        layer: str = "raw",
        timeframe: str = "1min",
        market: str | None = None,
        frequency: str | pd.Timedelta | BaseOffset | None = None,
    ) -> None:
        if not timeframe or not timeframe.strip():
            raise ValueError("timeframe must be a non-empty string")

        self._cache_service = cache_service or DataIngestionCacheService()
        self._layer = layer
        self._timeframe = timeframe
        self._market = market
        self._frequency = self._resolve_frequency(frequency or timeframe)

    def synchronise(
        self,
        *,
        symbol: str,
        venue: str,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        historical: TickPayload = None,
        live: TickPayload = None,
        start: datetime | pd.Timestamp | float | int | str | None = None,
        end: datetime | pd.Timestamp | float | int | str | None = None,
        market: str | None = None,
        gap_fetcher: GapFetcher | None = None,
    ) -> AggregationResult:
        """Merge cached data, historical batches and live ticks into one frame.

        Parameters
        ----------
        symbol, venue, instrument_type:
            Identify the instrument whose data should be consolidated.
        historical:
            Optional payload representing historical ticks.  Can be a sequence
            of :class:`~core.data.models.PriceTick` instances or a Pandas frame.
        live:
            Optional payload representing live ticks using the same format as
            ``historical``.
        start, end:
            Desired coverage window used to compute backfill plans.  When not
            provided the aggregator falls back to the boundaries of the merged
            dataset currently stored in the cache.  Values may be provided as
            ``datetime`` objects, UNIX timestamps, or ISO-8601 formatted strings.
        market:
            Explicit market calendar identifier.  Defaults to the value passed
            at construction time.
        gap_fetcher:
            Optional callable invoked for each gap detected in the merged
            dataset.  The callback receives ``(start, end)`` timestamps expressed
            in UTC and must return a tick payload compatible with ``historical``
            and ``live`` arguments.
        """

        canonical_key = self._build_cache_key(symbol, venue, instrument_type)
        market_hint = market or self._market

        existing = self._cache_service.get_cached_frame(
            layer=self._layer,
            symbol=canonical_key.symbol,
            venue=canonical_key.venue,
            timeframe=self._timeframe,
            instrument_type=instrument_type,
        )

        frames = [
            existing,
            self._coerce_to_frame(
                historical, canonical_key, instrument_type, market_hint
            ),
            self._coerce_to_frame(live, canonical_key, instrument_type, market_hint),
        ]

        merged = self._merge_frames(frames)
        cached = self._cache_service.cache_frame(
            merged,
            layer=self._layer,
            symbol=canonical_key.symbol,
            venue=canonical_key.venue,
            timeframe=self._timeframe,
            market=market_hint,
            instrument_type=instrument_type,
        )

        window = self._resolve_window(cached, start, end, market_hint)
        if window is None:
            plan = BackfillPlan()
            return AggregationResult(
                key=canonical_key, frame=cached, backfill_plan=plan
            )

        expected_index = self._build_expected_index(*window, market=market_hint)
        if expected_index.empty:
            plan = BackfillPlan()
            return AggregationResult(
                key=canonical_key, frame=cached, backfill_plan=plan
            )

        planner = self._get_planner()
        plan = planner.plan(
            canonical_key,
            expected_index=expected_index,
            frequency=self._frequency,
        )
        if plan.gaps and gap_fetcher is not None:
            gap_frames: list[pd.DataFrame] = []
            for gap in plan.gaps:
                payload = gap_fetcher(
                    gap.start.to_pydatetime(), gap.end.to_pydatetime()
                )
                gap_frame = self._coerce_to_frame(
                    payload, canonical_key, instrument_type, market_hint
                )
                if not gap_frame.empty:
                    gap_frames.append(gap_frame)

            if gap_frames:
                merged = self._merge_frames([cached, *gap_frames])
                cached = self._cache_service.cache_frame(
                    merged,
                    layer=self._layer,
                    symbol=canonical_key.symbol,
                    venue=canonical_key.venue,
                    timeframe=self._timeframe,
                    market=market_hint,
                    instrument_type=instrument_type,
                )
                planner = self._get_planner()
                plan = planner.plan(
                    canonical_key,
                    expected_index=expected_index,
                    frequency=self._frequency,
                )

        return AggregationResult(key=canonical_key, frame=cached, backfill_plan=plan)

    # ------------------------------------------------------------------
    # Internal helpers
    def _resolve_frequency(
        self, value: str | pd.Timedelta | BaseOffset
    ) -> pd.Timedelta:
        try:
            freq = pd.to_timedelta(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
            raise ValueError("frequency must be a pandas-compatible timedelta") from exc
        if freq <= pd.Timedelta(0):
            raise ValueError("frequency must be strictly positive")
        return freq

    def _build_cache_key(
        self,
        symbol: str,
        venue: str,
        instrument_type: InstrumentType,
    ) -> CacheKey:
        canonical_symbol = normalize_symbol(
            symbol, instrument_type_hint=instrument_type
        )
        canonical_venue = normalize_venue(venue)
        return CacheKey(
            layer=self._layer,
            symbol=canonical_symbol,
            venue=canonical_venue,
            timeframe=self._timeframe,
        )

    def _coerce_to_frame(
        self,
        payload: TickPayload,
        key: CacheKey,
        instrument_type: InstrumentType,
        market: str | None,
    ) -> pd.DataFrame:
        if payload is None:
            return self._empty_frame()

        if isinstance(payload, pd.DataFrame):
            if payload.empty:
                return self._empty_frame()
            frame = payload.copy()
            if not isinstance(frame.index, pd.DatetimeIndex):
                raise TypeError("data frame index must be a DatetimeIndex")
            return normalise_index(frame, market=market).sort_index()

        ticks = list(payload)
        if not ticks:
            return self._empty_frame()
        self._validate_tick_metadata(ticks, key, instrument_type)

        timestamps = [
            self._normalise_tick_timestamp(tick.timestamp, market) for tick in ticks
        ]
        index = pd.DatetimeIndex(pd.to_datetime(timestamps, utc=True))
        index.name = "timestamp"
        frame = pd.DataFrame(
            {
                "price": [float(tick.price) for tick in ticks],
                "volume": [float(tick.volume) for tick in ticks],
            },
            index=index,
        )
        return normalise_index(frame, market=market).sort_index()

    def _merge_frames(self, frames: Sequence[pd.DataFrame]) -> pd.DataFrame:
        candidates = [
            frame for frame in frames if frame is not None and not frame.empty
        ]
        if not candidates:
            return self._empty_frame()
        combined = pd.concat(candidates)
        combined = combined[~combined.index.duplicated(keep="last")]
        return combined.sort_index()

    def _resolve_window(
        self,
        frame: pd.DataFrame,
        start: datetime | pd.Timestamp | float | int | None,
        end: datetime | pd.Timestamp | float | int | None,
        market: str | None,
    ) -> tuple[datetime, datetime] | None:
        resolved_start = self._coerce_timestamp(start, market)
        resolved_end = self._coerce_timestamp(end, market)

        if resolved_start is None and not frame.empty:
            resolved_start = frame.index.min().to_pydatetime()
        if resolved_end is None and not frame.empty:
            resolved_end = frame.index.max().to_pydatetime()

        if resolved_start is None or resolved_end is None:
            return None
        if resolved_end < resolved_start:
            raise ValueError("end timestamp must be greater than or equal to start")
        return resolved_start, resolved_end

    def _build_expected_index(
        self, start: datetime, end: datetime, *, market: str | None
    ) -> pd.DatetimeIndex:
        start_ts = pd.Timestamp(start)
        if start_ts.tz is None:
            start_ts = start_ts.tz_localize(UTC)
        else:
            start_ts = start_ts.tz_convert(UTC)

        end_ts = pd.Timestamp(end)
        if end_ts.tz is None:
            end_ts = end_ts.tz_localize(UTC)
        else:
            end_ts = end_ts.tz_convert(UTC)

        base_index = pd.date_range(
            start=start_ts, end=end_ts, freq=self._frequency, tz=UTC
        )
        base_index.name = "timestamp"
        if base_index.empty or not market:
            return base_index

        try:
            calendar = get_market_calendar(market)
        except KeyError:
            return base_index

        exchange_calendar = calendar.exchange_calendar
        minute = pd.Timedelta(minutes=1)
        if (
            exchange_calendar is None
            or not hasattr(exchange_calendar, "minutes_in_range")
            or self._frequency < minute
            or self._frequency % minute != pd.Timedelta(0)
        ):
            return base_index

        start_floor = start_ts.floor("min")
        end_ceiling = end_ts.ceil("min")
        trading_minutes = exchange_calendar.minutes_in_range(start_floor, end_ceiling)
        if trading_minutes.empty:
            return pd.DatetimeIndex([], tz=UTC, name="timestamp")

        stride = max(int(self._frequency / minute), 1)
        if stride == 1:
            resampled = trading_minutes
        else:
            minute_values = trading_minutes.asi8
            if minute_values.size == 0:
                return pd.DatetimeIndex([], tz=UTC, name="timestamp")

            gaps = np.flatnonzero(np.diff(minute_values) > minute.value) + 1
            segments = (
                np.split(trading_minutes, gaps) if gaps.size else [trading_minutes]
            )
            selected_segments = [
                segment[::stride] for segment in segments if not segment.empty
            ]
            if not selected_segments:
                return pd.DatetimeIndex([], tz=UTC, name="timestamp")
            resampled = (
                selected_segments[0].append(selected_segments[1:])
                if len(selected_segments) > 1
                else selected_segments[0]
            )
        resampled = resampled.sort_values()
        mask = (resampled >= start_ts) & (resampled <= end_ts)
        aligned = resampled[mask]
        aligned = aligned.tz_convert(UTC)
        aligned.name = "timestamp"
        return aligned

    def _validate_tick_metadata(
        self,
        ticks: Sequence[PriceTick],
        key: CacheKey,
        instrument_type: InstrumentType,
    ) -> None:
        for tick in ticks:
            canonical_symbol = normalize_symbol(
                tick.symbol, instrument_type_hint=tick.instrument_type
            )
            if canonical_symbol != key.symbol:
                raise ValueError(
                    "Tick symbol does not match aggregation key: "
                    f"expected {key.symbol}, got {canonical_symbol}"
                )
            canonical_venue = normalize_venue(tick.venue)
            if canonical_venue != key.venue:
                raise ValueError(
                    "Tick venue does not match aggregation key: "
                    f"expected {key.venue}, got {canonical_venue}"
                )
            if tick.instrument_type != instrument_type:
                raise ValueError(
                    "Tick instrument type does not match aggregation key: "
                    f"expected {instrument_type}, got {tick.instrument_type}"
                )

    def _normalise_tick_timestamp(
        self,
        value: datetime,
        market: str | None,
    ) -> datetime:
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        return normalize_timestamp(value, market=market)

    def _coerce_timestamp(
        self,
        value: datetime | pd.Timestamp | float | int | str | None,
        market: str | None,
    ) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, pd.Timestamp):
            value = value.to_pydatetime()
        return normalize_timestamp(value, market=market)

    def _get_planner(self) -> GapFillPlanner:
        registry = self._cache_service.cache_registry
        layer_cache = registry.cache_for(self._layer)
        return GapFillPlanner(layer_cache)

    @staticmethod
    def _empty_frame() -> pd.DataFrame:
        index = pd.DatetimeIndex([], tz=UTC, name="timestamp")
        return pd.DataFrame(columns=["price", "volume"], index=index)


__all__ = ["AggregationResult", "TickStreamAggregator"]
