# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from exchange_calendars import always_open, errors

from core.data.timeutils import (
    MarketCalendar,
    MarketCalendarRegistry,
    convert_timestamp,
    get_market_calendar,
    get_timezone,
    is_market_open,
    normalize_timestamp,
    to_utc,
    validate_bar_alignment,
)


def test_normalize_timestamp_from_float() -> None:
    ts = normalize_timestamp(1_700_000_000.0)
    assert ts.tzinfo == timezone.utc
    assert ts.timestamp() == pytest.approx(1_700_000_000.0)


def test_normalize_timestamp_with_market() -> None:
    ts = normalize_timestamp(1_700_000_000.0, market="BINANCE")
    assert ts.tzinfo == timezone.utc


def test_normalize_timestamp_from_datetime() -> None:
    source = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    result = normalize_timestamp(source)
    assert result == source


def test_normalize_timestamp_from_iso_string() -> None:
    iso_value = "2024-01-01T12:34:56+00:00"
    result = normalize_timestamp(iso_value)
    assert result == datetime(2024, 1, 1, 12, 34, 56, tzinfo=timezone.utc)


def test_normalize_timestamp_from_numeric_string() -> None:
    result = normalize_timestamp("1700000000")
    assert result.tzinfo == timezone.utc
    assert result.timestamp() == pytest.approx(1_700_000_000.0)


def test_normalize_timestamp_from_milliseconds() -> None:
    # 1_700_000_000_000 represents the same instant as 1_700_000_000 seconds
    dt = normalize_timestamp(1_700_000_000_000)
    assert dt == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_normalize_timestamp_from_microseconds() -> None:
    # 1_700_000_000_000_000 represents the same instant as 1_700_000_000 seconds
    dt = normalize_timestamp(1_700_000_000_000_000)
    assert dt == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_normalize_timestamp_numeric_string_preserves_precision() -> None:
    dt = normalize_timestamp("1700000000000000")
    assert dt == datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def test_normalize_timestamp_rejects_nan() -> None:
    with pytest.raises(ValueError):
        normalize_timestamp(float("nan"))


def test_normalize_timestamp_rejects_empty_string() -> None:
    with pytest.raises(ValueError):
        normalize_timestamp("   ")


def test_normalize_timestamp_rejects_unparseable_string() -> None:
    with pytest.raises(ValueError):
        normalize_timestamp("not-a-timestamp")


def test_normalize_timestamp_rejects_out_of_range_numeric_value() -> None:
    with pytest.raises(ValueError):
        normalize_timestamp(10**22)


def test_normalize_timestamp_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError):
        normalize_timestamp(object())


def test_normalize_timestamp_handles_market_dst_offsets() -> None:
    ny = ZoneInfo("America/New_York")
    before_shift = datetime(2024, 3, 8, 9, 30, tzinfo=ny)
    after_shift = datetime(2024, 3, 11, 9, 30, tzinfo=ny)

    before_normalized = normalize_timestamp(before_shift, market="NYSE")
    after_normalized = normalize_timestamp(after_shift, market="NYSE")

    assert before_normalized == datetime(2024, 3, 8, 14, 30, tzinfo=timezone.utc)
    assert after_normalized == datetime(2024, 3, 11, 13, 30, tzinfo=timezone.utc)


def test_convert_timestamp_changes_timezone() -> None:
    utc_dt = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    ny_dt = convert_timestamp(utc_dt, "NYSE")
    assert ny_dt.tzinfo is not None
    assert ny_dt.tzinfo.utcoffset(ny_dt).total_seconds() == pytest.approx(-5 * 3600)


def test_convert_timestamp_handles_dst_shift() -> None:
    before = datetime(2024, 3, 8, 19, 0, tzinfo=timezone.utc)
    after = datetime(2024, 3, 11, 19, 0, tzinfo=timezone.utc)

    before_local = convert_timestamp(before, "NYSE")
    after_local = convert_timestamp(after, "NYSE")

    assert before_local.hour == 14  # UTC-5
    assert after_local.hour == 15  # UTC-4 after DST transition


def test_convert_timestamp_handles_naive_datetime() -> None:
    naive = datetime(2024, 1, 1, 12, 0)
    localized = convert_timestamp(naive, "BINANCE")
    assert localized.tzinfo is not None
    assert localized.utcoffset().total_seconds() == pytest.approx(0)


