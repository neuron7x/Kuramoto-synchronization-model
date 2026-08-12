"""Tests for LiveFeedLoop."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from coherence_bridge.live_feed import LiveFeedLoop


def test_synthetic_bar_generates_valid_ohlcv() -> None:
    adapter = MagicMock()
    adapter.instruments = ["EURUSD"]
    feed = LiveFeedLoop(adapter, mode="synthetic")
    bar = feed._generate_synthetic_bar("EURUSD")

    assert bar["low"] <= bar["open"]
    assert bar["low"] <= bar["close"]
    assert bar["high"] >= bar["open"]
    assert bar["high"] >= bar["close"]
    assert bar["volume"] > 0


def test_feed_calls_update_market_data() -> None:
    adapter = MagicMock()
    adapter.instruments = ["EURUSD"]
    adapter.update_market_data = MagicMock()

    feed = LiveFeedLoop(adapter, mode="synthetic", bar_interval_s=0.05)

    t = threading.Thread(target=feed.run, daemon=True)
    t.start()
    time.sleep(0.3)
    feed.stop()
    t.join(timeout=1)

    assert adapter.update_market_data.call_count >= 3
    # First arg should be instrument name
    first_call = adapter.update_market_data.call_args_list[0]
    assert first_call[0][0] == "EURUSD"


def test_history_grows_up_to_limit() -> None:
    adapter = MagicMock()
    adapter.instruments = ["EURUSD"]
    feed = LiveFeedLoop(adapter, mode="synthetic", history_bars=10)

    for _ in range(20):
        bar = feed._generate_synthetic_bar("EURUSD")
        feed._append_bar("EURUSD", bar)

    assert len(feed._histories["EURUSD"]) == 10


def test_deterministic_with_same_seed() -> None:
    adapter1 = MagicMock()
    adapter1.instruments = ["EURUSD"]
    feed1 = LiveFeedLoop(adapter1, mode="synthetic")

    adapter2 = MagicMock()
    adapter2.instruments = ["EURUSD"]
    feed2 = LiveFeedLoop(adapter2, mode="synthetic")

    bar1 = feed1._generate_synthetic_bar("EURUSD")
    bar2 = feed2._generate_synthetic_bar("EURUSD")
    assert bar1["close"] == bar2["close"]
