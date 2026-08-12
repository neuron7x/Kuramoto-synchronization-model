# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pandas as pd

os.environ.setdefault("GEOSYNC_ADMIN_TOKEN", "test-token")
os.environ.setdefault("GEOSYNC_AUDIT_SECRET", "test-secret-value")

from application.api.service import FeatureRequest, MarketBar


def test_market_bar_normalises_naive_timestamp_and_alias_fields() -> None:
    naive_timestamp = datetime(2024, 1, 2, 3, 4, 5)

    bar = MarketBar(
        timestamp=naive_timestamp,
        open=101.0,
        high=105.0,
        low=99.5,
        close=102.5,
        volume=123.0,
        bidVolume=15.0,
        askVolume=12.0,
        signedVolume=-3.0,
    )

    assert bar.timestamp.tzinfo is timezone.utc

    record = bar.as_record()

    assert isinstance(record["timestamp"], datetime)
    assert record["timestamp"].tzinfo is timezone.utc
    assert record["bid_volume"] == 15.0
    assert record["ask_volume"] == 12.0
    assert record["signed_volume"] == -3.0


def test_market_bar_excludes_none_fields_from_dump() -> None:
    bar = MarketBar(
        timestamp=datetime(2024, 2, 10, 8, 0, 0),
        open=None,
        high=201.0,
        low=198.5,
        close=200.5,
        volume=None,
        bidVolume=None,
        askVolume=30.0,
        signedVolume=None,
    )

    dumped = bar.model_dump(exclude_none=True)

    assert "open" not in dumped
    assert "volume" not in dumped
    assert "bid_volume" not in dumped
    assert "signed_volume" not in dumped
    assert dumped["ask_volume"] == 30.0


def test_feature_request_to_frame_sorts_and_sets_utc_index() -> None:
    bars = [
        MarketBar(
            timestamp=datetime(2024, 3, 20, 12, 0, 0),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=150.0,
            bidVolume=70.0,
            askVolume=65.0,
            signedVolume=5.0,
        ),
        MarketBar(
            timestamp=datetime(2024, 3, 20, 12, 2, 0),
            open=101.0,
            high=102.0,
            low=100.5,
            close=101.5,
            volume=175.0,
            bidVolume=72.0,
            askVolume=68.0,
            signedVolume=4.0,
        ),
        MarketBar(
            timestamp=datetime(2024, 3, 20, 12, 1, 0),
            open=100.5,
            high=101.5,
            low=100.0,
            close=101.0,
            volume=160.0,
            bidVolume=71.0,
            askVolume=66.0,
            signedVolume=5.5,
        ),
    ]

    request = FeatureRequest(symbol="BTC-USD", bars=bars)

    frame = request.to_frame()

    expected_order = [
        pd.Timestamp(bar.timestamp) for bar in sorted(bars, key=lambda bar: bar.timestamp)
    ]

    assert list(frame.index) == expected_order
    assert frame.index.tz is not None
    assert frame.index.tz.utcoffset(None) == timedelta(0)

    expected_columns = {
        "open",
        "high",
        "low",
        "close",
        "volume",
        "bid_volume",
        "ask_volume",
        "signed_volume",
    }
    assert set(frame.columns) == expected_columns

    assert frame.index.is_monotonic_increasing