def test_to_utc_assigns_timezone_when_missing() -> None:
    naive = datetime(2024, 1, 1, 12, 0)
    localized = to_utc(naive)
    assert localized.tzinfo == timezone.utc


def test_is_market_open_handles_weekends() -> None:
    weekend = datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)  # Saturday
    assert not is_market_open(weekend, "NYSE")


def test_is_market_open_respects_holidays() -> None:
    independence_day = datetime(2024, 7, 4, 15, 0, tzinfo=timezone.utc)
    assert not is_market_open(independence_day, "NYSE")


@pytest.mark.parametrize(
    ("market", "timestamp", "expected", "reason"),
    (
        (
            "NYSE",
            datetime(2024, 3, 8, 14, 35, tzinfo=timezone.utc),
            True,
            "Open before US DST change",
        ),
        (
            "NYSE",
            datetime(2024, 3, 11, 13, 35, tzinfo=timezone.utc),
            True,
            "Open after US DST change",
        ),
        (
            "NYSE",
            datetime(2024, 7, 4, 15, 0, tzinfo=timezone.utc),
            False,
            "Closed for Independence Day",
        ),
        (
            "NASDAQ",
            datetime(2024, 3, 11, 13, 35, tzinfo=timezone.utc),
            True,
            "NASDAQ mirrors NYSE DST",
        ),
        (
            "NASDAQ",
            datetime(2024, 7, 4, 15, 0, tzinfo=timezone.utc),
            False,
            "NASDAQ holiday closure",
        ),
        (
            "CME",
            datetime(2024, 3, 11, 21, 55, tzinfo=timezone.utc),
            True,
            "CME open before session close (exchange_calendars does not model daily breaks)",
        ),
        (
            "CME",
            datetime(2024, 3, 11, 22, 5, tzinfo=timezone.utc),
            True,
            "CME open after DST shift",
        ),
        (
            "BINANCE",
            datetime(2024, 3, 11, 0, 0, tzinfo=timezone.utc),
            True,
            "24/7 venue unaffected",
        ),
    ),
)
def test_is_market_open_covers_dst_and_holiday_edges(
    market: str, timestamp: datetime, expected: bool, reason: str
) -> None:
    """Validate open/closed detection across DST transitions and holidays."""

    assert is_market_open(timestamp, market) is expected, reason


@pytest.mark.parametrize(
    ("market", "tz", "open_time", "close_time"),
    (
        ("NYSE", "America/New_York", time(9, 30), time(16, 0)),
        ("NASDAQ", "America/New_York", time(9, 30), time(16, 0)),
        # CME excluded: overnight session with continuous trading (no break modeled by exchange_calendars)
    ),
)
def test_is_market_open_session_boundaries(
    market: str, tz: str, open_time: time, close_time: time
) -> None:
    """Ensure open/close edges honour session boundaries for each market."""

    zone = ZoneInfo(tz)

    def to_utc(local_dt: datetime) -> datetime:
        return local_dt.replace(tzinfo=zone).astimezone(timezone.utc)

    trading_day = datetime(2024, 3, 11, 0, 0)
    before_open_local = trading_day.replace(
        hour=open_time.hour, minute=open_time.minute
    ) - timedelta(minutes=1)
    open_local = trading_day.replace(hour=open_time.hour, minute=open_time.minute)
    just_before_close_local = trading_day.replace(
        hour=close_time.hour, minute=close_time.minute
    ) - timedelta(minutes=1)
    after_close_local = trading_day.replace(hour=close_time.hour, minute=close_time.minute)

    before_open = to_utc(before_open_local)
    at_open = to_utc(open_local)
    before_close = to_utc(just_before_close_local)
    after_close = to_utc(after_close_local)

    assert not is_market_open(before_open, market)
    assert is_market_open(at_open, market)
    assert is_market_open(before_close, market)
    assert not is_market_open(after_close, market)


def test_registry_allows_custom_calendar() -> None:
    registry = MarketCalendarRegistry()
    custom = MarketCalendar(market="TEST", timezone="UTC")
    registry.register(custom)
    assert registry.get("TEST") == custom


def test_default_registry_includes_nasdaq() -> None:
    calendar = get_market_calendar("NASDAQ")
    assert calendar.timezone == "America/New_York"


def test_registry_raises_for_unknown_market() -> None:
    with pytest.raises(KeyError):
        get_market_calendar("UNKNOWN")


