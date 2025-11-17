from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
from pandas.tseries.offsets import Minute

from core.data.models import InstrumentType, PriceTick
from src.data import DataIngestionCacheService, TickStreamAggregator

BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _make_tick(
    minutes: int,
    price: float | int | str,
    *,
    symbol: str = "BTC/USDT",
    venue: str = "BINANCE",
    volume: float | int | str = 1,
    instrument_type: InstrumentType = InstrumentType.SPOT,
) -> PriceTick:
    return PriceTick.create(
        symbol=symbol,
        venue=venue,
        price=price,
        volume=volume,
        timestamp=BASE_TS + timedelta(minutes=minutes),
        instrument_type=instrument_type,
    )


def test_tick_stream_aggregator_merges_sources_and_detects_gaps() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(cache_service=cache_service, timeframe="1min")

    historical = [_make_tick(0, "30000"), _make_tick(1, "30010")]
    live = [_make_tick(1, "30020"), _make_tick(2, "30030")]

    result = aggregator.synchronise(
        symbol="BTC/USDT",
        venue="BINANCE",
        instrument_type=InstrumentType.SPOT,
        historical=historical,
        live=live,
        start=BASE_TS,
        end=BASE_TS + timedelta(minutes=3),
    )

    frame = result.frame
    assert frame.index.tz == UTC
    assert frame.index.is_monotonic_increasing
    assert list(frame.index) == [
        pd.Timestamp(BASE_TS),
        pd.Timestamp(BASE_TS + timedelta(minutes=1)),
        pd.Timestamp(BASE_TS + timedelta(minutes=2)),
    ]
    assert frame.loc[pd.Timestamp(BASE_TS + timedelta(minutes=1))][
        "price"
    ] == pytest.approx(30020.0)
    assert frame.loc[pd.Timestamp(BASE_TS + timedelta(minutes=2))][
        "price"
    ] == pytest.approx(30030.0)

    assert len(result.backfill_plan.gaps) == 1
    gap = result.backfill_plan.gaps[0]
    assert gap.start == pd.Timestamp(BASE_TS + timedelta(minutes=3))
    assert gap.end == pd.Timestamp(BASE_TS + timedelta(minutes=4))


def test_tick_stream_aggregator_accepts_string_window_bounds() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(cache_service=cache_service, timeframe="1min")

    historical = [_make_tick(0, "30000"), _make_tick(1, "30010")]

    result = aggregator.synchronise(
        symbol="BTC/USDT",
        venue="BINANCE",
        instrument_type=InstrumentType.SPOT,
        historical=historical,
        start="2024-01-01T00:00:00Z",
        end="2024-01-01T00:02:00Z",
    )

    assert list(result.frame.index) == [
        pd.Timestamp(BASE_TS),
        pd.Timestamp(BASE_TS + timedelta(minutes=1)),
    ]
    assert len(result.backfill_plan.gaps) == 1


def test_tick_stream_aggregator_rejects_invalid_string_window_bounds() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(cache_service=cache_service, timeframe="1min")

    with pytest.raises(ValueError):
        aggregator.synchronise(
            symbol="BTC/USDT",
            venue="BINANCE",
            instrument_type=InstrumentType.SPOT,
            start="invalid",  # type: ignore[arg-type]
            end="2024-01-01T00:02:00Z",
        )


def test_tick_stream_aggregator_backfills_gaps_via_callback() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(cache_service=cache_service, timeframe="1min")

    historical = [_make_tick(0, "30000"), _make_tick(2, "30040")]
    fetched: list[tuple[datetime, datetime]] = []

    def fetcher(start: datetime, end: datetime) -> list[PriceTick]:
        fetched.append((start, end))
        assert start.tzinfo is not None and end.tzinfo is not None
        return [_make_tick(1, "30020")]

    result = aggregator.synchronise(
        symbol="BTC/USDT",
        venue="BINANCE",
        instrument_type=InstrumentType.SPOT,
        historical=historical,
        start=BASE_TS,
        end=BASE_TS + timedelta(minutes=2),
        gap_fetcher=fetcher,
    )

    assert fetched == [
        (
            pd.Timestamp(BASE_TS + timedelta(minutes=1)).to_pydatetime(),
            pd.Timestamp(BASE_TS + timedelta(minutes=2)).to_pydatetime(),
        )
    ]
    assert not result.backfill_plan.gaps

    frame = result.frame
    assert frame.index.tz == UTC
    assert len(frame) == 3
    assert frame.loc[pd.Timestamp(BASE_TS + timedelta(minutes=1))][
        "price"
    ] == pytest.approx(30020.0)


