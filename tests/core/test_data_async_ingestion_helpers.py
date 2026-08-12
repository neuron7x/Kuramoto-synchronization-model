# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Tests for core.data.async_ingestion internal helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.data.async_ingestion import _TickMetricBatcher


class TestTickMetricBatcher:
    def test_init(self):
        collector = MagicMock()
        batcher = _TickMetricBatcher(collector, "binance", "BTCUSD")
        assert batcher._flush_threshold == 256
        assert batcher._pending == 0

    def test_custom_threshold(self):
        batcher = _TickMetricBatcher(MagicMock(), "src", "sym", flush_threshold=10)
        assert batcher._flush_threshold == 10

    def test_min_threshold(self):
        batcher = _TickMetricBatcher(MagicMock(), "src", "sym", flush_threshold=0)
        assert batcher._flush_threshold == 1

    def test_negative_threshold_clamped(self):
        batcher = _TickMetricBatcher(MagicMock(), "src", "sym", flush_threshold=-5)
        assert batcher._flush_threshold == 1

    def test_add_below_threshold(self):
        collector = MagicMock()
        batcher = _TickMetricBatcher(collector, "src", "sym", flush_threshold=10)
        batcher.add(5)
        assert batcher._pending == 5

    def test_add_triggers_flush(self):
        collector = MagicMock()
        batcher = _TickMetricBatcher(collector, "src", "sym", flush_threshold=5)
        batcher.add(5)
        # Should have flushed
        assert batcher._pending == 0

    def test_add_exceeds_threshold(self):
        collector = MagicMock()
        batcher = _TickMetricBatcher(collector, "src", "sym", flush_threshold=3)
        batcher.add(10)
        # Should have flushed immediately (pending >= threshold)
        assert batcher._pending == 0

    def test_add_zero_ignored(self):
        batcher = _TickMetricBatcher(MagicMock(), "src", "sym")
        batcher.add(0)
        assert batcher._pending == 0

    def test_add_negative_ignored(self):
        batcher = _TickMetricBatcher(MagicMock(), "src", "sym")
        batcher.add(-5)
        assert batcher._pending == 0

    def test_manual_flush(self):
        collector = MagicMock()
        batcher = _TickMetricBatcher(collector, "src", "sym", flush_threshold=1000)
        batcher.add(5)
        assert batcher._pending == 5
        batcher.flush()
        assert batcher._pending == 0

    def test_flush_with_record_method(self):
        collector = MagicMock()
        # record_tick_processed method exists
        collector.record_tick_processed = MagicMock()
        batcher = _TickMetricBatcher(collector, "binance", "BTC")
        batcher.add(3)
        batcher.flush()
        collector.record_tick_processed.assert_called_once_with("binance", "BTC", 3)

    def test_flush_without_record_method(self):
        collector = MagicMock(spec=[])  # No attributes
        batcher = _TickMetricBatcher(collector, "src", "sym")
        batcher.add(3)
        # Should not raise when record method missing
        batcher.flush()
        assert batcher._pending == 0

    def test_context_manager(self):
        collector = MagicMock()
        with _TickMetricBatcher(collector, "src", "sym") as batcher:
            batcher.add(5)
        # Should be flushed on exit
        assert batcher._pending == 0

    def test_context_manager_flushes_on_exception(self):
        collector = MagicMock()
        try:
            with _TickMetricBatcher(collector, "src", "sym") as batcher:
                batcher.add(2)
                raise ValueError("oops")
        except ValueError:
            pass
        assert batcher._pending == 0

    def test_flush_empty(self):
        collector = MagicMock()
        batcher = _TickMetricBatcher(collector, "src", "sym")
        batcher.flush()  # Should not call collector
        # No pending, no call needed

    @pytest.mark.parametrize("threshold", [1, 5, 10, 50, 100, 1000])
    def test_various_thresholds(self, threshold):
        batcher = _TickMetricBatcher(MagicMock(), "src", "sym", flush_threshold=threshold)
        assert batcher._flush_threshold == threshold