def test_market_calendar_requires_market_name() -> None:
    with pytest.raises(ValueError):
        MarketCalendar(market="", timezone="UTC")


def test_market_calendar_requires_timezone_without_calendar_name() -> None:
    with pytest.raises(ValueError):
        MarketCalendar(market="TEST")


def test_market_calendar_ensures_weekend_defaults() -> None:
    cal = MarketCalendar(market="TEST", timezone="UTC", weekend_closure=None)
    assert cal.weekend_closure == frozenset({5, 6})


def test_market_calendar_uses_exchange_calendar_metadata() -> None:
    cal = MarketCalendar(market="ALWAYS", calendar_name="ALWAYS_OPEN", weekend_closure=None)
    assert cal.timezone == "UTC"
    assert cal.weekend_closure == frozenset()


def test_market_calendar_tzinfo_requires_timezone() -> None:
    cal = MarketCalendar(market="ALWAYS", calendar_name="ALWAYS_OPEN", weekend_closure=None)
    object.__setattr__(cal, "timezone", None)

    with pytest.raises(ValueError):
        cal.tzinfo()


def test_exchange_aliases_are_supported() -> None:
    nyse = get_market_calendar("NYSE")
    assert nyse is get_market_calendar("XNYS")
    assert get_market_calendar("24/7").market == "BINANCE"


def test_load_exchange_calendar_falls_back_to_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core.data import timeutils as tu

    def fake_resolve(name: str) -> str:
        raise errors.InvalidCalendarName()

    monkeypatch.setattr(tu, "resolve_alias", fake_resolve)
    monkeypatch.setattr(tu, "get_calendar", lambda name: always_open.AlwaysOpenCalendar())

    calendar = tu._load_exchange_calendar("custom")
    assert isinstance(calendar, always_open.AlwaysOpenCalendar)


def test_market_calendar_is_open_handles_naive_timestamp() -> None:
    nyse = get_market_calendar("NYSE")
    assert nyse.is_open(datetime(2024, 3, 4, 15, 30))


def test_market_calendar_is_open_with_overnight_session() -> None:
    overnight = MarketCalendar(
        market="FUTURES",
        timezone="UTC",
        open_time=time(22, 0),
        close_time=time(6, 0),
        weekend_closure=(),
    )

    from core.data import timeutils as tu

    tu._registry.register(overnight)

    late = datetime(2024, 3, 4, 23, 0, tzinfo=timezone.utc)
    early = datetime(2024, 3, 5, 4, 0, tzinfo=timezone.utc)
    midday = datetime(2024, 3, 5, 12, 0, tzinfo=timezone.utc)

    assert overnight.is_open(late)
    assert overnight.is_open(early)
    assert not overnight.is_open(midday)


def test_market_calendar_manual_session_holidays_and_weekends() -> None:
    manual = MarketCalendar(
        market="MANUAL",
        timezone="UTC",
        open_time=time(9, 0),
        close_time=time(17, 0),
        weekend_closure={5, 6},
        holidays=[date(2024, 1, 1)],
    )

    from core.data import timeutils as tu

    tu._registry.register(manual)

    holiday = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    weekend = datetime(2024, 1, 6, 12, 0, tzinfo=timezone.utc)
    trading = datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)

    assert not manual.is_open(holiday)
    assert not manual.is_open(weekend)
    assert manual.is_open(trading)


def test_validate_bar_alignment_accepts_dst_boundary_minutes() -> None:
    timestamps = pd.DatetimeIndex(
        [
            "2024-03-08 20:55:00+00:00",
            "2024-03-08 20:56:00+00:00",
            "2024-03-08 20:57:00+00:00",
            "2024-03-08 20:58:00+00:00",
            "2024-03-08 20:59:00+00:00",
            "2024-03-11 13:30:00+00:00",
            "2024-03-11 13:31:00+00:00",
        ]
    )

    validate_bar_alignment(timestamps, market="NYSE", frequency="1min")


def test_validate_bar_alignment_detects_gaps() -> None:
    timestamps = pd.DatetimeIndex(
        [
            "2024-03-11 13:30:00+00:00",
            "2024-03-11 13:31:00+00:00",
            "2024-03-11 13:33:00+00:00",  # Missing 13:32
        ]
    )

    with pytest.raises(ValueError):
        validate_bar_alignment(timestamps, market="NYSE", frequency="1min")