def test_tick_stream_aggregator_skips_closed_calendar_windows() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(
        cache_service=cache_service, timeframe="1min", market="NYSE"
    )

    weekend_start = datetime(2024, 3, 9, tzinfo=UTC)
    weekend_end = datetime(2024, 3, 10, 23, 59, tzinfo=UTC)

    result = aggregator.synchronise(
        symbol="AAPL",
        venue="NYSE",
        instrument_type=InstrumentType.SPOT,
        start=weekend_start,
        end=weekend_end,
    )

    assert result.frame.empty
    assert not result.backfill_plan.gaps


def test_tick_stream_aggregator_rejects_mismatched_metadata() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(cache_service=cache_service, timeframe="1min")

    historical = [_make_tick(0, "30000"), _make_tick(1, "1500", symbol="ETH/USDT")]

    with pytest.raises(ValueError, match="Tick symbol does not match aggregation key"):
        aggregator.synchronise(
            symbol="BTC/USDT",
            venue="BINANCE",
            instrument_type=InstrumentType.SPOT,
            historical=historical,
            start=BASE_TS,
            end=BASE_TS + timedelta(minutes=1),
        )


def test_tick_stream_aggregator_validates_venue_and_instrument_metadata() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(cache_service=cache_service, timeframe="1min")

    venue_mismatch = [_make_tick(0, "30000", venue="COINBASE")]
    with pytest.raises(ValueError, match="Tick venue does not match aggregation key"):
        aggregator.synchronise(
            symbol="BTC/USDT",
            venue="BINANCE",
            instrument_type=InstrumentType.SPOT,
            historical=venue_mismatch,
            start=BASE_TS,
            end=BASE_TS + timedelta(minutes=1),
        )

    instrument_mismatch = [
        _make_tick(0, "30000", symbol="AAPL", instrument_type=InstrumentType.FUTURES)
    ]
    with pytest.raises(
        ValueError, match="Tick instrument type does not match aggregation key"
    ):
        aggregator.synchronise(
            symbol="AAPL",
            venue="BINANCE",
            instrument_type=InstrumentType.SPOT,
            historical=instrument_mismatch,
            start=BASE_TS,
            end=BASE_TS + timedelta(minutes=1),
        )


def test_tick_stream_aggregator_rejects_non_datetime_dataframe_index() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(cache_service=cache_service, timeframe="1min")

    payload = pd.DataFrame({"price": [1.0], "volume": [1.0]}, index=pd.Index([0]))

    with pytest.raises(TypeError, match="data frame index must be a DatetimeIndex"):
        aggregator.synchronise(
            symbol="BTC/USDT",
            venue="BINANCE",
            instrument_type=InstrumentType.SPOT,
            historical=payload,
            start=BASE_TS,
            end=BASE_TS + timedelta(minutes=1),
        )


def test_tick_stream_aggregator_detects_inverted_time_window() -> None:
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(cache_service=cache_service, timeframe="1min")

    historical = [_make_tick(0, "30000"), _make_tick(1, "30010")]

    with pytest.raises(
        ValueError, match="end timestamp must be greater than or equal to start"
    ):
        aggregator.synchronise(
            symbol="BTC/USDT",
            venue="BINANCE",
            instrument_type=InstrumentType.SPOT,
            historical=historical,
            start=BASE_TS + timedelta(minutes=2),
            end=BASE_TS + timedelta(minutes=1),
        )


def test_tick_stream_aggregator_requires_positive_frequency() -> None:
    cache_service = DataIngestionCacheService()

    with pytest.raises(ValueError, match="frequency must be strictly positive"):
        TickStreamAggregator(
            cache_service=cache_service, timeframe="1min", frequency="0min"
        )


def test_tick_stream_aggregator_requires_non_empty_timeframe() -> None:
    with pytest.raises(ValueError, match="timeframe must be a non-empty string"):
        TickStreamAggregator(timeframe="   ")


def test_tick_stream_aggregator_accepts_offset_frequency_and_calendar_alignment() -> (
    None
):
    cache_service = DataIngestionCacheService()
    aggregator = TickStreamAggregator(
        cache_service=cache_service,
        timeframe="1min",
        market="NYSE",
        frequency=Minute(1),
    )

    market_open = datetime(2024, 3, 11, 13, 30, tzinfo=UTC)
    market_close = datetime(2024, 3, 11, 13, 35, tzinfo=UTC)

    result = aggregator.synchronise(
        symbol="AAPL",
        venue="NYSE",
        instrument_type=InstrumentType.SPOT,
        start=market_open,
        end=market_close,
    )

    assert result.backfill_plan.is_full_refresh is True
    assert len(result.backfill_plan.gaps) == 1
    gap = result.backfill_plan.gaps[0]
    assert gap.start == pd.Timestamp(market_open)
    assert gap.end == pd.Timestamp(market_close) + pd.Timedelta(minutes=1)
