from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from agent.substrate_oracle import classify_columns, evaluate_substrate


def _now() -> datetime:
    return datetime(2026, 4, 11, 0, 0, tzinfo=timezone.utc)


def test_classifies_ohlc_only() -> None:
    assert classify_columns(["open", "high", "low", "close"]) == "OHLC_ONLY"


def test_classifies_bid_ask() -> None:
    assert classify_columns(["x_bid_close", "x_ask_close"]) == "BID_ASK"


def test_classifies_microstructure_depth() -> None:
    assert classify_columns(["bid_depth_1", "ask_depth_1"]) == "MICROSTRUCTURE"


def test_nan_abort() -> None:
    df = pd.DataFrame({"x_bid_close": [1.0, None], "x_ask_close": [1.1, 1.2]})
    out = evaluate_substrate(df, now_utc=_now())
    assert out.reason_code == "NAN_ABORT"


def test_stale_feed_block() -> None:
    now = datetime.now(timezone.utc)
    ts = pd.date_range(now - timedelta(hours=3), periods=2, freq="h")
    df = pd.DataFrame({"x_bid_close": [1.0, 1.1], "x_ask_close": [1.1, 1.2]}, index=ts)
    out = evaluate_substrate(df, now_utc=now)
    assert out.reason_code == "STALE_FEED"


def test_future_clock_skew_not_stale() -> None:
    now = datetime.now(timezone.utc)
    ts = pd.date_range(now + timedelta(minutes=5), periods=2, freq="h")
    df = pd.DataFrame({"x_bid_close": [1.0, 1.1], "x_ask_close": [1.1, 1.2]}, index=ts)
    out = evaluate_substrate(df, now_utc=now)
    assert out.reason_code == "SUBSTRATE_LIVE"


def test_unknown_schema_quarantine() -> None:
    df = pd.DataFrame({"foo": [1.0], "bar": [2.0]})
    out = evaluate_substrate(df, now_utc=_now())
    assert out.reason_code == "SCHEMA_DRIFT"


def test_ohlc_dead_substrate() -> None:
    ts = pd.date_range(_now() - timedelta(minutes=10), periods=2, freq="h")
    df = pd.DataFrame({"open": [1.0, 1.1], "close": [1.1, 1.2]}, index=ts)
    out = evaluate_substrate(df, now_utc=_now())
    assert out.reason_code == "SUBSTRATE_DEAD_OHLC_ONLY"


def test_microstructure_go() -> None:
    ts = pd.date_range(_now() - timedelta(minutes=10), periods=2, freq="h")
    df = pd.DataFrame(
        {"x_bid_close": [1.0, 1.1], "x_ask_close": [1.1, 1.2], "ofi": [0.1, 0.2]}, index=ts
    )
    out = evaluate_substrate(df, now_utc=_now())
    assert out.reason_code == "SUBSTRATE_LIVE"