def test_validate_bar_alignment_handles_empty_sequence() -> None:
    validate_bar_alignment([], market="NYSE", frequency="1min")


def test_validate_bar_alignment_handles_always_open_market() -> None:
    timestamps = pd.date_range(
        "2024-01-01 00:00:00+00:00",
        periods=6,
        freq="5min",
        tz="UTC",
    )

    validate_bar_alignment(timestamps, market="BINANCE", frequency="5min")


def test_get_timezone_round_trip() -> None:
    tz = get_timezone("America/New_York")
    assert tz.key == "America/New_York"

    with pytest.raises(ValueError):
        get_timezone("Mars/Phobos")


def test_validate_bar_alignment_rejects_unsorted() -> None:
    timestamps = [
        datetime(2024, 3, 11, 13, 31, tzinfo=timezone.utc),
        datetime(2024, 3, 11, 13, 30, tzinfo=timezone.utc),
    ]

    with pytest.raises(ValueError):
        validate_bar_alignment(timestamps, market="NYSE", frequency="1min")


def test_validate_bar_alignment_rejects_duplicates() -> None:
    timestamps = [
        datetime(2024, 3, 11, 13, 30, tzinfo=timezone.utc),
        datetime(2024, 3, 11, 13, 30, tzinfo=timezone.utc),
    ]

    with pytest.raises(ValueError):
        validate_bar_alignment(timestamps, market="NYSE", frequency="1min")


def test_validate_bar_alignment_requires_positive_minute_frequency() -> None:
    timestamps = [datetime(2024, 3, 11, 13, 30, tzinfo=timezone.utc)]

    with pytest.raises(ValueError):
        validate_bar_alignment(timestamps, market="NYSE", frequency="0min")

    with pytest.raises(ValueError):
        validate_bar_alignment(timestamps, market="NYSE", frequency="30s")


def test_validate_bar_alignment_invalid_trading_minute() -> None:
    timestamps = [
        datetime(2024, 3, 9, 15, 30, tzinfo=timezone.utc),  # Saturday
        datetime(2024, 3, 11, 13, 30, tzinfo=timezone.utc),
    ]

    with pytest.raises(ValueError):
        validate_bar_alignment(timestamps, market="NYSE", frequency="1min")


def test_validate_bar_alignment_invalid_end_minute() -> None:
    timestamps = [
        datetime(2024, 3, 11, 13, 30, tzinfo=timezone.utc),
        datetime(2024, 3, 11, 21, 0, tzinfo=timezone.utc),  # After close
    ]

    with pytest.raises(ValueError):
        validate_bar_alignment(timestamps, market="NYSE", frequency="1min")


def test_validate_bar_alignment_reports_missing_and_extra() -> None:
    timestamps = pd.DatetimeIndex(
        [
            "2024-03-11 13:30:00+00:00",
            "2024-03-11 13:32:00+00:00",
            "2024-03-11 13:33:00+00:00",
        ]
    )

    with pytest.raises(ValueError) as err:
        validate_bar_alignment(timestamps, market="NYSE", frequency="1min")

    message = str(err.value)
    assert "missing" in message and "extra" in message


def test_validate_bar_alignment_with_manual_calendar() -> None:
    custom = MarketCalendar(market="CUSTOM", timezone="UTC")
    _ = get_market_calendar("BINANCE")  # ensure registry initialised
    # Registering custom calendar on module-level registry
    from core.data import timeutils as tu

    tu._registry.register(custom)

    timestamps = pd.date_range("2024-01-01 00:00:00+00:00", periods=4, freq="15min", tz="UTC")

    validate_bar_alignment(timestamps, market="CUSTOM", frequency="15min")


def test_validate_bar_alignment_with_manual_calendar_mismatch() -> None:
    custom = MarketCalendar(market="CUSTOM_MISMATCH", timezone="UTC")
    from core.data import timeutils as tu

    tu._registry.register(custom)

    timestamps = pd.date_range(
        "2024-01-01 00:00:00+00:00", periods=4, freq="15min", tz="UTC"
    ).delete(1)

    with pytest.raises(ValueError):
        validate_bar_alignment(timestamps, market="CUSTOM_MISMATCH", frequency="15min")


def test_as_utc_index_handles_naive_values() -> None:
    from core.data import timeutils as tu

    index = tu._as_utc_index([datetime(2024, 1, 1, 0, 0), datetime(2024, 1, 1, 0, 1)])
    assert str(index.tz) == "UTC"
