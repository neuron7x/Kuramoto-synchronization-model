# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.data.backfill module."""

from __future__ import annotations

import pandas as pd
import pytest

from core.data.backfill import CacheEntry, CacheKey, LayerCache


class TestCacheKey:
    def test_creation(self):
        key = CacheKey(layer="ohlcv", symbol="BTCUSD", venue="binance", timeframe="1m")
        assert key.layer == "ohlcv"
        assert key.symbol == "BTCUSD"
        assert key.venue == "binance"
        assert key.timeframe == "1m"

    def test_frozen(self):
        key = CacheKey(layer="raw", symbol="ETH", venue="kraken", timeframe="1s")
        with pytest.raises(Exception):
            key.layer = "other"

    def test_hashable(self):
        key1 = CacheKey("raw", "BTC", "venue1", "1m")
        key2 = CacheKey("raw", "BTC", "venue1", "1m")
        assert hash(key1) == hash(key2)
        assert key1 == key2

    def test_different_keys(self):
        key1 = CacheKey("raw", "BTC", "v1", "1m")
        key2 = CacheKey("raw", "BTC", "v2", "1m")
        assert key1 != key2


class TestCacheEntry:
    def _frame(self):
        idx = pd.date_range("2024-01-01", periods=5, freq="1h")
        return pd.DataFrame({"price": [100, 101, 102, 103, 104]}, index=idx)

    def test_creation(self):
        df = self._frame()
        entry = CacheEntry(frame=df, start=df.index[0], end=df.index[-1])
        assert entry.frame is df
        assert entry.start == df.index[0]

    def test_slice_full(self):
        df = self._frame()
        entry = CacheEntry(frame=df, start=df.index[0], end=df.index[-1])
        sliced = entry.slice(None, None)
        assert len(sliced) == 5

    def test_slice_from_start(self):
        df = self._frame()
        entry = CacheEntry(frame=df, start=df.index[0], end=df.index[-1])
        sliced = entry.slice(df.index[2], None)
        assert len(sliced) == 3

    def test_slice_to_end(self):
        df = self._frame()
        entry = CacheEntry(frame=df, start=df.index[0], end=df.index[-1])
        sliced = entry.slice(None, df.index[1])
        assert len(sliced) == 2

    def test_slice_range(self):
        df = self._frame()
        entry = CacheEntry(frame=df, start=df.index[0], end=df.index[-1])
        sliced = entry.slice(df.index[1], df.index[3])
        assert len(sliced) == 3

    def test_slice_returns_copy(self):
        df = self._frame()
        entry = CacheEntry(frame=df, start=df.index[0], end=df.index[-1])
        sliced = entry.slice(None, None)
        assert sliced is not df


class TestLayerCache:
    def _make_frame(self, n=5):
        idx = pd.date_range("2024-01-01", periods=n, freq="1h")
        return pd.DataFrame({"price": list(range(100, 100 + n))}, index=idx)

    def test_empty(self):
        cache = LayerCache()
        assert cache._entries == {}

    def test_put_and_retrieve(self):
        cache = LayerCache()
        key = CacheKey("ohlcv", "BTC", "v1", "1h")
        df = self._make_frame()
        cache.put(key, df)
        assert key in cache._entries

    def test_put_empty_ignored(self):
        cache = LayerCache()
        key = CacheKey("ohlcv", "BTC", "v1", "1h")
        cache.put(key, pd.DataFrame())
        assert key not in cache._entries

    def test_put_non_datetime_index_raises(self):
        cache = LayerCache()
        key = CacheKey("ohlcv", "BTC", "v1", "1h")
        df = pd.DataFrame({"price": [1, 2, 3]})
        with pytest.raises(TypeError, match="DatetimeIndex"):
            cache.put(key, df)

    def test_merge_new_entry(self):
        cache = LayerCache()
        key = CacheKey("ohlcv", "BTC", "v1", "1h")
        df = self._make_frame()
        cache.merge(key, df)
        assert key in cache._entries

    def test_merge_empty_ignored(self):
        cache = LayerCache()
        key = CacheKey("ohlcv", "BTC", "v1", "1h")
        cache.merge(key, pd.DataFrame())
        assert key not in cache._entries

    def test_put_replaces(self):
        cache = LayerCache()
        key = CacheKey("ohlcv", "BTC", "v1", "1h")
        df1 = self._make_frame(5)
        df2 = self._make_frame(10)
        cache.put(key, df1)
        cache.put(key, df2)
        entry = cache._entries[key]
        assert len(entry.frame) == 10
